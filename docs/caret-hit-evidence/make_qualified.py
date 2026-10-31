"""Writes tests/fixtures/caret-hit-qualified.json from a tests/abi/caret_hit.py --measure file: every difference is
classified into a named qualification, and an unclassified difference stops the script."""
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
        'gives the 0x20 caret box at the text end (x 40); Chromium gives 0x0 at (0, 0).',
}


def zero(rect):
    return rect is not None and all(rect[k] == 0 for k in ['x', 'y', 'width', 'height'])


def classify(d):
    native, chromium = d['native'], d['chromium']
    if d['member'] == 'range' and native and chromium and native['offset'] == 0 and native['node']['kind'] == 'element' \
            and native['node']['id'] in ('host', 'closed', 'field') and chromium['node'].get('name') == 'BODY':
        return 'legacy-range-shadow-retarget'
    if d['scroll'] == 'held' and d['point'] == 'shortened' and native == {'x': 40.0, 'y': 0.0, 'width': 0.0, 'height': 20.0} and zero(chromium):
        return 'stale-offset-rect'
    if d['member'] in ('position', 'shadowRoots') and native and chromium and native['node'] == chromium['node'] \
            and native['offset'] == chromium['offset'] and zero(native['rect']) and chromium['rect']['width'] == 0 and chromium['rect']['height'] == 20:
        if native['node'].get('name') == 'INPUT':
            return 'text-control-rect'
        if native['node']['kind'] == 'text' and native['offset'] in (4, 9):
            return 'collapsed-line-end-rect'
    raise SystemExit('unclassified difference: ' + json.dumps(d))


def main(measure, native_label):
    measured = json.loads(Path(measure).read_text(encoding='utf-8'))
    differences = []
    for d in measured['differences']:
        differences.append({'qualification': classify(d), **d})
    counts = {name: sum(1 for d in differences if d['qualification'] == name) for name in REASONS}
    result = {'description': 'Measured differences between the native engine and Chromium ' + measured['browser'] + ' for tests/fixtures/caret-hit-oracle.json. '
                             'tests/abi/caret_hit.py requires exactly these; any other difference fails.',
              'native': native_label, 'browser': measured['browser'], 'checked': measured['checked'],
              'qualifications': [{'name': name, 'count': counts[name], 'reason': reason} for name, reason in REASONS.items() if counts[name]],
              'differences': differences}
    (repo / 'tests/fixtures/caret-hit-qualified.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    print(measured['checked'], 'checks', counts)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
