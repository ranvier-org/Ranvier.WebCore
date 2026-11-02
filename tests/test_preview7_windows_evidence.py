import importlib.util
from pathlib import Path
import re
import unittest

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).resolve().parents[1] / 'scripts/recover_preview7_gpu.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class WindowsEvidenceTests(unittest.TestCase):
    def test_evidence_pins_are_complete_and_specific(self):
        self.assertEqual(recovery.TRUSTED_QUALIFICATION, 41541720378)
        self.assertEqual(recovery.TRUSTED_POLICY, '4d99783d1a90863bfdeaffccb8e032edded846de')
        self.assertGreaterEqual(len(recovery.EVIDENCE_SHA), 20)
        self.assertIn('policy/sampler-format-probe.json', recovery.EVIDENCE_SHA)
        self.assertIn('policy/gpu_pixel_gate_v3.py', recovery.EVIDENCE_SHA)
        self.assertIn('negative-old-cpu.json', recovery.EVIDENCE_SHA)

    def test_recovery_is_isolated_and_revalidates_before_oidc(self):
        text = (Path(__file__).resolve().parents[1] / '.github/workflows/build.yml').read_text()
        jobs = re.split(r'\n  (?=[a-z][a-z0-9-]*:\n)', text.split('\njobs:\n', 1)[1])
        for block in jobs:
            name = block.split(':', 1)[0].strip()
            if name not in ('verify-preview7-windows-recovery', 'publish-preview7-windows-recovery'):
                self.assertIn('!inputs.recover_preview7_windows', block.split('runs-on:', 1)[0], name)
        verify = text.split('\n  verify-preview7-windows-recovery:\n', 1)[1].split('\n  publish-preview7-windows-recovery:', 1)[0]
        publish = text.split('\n  publish-preview7-windows-recovery:\n', 1)[1]
        for block in (verify, publish):
            self.assertIn("github.ref == 'refs/heads/main'", block)
            self.assertIn('!inputs.recover_preview7_linux', block)
            self.assertIn('scripts/prepare_preview7_windows_gpu.py', block)
        self.assertLess(publish.index('scripts/prepare_preview7_windows_gpu.py'), publish.index('NuGet/login@v1'))


if __name__ == '__main__':
    unittest.main()
