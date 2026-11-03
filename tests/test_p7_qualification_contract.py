import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'qualify_p7_clipping.py'
spec = importlib.util.spec_from_file_location('qualify_p7_clipping', MODULE)
qualify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualify)


class QualificationContract(unittest.TestCase):
    def setUp(self):
        self.expected = {('composited-translate', 1.5), ('composited-translate', 2)}
        self.report = {'completeKeys': 54, 'strictContentMaskKeys': 12,
                       'failures': [{'name': n, 'scale': s, 'strictFixedCase': False} for n, s in self.expected]}
        self.model = {'result': 'PASS', 'cases': [{'scale': 1.5, 'checkedPixels': 1080000, 'failures': 0},
                                                  {'scale': 2, 'checkedPixels': 1920000, 'failures': 0}]}

    def test_known_two_failures_with_complete_model_are_admitted(self):
        qualify.check_results(self.report, self.model)

    def test_unrelated_failure_rejected(self):
        self.report['failures'][0]['name'] = 'unrelated'
        with self.assertRaises(AssertionError): qualify.check_results(self.report, self.model)

    def test_strict_mask_failure_rejected(self):
        self.report['failures'][0]['strictFixedCase'] = True
        with self.assertRaises(AssertionError): qualify.check_results(self.report, self.model)

    def test_incomplete_coverage_rejected(self):
        self.report['completeKeys'] = 53
        with self.assertRaises(AssertionError): qualify.check_results(self.report, self.model)

    def test_duplicate_target_rejected(self):
        self.report['failures'][1] = self.report['failures'][0].copy()
        with self.assertRaises(AssertionError): qualify.check_results(self.report, self.model)

    def test_incomplete_model_rejected(self):
        self.model['cases'][0]['checkedPixels'] -= 1
        with self.assertRaises(AssertionError): qualify.check_results(self.report, self.model)

    def test_untrusted_artifacts_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, manifest = root / 'package', root / 'manifest'
            package.write_bytes(b'untrusted')
            manifest.write_text('{}')
            with self.assertRaises(AssertionError):
                qualify.stage_artifact(package, manifest, root / 'native')
            self.assertFalse((root / 'native').exists())


if __name__ == '__main__': unittest.main()
