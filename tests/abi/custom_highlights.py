"""T03 custom highlights probe against an actual runtime directory. Replays the Chromium oracle
tests/fixtures/custom-highlights-oracle.json: CSS.highlights (maplike) and Highlight (setlike) in iteration order, the
snapshot copies values() and entries() return while the set or map changes, and the colour at the centre of each 20px
Ahem cell of tests/fixtures/custom-highlights.html after each paint step. Differences from Chromium must equal
tests/fixtures/custom-highlights-qualified.json exactly. Then checks argument, enumeration and thread errors, highlights
and ranges held past document replacement and rv_host_destroy, and a highlight whose ranges belong to another document."""

import argparse
import base64
import ctypes
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, WRONG_THREAD, UNSUPPORTED = 0, -1, -2, -9
ABI = 54
TYPES = ['highlight', 'spelling-error', 'grammar-error']
COLOURS = {(0, 0, 0): 'k', (255, 255, 255): 'w', (0, 0, 255): 'B', (255, 0, 0): 'R', (255, 255, 0): 'Y', (0, 128, 0): 'G'}


class Sequence(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('count', ctypes.c_int32), ('items', ctypes.POINTER(ctypes.c_void_p))]


class Span(ctypes.Structure):
    _fields_ = [('data', ctypes.POINTER(ctypes.c_uint8)), ('length', ctypes.c_int32)]


class Entry(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('key', Span), ('value', ctypes.c_void_p)]


class Entries(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('count', ctypes.c_int32), ('items', ctypes.POINTER(Entry))]


def page(webkit_source):
    font = (Path(webkit_source) / 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').read_bytes()
    return (FIXTURES / 'custom-highlights.html').read_text().replace('{{FONT_BASE64}}', base64.b64encode(font).decode())


class Highlights:
    """The ABI of the custom highlight API over one SvgProbe host."""

    def __init__(self, p):
        self.p = p
        P, I, U = p.pointer, p.integer, ctypes.c_uint32
        b = p.bind
        self.create = b('rv_dom_highlight_create', I, [P, ctypes.POINTER(Sequence), ctypes.POINTER(P)])
        self.h_size = b('rv_dom_highlight_size', I, [P, ctypes.POINTER(U)])
        self.h_has = b('rv_dom_highlight_has', I, [P, P, ctypes.POINTER(I)])
        self.h_values = b('rv_dom_highlight_values', I, [P, ctypes.POINTER(Sequence)])
        self.h_add = b('rv_dom_highlight_add', I, [P, P])
        self.h_delete = b('rv_dom_highlight_delete', I, [P, P, ctypes.POINTER(I)])
        self.h_clear = b('rv_dom_highlight_clear', I, [P])
        self.get_priority = b('rv_dom_highlight_get_priority', I, [P, ctypes.POINTER(I)])
        self.set_priority = b('rv_dom_highlight_set_priority', I, [P, I])
        self.get_type = b('rv_dom_highlight_get_type', I, [P, ctypes.POINTER(I)])
        self.set_type = b('rv_dom_highlight_set_type', I, [P, I])
        self.registry_of = b('rv_dom_css_get_highlights', I, [P, ctypes.POINTER(P)])
        self.r_size = b('rv_dom_highlight_registry_size', I, [P, ctypes.POINTER(U)])
        self.r_has = b('rv_dom_highlight_registry_has', I, [P, ctypes.c_char_p, I, ctypes.POINTER(I)])
        self.r_get = b('rv_dom_highlight_registry_get', I, [P, ctypes.c_char_p, I, ctypes.POINTER(P)])
        self.r_entries = b('rv_dom_highlight_registry_entries', I, [P, ctypes.POINTER(Entries)])
        self.r_set = b('rv_dom_highlight_registry_set', I, [P, ctypes.c_char_p, I, P])
        self.r_delete = b('rv_dom_highlight_registry_delete', I, [P, ctypes.c_char_p, I, ctypes.POINTER(I)])
        self.r_clear = b('rv_dom_highlight_registry_clear', I, [P])
        self.release_values = b('rv_dom_sequence_abstract_range_release', None, [ctypes.POINTER(Sequence)])
        self.release_static = b('rv_dom_sequence_static_range_release', None, [ctypes.POINTER(Sequence)])
        self.release_entries = b('rv_dom_sequence_pair_dom_string_and_highlight_release', None, [ctypes.POINTER(Entries)])
        self.release_highlight = b('rv_dom_highlight_release', None, [P])
        self.release_registry = b('rv_dom_highlight_registry_release', None, [P])
        self.release_range = b('rv_dom_abstract_range_release', None, [P])
        self.retain_range = b('rv_dom_abstract_range_retain', P, [P])

    def ok(self, status, label):
        self.p.expect(status == OK, f'{label}: status {status}')

    def registry(self, document):
        result = self.p.pointer()
        self.ok(self.registry_of(document, ctypes.byref(result)), 'CSS.highlights')
        self.p.retained.append(('rv_dom_highlight_registry_release', result.value))
        return result.value

    def highlight(self, document, *ranges):
        items = (ctypes.c_void_p * max(len(ranges), 1))(*ranges)
        sequence = Sequence(1, len(ranges), ctypes.cast(items, ctypes.POINTER(ctypes.c_void_p)))
        result = self.p.pointer()
        self.ok(self.create(document, ctypes.byref(sequence), ctypes.byref(result)), 'new Highlight')
        self.p.retained.append(('rv_dom_highlight_release', result.value))
        return result.value

    def size(self, target, registry=False):
        value = ctypes.c_uint32()
        self.ok((self.r_size if registry else self.h_size)(target, ctypes.byref(value)), 'size')
        return value.value

    def has(self, highlight, value):
        result = self.p.integer()
        self.ok(self.h_has(highlight, value, ctypes.byref(result)), 'Highlight.has')
        return bool(result.value)

    def values(self, highlight):
        sequence = Sequence()
        self.ok(self.h_values(highlight, ctypes.byref(sequence)), 'Highlight.values')
        items = [sequence.items[i] for i in range(sequence.count)]
        self.release_values(ctypes.byref(sequence))
        return items

    def add(self, highlight, value):
        self.ok(self.h_add(highlight, value), 'Highlight.add')

    def delete(self, highlight, value):
        result = self.p.integer()
        self.ok(self.h_delete(highlight, value, ctypes.byref(result)), 'Highlight.delete')
        return bool(result.value)

    def priority(self, highlight, value=None):
        if value is not None:
            self.ok(self.set_priority(highlight, value), 'Highlight.priority setter')
        result = self.p.integer()
        self.ok(self.get_priority(highlight, ctypes.byref(result)), 'Highlight.priority')
        return result.value

    def type(self, highlight):
        result = self.p.integer()
        self.ok(self.get_type(highlight, ctypes.byref(result)), 'Highlight.type')
        return TYPES[result.value]

    def set(self, registry, name, highlight):
        key = name.encode()
        self.ok(self.r_set(registry, key, len(key), highlight), f'registry.set {name}')

    def get(self, registry, name):
        key, result = name.encode(), self.p.pointer()
        self.ok(self.r_get(registry, key, len(key), ctypes.byref(result)), f'registry.get {name}')
        if result.value:
            self.release_highlight(result.value)
        return result.value

    def registry_has(self, registry, name):
        key, result = name.encode(), self.p.integer()
        self.ok(self.r_has(registry, key, len(key), ctypes.byref(result)), f'registry.has {name}')
        return bool(result.value)

    def registry_delete(self, registry, name):
        key, result = name.encode(), self.p.integer()
        self.ok(self.r_delete(registry, key, len(key), ctypes.byref(result)), f'registry.delete {name}')
        return bool(result.value)

    def entries(self, registry):
        entries = Entries()
        self.ok(self.r_entries(registry, ctypes.byref(entries)), 'registry.entries')
        items = [(ctypes.string_at(entries.items[i].key.data, entries.items[i].key.length).decode(), entries.items[i].value)
                 for i in range(entries.count)]
        self.release_entries(ctypes.byref(entries))
        return items

    def keys(self, registry):
        return [key for key, _ in self.entries(registry)]


class Fixture:
    """The loaded fixture: its text node, live Ranges and StaticRanges over it, and the first-line cell colours."""

    def __init__(self, p, webkit_source):
        self.p = p
        P, I = p.pointer, p.integer
        p.load(page(webkit_source), standalone=False)
        self.document = p.bind('rv_host_document', P, [P])(p.host)
        self.cycle = p.bind('rv_run_loop_cycle', I, [I])
        # The wait reads through uncounted calls, so the assertion count is independent of the font load time.
        probe = p.node('w')
        update = p.bind('rv_host_update', I, [P])
        deadline = time.monotonic() + 10
        while self.width(probe) != 160:
            if time.monotonic() > deadline:
                raise AssertionError('pinned Ahem was not applied: width ' + str(self.width(probe)))
            self.cycle(10)
            update(p.host)
        p.update()
        p.expect(self.width(probe) == 160, 'pinned Ahem applied')
        paragraph = p.node('t')
        self.text = p.object('rv_dom_node_get_first_child', [P], [paragraph], 'node')
        self.selection = p.object('rv_dom_document_get_selection', [P], [self.document], 'dom_selection')

    def width(self, element):
        p = self.p
        rect, width = p.pointer(), p.double()
        status = p.bind('rv_dom_element_get_bounding_client_rect', p.integer, [p.pointer, ctypes.POINTER(p.pointer)])(element, ctypes.byref(rect))
        if status != OK or not rect.value:
            return None
        p.bind('rv_dom_dom_rect_read_only_get_width', p.integer, [p.pointer, ctypes.POINTER(p.double)])(rect.value, ctypes.byref(width))
        p.bind('rv_dom_dom_rect_read_only_release', None, [p.pointer])(rect.value)
        return width.value

    def range(self, start, end):
        p = self.p
        result = p.object('rv_dom_document_create_range', [p.pointer], [self.document], 'abstract_range')
        p.call('rv_dom_range_set_start', [p.pointer, p.pointer, ctypes.c_uint32], result, self.text, start)
        p.call('rv_dom_range_set_end', [p.pointer, p.pointer, ctypes.c_uint32], result, self.text, end)
        return result

    def static_range(self, highlights, start, end):
        """A StaticRange from Selection.getComposedRanges over the text's [start, end)."""
        p = self.p
        p.call('rv_dom_dom_selection_set_base_and_extent', [p.pointer, p.pointer, ctypes.c_uint32, p.pointer, ctypes.c_uint32],
               self.selection, self.text, start, self.text, end)
        roots, result = Sequence(1, 0, None), Sequence()
        p.call('rv_dom_dom_selection_get_composed_ranges', [p.pointer, p.pointer, ctypes.POINTER(Sequence), ctypes.POINTER(Sequence)],
               self.selection, None, ctypes.byref(roots), ctypes.byref(result))
        p.expect(result.count == 1, 'one composed range')
        static = highlights.retain_range(result.items[0])
        highlights.release_static(ctypes.byref(result))
        p.call('rv_dom_dom_selection_remove_all_ranges', [p.pointer], self.selection)
        p.retained.append(('rv_dom_abstract_range_release', static))
        return static

    def row(self, cells):
        for _ in range(3):
            self.p.update()
            self.cycle(10)
        rgba = self.p.paint()
        return [self.p.pixel(rgba, i * 20 + 10, 10)[:3] for i in range(cells)]


def letters(row):
    return ''.join(COLOURS.get(tuple(colour), '?') for colour in row)


def verify(native_directory, webkit_source, abi, record=None):
    oracle = json.loads((FIXTURES / 'custom-highlights-oracle.json').read_text(encoding='utf-8'))
    qualified = json.loads((FIXTURES / 'custom-highlights-qualified.json').read_text(encoding='utf-8'))['differences']
    differences = {}
    with SvgProbe(native_directory, 320, 60) as p:
        p.expect(p.bind('rv_abi_version', p.integer, [])() == abi, f'ABI version {abi}')
        p.expect(p.bind('rv_abi_has', p.integer, [ctypes.c_char_p])(b'dom-custom-highlights') == 1, 'dom-custom-highlights feature')
        for feature in [b'dom:Highlight', b'dom:HighlightRegistry', b'dom-constructor:Highlight']:
            p.expect(p.bind('rv_abi_has', p.integer, [ctypes.c_char_p])(feature) == 1, feature.decode())
        x = Highlights(p)
        f = Fixture(p, webkit_source)

        def compare(key, actual, expected):
            if actual == expected:
                p.expect(True, key)
                return
            differences[key] = {'native': actual, 'chromium': expected}
            if record is None:
                p.expect(key in qualified and qualified[key]['native'] == actual,
                         f'{key}: native {json.dumps(actual)} != chromium {json.dumps(expected)}')

        api = {}
        reg = x.registry(f.document)
        again = p.pointer()
        x.ok(x.registry_of(f.document, ctypes.byref(again)), 'CSS.highlights again')
        p.expect(again.value == reg, 'CSS.highlights is one registry per document')
        x.release_registry(again.value)
        h1, h2, h4 = x.highlight(f.document), x.highlight(f.document, f.range(0, 1)), x.highlight(f.document)
        label = lambda v: {h1: 'h1', h2: 'h2', h4: 'h4'}.get(v, '?')
        api['registry.empty'] = x.size(reg, True)
        x.set(reg, 'a', h1); x.set(reg, 'b', h2); x.set(reg, 'c', h1)
        api['registry.order'] = [x.keys(reg), x.size(reg, True)]
        x.set(reg, 'a', h4)
        api['registry.replace'] = [x.keys(reg), label(x.get(reg, 'a')), x.size(reg, True)]
        api['registry.delete'] = [x.registry_delete(reg, 'b'), x.registry_delete(reg, 'b'), x.keys(reg), x.registry_has(reg, 'b'),
                                  x.get(reg, 'zz'), x.registry_has(reg, 'a')]
        x.set(reg, 'b', h2)
        api['registry.reinsert'] = x.keys(reg)
        api['registry.entries'] = [[k, label(v)] for k, v in x.entries(reg)]
        api['registry.sameHighlightTwice'] = [label(x.get(reg, 'a')), label(x.get(reg, 'c')), x.get(reg, 'c') == x.get(reg, 'c')]
        # entries() is a snapshot copy: the mutation Chromium makes while visiting 'a' leaves it unchanged.
        snapshot = x.entries(reg)
        api['registry.iterationSnapshot'] = [k for k, _ in snapshot]
        x.registry_delete(reg, 'c'); x.set(reg, 'd', h1)
        p.expect([k for k, _ in snapshot] == ['a', 'c', 'b'], 'entries() snapshot unchanged by later mutation')
        api['registry.afterIteration'] = x.keys(reg)
        x.ok(x.r_clear(reg), 'registry.clear')
        api['registry.clear'] = [x.size(reg, True), x.keys(reg), x.size(h2)]
        p.expect(x.size(h2) == 1, 'registry.clear unregisters every name and leaves each highlight its ranges')

        r1, r2, r3, r4 = f.range(0, 1), f.range(2, 3), f.range(4, 5), f.range(8, 9)
        s1 = f.static_range(x, 6, 7)
        name = lambda r: {r1: 'r1', r2: 'r2', r3: 'r3', r4: 'r4', s1: 's1'}.get(r, '?')
        api['highlight.emptyConstructor'] = x.size(x.highlight(f.document))
        h = x.highlight(f.document, r1, r2, r1)
        api['highlight.constructor'] = [x.size(h), [name(r) for r in x.values(h)], x.priority(h), x.type(h)]
        x.add(h, r3); x.add(h, r1)
        api['highlight.addKeepsPosition'] = [[name(r) for r in x.values(h)], x.size(h)]
        x.add(h, s1)
        api['highlight.addStatic'] = [name(r) for r in x.values(h)]
        api['highlight.delete'] = [x.delete(h, r2), x.delete(h, r2), x.has(h, r2), x.has(h, r1), [name(r) for r in x.values(h)]]
        before = x.values(h)
        api['highlight.iterationSnapshot'] = [name(r) for r in before]
        x.delete(h, r3); x.add(h, r4)
        p.expect([name(r) for r in before] == ['r1', 'r3', 's1'], 'values() snapshot unchanged by later mutation')
        api['highlight.afterIteration'] = [name(r) for r in x.values(h)]
        api['highlight.priority'] = [x.priority(h, v) for v in [5, -1, 2147483647, -2147483648, 0]]
        types = []
        for value in ['spelling-error', 'grammar-error', 'highlight']:
            x.ok(x.set_type(h, TYPES.index(value)), 'Highlight.type setter')
            types.append(x.type(h))
        api['highlight.type'] = types
        p.expect(x.set_type(h, 3) == UNSUPPORTED and x.set_type(h, -1) == UNSUPPORTED, 'an unknown HighlightType index')
        api['highlight.invalidType'] = x.type(h)
        x.ok(x.h_clear(h), 'Highlight.clear')
        api['highlight.clear'] = [x.size(h), len(x.values(h))]
        buffer, length = ctypes.create_string_buffer(64), p.integer()
        p.call('rv_dom_character_data_get_data', [p.pointer, p.pointer, p.integer, ctypes.POINTER(p.integer)], f.text, buffer, 64, ctypes.byref(length))
        api['text'] = buffer.raw[:length.value].decode()
        for key, expected in oracle['api'].items():
            if key.endswith('iterationLive'):
                # Chromium's iterator is live; the ABI has none: values() and entries() are snapshots.
                differences[key] = {'native': None, 'chromium': expected}
                p.expect(record is not None or (key in qualified and qualified[key]['native'] is None), key + ' qualified')
                continue
            compare(key, api.get(key), expected)

        # Paint, step by step as the oracle.
        paint = {}
        state = {}
        cells = oracle['cells']

        def step(name):
            if name == 'red':
                state['rr'] = f.range(4, 11)
                state['red'] = x.highlight(f.document, state['rr'])
                x.set(reg, 'red', state['red'])
            elif name == 'redThenGreen':
                state['green'] = x.highlight(f.document, f.range(8, 15))
                x.set(reg, 'green', state['green'])
            elif name == 'redPriority1':
                x.priority(state['red'], 1)
            elif name == 'redPriority0':
                x.priority(state['red'], 0)
            elif name == 'redSetAgain':
                x.set(reg, 'red', state['red'])
            elif name == 'redReplaced':
                state['red2'] = x.highlight(f.document, state['rr'])
                x.set(reg, 'red', state['red2'])
            elif name == 'redDeletedAndSet':
                x.registry_delete(reg, 'red'); x.set(reg, 'red', state['red2'])
            elif name == 'greenDeleted':
                x.registry_delete(reg, 'green')
            elif name == 'liveRangeShrunk':
                p.call('rv_dom_range_set_end', [p.pointer, p.pointer, ctypes.c_uint32], state['rr'], f.text, 5)
            elif name == 'textInserted':
                p.call('rv_dom_character_data_insert_data', [p.pointer, ctypes.c_uint32, Utf8], f.text, 0, b'X ')
            elif name == 'staticAdded':
                x.add(state['red2'], f.static_range(x, 12, 13))
            elif name == 'rangeRemovedFromHighlight':
                p.expect(x.delete(state['red2'], state['rr']), 'delete the live range')
            elif name == 'unstyledOnly':
                x.set(reg, 'unstyled', x.highlight(f.document, state['rr'])); x.registry_delete(reg, 'red')
            elif name == 'cleared':
                x.ok(x.r_clear(reg), 'registry.clear')
            else:
                assert name == 'base', name

        for name in oracle['steps']:
            step(name)
            paint[name] = f.row(cells)
            compare('paint.' + name, letters(paint[name]), letters(oracle['paint'][name]))
            p.expect(all(tuple(c) in COLOURS for c in paint[name]), f'paint.{name}: every sampled cell is a fixture colour')
        p.call('rv_dom_character_data_get_data', [p.pointer, p.pointer, p.integer, ctypes.POINTER(p.integer)], f.text, buffer, 64, ctypes.byref(length))
        p.expect(buffer.raw[:length.value].decode() == oracle['textAfter'][0], 'highlights leave the text unchanged')

        # Errors.
        status = []
        result = ctypes.c_uint32()
        p.expect(x.h_size(None, ctypes.byref(result)) == NULL_ARGUMENT and x.h_size(h1, None) == NULL_ARGUMENT, 'NULL highlight or result')
        p.expect(x.r_set(reg, b'a', 1, None) == NULL_ARGUMENT, 'registry.set with a NULL highlight')
        p.expect(x.r_set(reg, None, 3, h1) == NULL_ARGUMENT, 'registry.set with a NULL key and a length')
        p.expect(x.h_add(h1, None) == NULL_ARGUMENT, 'Highlight.add with a NULL range')
        p.expect(x.create(f.document, None, ctypes.byref(p.pointer())) == NULL_ARGUMENT, 'new Highlight with NULL ranges')
        wrong = p.pointer()
        p.expect(x.registry_of(f.text, ctypes.byref(wrong)) == -11, 'CSS.highlights of a non-document node')
        worker = threading.Thread(target=lambda: status.append(x.h_size(h1, ctypes.byref(ctypes.c_uint32()))))
        worker.start(); worker.join()
        p.expect(status == [WRONG_THREAD], 'wrong thread')
        x.set(reg, '', h1)
        p.expect(x.keys(reg) == [''] and x.registry_has(reg, ''), 'the empty name is a key')
        nul = b'a\x00b'
        p.expect(x.r_set(reg, nul, 3, h1) == OK, 'a name with U+0000')
        entries = x.entries(reg)
        p.expect([k for k, _ in entries] == ['', 'a\x00b'], 'U+0000 survives the name round trip')
        x.ok(x.r_clear(reg), 'registry.clear')

        # Teardown 1: the document is replaced. The old registry and highlights stay readable; the new document has
        # its own empty registry; a highlight over the old document's ranges paints nothing in the new one.
        held = x.highlight(f.document, f.range(0, 3))
        x.set(reg, 'red', held)
        p.load(page(webkit_source), standalone=False)
        replaced = Fixture(p, webkit_source)
        fresh = x.registry(replaced.document)
        p.expect(fresh != reg and x.size(fresh, True) == 0, 'the new document has its own empty registry')
        # Document teardown clears the replaced document's registry and the ranges of each highlight registered in it,
        # which releases the old document's ranges.
        p.expect(x.keys(reg) == [] and x.size(held) == 0, 'the replaced document registry is cleared with its highlights')
        x.set(fresh, 'red', held)
        p.expect(letters(replaced.row(cells)) == letters(oracle['paint']['base']), 'ranges of the replaced document paint nothing')
        x.set(fresh, 'green', x.highlight(replaced.document, replaced.range(2, 3)))
        p.expect(letters(replaced.row(cells))[2] == 'Y', 'the new document paints its own highlight')
        # Teardown 2: rv_host_destroy tears the document down the same way. A highlight registered in its registry
        # loses its ranges; an unregistered highlight keeps its ranges, and every handle stays usable until released.
        x.add(held, replaced.range(0, 3))
        loose = x.highlight(replaced.document, replaced.range(4, 5), replaced.static_range(x, 6, 7))
        loose_ranges = x.values(loose)
        p.release_nodes()
        p.dispose_host()
        p.expect(x.size(held) == 0 and x.size(fresh, True) == 0 and x.size(reg, True) == 0, 'host destroy clears the registry and its highlights')
        p.expect(x.size(loose) == 2 and x.values(loose) == loose_ranges, 'an unregistered highlight keeps its ranges past host destroy')
        p.expect(x.delete(loose, loose_ranges[0]) and x.size(loose) == 1, 'Highlight.delete after host destroy')
        x.add(loose, loose_ranges[0])
        x.set(fresh, 'late', loose)
        p.expect(x.keys(fresh) == ['late'] and x.values(loose) == [loose_ranges[1], loose_ranges[0]], 'a registry held past host destroy')
        x.ok(x.r_clear(fresh), 'registry.clear after host destroy')
        p.release_all()
        p.collect()

    if record is not None:
        Path(record).write_text(json.dumps({'differences': differences}, indent=1) + '\n', encoding='utf-8')
    print(f'custom_highlights: {p.assertions} assertions, {len(differences)} qualified differences, {len(oracle["steps"])} paint steps')
    for key in sorted(differences):
        print(f'  {key}: native {json.dumps(differences[key]["native"])} chromium {json.dumps(differences[key]["chromium"])}')
    return p.assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--webkit-source', default='C:/wk/src')
    parser.add_argument('--abi', type=int, default=ABI, help='the expected ABI version of a later runtime')
    parser.add_argument('--record-differences', help='write every difference from Chromium instead of failing on unqualified ones')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.webkit_source, arguments.abi, arguments.record_differences)
