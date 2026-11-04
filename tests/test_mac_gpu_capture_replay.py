from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('capture_replay', ROOT / 'scripts/replay_mac_gpu_captures.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class CaptureReplayTests(unittest.TestCase):
    def receipt(self):
        native = {'actual-six-file-map': 'a' * 64}
        steps = [dict(name=name, exit=0) for name in sorted(replay.EXPECTED_STEPS)]
        negative = next(row for row in steps if row['name'] == 'reject-steady-base-repaint')
        negative.update(exit=1, expectedFailure='MAC_GPU_SPIKE FAIL transform and opacity animation reuse base backing')
        return dict(passed=True, nativeBefore=native, nativeAfter=dict(native), steps=steps), native

    def test_unchanged_semantic_steps_and_expected_negative_are_required(self):
        receipt, native = self.receipt()
        replay.validate_public_receipt(receipt, native)
        for label in ['missing', 'duplicate', 'success-instead-of-negative', 'wrong-negative', 'changed-native']:
            altered = deepcopy(receipt)
            negative = next(row for row in altered['steps'] if row['name'] == 'reject-steady-base-repaint')
            if label == 'missing': altered['steps'].pop()
            if label == 'duplicate': altered['steps'].append(dict(altered['steps'][0]))
            if label == 'success-instead-of-negative': negative['exit'] = 0
            if label == 'wrong-negative': negative['expectedFailure'] = 'unrelated failure'
            if label == 'changed-native': altered['nativeAfter'] = {'changed': 'b' * 64}
            with self.subTest(label=label), self.assertRaises(ValueError):
                replay.validate_public_receipt(altered, native)

    def test_pixel_contract_is_exact_fifteen_bmp_names(self):
        self.assertEqual(len(replay.EXPECTED_CAPTURES), 15)
        self.assertEqual(len([name for name in replay.EXPECTED_CAPTURES if name.startswith('cycle')]), 6)
        self.assertEqual(len([name for name in replay.EXPECTED_CAPTURES if name.startswith('input-')]), 9)

    def test_source_is_exact_manual_main_and_has_no_producer_steps(self):
        text = (ROOT / '.github/workflows/macos-preview12-capture-replay.yml').read_text()
        gate, = [line for line in text.splitlines() if line.startswith('    if:')]
        self.assertIn(gate, {
            "    if: ${{ false && github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}",
            "    if: ${{ github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}",
        })
        self.assertIn('contents: read', text)
        self.assertIn('actions: read', text)
        self.assertIn('include-hidden-files: true', text)
        self.assertNotIn('id-token:', text)
        self.assertNotIn('build.py', text)
        self.assertNotIn('actions/cache', text)


if __name__ == '__main__':
    unittest.main()
