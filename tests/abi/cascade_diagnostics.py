"""C25 cascade diagnostics probe against an actual runtime directory. Loads tests/fixtures/cascade-diagnostics.html and
replays every case of the shared conformance fixture tests/fixtures/cascade-diagnostics.json through
rv_host_inspect_cascade: the declarations of the property in cascade order with origin, importance, layer, position,
shorthand, conditions and depth, and the winner the engine's cascade selects. The winner's value agrees with the
native computed value, and the Chromium oracle tests/fixtures/cascade-diagnostics-oracle.json agrees with the
fixture's computed value in every case. Then checks that queries change no computed value or layout and start no
style update, that a pending class change is read as the DOM holds it, that positions are stable, the opt-in, errors,
threads, and snapshots held past rv_host_destroy. --repeat runs the whole probe that many times in one process."""

import argparse
import ctypes
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe

OK, NULL_ARGUMENT, WRONG_THREAD, NOT_ELEMENT, BUFFER_TOO_SMALL, UNSUPPORTED = 0, -1, -2, -4, -6, -9
ABI = 54
FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
MATCHED_RULES, CASCADE = 2, 3
ORIGINS = {'user-agent': 0, 'user': 1, 'author': 2, 'inline': 3, 'presentational-hint': 4}
(ORIGIN, SPEC_A, SPEC_B, SPEC_C, IMPORTANT, LAYER_ORDER, WINNER, DEPTH, SHEET, RULE, DECLARATION, VARIABLE,
 NUMBER_FIELDS) = range(13)
SELECTOR_TEXT, MATCHED_SELECTOR, PROPERTY, VALUE, SHORTHAND, LAYER, CONDITIONS, STRING_FIELDS = range(8)
NUMBER_NAMES = ['origin', 'a', 'b', 'c', 'important', 'layerOrder', 'winner', 'depth', 'sheet', 'rule', 'declaration', 'variable']
STRING_NAMES = ['selector', 'matchedSelector', 'property', 'value', 'shorthand', 'layer', 'conditions']


def number_of(text):
    """The leading number of a computed value, or None."""
    digits = ''
    for character in text.strip():
        if character.isdigit() or character in '.-' and not digits.count(character):
            digits += character
        else:
            break
    try:
        return float(digits)
    except ValueError:
        return None


def matches(expected, actual):
    return number_of(actual) == expected if isinstance(expected, (int, float)) else actual.strip() == expected


class Cascade:
    def __init__(self, p):
        P, I, D = p.pointer, p.integer, p.double
        self.p = p
        self.has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        self.enable = p.bind('rv_host_set_diagnostics', I, [P, I])
        self.inspect = p.bind('rv_host_inspect_cascade', I, [P, P, ctypes.c_char_p, I, ctypes.POINTER(P)])
        self.matched_rules = p.bind('rv_host_inspect_matched_rules', I, [P, P, ctypes.POINTER(P)])
        self.kind = p.bind('rv_diagnostic_kind', I, [P])
        self.text_of = p.bind('rv_diagnostic_text', I, [P, ctypes.c_char_p, I, ctypes.POINTER(I)])
        self.count = p.bind('rv_diagnostic_count', I, [P])
        self.entry_string = p.bind('rv_diagnostic_entry_string', I, [P, I, I, ctypes.c_char_p, I, ctypes.POINTER(I)])
        self.entry_number = p.bind('rv_diagnostic_entry_number', I, [P, I, I, ctypes.POINTER(D)])
        self.release = p.bind('rv_diagnostic_release', None, [P])
        self.live = p.bind('rv_diagnostic_live_count', I, [])
        self.fact_of = p.bind('rv_host_capability_fact', I, [P, I, ctypes.c_char_p, I, ctypes.POINTER(I)])
        self.computed_style = p.bind('rv_element_computed_style', I, [P, ctypes.c_char_p, ctypes.c_char_p, I, ctypes.POINTER(I)])
        self.rect = p.bind('rv_element_rect', I, [P] + [ctypes.POINTER(D)] * 4)
        self.held = []

    def query(self, host, element, name):
        result = self.p.pointer()
        encoded = name.encode('utf-8')
        status = self.inspect(host, element, encoded, len(encoded), ctypes.byref(result))
        self.p.expect(status == OK and bool(result.value), 'rv_host_inspect_cascade ' + name + ': status ' + str(status))
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

    def entries(self, diagnostic):
        rows = []
        for i in range(self.count(diagnostic)):
            row = {name: int(self.number(diagnostic, i, field)) for field, name in enumerate(NUMBER_NAMES)}
            row.update({name: self.string(diagnostic, i, field) for field, name in enumerate(STRING_NAMES)})
            rows.append(row)
        return rows

    def style(self, element, name):
        buffer, length = ctypes.create_string_buffer(512), self.p.integer()
        self.p.expect(self.computed_style(element, name.encode(), buffer, len(buffer), ctypes.byref(length)) == OK, 'computed ' + name)
        return buffer.raw[:length.value].decode('utf-8')

    def box(self, element):
        values = [ctypes.c_double() for _ in range(4)]
        self.p.expect(self.rect(element, *[ctypes.byref(v) for v in values]) == OK, 'element rect')
        return tuple(v.value for v in values)

    def fact(self, host, name, dimension):
        value = self.p.integer(42)
        self.p.expect(self.fact_of(host, 4, name.encode(), dimension, ctypes.byref(value)) == OK, 'capability fact ' + name)
        return value.value


def wait_for_import(c, host, element):
    """Cycles until the data: URL import applies to #imported; a hang guard, counting no assertions."""
    cycle = c.p.bind('rv_run_loop_cycle', c.p.integer, [c.p.integer])
    update = c.p.bind('rv_host_update', c.p.integer, [c.p.pointer])
    deadline = time.monotonic() + 10
    while True:
        result = c.p.pointer()
        if c.inspect(host, element, b'order', 5, ctypes.byref(result)) == OK:
            count = c.count(result.value)
            c.release(result.value)
            if count == 2:
                return
        if time.monotonic() > deadline:
            raise AssertionError('the data: URL import did not apply')
        cycle(10)
        update(host)


def resolve(p, path):
    """The element of an id path: a document id, then ids in the open shadow root of each element before."""
    identifiers = path.split('/')
    element = p.node(identifiers[0])
    for identifier in identifiers[1:]:
        root = p.bind('rv_element_shadow_root', p.pointer, [p.pointer])(element)
        p.expect(bool(root), 'open shadow root of ' + path)
        p.retained.append(('rv_node_release', root))
        element = p.object('rv_dom_document_fragment_get_element_by_id', [p.pointer, ctypes.c_char_p, p.integer],
                           [root, identifier.encode(), len(identifier)], 'node')
    return element


def check_case(c, case, rows, layer_order):
    """Asserts a case's entries against the fixture; returns its winners."""
    p, name = c.p, case['name']
    ua = [r for r in rows if r['origin'] == ORIGINS['user-agent']]
    rest = rows[len(ua):]
    p.expect(all(r['origin'] != ORIGINS['user-agent'] for r in rest), name + ': user-agent entries lead')
    expectation = case.get('userAgent')
    if expectation is None:
        p.expect(not ua, name + ': no user-agent entries: ' + str(ua))
    else:
        p.expect(len(ua) >= 1, name + ': user-agent entries present')
        p.expect(any(r['winner'] for r in ua) == expectation['winner'], name + ': user-agent winner ' + str(expectation['winner']))
        for row in ua:
            p.expect(row['property'] in expectation.get('properties', [case['property']]), name + ': user-agent property ' + row['property'])
            p.expect(row['layerOrder'] == -1 and row['layer'] == '' and row['sheet'] == -1 and row['rule'] == -1, name + ': user-agent position')
        for row in (r for r in ua if r['winner']):
            if 'important' in expectation:
                p.expect(row['important'] == int(expectation['important']), name + ': user-agent importance')
            if 'value' in expectation:
                p.expect(row['value'] == expectation['value'], name + ': user-agent value ' + row['value'])
    contributors = case['contributors']
    p.expect(len(rest) == len(contributors), name + ': entry count ' + str(len(rest)) + ' ' + str(rest))
    for row, want in zip(rest, contributors):
        label = name + ' ' + want['value']
        origin = want.get('origin', 'author')
        p.expect(row['origin'] == ORIGINS[origin], label + ': origin ' + str(row['origin']))
        p.expect(row['value'] == want['value'], label + ': value ' + row['value'])
        p.expect(row['property'] == want.get('declared', case['property']), label + ': declared property ' + row['property'])
        p.expect(row['important'] == int(want.get('important', False)), label + ': importance')
        p.expect(row['winner'] == int(want.get('winner', False)), label + ': winner flag')
        p.expect(row['depth'] == want.get('depth', 0), label + ': depth')
        p.expect(row['shorthand'] == want.get('shorthand', ''), label + ': shorthand ' + row['shorthand'])
        p.expect(row['variable'] == int(want.get('variable', False)), label + ': var() flag')
        layer = want.get('layer')
        p.expect(row['layer'] == (layer or ''), label + ': layer name ' + repr(row['layer']))
        order = want.get('layerOrder', -1 if layer is None else layer_order.get(layer))
        p.expect(row['layerOrder'] == order, label + ': layer order ' + str(row['layerOrder']))
        if origin == 'author':
            p.expect((row['sheet'], row['rule']) == (want.get('sheet', 1), want['rule']), label + ': position ' + str((row['sheet'], row['rule'])))
            p.expect((row['a'], row['b'], row['c']) == tuple(want['specificity']), label + ': specificity')
            p.expect(row['selector'] != '' and row['matchedSelector'] != '', label + ': selector text')
            if 'selector' in want:
                p.expect(row['matchedSelector'] == want['selector'], label + ': matched selector ' + row['matchedSelector'])
        else:
            p.expect((row['sheet'], row['rule'], row['a'], row['b'], row['c'], row['selector'], row['matchedSelector']) == (-1, -1, 0, 0, 0, '', ''),
                     label + ': no rule position or selector')
        if 'declaration' in want:
            p.expect(row['declaration'] == want['declaration'], label + ': declaration index ' + str(row['declaration']))
        lines = [line for line in row['conditions'].split('\n') if line]
        keywords = want.get('conditions', [])
        p.expect(len(lines) == len(keywords) and all(line.startswith(k + ' ') for line, k in zip(lines, keywords)), label + ': conditions ' + repr(row['conditions']))
    # At most one winner per level, levels ordered from the element outwards.
    depths = sorted({r['depth'] for r in rows})
    p.expect(all(sum(r['winner'] for r in rows if r['depth'] == d) <= 1 for d in depths), name + ': at most one winner per level')
    p.expect([r['depth'] for r in rows] == sorted(r['depth'] for r in rows), name + ': levels in order from the element')
    return [r for r in rows if r['winner']]


def run_once(native_directory, fixture, oracle):
    with SvgProbe(native_directory, 320, 240) as p:
        P, I = p.pointer, p.integer
        c = Cascade(p)
        baseline = c.live()
        try:
            p.expect(p.bind('rv_abi_version', I, [])() == ABI, f'ABI version {ABI}')
            p.expect(c.has(b'cascade-diagnostics') == 1 and c.has(b'diagnostics') == 1, 'rv_abi_has("cascade-diagnostics")')
            p.load((FIXTURES / 'cascade-diagnostics.html').read_text(encoding='utf-8'), standalone=False)
            p.update()
            elements = {case['element']: None for case in fixture['cases']}
            for identifier in list(elements) + ['pend', 'probe']:
                elements[identifier] = resolve(p, identifier)
            text_node = p.object('rv_dom_node_get_first_child', [P], [elements['vt']], 'node')
            set_attribute = p.bind('rv_element_set_attribute', I, [P, ctypes.c_char_p, ctypes.c_char_p])

            # Capability facts and the opt-in.
            p.expect(c.fact(p.host, 'cascade-diagnostics', 1) == 1 and c.fact(p.host, 'cascade-diagnostics', 2) == 0, 'implemented, not enabled')
            result = P(42)
            p.expect(c.inspect(p.host, text_node, b'order', 5, ctypes.byref(result)) == UNSUPPORTED and result.value == 42,
                     'disabled host answers before reading the node')
            p.expect(c.inspect(p.host, elements['spec'], b'order', 5, ctypes.byref(result)) == UNSUPPORTED and result.value == 42, 'disabled host')
            p.expect(c.enable(p.host, 1) == OK and c.fact(p.host, 'cascade-diagnostics', 2) == 1 and c.fact(p.host, 'diagnostics', 2) == 1,
                     'cascade diagnostics enabled with diagnostics')
            wait_for_import(c, p.host, elements['imported'])
            p.update()

            # Computed values and layout before any further query.
            def observed():
                return [(c.style(elements[case['element']], case['property']), c.box(elements[case['element']])) for case in fixture['cases']]

            before = observed()

            # Every conformance case.
            first = {}
            for case in fixture['cases']:
                snapshot = c.query(p.host, elements[case['element']], case['property'])
                p.expect(c.kind(snapshot) == CASCADE and c.text(snapshot) == case['property'], case['name'] + ': kind and canonical name')
                rows = c.entries(snapshot)
                first[case['name']] = rows
                winners = check_case(c, case, rows, fixture['layerOrder'])
                native = c.style(elements[case['element']], case['property'])
                p.expect(matches(case['computed'], native), case['name'] + ': native computed ' + repr(native))
                if winners:
                    effective = max(winners, key=lambda r: r['depth'])
                    # User-agent values are engine-specific, and inherit, unset and var() resolve elsewhere.
                    if effective['origin'] != ORIGINS['user-agent'] and effective['value'] not in ('inherit', 'unset') and not effective['variable']:
                        p.expect(matches(case['computed'], effective['value']), case['name'] + ': winner value equals the computed value')
            # The Chromium oracle agrees with the fixture.
            by_name = {entry['name']: entry for entry in oracle['cases']}
            for case in fixture['cases']:
                entry = by_name[case['name']]
                p.expect(entry['matchesFixture'] and matches(case['computed'], entry['computed']) and entry['property'] == case['property'],
                         case['name'] + ': Chromium computed ' + repr(entry['computed']))

            # Queries change no computed value or layout, and positions are stable.
            p.expect(observed() == before, 'computed values and layout unchanged across the queries')
            again = {case['name']: c.entries(c.query(p.host, elements[case['element']], case['property'])) for case in fixture['cases']}
            p.expect(again == first, 'a second query reports the same entries')
            extra = p.bind('rv_document_create_element', P, [P, ctypes.c_char_p])(p.host, b'section')
            p.retained.append(('rv_node_release', extra))
            body = p.bind('rv_document_body', P, [P])(p.host)
            p.retained.append(('rv_node_release', body))
            p.expect(p.bind('rv_node_append_child', I, [P, P])(body, extra) == OK, 'unrelated insertion')
            p.expect(set_attribute(elements['plain'], b'data-unrelated', b'1') == OK, 'unrelated attribute')
            p.update()
            mutated = {case['name']: c.entries(c.query(p.host, elements[case['element']], case['property'])) for case in fixture['cases']}
            p.expect(mutated == first, 'entries and positions unchanged after an unrelated DOM mutation')

            # A pending class change is read as the DOM holds it, and the query starts no style update: a change
            # reverted before the next update leaves no transition, while a computed-style read in between starts one
            # whose jump-start step leaves the reverted value to transition back from.
            pend, probe = elements['pend'], elements['probe']
            p.expect(set_attribute(pend, b'class', b'pb') == OK, 'pending class change')
            pending = c.entries(c.query(p.host, pend, 'opacity'))
            p.expect([(r['value'], r['winner']) for r in pending] == [('1', 0), ('0', 1)], 'pending change read from the DOM: ' + str(pending))
            p.expect(set_attribute(pend, b'class', b'') == OK, 'class change reverted')
            p.update()
            settled = c.entries(c.query(p.host, pend, 'opacity'))
            p.expect([(r['value'], r['winner']) for r in settled] == [('1', 1)], 'reverted change')
            p.expect(set_attribute(pend, b'class', b'pb') == OK and c.entries(c.query(p.host, pend, 'opacity')) == pending, 'pending again')
            p.update()
            p.expect(c.entries(c.query(p.host, pend, 'opacity')) == pending, 'the pending query equals the query after the update')
            animations = p.bind('rv_element_animations', I, [P, I, ctypes.POINTER(P), I, ctypes.POINTER(I)])

            def transitions(element):
                count = I(-1)
                p.expect(animations(element, 0, None, 0, ctypes.byref(count)) in (OK, BUFFER_TOO_SMALL), 'animation count')
                return count.value

            p.expect(transitions(probe) == 0, 'no transition before the probe')
            p.expect(set_attribute(probe, b'class', b'pb') == OK, 'probe class change')
            c.query(p.host, probe, 'opacity')
            p.expect(set_attribute(probe, b'class', b'') == OK, 'probe class reverted')
            p.update()
            p.expect(transitions(probe) == 0, 'a cascade query starts no style update')
            p.expect(set_attribute(probe, b'class', b'pb') == OK, 'control class change')
            c.style(probe, 'opacity')
            p.expect(set_attribute(probe, b'class', b'') == OK, 'control class reverted')
            p.update()
            p.expect(transitions(probe) >= 1, 'control: a computed-style read updates style and starts a transition')

            # A pending style sheet insertion applies to the query; the element's style waits for the next update.
            sheet = p.bind('rv_document_create_element', P, [P, ctypes.c_char_p])(p.host, b'style')
            p.retained.append(('rv_node_release', sheet))
            p.expect(p.bind('rv_node_set_text_content', I, [P, ctypes.c_char_p])(sheet, b"#plain{order:90}@property --late{syntax:'<integer>';inherits:false;initial-value:0}#rn{--late:7}") == OK,
                     'inserted sheet text')
            head = p.bind('rv_document_head', P, [P])(p.host)
            p.retained.append(('rv_node_release', head))
            p.expect(p.bind('rv_node_append_child', I, [P, P])(head, sheet) == OK, 'pending sheet insertion')
            inserted = c.entries(c.query(p.host, elements['plain'], 'order'))
            p.expect([(r['value'], r['winner'], r['sheet'], r['rule']) for r in inserted] == [('90', 1, 2, 0)], 'inserted sheet: ' + str(inserted))
            late = c.entries(c.query(p.host, elements['rnkid'], '--late'))
            p.expect(late == [], 'a pending @property registration applies to the query: ' + str(late))
            p.update()
            p.expect(c.entries(c.query(p.host, elements['plain'], 'order')) == inserted and matches(90, c.style(elements['plain'], 'order')),
                     'the inserted sheet after the update')

            # Errors and fields.
            spec = elements['spec']
            for name, status in [(b'margin', UNSUPPORTED), (b'not-a-property', UNSUPPORTED), (b'', UNSUPPORTED), (b'\xff\xfe', UNSUPPORTED)]:
                p.expect(c.inspect(p.host, spec, name, len(name), ctypes.byref(result)) == status and result.value == 42, repr(name) + ' rejected')
            p.expect(c.inspect(p.host, spec, b'order', -1, ctypes.byref(result)) == UNSUPPORTED and result.value == 42, 'negative length')
            p.expect(c.inspect(p.host, spec, None, -1, ctypes.byref(result)) == NULL_ARGUMENT and result.value == 42, 'NULL property')
            p.expect(c.inspect(p.host, spec, b'orderly', 5, ctypes.byref(result)) == OK and c.text(result.value) == 'order', 'explicit length')
            c.release(result.value)
            result = P(42)
            p.expect(c.inspect(p.host, text_node, b'order', 5, ctypes.byref(result)) == NOT_ELEMENT and result.value == 42, 'text node')
            detached = p.bind('rv_document_create_element', P, [P, ctypes.c_char_p])(p.host, b'div')
            p.retained.append(('rv_node_release', detached))
            p.expect(c.inspect(p.host, detached, b'order', 5, ctypes.byref(result)) == UNSUPPORTED and result.value == 42, 'detached element')
            p.expect(c.inspect(p.host, spec, b'order', 5, None) == NULL_ARGUMENT and c.inspect(p.host, None, b'order', 5, ctypes.byref(result)) == NULL_ARGUMENT,
                     'null element or output')
            sample = c.query(p.host, spec, 'order')
            count = c.count(sample)
            number, buffer, length = ctypes.c_double(9.5), ctypes.create_string_buffer(4), I(-5)
            for index, field in [(count, ORIGIN), (-1, ORIGIN), (0, NUMBER_FIELDS), (0, -1)]:
                p.expect(c.entry_number(sample, index, field, ctypes.byref(number)) == UNSUPPORTED and number.value == 9.5, 'number out of range')
            p.expect(c.entry_number(sample, 0, VARIABLE, ctypes.byref(number)) == OK and number.value == 0, 'last number field')
            for index, field in [(count, SELECTOR_TEXT), (0, STRING_FIELDS)]:
                p.expect(c.entry_string(sample, index, field, buffer, 4, ctypes.byref(length)) == UNSUPPORTED, 'string out of range')
            p.expect(c.entry_string(sample, 0, PROPERTY, buffer, 2, ctypes.byref(length)) == BUFFER_TOO_SMALL and length.value == 5, 'short buffer')
            rules = P()
            p.expect(c.matched_rules(p.host, spec, ctypes.byref(rules)) == OK, 'matched rules')
            c.held.append(rules.value)
            p.expect(c.entry_number(rules.value, 0, 6, ctypes.byref(number)) == UNSUPPORTED and c.entry_string(rules.value, 0, 3, buffer, 4, ctypes.byref(length)) == UNSUPPORTED,
                     'matched-rules fields unchanged')

            # Threads: host calls stay on the owning thread; snapshots read on any thread.
            statuses = []

            def worker():
                out = P(42)
                statuses.append((c.inspect(p.host, spec, b'order', 5, ctypes.byref(out)), out.value))
                statuses.append((c.kind(sample), c.count(sample)))

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()
            p.expect(statuses == [(WRONG_THREAD, 42), (CASCADE, count)], 'thread rules: ' + str(statuses))

            # Disabling keeps snapshots readable.
            sample_rows = c.entries(sample)
            p.expect(c.enable(p.host, 0) == OK and c.fact(p.host, 'cascade-diagnostics', 2) == 0, 'disabled')
            p.expect(c.entries(sample) == sample_rows, 'snapshot readable after disabling')
            p.expect(c.inspect(p.host, spec, b'order', 5, ctypes.byref(result)) == UNSUPPORTED and result.value == 42, 'disabled again')
            live = c.live()
            p.expect(live - baseline == len(c.held), 'live count tracks snapshots')
            c.drop(rules.value)
            p.expect(c.live() == live - 1, 'release frees one snapshot')
            held = len(c.held)
        except BaseException:
            c.release_all()
            raise
        # Snapshots outlive the host.
        p.release_all()
        expired = p.host
        p.dispose_host()
        p.expect(c.entries(sample) == sample_rows and c.text(sample) == 'order', 'snapshot readable after rv_host_destroy')
        result = P(42)
        p.expect(c.inspect(expired, None, b'order', 5, ctypes.byref(result)) == NULL_ARGUMENT, 'destroyed host, null element')
        c.release_all()
        p.expect(c.live() == baseline, 'every snapshot released')
        return p.assertions, len(fixture['cases']), held


def run(native_directory, repeat):
    fixture = json.loads((FIXTURES / 'cascade-diagnostics.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'cascade-diagnostics-oracle.json').read_text(encoding='utf-8'))
    totals = set()
    for _ in range(repeat):
        totals.add(run_once(native_directory, fixture, oracle))
    if len(totals) != 1:
        raise AssertionError('assertion counts vary across repeats: ' + str(totals))
    assertions, cases, held = totals.pop()
    print(f'cascade diagnostics PASS: {assertions} assertions, {cases} conformance cases with Chromium computed values, '
          f'{held} snapshots held past destroy, {repeat} run(s)', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--repeat', type=int, default=1)
    args = parser.parse_args()
    run(args.native_directory, args.repeat)
