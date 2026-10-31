"""Collects the WebCore G14 evidence into docs/coordinate-evidence: RED, the batch GREEN against the baseline batch, the
coordinate_spaces report and repeats, teardown and the per-probe count comparison, each file with its SHA-256.

Usage: python -I make_coords_evidence.py <candidate> <baseline batch dir> <baseline head> <stacked-on note>"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
candidate, baseline, baseline_head, stacked = sys.argv[1:5]
baseline = Path(baseline)
evidence = repo / 'docs/coordinate-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
runtime = repo / 'artifacts' / (candidate + '-frozen') / 'runtimes/win-x64/native'
copies = {
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'coordinate-spaces-probe.log': batch / 'coordinate_spaces.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
report = evidence / 'coordinate-spaces-report.json'
subprocess.run([sys.executable, '-I', '-X', 'utf8', str(repo / 'tests/abi/coordinate_spaces.py'), '--native-directory', str(runtime),
                '--report', str(report)], check=True, capture_output=True)
records = json.loads((batch / 'results.json').read_text(encoding='utf-8'))
base = {item['name']: item for item in json.loads((baseline / 'results.json').read_text(encoding='utf-8'))}
comparison = []
for item in records:
    previous = base.get(item['name'])
    entry = {'name': item['name'], 'assertions': item.get('assertions'), 'exitCode': item['exitCode']}
    if previous:
        entry['baselineAssertions'] = previous.get('assertions')
        entry['sameCount'] = previous.get('assertions') == item.get('assertions')
    else:
        entry['new'] = True
    comparison.append(entry)
(evidence / 'baseline-comparison.json').write_text(json.dumps(comparison, indent=2) + '\n', encoding='utf-8', newline='\n')
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text(encoding='utf-8'))
base_teardown = json.loads((baseline / 'teardown/teardown-probes.json').read_text(encoding='utf-8'))
receipt = json.loads((evidence / 'runtime-receipt.json').read_text(encoding='utf-8'))
repeats = (evidence / 'coordinate-spaces-repeat30.txt').read_text(encoding='utf-8').splitlines()
probe = json.loads(report.read_text(encoding='utf-8'))
result = {
    'group': ['G14 coordinate-space conversion (ranvier-org/Ranvier.WebCore#58)'],
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'features': ['coordinate-spaces'],
    'members': ['rv_node_convert_points', 'rv_node_box_quad', 'RV_SPACE_NODE/PAGE/CLIENT/HOST/DEVICE', 'RV_QUAD_*_BOX',
                'RV_ERR_WRONG_HOST (-12)'],
    'sourcePatch': 'none: the conversion is WebCore embedder glue (host/RanvierViewportGlue.cpp)',
    'sourceHeadOfBatch': receipt['sourceHead'],
    'stackedOn': stacked,
    'baseline': {'batch': str(baseline), 'head': baseline_head,
                 'rawAssertions': sum(item.get('assertions', 0) for item in base.values() if item['name'] not in ('frames', 'teardown')),
                 'teardownCases': len(base_teardown)},
    'red': {'native': 'red-native.json (red_native.py)', 'chromium': 'red-chromium.json (red_chromium.mjs)',
            'finding': 'no conversion export; rv_element_rect gives axis-aligned bounds; at page scale 2 origin 40,60 '
                       'rv_host_mouse lands at client x/2, y/2 while rv_host_scroll_position reads 40,60'},
    'chromiumOracle': {'file': 'tests/fixtures/coordinate-spaces-oracle.json', 'script': 'tests/abi/coordinate_spaces_browser.mjs',
                       'browser': probe['browser']},
    'green': {
        'coordinateSpacesAssertions': next(item['assertions'] for item in records if item['name'] == 'coordinate_spaces'),
        'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
        'maxError': probe['maxError'],
        'qualified': probe['qualified'],
        'perspectivePaint': probe['perspectivePaint'],
        'perspectiveFunctionPaint': probe['perspectiveFunctionPaint'],
        'singular': probe['singular'],
        'teardownStatuses': probe['teardown'],
        'arguments': probe['arguments'],
        'pageScaleStates': [{k: s[k] for k in ('name', 'pageOffset', 'scale', 'clientToHost', 'hostToClient') if k in s} for s in probe['states']],
        'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
        'rawAssertions': sum(item.get('assertions', 0) for item in records),
        'baselineProbesSameCount': all(entry.get('sameCount', True) for entry in comparison),
        'newProbes': [entry['name'] for entry in comparison if entry.get('new')],
        'teardownCases': len(teardown),
        'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown),
    },
    'files': {},
}
for path in sorted(evidence.rglob('*')):
    if path.is_file() and path.name != 'final-evidence.json':
        result['files'][path.relative_to(evidence).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], result['green']['baselineProbesSameCount'],
      hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
