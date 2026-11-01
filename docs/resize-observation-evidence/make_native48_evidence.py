"""Records the Native48 #55 (G10) lane proof: candidate receipt, full batch, the probe's 30-run repeat and the oracle.
usage: make_native48_evidence.py <native48-candidate-N> <repeat30 file> <note>"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

repo = Path(__file__).resolve().parents[2]
candidate, repeat, note = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
batch = repo / 'artifacts' / (candidate + '-batch')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


results = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
lines = [line.strip() for line in repeat.read_text(encoding='utf-8').splitlines() if line.strip()]
fixtures = repo / 'tests/fixtures'
evidence = {
    'group': 'G10', 'issue': 'ranvier-org/Ranvier.WebCore#55', 'note': note,
    'head': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True, check=True).stdout.strip(),
    'abi': 53, 'numbering': 'placeholder: root assigns NativeNN/ABI at batch integration (pipeline v2)',
    'candidate': candidate, 'runtimeReceipt': json.loads((repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json').read_text()),
    'batch': {'probes': len(results), 'allExitZero': all(item['exitCode'] == 0 for item in results),
              'rawAssertions': sum(item.get('assertions', 0) for item in results), 'teardownRecords': len(teardown),
              'resultsSha256': digest(batch / 'results.json')},
    'probe': {'name': 'resize_observation', 'repeat': len(lines), 'distinct': sorted(set(lines))},
    'oracle': {'file': 'tests/fixtures/resize-observation-oracle.json', 'sha256': digest(fixtures / 'resize-observation-oracle.json')},
    'qualified': json.loads((fixtures / 'resize-observation-qualified.json').read_text(encoding='utf-8'))['differences'],
    'devicePixelFollowUp': 'ranvier-org/Ranvier.WebCore#146',
}
assert evidence['batch']['allExitZero'] and len(lines) == 30 and len(set(lines)) == 1
out = repo / 'docs/resize-observation-evidence/final-evidence.json'
out.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
print('EVIDENCE', out, digest(out))
