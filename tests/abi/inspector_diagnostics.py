"""H08 inspector diagnostics probe against an actual runtime directory. Loads tests/fixtures/inspector-diagnostics.html
(pinned Ahem) and inspects it through the native diagnostics: the opt-in and its capability facts, the render tree
dump of the document and of an element, the matched style rules of an element in cascade order with origin and
specificity, and the box model, which replays the Chromium oracle tests/fixtures/inspector-diagnostics-oracle.json
unscrolled, scrolled and at page scale 2 within 1/64 px. The accessibility tree of the same fixture is read through
the existing rv_ax_* functions. Then checks errors, threads, snapshots held past disabling and rv_host_destroy, and
that every snapshot is released. --repeat runs the whole probe that many times in one process."""

import argparse
import base64
import ctypes
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe

OK, NULL_ARGUMENT, WRONG_THREAD, NOT_ELEMENT, BUFFER_TOO_SMALL, UNSUPPORTED = 0, -1, -2, -4, -6, -9
ABI = 54
AHEM_SHA256 = '63d2abd0041c3e3b4b52ad8d382353b53c51c6785e76ce56ed9dacad2d2e31c4'
FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
RENDER_TREE, MATCHED_RULES = 1, 2
ALL_LAYERS, LAYER_NESTING, OVERFLOW, SVG_GEOMETRY, ID_AND_CLASS, LAYOUT_STATE = 1, 2, 4, 8, 16, 32
USER_AGENT, USER, AUTHOR, INLINE = 0, 1, 2, 3
ORIGIN, SPEC_A, SPEC_B, SPEC_C, SELECTOR_COUNT, MATCHED_COUNT = range(6)
SELECTOR_TEXT, MATCHED_SELECTOR, DECLARATIONS = range(3)
BOXES = ['content', 'padding', 'border', 'margin']
QUANTUM = 1 / 64
# The fixture's author rules for #target in cascade order: layer base, layer top, then unlayered by specificity and
# position. Each sets --order to its name; [name, selector list, matched selector, specificity, selectors, matched].
TARGET_AUTHOR = [
    ['base', '#target', '#target', (1, 0, 0), 1, 1],
    ['top', '#target', '#target', (1, 0, 0), 1, 1],
    ['where', ':where(#target)', ':where(#target)', (0, 0, 0), 1, 1],
    ['list', '.box, #nomatch, div', '.box', (0, 1, 0), 3, 2],
    ['media', '.box', '.box', (0, 1, 0), 1, 1],
    ['main', '#target', '#target', (1, 0, 0), 1, 1],
    ['is', ':is(#target, .box)', ':is(#target, .box)', (1, 0, 0), 1, 1],
    ['compound', 'div.box#target', 'div.box#target', (1, 1, 1), 1, 1],
]


def fixture_page(webkit_source):
    font = (Path(webkit_source) / 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').read_bytes()
    assert hashlib.sha256(font).hexdigest() == AHEM_SHA256, 'pinned Ahem fixture identity'
    template = (FIXTURES / 'inspector-diagnostics.html').read_text(encoding='utf-8')
    return template.replace('{{FONT_BASE64}}', base64.b64encode(font).decode())


class Diagnostics:
    def __init__(self, p):
        P, I, D = p.pointer, p.integer, p.double
        self.p = p
        self.has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        self.enable = p.bind('rv_host_set_diagnostics', I, [P, I])
        self.render_tree = p.bind('rv_host_inspect_render_tree', I, [P, P, I, ctypes.POINTER(P)])
        self.matched_rules = p.bind('rv_host_inspect_matched_rules', I, [P, P, ctypes.POINTER(P)])
        self.box_model = p.bind('rv_host_inspect_box_model', I, [P, P, ctypes.POINTER(D)])
        self.kind = p.bind('rv_diagnostic_kind', I, [P])
        self.text_of = p.bind('rv_diagnostic_text', I, [P, ctypes.c_char_p, I, ctypes.POINTER(I)])
        self.count = p.bind('rv_diagnostic_count', I, [P])
        self.entry_string = p.bind('rv_diagnostic_entry_string', I, [P, I, I, ctypes.c_char_p, I, ctypes.POINTER(I)])
        self.entry_number = p.bind('rv_diagnostic_entry_number', I, [P, I, I, ctypes.POINTER(D)])
        self.release = p.bind('rv_diagnostic_release', None, [P])
        self.live = p.bind('rv_diagnostic_live_count', I, [])
        self.fact_of = p.bind('rv_host_capability_fact', I, [P, I, ctypes.c_char_p, I, ctypes.POINTER(I)])
        self.held = []

    def snapshot(self, operation, *arguments):
        result = self.p.pointer()
        status = operation(*arguments, ctypes.byref(result))
        self.p.expect(status == OK and bool(result.value), operation.__name__ + ': status ' + str(status))
        self.held.append(result.value)
        return result.value

    def drop(self, diagnostic):
        self.held.remove(diagnostic)
        self.release(diagnostic)

    def release_all(self):
        for diagnostic in self.held:
            self.release(diagnostic)
        self.held = []

    def text(self, diagnostic):
        length = self.p.integer(-5)
        self.p.expect(self.text_of(diagnostic, None, 0, ctypes.byref(length)) in (OK, BUFFER_TOO_SMALL), 'text length query')
        buffer = ctypes.create_string_buffer(max(length.value, 1))
        self.p.expect(self.text_of(diagnostic, buffer, length.value, ctypes.byref(length)) == OK, 'copy text')
        return buffer.raw[:length.value].decode('utf-8')

    def string(self, diagnostic, index, field):
        buffer, length = ctypes.create_string_buffer(4096), self.p.integer()
        self.p.expect(self.entry_string(diagnostic, index, field, buffer, len(buffer), ctypes.byref(length)) == OK, 'entry string')
        return buffer.raw[:length.value].decode('utf-8')

    def number(self, diagnostic, index, field):
        value = ctypes.c_double()
        self.p.expect(self.entry_number(diagnostic, index, field, ctypes.byref(value)) == OK, 'entry number')
        return value.value

    def rules(self, diagnostic):
        return [{'origin': int(self.number(diagnostic, i, ORIGIN)),
                 'specificity': tuple(int(self.number(diagnostic, i, f)) for f in (SPEC_A, SPEC_B, SPEC_C)),
                 'selectors': int(self.number(diagnostic, i, SELECTOR_COUNT)), 'matched': int(self.number(diagnostic, i, MATCHED_COUNT)),
                 'selectorText': self.string(diagnostic, i, SELECTOR_TEXT), 'matchedSelector': self.string(diagnostic, i, MATCHED_SELECTOR),
                 'declarations': self.string(diagnostic, i, DECLARATIONS)} for i in range(self.count(diagnostic))]

    def boxes(self, host, element):
        values = (ctypes.c_double * 16)()
        status = self.box_model(host, element, values)
        self.p.expect(status == OK, 'box model status ' + str(status))
        return {name: dict(zip(['x', 'y', 'width', 'height'], values[i * 4:i * 4 + 4])) for i, name in enumerate(BOXES)}

    def fact(self, host, name, dimension):
        value = self.p.integer(42)
        self.p.expect(self.fact_of(host, 4, name.encode(), dimension, ctypes.byref(value)) == OK, 'capability fact ' + name)
        return value.value


def wait_for_ahem(p):
    """Cycles until the pinned font lays out the inline span 20px wide; a hang guard, counting no assertions."""
    find = p.bind('rv_document_get_element_by_id', p.pointer, [p.pointer, ctypes.c_char_p])
    rect = p.bind('rv_element_rect', p.integer, [p.pointer] + [ctypes.POINTER(p.double)] * 4)
    release = p.bind('rv_node_release', None, [p.pointer])
    cycle = p.bind('rv_run_loop_cycle', p.integer, [p.integer])
    update = p.bind('rv_host_update', p.integer, [p.pointer])
    deadline = time.monotonic() + 10
    while True:
        span = find(p.host, b'inline')
        values = [p.double() for _ in range(4)]
        rect(span, *[ctypes.byref(v) for v in values])
        release(span)
        # FreeType may scale the Ahem advances by a few 1/65536 px.
        if abs(values[2].value - 20) < 0.01:
            return
        if time.monotonic() > deadline:
            raise AssertionError('pinned Ahem was not applied: inline width ' + str(values[2].value))
        cycle(10)
        update(p.host)


def renderer_lines(text):
    """(indent, line) per nonblank line; the dump indents two spaces per nesting level."""
    lines = []
    for line in text.splitlines():
        if line.strip():
            stripped = line.lstrip(' ')
            lines.append(((len(line) - len(stripped)) // 2, stripped))
    return lines


def at_size(line):
    match = re.search(r'at \((-?[\d.]+),(-?[\d.]+)\) size ([\d.]+)x([\d.]+)', line)
    return tuple(float(v) for v in match.groups()) if match else None


def close(a, b, tolerance=QUANTUM):
    return abs(a - b) <= tolerance + 1e-9


def run_once(native_directory, webkit_source, oracle):
    with SvgProbe(native_directory, 320, 240) as p:
        P, I = p.pointer, p.integer
        d = Diagnostics(p)
        baseline = d.live()
        try:
            p.expect(p.bind('rv_abi_version', I, [])() == ABI, f'ABI version {ABI}')
            p.expect(d.has(b'diagnostics') == 1, 'rv_abi_has("diagnostics")')
            p.load(fixture_page(webkit_source), standalone=False)
            wait_for_ahem(p)
            p.update()
            document = p.bind('rv_host_document', P, [P])(p.host)
            p.retained.append(('rv_node_release', document))
            target, flow, inline, hidden, action, turned, zoomed = (p.node(n) for n in ['target', 'flow', 'inline', 'hidden', 'action', 'turned', 'zoomed'])
            text_node = p.object('rv_dom_node_get_first_child', [P], [target], 'node')

            # Capability facts and the opt-in.
            p.expect(d.fact(p.host, 'diagnostics', 1) == 1 and d.fact(p.host, 'diagnostics', 2) == 0, 'diagnostics implemented, not enabled')
            p.expect(d.fact(p.host, 'inspector-frontend', 1) == 0 and d.fact(p.host, 'inspector-frontend', 4) == 0, 'no developer-tools frontend')
            for name in ['inspector', 'jsc-inspector']:
                p.expect(d.fact(p.host, name, 1) == 0, name + ' is the stub in this flavor')
            result = P(42)
            p.expect(d.render_tree(p.host, None, 0, ctypes.byref(result)) == UNSUPPORTED and result.value == 42, 'disabled host: render tree unsupported')
            p.expect(d.matched_rules(p.host, text_node, ctypes.byref(result)) == UNSUPPORTED and result.value == 42,
                     'disabled host answers before reading the node')
            values = (ctypes.c_double * 16)(*([7.0] * 16))
            p.expect(d.box_model(p.host, target, values) == UNSUPPORTED and list(values) == [7.0] * 16, 'disabled host: box model unsupported')
            p.expect(d.enable(p.host, 2) == UNSUPPORTED and d.fact(p.host, 'diagnostics', 2) == 0, 'enable takes 0 or 1')
            p.expect(d.enable(p.host, 1) == OK and d.fact(p.host, 'diagnostics', 2) == 1, 'diagnostics enabled')

            # Render tree of the document.
            tree = d.snapshot(d.render_tree, p.host, None, ID_AND_CLASS)
            p.expect(d.kind(tree) == RENDER_TREE and d.count(tree) == 0, 'render-tree snapshot kind and count')
            text = d.text(tree)
            lines = renderer_lines(text)
            p.expect(lines[0][0] == 0 and lines[0][1].startswith('layer at (0,0)'), 'dump starts with the root layer')
            p.expect(lines[1] == (1, lines[1][1]) and lines[1][1].startswith('RenderView at (0,0) size 320x240'), 'the view box under the root layer')
            # Each layer line opens a group whose renderers nest one level below it and deepen one level at a time.
            groups, nested = [], True
            for level, line in lines:
                if line.startswith('layer '):
                    groups.append((level, []))
                elif groups:
                    layer_level, members = groups[-1]
                    previous = members[-1][0] if members else layer_level
                    nested = nested and layer_level < level <= previous + 1
                    members.append((level, line))
            p.expect(nested and all(members for _, members in groups), 'renderers nest under their layer one level at a time')
            html = next(members for _, members in groups if members[0][1].startswith('RenderBlock {HTML}'))
            p.expect(html[1][1].startswith('RenderBody {BODY}') and html[1][0] == html[0][0] + 1, 'body nests in html')
            p.expect([sum('id="' + i + '"' in l for _, l in lines) for i in ['target', 'flow', 'zoomed', 'turned', 'inline', 'action']] == [1] * 6,
                     'one box for each visible element')
            p.expect(not any('id="hidden"' in l for _, l in lines), 'no box for display:none')
            target_group = next(members for _, members in groups if 'id="target"' in members[0][1])
            target_line = target_group[0][1]
            p.expect(target_line.startswith('RenderBlock (positioned) {DIV}'), 'a positioned block heads the #target layer')
            p.expect(target_group[1][1].startswith('RenderText {#text}') and re.match(r'text run at \(\d+,\d+\) width [\d.]+: "AB"', target_group[2][1]),
                     'text and text run of #target nest in its box')
            border = d.boxes(p.host, target)['border']
            # The dump snaps positions and sizes to whole pixels.
            p.expect(at_size(target_line) is not None and all(abs(a - b) <= 1 for a, b in zip(at_size(target_line),
                     (border['x'], border['y'], border['width'], border['height']))), 'dump position and size of #target agree with the box model')
            layered = d.snapshot(d.render_tree, p.host, document, ALL_LAYERS | LAYER_NESTING | OVERFLOW | ID_AND_CLASS | LAYOUT_STATE)
            layer_lines = [l for _, l in renderer_lines(d.text(layered)) if l.startswith('layer ')]
            p.expect(len(layer_lines) == 7, 'a layer for the view, the html and each of the five positioned boxes: ' + str(len(layer_lines)))
            p.expect(any(l.startswith('positive z-order list') or l.startswith('normal flow list') for _, l in renderer_lines(d.text(layered))),
                     'layer nesting annotates the lists')
            # Render tree of an element.
            subtree = d.snapshot(d.render_tree, p.host, flow, ID_AND_CLASS)
            sub = renderer_lines(d.text(subtree))
            p.expect(sub[0][0] == 0 and sub[0][1].startswith('RenderBlock (positioned) {DIV}') and 'id="flow"' in sub[0][1], 'element dump starts at its box')
            p.expect(all(level >= 1 for level, _ in sub[1:]) and not any(l.startswith(('layer ', 'text run')) for _, l in sub), 'element dump nests renderers only')
            p.expect(any(l.startswith('RenderInline {SPAN}') and 'id="inline"' in l for _, l in sub), 'inline box in the subtree')
            p.expect(any(l.startswith('RenderButton {BUTTON}') for _, l in sub), 'button box in the subtree')
            inline_tree = d.snapshot(d.render_tree, p.host, inline, 0)
            p.expect(renderer_lines(d.text(inline_tree))[0][1].startswith('RenderInline {SPAN}'), 'inline element dump')
            for flags, node, label in [(ALL_LAYERS, flow, 'layer flag with an element'), (64, None, 'unknown flag'), (1 << 30, None, 'high unknown flag'),
                                       (0, hidden, 'element without a renderer')]:
                p.expect(d.render_tree(p.host, node, flags, ctypes.byref(result)) == UNSUPPORTED and result.value == 42, label + ' unsupported')
            p.expect(d.render_tree(p.host, None, 0, None) == NULL_ARGUMENT, 'null output rejected')

            # Matched rules of #target.
            rules_snapshot = d.snapshot(d.matched_rules, p.host, target)
            p.expect(d.kind(rules_snapshot) == MATCHED_RULES and d.text(rules_snapshot) == '', 'matched-rules kind and empty text')
            rules = d.rules(rules_snapshot)
            origins = [r['origin'] for r in rules]
            p.expect(origins == sorted(origins), 'origins in cascade order: ' + str(origins))
            p.expect(USER_AGENT in origins and USER not in origins and origins[-1] == INLINE and origins.count(INLINE) == 1, 'user-agent, author and one inline entry')
            p.expect(any(r['origin'] == USER_AGENT and 'display: block' in r['declarations'] for r in rules), 'user-agent div rule')
            author = [r for r in rules if r['origin'] == AUTHOR]
            names = [re.search(r'--order: (\w+)', r['declarations']).group(1) for r in author]
            p.expect(names == [row[0] for row in TARGET_AUTHOR], 'author cascade order: ' + str(names))
            for rule, (name, selector, matched, specificity, selectors, matched_count) in zip(author, TARGET_AUTHOR):
                p.expect(rule['selectorText'] == selector and rule['matchedSelector'] == matched, name + ' selector text: ' + str(rule))
                p.expect(rule['specificity'] == specificity, name + ' specificity ' + str(rule['specificity']))
                p.expect(rule['selectors'] == selectors and rule['matched'] == matched_count, name + ' selector counts')
                p.expect(re.fullmatch(r'(?:[-\w]+: [^;]+;)(?: [-\w]+: [^;]+;)*', rule['declarations']) is not None, name + ' declaration block structure')
            p.expect('excluded' not in ' '.join(r['declarations'] for r in rules), 'non-matching @media rule absent')
            inline_rule = rules[-1]
            p.expect(inline_rule['selectorText'] == '' and inline_rule['matchedSelector'] == '' and inline_rule['specificity'] == (0, 0, 0)
                     and inline_rule['selectors'] == 0 and inline_rule['matched'] == 0 and inline_rule['declarations'] == 'opacity: 0.5;', 'inline entry')
            again = d.rules(d.snapshot(d.matched_rules, p.host, target))
            p.expect(again == rules, 'cascade order is deterministic')
            plain = d.rules(d.snapshot(d.matched_rules, p.host, inline))
            p.expect(all(r['origin'] != INLINE for r in plain), 'no inline entry without a style attribute')
            p.expect(d.matched_rules(p.host, text_node, ctypes.byref(result)) == NOT_ELEMENT and result.value == 42, 'text node is not an element')
            buffer, length = ctypes.create_string_buffer(4), I(-5)
            p.expect(d.entry_string(rules_snapshot, 0, DECLARATIONS, buffer, 2, ctypes.byref(length)) == BUFFER_TOO_SMALL and length.value > 2, 'short buffer reports the length')
            number = ctypes.c_double(9.5)
            for index, field in [(len(rules), ORIGIN), (-1, ORIGIN), (0, 6), (0, -1)]:
                p.expect(d.entry_number(rules_snapshot, index, field, ctypes.byref(number)) == UNSUPPORTED and number.value == 9.5, 'number out of range')
            for index, field in [(len(rules), SELECTOR_TEXT), (0, 3)]:
                p.expect(d.entry_string(rules_snapshot, index, field, buffer, 4, ctypes.byref(length)) == UNSUPPORTED, 'string out of range')

            # Box model against the Chromium oracle, and its own invariants.
            scroll_to = p.bind('rv_host_scroll_to', I, [P, I, I])
            page_scale = p.bind('rv_host_set_page_scale', I, [P, ctypes.c_double, I, I])
            element_rect = p.bind('rv_element_rect', I, [P] + [ctypes.POINTER(p.double)] * 4)
            handles = {'target': target, 'flow': flow, 'zoomed': zoomed, 'action': action}
            checked = 0
            for case in oracle['cases']:
                p.expect(page_scale(p.host, case['pageScale'], 0, 0) == OK, 'page scale ' + case['name'])
                p.expect(scroll_to(p.host, case['scrollX'], case['scrollY']) == OK, 'scroll ' + case['name'])
                p.update()
                for identifier, expected in case['boxes'].items():
                    native = d.boxes(p.host, handles[identifier])
                    for box in BOXES:
                        for field in ['x', 'y', 'width', 'height']:
                            p.expect(close(native[box][field], expected[box][field]), f"{case['name']} #{identifier} {box} {field}: "
                                     f"native {native[box][field]} Chromium {expected[box][field]}")
                            p.expect(abs(native[box][field] * 64 - round(native[box][field] * 64)) < 1e-6, 'LayoutUnit quantised')
                            checked += 1
                    rect = [p.double() for _ in range(4)]
                    element_rect(handles[identifier], *[ctypes.byref(v) for v in rect])
                    p.expect([v.value for v in rect] == [native['border'][f] for f in ['x', 'y', 'width', 'height']], 'border box equals rv_element_rect')
            p.expect(page_scale(p.host, 1, 0, 0) == OK and scroll_to(p.host, 0, 0) == OK, 'reset scale and scroll')
            p.update()
            rotated = d.boxes(p.host, turned)
            p.expect(close(rotated['border']['width'], 22) and close(rotated['border']['height'], 42), 'bounding rectangle after a transform')
            for node, status, label in [(hidden, UNSUPPORTED, 'display:none'), (inline, UNSUPPORTED, 'inline box'), (text_node, NOT_ELEMENT, 'text node')]:
                values = (ctypes.c_double * 16)(*([7.0] * 16))
                p.expect(d.box_model(p.host, node, values) == status and list(values) == [7.0] * 16, label + ' box model rejected')

            # The accessibility tree of the same fixture, through the existing AX functions.
            set_ax = p.bind('rv_host_set_accessibility', I, [P, I, P, P])
            p.expect(set_ax(p.host, 1, None, None) == OK, 'accessibility on')
            node_ax = p.bind('rv_node_ax', P, [P])
            ax_release = p.bind('rv_ax_release', None, [P])
            ax_role = p.bind('rv_ax_role', I, [P])
            ax_rect = p.bind('rv_ax_rect', I, [P] + [ctypes.POINTER(p.double)] * 4)
            button = node_ax(action)
            p.expect(bool(button), 'button accessibility object')
            try:
                p.expect(ax_role(button) >= 0, 'button role')
                rect = [p.double() for _ in range(4)]
                p.expect(ax_rect(button, *[ctypes.byref(v) for v in rect]) == OK and rect[2].value > 0 and rect[3].value > 0, 'button AX rect')
                border = d.boxes(p.host, action)['border']
                p.expect(close(rect[2].value, border['width'], 1) and close(rect[3].value, border['height'], 1), 'AX rect matches the border box size')
            finally:
                ax_release(button)
            p.expect(set_ax(p.host, 0, None, None) == OK, 'accessibility off')

            # Threads: host calls stay on the owning thread; snapshots read on any thread.
            statuses = []

            def worker():
                out = P(42)
                statuses.append((d.render_tree(p.host, None, 0, ctypes.byref(out)), out.value))
                statuses.append((d.enable(p.host, 0), None))
                statuses.append((d.kind(tree), d.count(rules_snapshot)))

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()
            p.expect(statuses == [(WRONG_THREAD, 42), (WRONG_THREAD, None), (RENDER_TREE, len(rules))], 'thread rules: ' + str(statuses))
            p.expect(d.enable(None, 1) == NULL_ARGUMENT and d.kind(None) == NULL_ARGUMENT and d.count(None) == NULL_ARGUMENT, 'null handles')
            d.release(None)

            # Disabling keeps snapshots readable; release frees them.
            before = d.live()
            p.expect(before - baseline == len(d.held), 'live count tracks snapshots')
            p.expect(d.enable(p.host, 0) == OK and d.fact(p.host, 'diagnostics', 2) == 0, 'diagnostics disabled')
            p.expect(d.text(tree) == text and d.rules(rules_snapshot) == rules, 'snapshots readable after disabling')
            p.expect(d.render_tree(p.host, None, 0, ctypes.byref(result)) == UNSUPPORTED, 'disabled again')
            d.drop(inline_tree)
            p.expect(d.live() == before - 1, 'release frees one snapshot')
            held = list(d.held)
        except BaseException:
            d.release_all()
            raise
        # Snapshots outlive the host.
        p.release_all()
        expired = p.host
        p.dispose_host()
        p.expect(d.text(tree) == text and d.rules(rules_snapshot) == rules, 'snapshots readable after rv_host_destroy')
        p.expect(d.enable(expired, 1) == UNSUPPORTED, 'destroyed host rejected before dereference')
        result = P(42)
        p.expect(d.render_tree(expired, None, 0, ctypes.byref(result)) == UNSUPPORTED and result.value == 42, 'destroyed host: no snapshot')
        d.release_all()
        p.expect(d.live() == baseline, 'every snapshot released')
        return p.assertions, checked, len(held)


def run(native_directory, webkit_source, repeat):
    oracle = json.loads((FIXTURES / 'inspector-diagnostics-oracle.json').read_text(encoding='utf-8'))
    totals = set()
    for _ in range(repeat):
        totals.add(run_once(native_directory, webkit_source, oracle))
    if len(totals) != 1:
        raise AssertionError('assertion counts vary across repeats: ' + str(totals))
    assertions, checked, held = totals.pop()
    print(f'inspector diagnostics PASS: {assertions} assertions, {checked} box-model oracle checks, {held} snapshots held past destroy, '
          f'{repeat} run(s)', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--webkit-source', required=True)
    parser.add_argument('--repeat', type=int, default=1)
    args = parser.parse_args()
    run(args.native_directory, args.webkit_source, args.repeat)
