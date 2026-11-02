from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / 'abi'))
from background_content_clip_regression import BASELINES, half_coverage_allowed, load_inputs, pixel_policy, solid_red, unique_entries


class PaintPolicyTests(unittest.TestCase):
    def test_linux_baseline_font_is_verified_and_other_platforms_do_not_query_fontconfig(self):
        import background_content_clip_regression as policy
        with patch.object(policy.subprocess, 'check_output') as query:
            self.assertIsNone(policy.font_identity('win-x64'))
            query.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            font = Path(temporary) / 'font.ttf'
            font.write_bytes(b'fixture font')
            import hashlib
            digest = hashlib.sha256(font.read_bytes()).hexdigest()
            with patch.object(policy.subprocess, 'check_output', return_value=str(font)), \
                 patch.object(policy, 'LINUX_FONT_SHA256', digest):
                self.assertEqual(policy.font_identity('linux-x64')['sha256'], digest)
                font.write_bytes(b'different font')
                with self.assertRaisesRegex(AssertionError, 'font differs'):
                    policy.font_identity('linux-x64')

    def test_font_precondition_is_only_on_linux_clipping_probe(self):
        import runpy
        probes = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/probes.py'))['PROBES']
        selected = [entry for entry in probes if 'FONTCONFIG_FILE' in entry['env']]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['rid'], 'linux-x64')
        self.assertEqual(selected[0]['flavor'], 'gpu')
        self.assertIn('background_content_clip_regression.py', selected[0]['commands'][0])

    def test_half_coverage_also_handles_the_reverse_rounding_direction(self):
        before, after = bytes([127,127,127,255]), bytes([128,128,128,255])
        result = pixel_policy(before,after,before,half_coverage=True)
        self.assertEqual(result['worsePixels'],[0])
        self.assertEqual(result['qualifiedHalfCoveragePixels'],[0])
        self.assertEqual(result['unexplainedWorsePixels'],[])

    def test_a_strict_case_never_uses_half_coverage_qualification(self):
        import background_content_clip_regression as policy
        with patch.object(policy,'FIXED',policy.FIXED | {'composited-translate'}):
            self.assertFalse(half_coverage_allowed('win-x64','composited-translate',1))

    def test_half_coverage_keeps_raw_loss_metrics_and_labels_qualified_pixels(self):
        before = bytes([128,128,128,255,255,128,128,255])
        after = bytes([127,127,127,255,255,127,127,255])
        result = pixel_policy(before, after, before, half_coverage=True)
        self.assertEqual(result['worsePixels'], [0,1])
        self.assertEqual(result['previouslyExactPixelsLost'], 2)
        self.assertEqual(result['totalL1ErrorDelta'], 5)
        self.assertEqual(result['qualifiedHalfCoveragePixels'], [0,1])
        self.assertEqual(result['unexplainedWorsePixels'], [])

    def test_half_coverage_does_not_allow_other_byte_or_alpha_changes(self):
        for old, new in [(126,128),(128,129),(0,1),(254,255)]:
            with self.subTest(before=old, after=new):
                before, after = bytes([old,old,old,255]), bytes([new,new,new,255])
                result = pixel_policy(before, after, before, half_coverage=True)
                self.assertEqual(result['qualifiedHalfCoveragePixels'], [])
                self.assertEqual(result['unexplainedWorsePixels'], [0])
        before, after = bytes([128,128,128,255]), bytes([127,127,127,254])
        result = pixel_policy(before, after, before, half_coverage=True)
        self.assertEqual(result['unexplainedWorsePixels'], [0])

    def test_half_coverage_does_not_hide_shape_or_coordinate_changes(self):
        red, half, white = bytes([255,0,0,255]), bytes([255,128,128,255]), bytes([255,255,255,255])
        for before, after in [(half,red),(red,half),(half+white,white+half)]:
            result = pixel_policy(before, after, before, half_coverage=True)
            self.assertTrue(result['unexplainedWorsePixels'])
            self.assertEqual(result['qualifiedHalfCoveragePixels'], [])

    def test_half_coverage_is_scoped_to_windows_gpu_composited_control(self):
        self.assertTrue(half_coverage_allowed('win-x64','composited-translate',1))
        for rid,name,scale in [('linux-x64','composited-translate',1),('win-x64','composited-translate',1.5),
                               ('win-x64','scale-fractional',1),('win-x64','always-composited',1),
                               ('win-x64','bordered-half-phase',1),('win-arm64','composited-translate',1)]:
            with self.subTest(rid=rid,name=name,scale=scale):
                self.assertFalse(half_coverage_allowed(rid,name,scale))
                before, after = bytes([128,128,128,255]), bytes([127,127,127,255])
                result = pixel_policy(before,after,before,half_coverage=half_coverage_allowed(rid,name,scale))
                self.assertEqual(result['unexplainedWorsePixels'],[0])

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
