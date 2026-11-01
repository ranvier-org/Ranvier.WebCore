"""Writes a platform's qualified caret differences from a tests/abi/caret_hit.py --measure file: every difference is
classified into a named qualification, and an unclassified difference stops the script.

    make_qualified.py MEASURE NATIVE_LABEL [windows|darwin|linux]

windows writes tests/fixtures/caret-hit-qualified.json; darwin and linux write caret-hit-qualified.<system>.json and
admit that system's font-rasteriser qualifications."""
import json
from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[2]
REASONS = {
    'legacy-range-shadow-retarget': 'Document.caretRangeFromPoint (non-standard; CSSOM View defines only caretPositionFromPoint) '
        'retargets a hit inside a shadow tree or text control to the host element at offset 0 (WebKit Document::caretPositionFromPoint(LayoutPoint) '
        'retargetToScope). Chromium returns the host\'s parent at the host\'s index, as caretPositionFromPoint does in both engines.',
    'collapsed-line-end-rect': 'CaretPosition.getClientRect at a line end before a collapsed trailing space (wrap offsets 4 and 9, RTL offset 4): WebKit '
        'Range::boundingClientRect of the collapsed range gives 0x0 at (0, 0); Chromium gives the 0x20 caret box at the line end. Node and offset agree.',
    'text-control-rect': 'CaretPosition.getClientRect for a position in a text control (offsetNode INPUT, offset 1): WebKit measures the collapsed '
        'range (INPUT, 1), which has no layout box, and gives 0x0 at (0, 0); Chromium gives the 0x20 caret box inside the control.',
    'stale-offset-rect': 'A held CaretPosition whose text node was shortened below its offset (offset 7, data "AA"): WebKit clamps the offset and '
        'gives the 0x20 caret box at the text end (x 40, x 39 under FreeType); Chromium gives 0x0 at (0, 0).',
}
PLATFORM_REASONS = {
    'darwin': {
        'coretext-synthetic-bold': 'CoreText synthesises bold for the Ahem <b>BB</b> run in #inline and widens each advance by font size / 36 '
            '(WebCore FontCoreText.cpp syntheticBoldScaleFactor), so caret boxes after the run sit 1px right (x 81, 121, 161 for 80, 120, 160). '
            'Node and offset agree.',
    },
    'linux': {
        'freetype-advance-rect': 'FreeType scales each 20px Ahem advance in 16.16 fixed point, so glyph boundaries fall a fraction of a pixel '
            'short of the 20px grid and the snapped caret box sits 1px left (x 19, 39, 119 for 20, 40, 120). Node and offset agree.',
        'freetype-advance-hit': 'The same FreeType advance deficit moves glyph midpoints and boundaries a fraction of a pixel left: a point '
            'on a glyph midpoint (document x 10, 50 or 70) resolves to the following offset, and a point 1px before a run boundary (x 39, 119) resolves to '
            'the boundary position in the adjacent text node of the same line. Both are text positions on the same line as the Chromium position.',
    },
}
LINES = [{'wrap'}, {'inline', 'b', 'i'}, {'bidi', 'bdo'}, {'rtl'}, {'s'}, {'t'}, {'far'}]


def zero(rect):
    return rect is not None and all(rect[k] == 0 for k in ['x', 'y', 'width', 'height'])


def same_line(a, b):
    return a['kind'] == b['kind'] == 'text' and any(a['parent'] in line and b['parent'] in line for line in LINES)


def shifted(native, chromium, dx):
    return native is not None and chromium is not None and native['x'] == chromium['x'] + dx         and all(native[k] == chromium[k] for k in ['y', 'width', 'height']) and chromium['height'] == 20


def classify_platform(d, system):
    native, chromium = d['native'], d['chromium']
    if d['scroll'] == 'held':
        if system == 'linux' and shifted(native, chromium, -1):
            return 'freetype-advance-rect'
        return None
    if not native or not chromium or 'error' in native or 'error' in chromium:
        return None
    if system == 'darwin' and d['member'] in ('position', 'shadowRoots') and native['node'] == chromium['node']             and native['offset'] == chromium['offset'] and native['node'].get('parent') in ('i', 'inline') and shifted(native['rect'], chromium['rect'], 1):
        return 'coretext-synthetic-bold'
    if system == 'linux':
        if d['member'] in ('position', 'shadowRoots') and native['node'] == chromium['node'] and native['offset'] == chromium['offset']                 and shifted(native['rect'], chromium['rect'], -1):
            return 'freetype-advance-rect'
        if same_line(native['node'], chromium['node']) and (native['node'] != chromium['node'] or abs(native['offset'] - chromium['offset']) == 1):
            return 'freetype-advance-hit'
    return None


def classify(d, system='windows'):
    platform = classify_platform(d, system) if system != 'windows' else None
    if platform:
        return platform
    native, chromium = d['native'], d['chromium']
    if d['member'] == 'range' and native and chromium and native['offset'] == 0 and native['node']['kind'] == 'element' \
            and native['node']['id'] in ('host', 'closed', 'field') and chromium['node'].get('name') == 'BODY':
        return 'legacy-range-shadow-retarget'
    stale_x = 39.0 if system == 'linux' else 40.0
    if d['scroll'] == 'held' and d['point'] == 'shortened' and native == {'x': stale_x, 'y': 0.0, 'width': 0.0, 'height': 20.0} and zero(chromium):
        return 'stale-offset-rect'
    if d['member'] in ('position', 'shadowRoots') and native and chromium and native['node'] == chromium['node'] \
            and native['offset'] == chromium['offset'] and zero(native['rect']) and chromium['rect']['width'] == 0 and chromium['rect']['height'] == 20:
        if native['node'].get('name') == 'INPUT':
            return 'text-control-rect'
        if native['node']['kind'] == 'text' and native['offset'] in (4, 9):
            return 'collapsed-line-end-rect'
    raise SystemExit('unclassified difference: ' + json.dumps(d))


def main(measure, native_label, system='windows'):
    measured = json.loads(Path(measure).read_text(encoding='utf-8'))
    reasons = {**REASONS, **PLATFORM_REASONS.get(system, {})}
    differences = []
    for d in measured['differences']:
        differences.append({'qualification': classify(d, system), **d})
    counts = {name: sum(1 for d in differences if d['qualification'] == name) for name in reasons}
    result = {'description': 'Measured differences between the native engine and Chromium ' + measured['browser'] + ' for tests/fixtures/caret-hit-oracle.json. '
                             'tests/abi/caret_hit.py requires exactly these; any other difference fails.',
              'native': native_label, 'browser': measured['browser'], 'checked': measured['checked'],
              'qualifications': [{'name': name, 'count': counts[name], 'reason': reason} for name, reason in reasons.items() if counts[name]],
              'differences': differences}
    name = 'caret-hit-qualified.json' if system == 'windows' else f'caret-hit-qualified.{system}.json'
    (repo / 'tests/fixtures' / name).write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(measured['checked'], 'checks', counts)


if __name__ == '__main__':
    main(*sys.argv[1:4])
