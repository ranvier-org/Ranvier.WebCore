from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / 'abi'))
from background_content_clip_regression import BASELINES, load_inputs, pixel_policy, solid_red, unique_entries


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

    def test_actual_git_blob_fixtures_load_with_lf_or_crlf_but_reject_changed_content(self):
        repo = Path(__file__).resolve().parents[1]
        names = ['background-content-clip-cases.json','background-content-clip-oracle.json',
                 'background-content-clip-baselines/chromium-rgba.json']
        blobs = {name:subprocess.check_output(['git','-C',str(repo),'show','HEAD:tests/fixtures/'+name])
                 for name in names}
        self.assertTrue(all(b'\r\n' not in blob for blob in blobs.values()))
        with tempfile.TemporaryDirectory() as directory:
            fixtures = Path(directory)
            baselines = fixtures/'background-content-clip-baselines'
            baselines.mkdir()
            profile = BASELINES/'linux-x64-gpu.json'
            (baselines/profile.name).write_bytes(profile.read_bytes())
            for ending in [b'\n',b'\r\n']:
                for name,blob in blobs.items():
                    (fixtures/name).write_bytes(blob.replace(b'\n',ending))
                _,_,expected,before,targets = load_inputs('linux-x64',fixtures,baselines)
                self.assertEqual(len(expected),54)
                self.assertEqual(set(before),set(targets))
            chrome = baselines/'chromium-rgba.json'
            value = json.loads(chrome.read_text())
            value['results'][0]['rgbaSha256'] = '0'*64
            chrome.write_text(json.dumps(value))
            with self.assertRaisesRegex(AssertionError,'Fixture JSON identity mismatch: chrome'):
                load_inputs('linux-x64',fixtures,baselines)


if __name__ == '__main__':
    unittest.main()
