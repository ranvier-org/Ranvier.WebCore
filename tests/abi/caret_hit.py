"""G09 caret hit-testing probe against an actual runtime directory. Replays the Chromium oracle
tests/fixtures/caret-hit-oracle.json through Document.caretPositionFromPoint (with and without
CaretPositionFromPointOptions.shadowRoots) and Document.caretRangeFromPoint at device scales 1, 1.5 and 2, unscrolled
and scrolled, then checks errors, a CaretPosition held past text changes, removal and rv_host_destroy, and a document
without a render tree. Each scroll is checked against the oracle case whose actual offset equals the runtime's.
Differences from Chromium must equal tests/fixtures/caret-hit-qualified.json exactly."""

import argparse
import ctypes
import json
import math
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from caret_hit_support import CaretPage, FIXTURES, coordinate, same_rect
from utf8_inputs import Utf8

OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, WRONG_INTERFACE = 0, -1, -2, -3, -11
ABI = 54
# FreeType scales each 20px Ahem advance in 16.16 fixed point on Linux; four glyphs may lose 4/65536 px.
RECT_TOLERANCE = 0.01


class ShadowRootSequence(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('count', ctypes.c_int32), ('items', ctypes.POINTER(ctypes.c_void_p))]


class CaretOptions(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('shadow_roots', ctypes.POINTER(ShadowRootSequence))]


def caret_options(roots, size=None):
    items = (ctypes.c_void_p * max(len(roots), 1))(*roots)
    sequence = ShadowRootSequence(present=1, count=len(roots), items=ctypes.cast(items, ctypes.POINTER(ctypes.c_void_p)))
    result = CaretOptions(size=ctypes.sizeof(CaretOptions) if size is None else size, shadow_roots=ctypes.pointer(sequence))
    result._keep = (items, sequence)
    return result


def long(value):
    value = coordinate(value)
    return 0 if not math.isfinite(value) else int(math.trunc(value))


class Caret:
    def __init__(self, p, fixture):
        P, I = p.pointer, p.integer
        self.p, self.fixture = p, fixture
        self.position = p.bind('rv_dom_document_caret_position_from_point', I, [P, ctypes.c_double, ctypes.c_double, ctypes.POINTER(CaretOptions), ctypes.POINTER(P)])
        self.range = p.bind('rv_dom_document_caret_range_from_point', I, [P, I, I, ctypes.POINTER(P)])
        self.offset = p.bind('rv_dom_caret_position_get_offset', I, [P, ctypes.POINTER(ctypes.c_uint32)])
        self.release = p.bind('rv_dom_caret_position_release', None, [P])
        self.last = p.bind('rv_last_exception', I, [I, P, I, ctypes.POINTER(I)])

    def exception(self):
        buffer, length = ctypes.create_string_buffer(256), self.p.integer()
        self.last(0, buffer, len(buffer), ctypes.byref(length))
        return buffer.value.decode()

    def read(self, handle):
        """The oracle's record of a CaretPosition: offsetNode described, offset and getClientRect."""
        p = self.p
        node = p.object('rv_dom_caret_position_get_offset_node', [p.pointer], [handle], 'node', nullable=True)
        offset = ctypes.c_uint32()
        p.expect(self.offset(handle, ctypes.byref(offset)) == OK, 'CaretPosition.offset')
        rect = p.object('rv_dom_caret_position_get_client_rect', [p.pointer], [handle], 'dom_rect_read_only', nullable=True)
        return {'node': self.fixture.describe(node), 'offset': offset.value, 'rect': self.fixture.rect(rect)}

    def hit(self, x, y, options=None):
        result = self.p.pointer()
        status = self.position(self.fixture.document, coordinate(x), coordinate(y), ctypes.byref(options) if options else None, ctypes.byref(result))
        if status == DOM_EXCEPTION:
            return {'error': self.exception()}
        self.p.expect(status == OK, 'caretPositionFromPoint status ' + str(status))
        if not result.value:
            return None
        self.p.retained.append(('rv_dom_caret_position_release', result.value))
        return self.read(result.value)

    def legacy(self, x, y):
        p, result = self.p, self.p.pointer()
        p.expect(self.range(self.fixture.document, long(x), long(y), ctypes.byref(result)) == OK, 'caretRangeFromPoint')
        if not result.value:
            return None
        p.retained.append(('rv_dom_abstract_range_release', result.value))
        container = p.object('rv_dom_abstract_range_get_start_container', [p.pointer], [result.value], 'node')
        return {'node': self.fixture.describe(container), 'offset': p.read('abstract_range', result.value, 'start_offset', p.unsigned)}


def release_since(p, keep):
    """Releases the handles retained after the first keep."""
    for release, target in reversed(p.retained[keep:]):
        p.bind(release, None, [p.pointer])(target)
    del p.retained[keep:]


def chromium_value(kind, value):
    if value is None or 'error' in value:
        return {'error': 'TypeError'} if value and kind != 'range' else value
    keys = ['node', 'offset'] + (['rect'] if kind != 'range' else [])
    return {k: value[k] for k in keys}


def matches(native, chromium):
    if native is None or chromium is None or 'error' in native or 'error' in chromium:
        return native == chromium
    return native['node'] == chromium['node'] and native['offset'] == chromium['offset'] and same_rect(native.get('rect'), chromium.get('rect'), RECT_TOLERANCE)


def replay(p, fixture, caret, oracle, scale, record):
    """Every oracle point, after every oracle scroll, compared with the case whose actual offset equals the runtime's."""
    roots = list(fixture.roots.values())
    both = caret_options([roots[0], roots[1]])
    checked, keep = 0, len(p.retained)
    for scroll_name, sx, sy in oracle['scrolls']:
        actual = fixture.scroll(sx, sy)
        case = next((c for c in oracle['cases'] if c['scale'] == scale and (c['scrollX'], c['scrollY']) == actual), None)
        p.expect(case is not None, f'an oracle case at scale {scale} scrolled to the runtime offset {actual}')
        for hit in case['hits']:
            native = {'position': caret.hit(hit['x'], hit['y']), 'shadowRoots': caret.hit(hit['x'], hit['y'], both), 'range': caret.legacy(hit['x'], hit['y'])}
            for kind in ['position', 'shadowRoots', 'range']:
                expected = chromium_value(kind, hit[kind])
                if not matches(native[kind], expected):
                    record.append({'scale': scale, 'scroll': scroll_name, 'oracleCase': case['scroll'], 'runtimeScroll': list(actual),
                                   'point': hit['name'], 'member': kind, 'native': native[kind], 'chromium': expected})
                checked += 1
            release_since(p, keep)
    return checked


def errors(p, fixture, caret, held):
    P, I = p.pointer, p.integer
    fixture.scroll(0, 0)
    result = P()
    for x, y in [(math.nan, 10), (10, math.inf), (-math.inf, 10)]:
        p.expect(caret.position(fixture.document, x, y, None, ctypes.byref(result)) == DOM_EXCEPTION and not result.value, 'non-finite coordinates throw')
        p.expect(caret.exception() == 'TypeError', 'non-finite coordinates throw TypeError')
    p.expect(caret.position(None, 5, 10, None, ctypes.byref(result)) == NULL_ARGUMENT, 'NULL document')
    p.expect(caret.position(fixture.document, 5, 10, None, None) == NULL_ARGUMENT, 'NULL result')
    element = p.node('wrap')
    p.expect(caret.position(element, 5, 10, None, ctypes.byref(result)) == WRONG_INTERFACE, 'an element is not a Document')
    # A ShadowRoot sequence holding an element is a handle of another interface.
    p.expect(caret.position(fixture.document, 25, 200, ctypes.byref(caret_options([element])), ctypes.byref(result)) == WRONG_INTERFACE, 'shadowRoots holds an element')
    # A struct whose size ends before shadow_roots takes the IDL default [], so the hit retargets to the host's parent.
    short = caret.hit(25, 200, caret_options(list(fixture.roots.values()), size=4))
    p.expect(short is not None and short['node']['name'] == 'BODY', 'options size before shadow_roots takes the default ' + str(short))
    listed = caret.hit(25, 200, caret_options([fixture.roots['open']]))
    p.expect(listed['node'] == {'kind': 'text', 'parent': 's', 'index': 0, 'scope': 'open'}, 'a listed open root yields its text')
    unlisted = caret.hit(225, 200, caret_options([fixture.roots['open']]))
    p.expect(unlisted['node']['name'] == 'BODY', 'an unlisted closed root retargets to the host parent')
    for member, call in [('offset', lambda h: caret.offset(h, ctypes.byref(ctypes.c_uint32()))),
                         ('offsetNode', lambda h: p.bind('rv_dom_caret_position_get_offset_node', I, [P, ctypes.POINTER(P)])(h, ctypes.byref(P()))),
                         ('getClientRect', lambda h: p.bind('rv_dom_caret_position_get_client_rect', I, [P, ctypes.POINTER(P)])(h, ctypes.byref(P())))]:
        p.expect(call(None) == NULL_ARGUMENT, member + ' NULL target')
    p.expect(caret.offset(held, None) == NULL_ARGUMENT, 'offset NULL result')
    statuses = []

    def off_thread():
        statuses.append((caret.position(fixture.document, 5, 10, None, ctypes.byref(P())), caret.offset(held, ctypes.byref(ctypes.c_uint32()))))
    worker = threading.Thread(target=off_thread)
    worker.start()
    worker.join()
    p.expect(statuses == [(WRONG_THREAD, WRONG_THREAD)], 'wrong thread ' + str(statuses))


def lifetime(p, fixture, caret, oracle, scale, record):
    """A CaretPosition keeps its node and offset past a text change and removal; its rectangle follows layout."""
    fixture.scroll(0, 0)
    expected = next(item for item in oracle['lifetime'] if item['scale'] == scale)
    result = p.pointer()
    p.expect(caret.position(fixture.document, 45, 30, None, ctypes.byref(result)) == OK and result.value, 'held caret')
    held = result.value
    text = p.object('rv_dom_node_get_first_child', [p.pointer], [p.node('wrap')], 'node')
    data = lambda: p.text('rv_dom_character_data_get_data', [p.pointer], text)

    def read():
        value = caret.read(held)
        connected = p.integer()
        p.call('rv_dom_node_get_is_connected', [p.pointer, ctypes.POINTER(p.integer)], text, ctypes.byref(connected))
        p.expect(fixture.is_same(p.object('rv_dom_caret_position_get_offset_node', [p.pointer], [held], 'node'), text), 'offsetNode is the held text node')
        return {'offset': value['offset'], 'connected': bool(connected.value), 'data': data(), 'rect': value['rect']}
    states = {'before': read()}
    p.call('rv_dom_character_data_set_data', [p.pointer, Utf8], text, b'AA')
    fixture.settle()
    states['shortened'] = read()
    p.call('rv_dom_element_remove', [p.pointer], p.node('wrap'))
    fixture.settle()
    states['removed'] = read()
    for name in ['before', 'shortened', 'removed']:
        native, chromium = states[name], expected[name]
        p.expect({k: native[k] for k in ['offset', 'connected', 'data']} == {k: chromium[k] for k in ['offset', 'connected', 'data']}, 'held caret ' + name + ' ' + str(native))
        if not same_rect(native['rect'], chromium['rect'], RECT_TOLERANCE):
            record.append({'scale': scale, 'scroll': 'held', 'point': name, 'member': 'getClientRect', 'native': native['rect'], 'chromium': chromium['rect']})
    # A document without a render tree yields no position, as Chromium's createHTMLDocument document does.
    implementation = p.object('rv_dom_document_get_implementation', [p.pointer], [fixture.document], 'dom_implementation')
    detached = p.object('rv_dom_dom_implementation_create_html_document', [p.pointer, Utf8], [implementation, b''], 'node')
    inert = p.pointer()
    p.expect(caret.position(detached, 5, 10, None, ctypes.byref(inert)) == OK and not inert.value and expected['detachedDocument'] is None, 'document without a render tree')
    caret.release(None)
    return held


def rounded(value):
    """The value with every number rounded to RECT_TOLERANCE, so a qualified rectangle survives FreeType quantisation."""
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, float):
        return round(value, 2)
    return value


def run(native_directory, webkit_source, measure=None):
    oracle = json.loads((FIXTURES / 'caret-hit-oracle.json').read_text())
    qualified = json.loads((FIXTURES / 'caret-hit-qualified.json').read_text()) if measure is None else {'differences': []}
    differences, checked, assertions = [], 0, 0
    for scale in oracle['scales']:
        with SvgProbe(native_directory, 320, 240) as p:
            P, I = p.pointer, p.integer
            p.expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version')
            p.expect(p.bind('rv_abi_has', I, [ctypes.c_char_p])(b'dom:CaretPosition') == 1, 'dom:CaretPosition feature')
            fixture = CaretPage(p, webkit_source, scale)
            caret = Caret(p, fixture)
            checked += replay(p, fixture, caret, oracle, scale, differences)
            first = P()
            p.expect(caret.position(fixture.document, 5, 10, None, ctypes.byref(first)) == OK and first.value, 'caret for error checks')
            p.retained.append(('rv_dom_caret_position_release', first.value))
            errors(p, fixture, caret, first.value)
            held = lifetime(p, fixture, caret, oracle, scale, differences)
            # Held past rv_host_destroy: the caret keeps its node; reading it stays defined and releasing it is safe.
            p.release_nodes()
            p.dispose_host()
            p.collect()
            offset = ctypes.c_uint32()
            p.expect(caret.offset(held, ctypes.byref(offset)) == OK and offset.value == 7, 'caret offset after host destroy')
            caret.release(held)
            p.collect()
            assertions += p.assertions
    if measure:
        Path(measure).write_text(json.dumps({'abi': ABI, 'browser': oracle['browser'], 'checked': checked, 'differences': differences}, indent=1) + '\n', encoding='utf-8')
        print('caret hit measurement:', checked, 'checks,', len(differences), 'differences ->', measure)
        return
    key = lambda d: json.dumps([d['scale'], d['scroll'], d['point'], d['member'], rounded(d['native'])], sort_keys=True)
    expected = sorted(key(d) for d in qualified['differences'])
    actual = sorted(key(d) for d in differences)
    if expected != actual:
        extra = [a for a in actual if a not in expected]
        missing = [e for e in expected if e not in actual]
        raise AssertionError('caret differences changed: unqualified ' + json.dumps(extra[:8]) + ' missing ' + json.dumps(missing[:8]))
    print(f'caret hit testing PASS: {checked} oracle checks, {len(differences)} qualified differences, {assertions} assertions', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--webkit-source', required=True)
    parser.add_argument('--measure')
    args = parser.parse_args()
    run(args.native_directory, args.webkit_source, args.measure)
