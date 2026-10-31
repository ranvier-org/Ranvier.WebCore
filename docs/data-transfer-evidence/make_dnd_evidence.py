"""Collects the drag/drop (I07, T09, T04) native evidence of a dnd candidate batch into docs/data-transfer-evidence.
usage: make_dnd_evidence.py <dnd-candidate-N> <repeat30 dir> <red json>"""
import hashlib
import json
from pathlib import Path
import shutil
import sys

repo = Path(__file__).resolve().parents[2]
candidate, repeat, red = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
here = repo / 'docs/data-transfer-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
frozen = repo / 'artifacts' / (candidate + '-frozen')
results = json.loads((batch / 'results.json').read_text())
assert all(item['exitCode'] == 0 for item in results)
baseline = {item['name']: item.get('assertions') for item in
            json.loads(Path('C:/wk/native-strings2/artifacts/native47-candidate-4-batch/results.json').read_text())}
counts = {item['name']: item.get('assertions') for item in results}
changed = {name: [baseline.get(name), count] for name, count in counts.items() if baseline.get(name) != count}
assert set(changed) == {'cascade_diagnostics', 'data_transfer'}, changed
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
shutil.copyfile(batch / 'teardown/teardown-probes.json', here / 'teardown-probes.json')
shutil.copyfile(frozen / 'runtime-receipt.json', here / 'runtime-receipt.json')
shutil.copyfile(repo / 'artifacts' / candidate / 'source-patches.json', here / 'source-patches.json')
shutil.copyfile(repeat / 'repeat30.txt', here / 'data-transfer-repeat30.txt')
shutil.copyfile(repeat / 'run-00.json', here / 'data-transfer-report.json')
(here / 'red').mkdir(exist_ok=True)
shutil.copyfile(red, here / 'red' / red.name)
shutil.copyfile(red.parent / 'red_probe.py', here / 'red' / 'red_probe.py')
log = next(item['log'] for item in results if item['name'] == 'data_transfer')
shutil.copyfile(log, here / 'data-transfer-probe.log')
(here / 'batch-green.json').write_text(json.dumps([{key: value for key, value in item.items() if key != 'executedAssets'} for item in results], indent=2) + '\n')
(here / 'baseline-comparison.json').write_text(json.dumps({
    'baseline': 'C:/wk/native-strings2/artifacts/native47-candidate-4-batch (#145 a9ba842)', 'changed': changed,
    'cascadeDiagnostics': 'batch-1 C25 shadow-scope cases (native46-candidate-6-batch: 6693)',
    'kept': sorted(name for name in counts if name not in changed)}, indent=2) + '\n')
raw = sum(count or 0 for count in counts.values())
lines = (repeat / 'repeat30.txt').read_text().splitlines()
evidence = {
    'groups': ['I07 drag/drop object model (#104)', 'T09 clipboard formats and file payloads (#77)', 'T04 rich beforeinput/input payloads (#75)'],
    'native': 'private dnd candidate on #145 Native47/ABI55 + batch-1 d1ff8ace (root assigns NativeNN/ABI at integration)',
    'abi': 55,
    'sourcePatch': '0041-data-transfer-in-memory-file-access.patch (unit UnifiedSource-dom-6 recompiled)',
    'batch': {'probes': len([item for item in results if item['name'] not in ('frames', 'teardown')]), 'rawAssertions': raw,
              'teardownCases': len(teardown), 'dataTransfer': counts['data_transfer']},
    'repeat30': {'runs': len(lines), 'identicalResults': len({line.split('results-sha256=')[1] for line in lines}) == 1},
    'qualified': len(json.loads((repo / 'tests/fixtures/data-transfer-qualified.json').read_text(encoding='utf-8'))['differences']),
    'chromium': json.loads((repo / 'tests/fixtures/data-transfer-oracle.json').read_text(encoding='utf-8'))['chromium'],
}
evidence['files'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(here.rglob('*'))
                     if path.is_file() and path.suffix in ('.json', '.txt', '.log') and path.name != 'final-evidence.json'}
(here / 'final-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
print('DND EVIDENCE', json.dumps(evidence['batch']), evidence['repeat30'])
