import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

module_path = Path(__file__).parent / 'p7_gpu_qualification/sampler_numeric_evidence.py'
spec = importlib.util.spec_from_file_location('sampler_numeric_evidence', module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NumericEvidenceTests(unittest.TestCase):
    def test_exact_failed_values_and_raw_arrays_survive_later_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = module.NumericEvidence(directory)
            reference = np.array([[[0, 0, 0, .5]]], dtype=np.float32)
            actual = np.array([[[0, 0, 0, 129]]], dtype=np.uint8)
            evidence.pattern(1, np.array([[1, 0], [0, 0]]), np.array([[.5]]))
            evidence.stage('float', reference, {'blend': False})
            evidence.stage('unorm', actual, {'blend': False})
            evidence.comparison('unormVersusFloat', reference, actual, np.array([[1.5]]), .6)
            evidence.save(status='FAIL', runtimeUnchanged=True)
            report = json.loads((Path(directory) / 'sampler-numeric-diagnostic.json').read_text())
            comparison = report['patterns'][0]['comparisons'][0]
            self.assertEqual(comparison['limitUnchanged'], .6)
            self.assertEqual(comparison['failures'], 1)
            self.assertEqual(comparison['samples'][0]['actual'], [0, 0, 0, 129])
            self.assertEqual(comparison['samples'][0]['reference'], [0, 0, 0, .5])
            with np.load(Path(directory) / 'sampler-grid-raw/pattern-01.npz') as raw:
                np.testing.assert_array_equal(raw['floatRgba'], reference)
                np.testing.assert_array_equal(raw['unormRgba'], actual)
                np.testing.assert_array_equal(raw['unormVersusFloatFailingCoordinatesYx'], [[0, 0]])

    def test_previous_pattern_raw_data_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = module.NumericEvidence(directory)
            for bits in [0, 1]:
                evidence.pattern(bits, np.array([[bits]]), np.array([[float(bits)]]))
                evidence.stage('float', np.full((1, 1, 4), bits, dtype=np.float32), {})
            for bits in [0, 1]:
                with np.load(Path(directory) / f'sampler-grid-raw/pattern-{bits:02d}.npz') as raw:
                    self.assertTrue(np.all(raw['floatRgba'] == bits))

    def test_nonfinite_failure_still_produces_strict_json_and_raw_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = module.NumericEvidence(directory)
            values = np.full((1, 1, 4), np.nan, dtype=np.float32)
            evidence.pattern(0, np.array([[0]]), np.array([[0.]]))
            evidence.stage('float', values, {})
            evidence.comparison('nonfinite', values, values, np.array([[np.nan]]), .6)
            def reject_non_json(value):
                raise AssertionError(value)
            report = json.loads((Path(directory) / 'sampler-numeric-diagnostic.json').read_text(),
                                parse_constant=reject_non_json)
            self.assertEqual(report['patterns'][0]['comparisons'][0]['failures'], 1)
            with np.load(Path(directory) / 'sampler-grid-raw/pattern-00.npz') as raw:
                self.assertTrue(np.isnan(raw['floatRgba']).all())


if __name__ == '__main__':
    unittest.main()
