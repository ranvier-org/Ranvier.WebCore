from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / 'abi'))
from background_content_clip_regression import pixel_policy, solid_red, unique_entries


class PaintPolicyTests(unittest.TestCase):
    def test_improvement_toward_chromium_is_allowed(self):
        result = pixel_policy(bytes([200,10,10,255]), bytes([230,0,0,255]), bytes([255,0,0,255]))
        self.assertEqual(result['worsePixels'], [])
        self.assertEqual(result['improvedPixels'], 1)
        self.assertEqual(result['totalL1ErrorDelta'], -50)

    def test_alpha_regression_loses_a_previously_exact_pixel(self):
        result = pixel_policy(bytes([255,0,0,255]), bytes([255,0,0,254]), bytes([255,0,0,255]))
        self.assertEqual(result['worsePixels'], [0])
        self.assertEqual(result['previouslyExactPixelsLost'], 1)

    def test_one_improvement_cannot_hide_another_pixels_regression(self):
        result = pixel_policy(bytes([200,0,0,255,200,0,0,255]),
                              bytes([255,0,0,255,150,0,0,255]),
                              bytes([255,0,0,255,255,0,0,255]))
        self.assertEqual(result['totalL1ErrorDelta'], -5)
        self.assertEqual(result['worsePixels'], [1])

    def test_complete_masks_detect_gaps_with_equal_bounds_and_pixel_counts(self):
        red, white = bytes([255,0,0,255]), bytes([255,255,255,255])
        first = solid_red(red + white + red + white + red)
        second = solid_red(red + white + white + red + red)
        self.assertEqual(sum(first), sum(second))
        self.assertNotEqual(first, second)

    def test_duplicate_or_missing_control_is_rejected(self):
        expected = {(str(index),1) for index in range(54)}
        valid = [dict(name=str(index),scale=1) for index in range(54)]
        self.assertEqual(set(unique_entries(valid,expected)), expected)
        with self.assertRaises(AssertionError):
            unique_entries(valid[:-1] + [valid[0]],expected)


if __name__ == '__main__':
    unittest.main()
