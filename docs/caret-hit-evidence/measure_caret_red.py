"""G09 RED measurement: replays tests/fixtures/caret-hit-oracle.json on a runtime through the exports that exist
today (Document.caretRangeFromPoint, WebIDL long coordinates), records which caretPositionFromPoint/CaretPosition
exports are absent, and writes the native values beside Chromium's."""
import ctypes
import json
import math
from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / 'tests/abi'))
from svg_paint_probe import SvgProbe
from caret_hit_support import CaretPage, coordinate

REQUIRED = ['rv_dom_document_caret_position_from_point', 'rv_dom_caret_position_get_offset_node', 'rv_dom_caret_position_get_offset',
            'rv_dom_caret_position_get_client_rect', 'rv_dom_caret_position_release']


def long(value):
    value = coordinate(value)
    return 0 if not math.isfinite(value) else int(math.trunc(value))


def measure(native_directory, webkit_source, out):
    oracle = json.loads((repo / 'tests/fixtures/caret-hit-oracle.json').read_text())
    result = {'runtime': str(native_directory), 'cases': [], 'missing': [], 'chromium': oracle['browser']}
    for scale in oracle['scales']:
        with SvgProbe(native_directory, 320, 240) as p:
            P, I = p.pointer, p.integer
            result['abiVersion'] = p.bind('rv_abi_version', I, [])()
            result['missing'] = [name for name in REQUIRED if not hasattr(p.library, name)]
            fixture = CaretPage(p, webkit_source, scale)
            for case in [c for c in oracle['cases'] if c['scale'] == scale]:
                sx, sy = next((x, y) for name, x, y in oracle['scrolls'] if name == case['scroll'])
                scrolled = fixture.scroll(sx, sy)
                record = {'scale': scale, 'scroll': case['scroll'], 'nativeScroll': scrolled, 'chromiumScroll': [case['scrollX'], case['scrollY']], 'hits': []}
                for hit in case['hits']:
                    status = None
                    range_ = P()
                    status = p.bind('rv_dom_document_caret_range_from_point', I, [P, I, I, ctypes.POINTER(P)])(fixture.document, long(hit['x']), long(hit['y']), ctypes.byref(range_))
                    native = None
                    if status == 0 and range_.value:
                        p.retained.append(('rv_dom_abstract_range_release', range_.value))
                        container = p.object('rv_dom_abstract_range_get_start_container', [P], [range_.value], 'node')
                        native = {'node': fixture.describe(container), 'offset': p.read('abstract_range', range_.value, 'start_offset', p.unsigned)}
                    elif status != 0:
                        native = {'status': status}
                    record['hits'].append({'name': hit['name'], 'nativeRange': native, 'chromiumRange': hit['range'], 'chromiumPosition': hit['position'],
                                           'rangeMatches': native == ({k: hit['range'][k] for k in ['node', 'offset']} if hit['range'] and 'node' in hit['range'] else hit['range'])})
                result['cases'].append(record)
    Path(out).write_text(json.dumps(result, indent=2) + '\n')
    for case in result['cases']:
        print(case['scale'], case['scroll'], 'native scroll', case['nativeScroll'], 'chromium', case['chromiumScroll'],
              'range matches', sum(h['rangeMatches'] for h in case['hits']), '/', len(case['hits']))
        for h in case['hits']:
            if not h['rangeMatches']:
                print('   <>', h['name'], h['nativeRange'], h['chromiumRange'])
    print('missing', result['missing'], 'abi', result['abiVersion'])


if __name__ == '__main__':
    measure(sys.argv[1], sys.argv[2], sys.argv[3])
