import importlib.util
from pathlib import Path
import unittest

import numpy as np


path = Path(__file__).parent / 'p7_gpu_qualification/sampler_format_policy.py'
spec = importlib.util.spec_from_file_location('sampler_format_policy', path)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class FormatPolicyTests(unittest.TestCase):
    def arrays(self, bits):
        ideal = policy.ideal_alpha(bits)
        floating = np.zeros((256, 256, 4), dtype=np.float32)
        floating[:, :, 3] = ideal
        unorm = np.zeros((256, 256, 4), dtype=np.uint8)
        unorm[:, :, 3] = np.floor(ideal * 255)
        white = np.full((256, 256, 4), 255, dtype=np.uint8)
        white[:, :, :3] = (255-unorm[:, :, 3])[:, :, None]
        return floating, unorm, white

    def test_cross_draw_red_remains_separate_from_existing_complete_path_budget(self):
        arrays = self.arrays(1)
        arrays[0][32, 108, 3] = .5058517456054688
        arrays[1][32, 108, 3] = 128
        arrays[2][32, 108, :3] = 127
        arrays[0][229, 18, 3] = .09800858050584793
        arrays[1][229, 18, 3] = 24
        arrays[2][229, 18, :3] = 231
        result = policy.evaluate(1, *arrays)
        self.assertEqual(result['policyFailures'], 0)
        self.assertGreater(result['historicalCrossDrawFailures'], 0)
        self.assertAlmostEqual(result['maximumUnormVsIdealUnits'], 1.003509521484375)

    def test_one_beyond_policy_bound_is_rejected(self):
        floating, unorm, white = self.arrays(1)
        ideal = policy.ideal_alpha(1)
        unorm[108, 32, 3] = int(np.floor(ideal[108, 32]*255+1.6))+1
        self.assertGreater(policy.evaluate(1, floating, unorm, white)['policyFailures'], 0)

    def test_constant_color_one_byte_mutation_is_rejected(self):
        floating, unorm, white = self.arrays(15)
        unorm[108, 32, 3] = 254
        self.assertGreater(policy.evaluate(15, floating, unorm, white)['policyFailures'], 0)

    def test_missing_or_duplicate_patterns_cannot_complete(self):
        rows = [policy.evaluate(bits, *self.arrays(bits)) for bits in range(16)]
        self.assertEqual(policy.complete(rows)['result'], 'PASS')
        self.assertEqual(policy.complete(rows[:-1])['result'], 'FAIL')
        self.assertEqual(policy.complete(rows[:-1]+[rows[0]])['result'], 'FAIL')

    def test_store_control_does_not_admit_a_sampling_budget(self):
        self.assertTrue(policy.store_control(np.array([129.]), np.array([.5058517456054688]))['pass'])
        self.assertFalse(policy.store_control(np.array([128.]), np.array([.5058517456054688]))['pass'])

    def test_nonfinite_sample_is_rejected(self):
        floating, unorm, white = self.arrays(1)
        floating[32, 108, 3] = np.nan
        self.assertGreater(policy.evaluate(1, floating, unorm, white)['policyFailures'], 0)

    def test_each_declared_negative_control_is_outside_the_policy(self):
        rows = policy.negative_controls(1, *self.arrays(1))
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row['failures'] > 0 for row in rows))


if __name__ == '__main__':
    unittest.main()
