import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from webcrypto_asymmetric_qualification import Backend

parser = argparse.ArgumentParser()
parser.add_argument('--native-directory', required=True)
parser.add_argument('--bridge-library', required=True)
parser.add_argument('--report', type=Path, required=True)
args = parser.parse_args()
controls = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/crypto-ec-jwk-canonicality.json').read_text())
backend = Backend(args.native_directory, args.bridge_library)
failures = []
try:
    for case in controls['cases']:
        result = backend.run(case['label'], case['algorithm'], 'import', format='jwk', jwk=case['jwk'], curve=case['curve'], usages=case['usages'])
        if result['exception'] != case['expectedError']:
            failures.append({'label': case['label'], 'expected': case['expectedError'], 'actual': result})
        if case['expectedError'] is None and result['firstKey']:
            exported = backend.run(case['label'] + '/export', case['algorithm'], 'export', key=result['firstKey'], format='jwk', curve=case['curve'])
            fields = ['x', 'y', 'd'] if case['private'] else ['x', 'y']
            if exported['exception'] or any(exported['jwk'].get(k) != case['jwk'][k] for k in fields):
                failures.append({'label': case['label'] + '/export', 'actual': exported})
    backend.check_script_guard()
    report = {'result': 'FAIL' if failures else 'PASS', 'controls': len(controls['cases']), 'rangeBoundaries': controls['rangeControls'], 'failures': failures, 'records': backend.records, 'privateWebCoreSha256': hashlib.sha256(Path(args.bridge_library).read_bytes()).hexdigest()}
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('EC JWK canonicality', report['result'], 'imports', len(controls['cases']), 'native operations', len(backend.records), 'failures', len(failures))
    for failure in failures:
        print(failure['label'])
    raise SystemExit(1 if failures else 0)
finally:
    backend.close()
