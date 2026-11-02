import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('asymmetric_probe', ROOT / 'tests/abi/webcrypto_asymmetric_qualification.py')
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)
FIXTURE = ROOT / 'tests/fixtures/crypto-ec-private-jwk-validation.json'
CASES = json.loads(FIXTURE.read_bytes())['cases']


class PrivateJwkValidationTests(unittest.TestCase):
    def replay(self, mutation=None):
        by_label = {case['label']: case for case in CASES}

        class Backend:
            def __init__(self, *_):
                self.records = []
                self.keys = {}

            def run(self, label, algorithm, operation, **arguments):
                if operation == 'import':
                    case = by_label[label]
                    key = len(self.records) + 1 if case['expectedError'] is None else 0
                    result = dict(label=label, exception=case['expectedError'], firstKey=key, secondKey=0)
                    if mutation:
                        mutation(case, result)
                    if result['firstKey']:
                        self.keys[result['firstKey']] = arguments['jwk']
                else:
                    result = dict(label=label, exception=None, jwk=self.keys[arguments['key']])
                self.records.append(result)
                return result

            def check_script_guard(self):
                pass

            def close(self):
                pass

        with patch.object(PROBE, 'Backend', Backend):
            return PROBE.verify_private_jwk('unused', FIXTURE)

    def test_valid_protocol_preserves_all_cases_and_exports(self):
        report = self.replay()
        self.assertEqual(report['result'], 'PASS')
        self.assertEqual(report['imports'], 68)
        self.assertEqual(len(report['records']), 80)
        self.assertEqual(sum(r['label'].endswith('/export') for r in report['records']), 12)

    def test_success_without_handle_fails_and_continues_remaining_cases(self):
        label = next(case['label'] for case in CASES if case['expectedError'] is None)

        def omit_key(case, result):
            if case['label'] == label:
                result['firstKey'] = 0

        report = self.replay(omit_key)
        self.assertEqual(report['result'], 'FAIL')
        self.assertEqual(report['imports'], 68)
        self.assertEqual(len(report['records']), 79)
        self.assertTrue(any(f['label'] == label and f.get('expected') == 'nonnull imported key' for f in report['failures']))

    def test_rejection_with_either_returned_handle_fails(self):
        label = next(case['label'] for case in CASES if case['expectedError'] is not None)
        for field in ['firstKey', 'secondKey']:
            with self.subTest(field=field):
                def leak_key(case, result):
                    if case['label'] == label:
                        result[field] = 999

                report = self.replay(leak_key)
                self.assertEqual(report['result'], 'FAIL')
                self.assertEqual(len(report['records']), 80)
                self.assertTrue(any(f['label'] == label and f.get('expected') == 'no returned keys on rejection' for f in report['failures']))


if __name__ == '__main__':
    unittest.main()
