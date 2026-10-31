"""Collects the G11 intersection observation evidence into docs/intersection-observation-evidence: RED, the batch GREEN,
the 30x probe and oracle repeats, teardown and the receipts, each file with its SHA-256.

Usage: python -I make_intersect_evidence.py <candidate> <repeat file> <oracle repeat file> <batch head> <stacked-on note>
                                            <baseline batch-green.json>"""
import hashlib
import json
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
candidate = sys.argv[1]
evidence = repo / 'docs/intersection-observation-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
copies = {
    'intersection-observation-repeat30.txt': Path(sys.argv[2]),
    'oracle-repeat30.txt': Path(sys.argv[3]),
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'intersection-observation-probe.log': batch / 'intersection_observation.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
baseline = json.loads(Path(sys.argv[6]).read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
cases = json.loads((repo / 'tests/fixtures/intersection-observation-cases.json').read_text(encoding='utf-8'))
oracle = json.loads((repo / 'tests/fixtures/intersection-observation-oracle.json').read_text(encoding='utf-8'))
qualified = json.loads((repo / 'tests/fixtures/intersection-observation-qualified.json').read_text(encoding='utf-8'))
repeats = [line.split(': ', 1)[1] for line in (evidence / 'intersection-observation-repeat30.txt').read_text().splitlines()]
oracle_repeats = (evidence / 'oracle-repeat30.txt').read_text().splitlines()
names = [item['name'] for item in records]
counts = {item['name']: item.get('assertions') for item in records}
baseline_counts = {item['name']: item.get('assertions') for item in baseline if item['name'] not in ('frames', 'teardown')}
grown = {'abi_layouts': 23}
result = {
    'group': ['G11 #56'],
    'status': 'lane-green (private Windows x64 slim; not accepted)',
    'native': receipt['nativeVersion'] + ' (placeholder; root renumbers at batch integration)',
    'abi': str(receipt['abiVersion']) + ' (placeholder)',
    'features': ['intersection-entries'],
    'members': ['RvIntersectionEntry', 'RvIntersectionEntriesCallback', 'rv_host_observe_intersection_entries', 'rv_observer_take_records',
                'rv_host_now', 'rv_observer_disconnect (G10, rehearsed from native-resize 3615444)'],
    'engine': 'WebCore IntersectionObserver with Init.root (element or document), rootMargin and scrollMargin; takeRecords and '
              'Performance::now through RanvierViewportGlue (compiled into WebCore); no source patch',
    'sourceHeadOfBatch': receipt['sourceHead'],
    'batchRunHead': sys.argv[4],
    'stackedOn': sys.argv[5],
    'red': {'chromium': 'red_chromium.mjs -> red-chromium.json',
            'native': 'red_native.py -> red-native.json (coords-candidate-5, ABI53: target, isIntersecting and ratio of a viewport root '
                      'only; no element roots, scrollMargin, rectangles, times or takeRecords)'},
    'green': {'intersectionObservationAssertions': counts['intersection_observation'], 'scenarios': len(cases['scenarios']),
              'qualifiedScenarios': len(cases['qualifiedScenarios']), 'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records),
              'baselineRawAssertions': sum(item.get('assertions', 0) for item in baseline),
              'baselineProbesUnchanged': all(grown.get(n, c) == counts.get(n) for n, c in baseline_counts.items()),
              'grownBaselineProbes': {n: [baseline_counts[n], counts[n]] for n in grown},
              'addedProbes': {n: counts[n] for n in ['resize_observation', 'intersection_observation']},
              'baselineProbesPresent': all(n in names for n in baseline_counts),
              'probesRun': [{'name': item['name'], 'exitCode': item['exitCode'], 'assertions': item.get('assertions')} for item in records],
              'teardownCases': len(teardown), 'intersectionTeardownCases': len([r for r in teardown if 'intersection' in r['probe']]),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'scenarios': len(oracle['scenarios']), 'qualified': len(oracle['qualified']),
                       'repeats': len(oracle_repeats) - 1, 'summary': oracle_repeats[-1]},
    'qualified': qualified['comment'],
    'measured': {
        'time': 'entry times lie within rv_host_now read before and after the rendering update that queued them and never decrease; '
                'rv_host_now is whole milliseconds and keeps its origin over rv_host_load_html; one frozen time per update',
        'takeRecords': 'empty outside delivery in both engines; inside the first delivering callback the other observer entries are '
                       'taken and its callback does not run',
        'teardown': 'a target retained from an entry outlives removal and observer release; a released target is collected with no '
                    'queued records; an observer of a replaced document never delivers; release inside a callback; host destroy',
    },
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.is_file() and path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], result['green']['baselineProbesUnchanged'],
      hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
