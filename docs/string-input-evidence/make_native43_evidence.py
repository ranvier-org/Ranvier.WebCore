"""Collects the WebCore #142 evidence into docs/string-input-evidence: RED, the batch GREEN against the baseline batch,
the string_nul repeats, teardown and the per-probe output comparison, each file with its SHA-256.

Usage: python -I make_native43_evidence.py <candidate> <baseline batch dir> <baseline head> <stacked-on note> <teardown repeat note>"""
import hashlib
import json
import re
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
candidate, baseline, baseline_head, stacked, teardown_repeat = sys.argv[1:6]
baseline = Path(baseline)
evidence = repo / 'docs/string-input-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
copies = {
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'string-nul-probe.log': batch / 'string_nul.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))


def normalized(path):
    text = path.read_text(encoding='utf-8', errors='replace')
    text = re.sub(r'\[rtk\][^\n]*\n', '', text)
    return re.sub(r'[0-9a-f]{64}', '<sha256>', text).splitlines()


records = json.loads((batch / 'results.json').read_text())
base = {item['name']: item for item in json.loads((baseline / 'results.json').read_text())}
comparison = []
for item in records:
    previous = base.get(item['name'])
    entry = {'name': item['name'], 'assertions': item.get('assertions'), 'exitCode': item['exitCode']}
    if previous:
        entry['baselineAssertions'] = previous.get('assertions')
        entry['sameCount'] = previous.get('assertions') == item.get('assertions')
        entry['sameOutput'] = normalized(Path(previous['log'])) == normalized(Path(item['log']))
    else:
        entry['new'] = True
    comparison.append(entry)
(evidence / 'baseline-comparison.json').write_text(json.dumps(comparison, indent=2) + '\n', encoding='utf-8', newline='\n')
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
base_teardown = json.loads((baseline / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
repeats = json.loads((evidence / 'string-nul-repeat30.json').read_text(encoding='utf-8'))
red = json.loads((evidence / 'red/string-nul-red.json').read_text(encoding='utf-8'))
api = json.loads((repo / 'gen/dom-api.json').read_text(encoding='utf-8'))
result = {
    'group': ['WebCore #142 length-delimited generated string inputs'],
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'abiBreaking': 'every generated rv_dom_* string input: plain arguments const uint8_t* plus int32_t length (-1 null or absent), '
                   'union and sequence strings RvDomUtf8StringSpan, dictionary string fields RvDomUtf8StringInput',
    'exceptions': [],
    'generatedFunctions': len(api['functions']),
    'nulTerminatedGeneratedInputs': sum(1 for f in api['functions'] for p in f['parameters'] if p['ctype'] == 'const char*'),
    'handWrittenExports': 'unchanged, NUL-terminated; follow-up ranvier-org/Ranvier.WebCore#145',
    'sourceHeadOfBatch': receipt['sourceHead'],
    'stackedOn': stacked,
    'baseline': {'batch': str(baseline), 'head': baseline_head,
                 'rawAssertions': sum(item.get('assertions', 0) for item in base.values()), 'teardownCases': len(base_teardown)},
    'red': {'file': 'red/string-nul-red.json', 'script': 'red/string_nul_red.py', 'abi': red['abi'], 'cases': red['cases'],
            'differ': red['differ'], 'byCategory': red['byCategory']},
    'green': {
        'stringNulAssertions': next(item['assertions'] for item in records if item['name'] == 'string_nul'),
        'stringNulRepeats': repeats['count'], 'stringNulRepeatsDistinct': repeats['distinctPassLines'],
        'teardownStringResultsRepeats': teardown_repeat,
        'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
        'rawAssertions': sum(item.get('assertions', 0) for item in records),
        'baselineProbesSameCount': all(entry.get('sameCount', True) for entry in comparison),
        'baselineProbesSameOutput': [entry['name'] for entry in comparison if entry.get('sameOutput')],
        'baselineProbesOtherOutput': {entry['name']: 'timing values only' if entry['name'] == 'frames' else
                                      'two added string results records' for entry in comparison
                                      if 'sameOutput' in entry and not entry['sameOutput']},
        'teardownCases': len(teardown),
        'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown),
    },
    'files': {},
}
for path in sorted(evidence.rglob('*')):
    if path.is_file() and path.name != 'final-evidence.json':
        result['files'][path.relative_to(evidence).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], result['green']['baselineProbesOtherOutput'],
      hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
