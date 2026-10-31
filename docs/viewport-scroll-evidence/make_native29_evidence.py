"""Collects the G05 Native29 evidence into docs/viewport-scroll-evidence: RED, batch GREEN, teardown, the probe report
and the measured qualifications, each file with its SHA-256."""
import hashlib
import json
from pathlib import Path
import shutil

repo = Path('C:/wk/native-scroll')
evidence = repo / 'docs/viewport-scroll-evidence'
batch = repo / 'artifacts/native29-batch'
copies = {
    'red-measure.json': repo / 'artifacts/g05-red-measure.json',
    'red-native28-probe.log': repo / 'artifacts/g05-red-probe.log',
    'measure_scroll_red.py': repo / 'artifacts/measure_scroll_red.py',
    'build_native29_candidate.py': repo / 'artifacts/build_native29_candidate.py',
    'run_native29_batch.py': repo / 'artifacts/run_native29_batch.py',
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts/native29-frozen/runtime-receipt.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'viewport-scroll-report.json': repo / 'artifacts/g05-focused-1.json',
}
for name, source in copies.items():
    shutil.copyfile(source, evidence / name)
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
report = json.loads((evidence / 'viewport-scroll-report.json').read_text())
red = json.loads((evidence / 'red-measure.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/viewport-scroll-oracle.json').read_text())
scroll = next(item for item in records if item['name'] == 'viewport_scroll')
steps = {}
for item in report['qualified']:
    steps.setdefault(item['step'], {'native': item['native'], 'chromium': item['chromium'], 'nativeEvents': item['nativeEvents'],
                                    'chromiumEvents': item['chromiumEvents'], 'cases': []})['cases'].append(item['case'])
result = {
    'group': ['G05 #50'],
    'native': receipt['nativeVersion'],
    'abi': 37,
    'feature': 'dom-window-scrolling',
    'sourceHeadOfBatch': receipt['sourceHead'],
    'candidate': 'artifacts/native29-candidate-1 (forms-candidate-4 objects; RanvierDomGlue regenerated; four host units)',
    'red': {'runtime': 'native-forms/artifacts/native28-frozen (Native28/ABI36)', 'abiVersion': red['abiVersion'],
            'result': 'AssertionError ABI version 37; rv_dom_window scroll members absent: ' + ', '.join(red['missing']),
            'logs': ['red-native28-probe.log', 'red-measure.json']},
    'green': {'viewportScrollAssertions': scroll['assertions'], 'probes': len(records) - 2,
              'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records), 'teardownCases': len(teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'fixture': 'tests/fixtures/viewport-scroll-oracle.json',
                       'scales': oracle['scales'], 'stepsPerCase': len(oracle['cases'][0]['steps']), 'cases': len(oracle['cases'])},
    'qualifications': [
        'Both engines keep whole-pixel scroll offsets at device scales 1, 1.5 and 2: every Chromium 156 value in the oracle is an '
        'integer, and the pinned WebKit stores ScrollPosition as IntPoint.',
        'The native engine truncates a fractional CSS scroll target toward zero; Chromium rounds to the nearest pixel '
        '(20.5 -> 20 vs 21, 10.75 -> 10 vs 11, 7.7 -> 7 vs 8, scrollTop = 11.6 -> 11 vs 12). The same 13 of 16 steps differ on '
        'the viewport (Window and scrolling-element routes) and on a scrolling box at every scale; the step list and values are '
        'under qualifiedSteps.',
        'Event differences follow from the positions: a step whose truncated position is unchanged dispatches no scroll or '
        'scrollend natively (scrollTo(10.75, 20.75) after (10, 20); scrollTo(10.4, 20.4) after (10, 20); scrollBy({top: 0.6}) from '
        '(5, 6)), and a step that moves natively but not in Chromium dispatches scroll and scrollend natively '
        '(scrollBy(-0.3, -0.3) from (5, 6) -> (4, 5); scrollBy(-0.5, -0.5) from the maximum -> one pixel less).',
        'Element.scrollTop/scrollLeft are WebIDL long in the pinned WebKit (webkit.org/b/188045): the setter takes int32, and '
        'the caller converts a CSS value with ToInt32 truncation.',
        'A smooth scrollTo dispatched 3 scroll events then scrollend natively and 4 then scrollend in Chromium; the count '
        'follows each engine\'s animation frames. The final position differs by the truncation rule ((0, 50) vs (1, 51)).',
        'Clamping at 0 and at the maximum is equal (viewport 1680x1761, box 900x901 at every scale), as are maxima, '
        'scrollWidth/scrollHeight minus client size, and every unqualified step\'s value and events.',
    ],
    'qualifiedSteps': steps,
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
(evidence / 'final-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result['green']), hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
