"""Collects the D17 value-factories evidence into docs/value-factories-evidence: RED, the generator delta, the batch
GREEN, the 30x repeats, the Chromium oracle repeats, teardown and the receipts, each file with its SHA-256.

Usage: python -I make_factories_evidence.py <candidate> <batch head> <baseline batch-green.json>"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
candidate = sys.argv[1]
evidence = repo / 'docs/value-factories-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
artifacts = Path('C:/wk/factories-artifacts')
copies = {
    'red-exports.json': artifacts / 'red/red-exports.json',
    'red_exports.py': artifacts / 'red/red_exports.py',
    'dom-report.diff': artifacts / 'dom-report.diff',
    'dom-api-delta.json': artifacts / 'dom-api-delta.json',
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'value-factories-probe.log': batch / 'value_factories.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
baseline = json.loads(Path(sys.argv[3]).read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
red = json.loads((evidence / 'red-exports.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/value-factories-oracle.json').read_text(encoding='utf-8'))
qualified = json.loads((repo / 'tests/fixtures/value-factories-qualified.json').read_text(encoding='utf-8'))
repeats = (evidence / 'value-factories-repeat30.txt').read_text().splitlines()
oracle_repeats = (evidence / 'oracle-repeat30.txt').read_text().splitlines()
baseline_counts = {item['name']: item.get('assertions') for item in baseline if item['name'] not in ('frames', 'teardown')}
counts = {item['name']: item.get('assertions') for item in records}
result = {
    'group': ['D17 #25'],
    'status': 'green (private Windows x64 slim; not accepted)',
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'] if 'abiVersion' in receipt else None,
    'abiNote': 'placeholder ABI of batch-1 (54); the exports are additive and root assigns the number at integration',
    'members': sorted(name for name, present in red['exportsPresent'].items()),
    'generatorKeys': ['referenceDictionaries', 'dictionaryEventTargetMembers', 'typedArrayInputTypes', 'idlDefaultDictionaries'],
    'sourceHeadOfBatch': receipt['sourceHead'],
    'batchRunHead': sys.argv[2],
    'red': {'file': 'red-exports.json', 'abi': red['abi'], 'runtime': red['runtime'], 'allAbsent': not any(red['exportsPresent'].values()),
            'allLeftOut': all(red['leftOut'].values())},
    'generatorDelta': {'reportDiff': 'dom-report.diff', 'apiDelta': 'dom-api-delta.json',
                       'functionsAdded': json.loads((evidence / 'dom-api-delta.json').read_text())['functions']['added'],
                       'functionsRemoved': json.loads((evidence / 'dom-api-delta.json').read_text())['functions']['removed']},
    'green': {'valueFactoriesAssertions': counts['value_factories'], 'measurements': len(oracle['values']),
              'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions') or 0 for item in records),
              'baselineRawAssertions': sum(item.get('assertions') or 0 for item in baseline),
              'baselineProbesUnchanged': all(counts.get(name) == value for name, value in baseline_counts.items()),
              'teardownCases': len(teardown),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'measurements': len(oracle['values']), 'repeats': len(oracle_repeats),
                       'repeatsDistinct': sorted(set(oracle_repeats)),
                       'qualified': [{'key': item['key'], 'reason': item['reason']} for item in qualified['differences']]},
    'parentRuntime': 'C:/wk/native-cascade-shadow/artifacts/native46-candidate-6 (binary inputs equal to batch-1 d247ceb0)',
    'postdatingPatch': {'patch': '0040 EmptyClients.h final -> override, carried by C:/wk/src after the parent WebCore objects',
                        'recompiledUnitsIncluding': ['host/RanvierWebCoreAbi.cpp (through build-win-slim WebCore/PrivateHeaders/WebCore/EmptyClients.h, identical to C:/wk/src)'],
                        'effect': 'final -> override changes no class layout or vtable; the borrowed WebCore objects stay compatible',
                        'receiptCorrection': 'source-patches.json of factories-candidate-2 says no recompiled unit includes EmptyClients.h; RanvierWebCoreAbi.cpp does'},
}
result['files'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(evidence.iterdir())
                   if path.is_file() and path.name != 'final-evidence.json'}
(evidence / 'final-evidence.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(result['green'] | {'repeats': result['green']['repeatsDistinct']}, indent=1)[:1200])
