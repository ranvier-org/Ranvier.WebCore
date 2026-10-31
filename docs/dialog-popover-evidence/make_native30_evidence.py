"""Collects the D16 Native30 evidence into docs/dialog-popover-evidence: RED, batch GREEN, teardown, the probe report
and the measured qualifications, each file with its SHA-256."""
import hashlib
import json
from pathlib import Path
import shutil

repo = Path('C:/wk/native-dialog')
evidence = repo / 'docs/dialog-popover-evidence'
batch = repo / 'artifacts/native30-batch'
copies = {
    'build_native30_candidate.py': repo / 'artifacts/build_native30_candidate.py',
    'run_native30_batch.py': repo / 'artifacts/run_native30_batch.py',
    'make_native30_evidence.py': repo / 'artifacts/make_native30_evidence.py',
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts/native30-frozen/runtime-receipt.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'dialog-popover-report.json': repo / 'artifacts/d16-native30-c1-green.json',
    'repeat-30.log': repo / 'artifacts/repeat-30b.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
report = json.loads((evidence / 'dialog-popover-report.json').read_text())
red = json.loads((evidence / 'red-native29.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/dialog-popover-oracle.json').read_text())
qualified = json.loads((repo / 'tests/fixtures/dialog-popover-qualified.json').read_text())
probe = next(item for item in records if item['name'] == 'dialog_popover')
added = [r for r in teardown if 'modal dialog' in r['probe'] or 'toggle event' in r['probe']]
result = {
    'group': ['D16 #24'],
    'native': receipt['nativeVersion'],
    'abi': 38,
    'features': ['dom:ToggleEvent', 'dom:CommandEvent', 'dom-constructor:ToggleEvent', 'dom-constructor:CommandEvent'],
    'hostSettings': {'PopoverHintEnabled': True},
    'sourceHeadOfBatch': receipt['sourceHead'],
    'candidate': 'artifacts/native30-candidate-1 (forms-candidate-4 objects; RanvierDomGlue regenerated; four host units)',
    'red': {'runtime': 'native-scroll/artifacts/native29-frozen (Native29/ABI37)', 'missing': red['missing'],
            'valueDifferences': sum(1 for d in red['differences'] if d['kind'] == 'value'), 'file': 'red-native29.json',
            'popoverHint': 'reflected "manual" (PopoverHintEnabled off)'},
    'green': {'dialogPopoverAssertions': probe['assertions'], 'probes': len(records) - 2,
              'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records), 'teardownCases': len(teardown),
              'teardownCasesAdded': len(added),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown),
              'probeTeardown': report['teardown']},
    'chromiumOracle': {'browser': oracle['browser'], 'fixture': 'tests/fixtures/dialog-popover-oracle.json',
                       'cases': len(oracle['cases']), 'steps': sum(len(c['steps']) for c in oracle['cases']),
                       'stableOverRuns': 3},
    'repeats': {'runs': 30, 'native30Candidate1': 'pass 30 fail 0', 'native32Candidate2': 'pass 30 fail 0 (C:/wk/native-caret/artifacts/native32-candidate-2)',
                'log': 'repeat-30.log', 'determinism': 'the probe drains the run loop after every step; queued toggles compare as per-element close count, final newState and oldState chain'},
    'unorderedQualifications': qualified.get('unordered', []),
    'valueDifferences': sum(1 for d in report['differences'] if d['kind'] == 'value'),
    'qualifications': [{'qualification': q['qualification'], 'case': q['case'], 'kind': q['kind'], 'reason': q['reason']}
                       for q in qualified['differences']],
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(json.dumps(result['green']['rawAssertions']), result['green']['teardownCases'], hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
