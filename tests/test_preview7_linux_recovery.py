import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / 'scripts/recover_preview7_linux_gpu.py'
spec = importlib.util.spec_from_file_location('p7_linux_recovery', source)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class ProfileContract(unittest.TestCase):
    def setUp(self):
        self.profile = {'version': 'OpenGL ES 3.2 Mesa 25.2.8-0ubuntu0.24.04.4',
                        'renderer': 'llvmpipe (LLVM 20.1.2, 256 bits)', 'vendor': 'Mesa', 'subpixelBits': 8,
                        'shaderPrecision': [{'shader': shader, 'kind': kind, 'bits': bits}
                                            for shader in ('vertex', 'fragment')
                                            for kind, bits in (('low', 10), ('medium', 10), ('high', 23))]}

    def test_expected_profile(self):
        recovery.check_profile(self.profile)

    def test_wrong_renderer_rejected(self):
        self.profile['renderer'] = 'different renderer'
        with self.assertRaises(ValueError): recovery.check_profile(self.profile)

    def test_wrong_precision_rejected(self):
        self.profile['shaderPrecision'][-1]['bits'] = 10
        with self.assertRaises(ValueError): recovery.check_profile(self.profile)

    def test_duplicate_precision_entry_rejected(self):
        self.profile['shaderPrecision'].append(self.profile['shaderPrecision'][0])
        with self.assertRaises(ValueError): recovery.check_profile(self.profile)

    def test_qualification_with_extra_job_rejected(self):
        producer = dict(head_sha=recovery.SOURCE, event='workflow_dispatch', path='.github/workflows/build.yml',
                        run_attempt=1, status='completed', conclusion='failure')
        pjobs = {'total_count': 3, 'jobs': [
            {'name': 'native (linux-x64, ubuntu-24.04, /mnt/rw)', 'conclusion': 'failure'},
            {'name': 'native (linux-arm64, ubuntu-24.04-arm, /mnt/rw)', 'conclusion': 'success'},
            {'name': 'publish', 'conclusion': 'skipped'}]}
        qualified = dict(head_sha=recovery.POLICY, event='push', path='.github/workflows/p7-linux-profile.yml',
                         run_attempt=1, status='completed', conclusion='success')
        qjobs = {'total_count': 2, 'jobs': [{'name': 'profile', 'conclusion': 'success'},
                                            {'name': 'unexpected', 'conclusion': 'success'}]}
        with patch.object(recovery, 'api', side_effect=[producer, pjobs, qualified, qjobs]):
            with self.assertRaisesRegex(ValueError, 'job list'): recovery.check_remote()

    def test_duplicate_producer_jobs_rejected(self):
        producer = dict(head_sha=recovery.SOURCE, event='workflow_dispatch', path='.github/workflows/build.yml',
                        run_attempt=1, status='completed', conclusion='failure')
        repeated = {'name': 'native (linux-x64, ubuntu-24.04, /mnt/rw)', 'conclusion': 'failure'}
        with patch.object(recovery, 'api', side_effect=[producer, {'total_count': 2, 'jobs': [repeated, repeated]}]):
            with self.assertRaisesRegex(ValueError, 'Duplicate'): recovery.check_remote()

    def test_standalone_workflow_is_retired(self):
        workflow = (source.parents[1] / '.github/workflows/preview7-linux-gpu-recovery.yml').read_text()
        self.assertEqual(workflow.count('if: ${{ false }}'), 2)
        self.assertEqual(workflow.count('python -I scripts/prepare_preview7_linux_gpu.py'), 2)
        self.assertLess(workflow.index('Independently re-download and verify before authentication'),
                        workflow.index('Authenticate after verification'))
        self.assertNotIn('scripts/build.py', workflow)


if __name__ == '__main__': unittest.main()
