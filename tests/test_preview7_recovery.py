import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).resolve().parents[1] / 'scripts/recover_preview7_gpu.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        files = [{'name': f'{i}.dll', 'bytes': 1, 'sha256': recovery.sha(bytes([i]))} for i in range(26)]
        self.manifest = {'source': {'commit': recovery.PRODUCT, 'dirty': False, 'builder': 'ci'},
                         'abi': 62, 'rid': 'win-x64', 'flavor': 'gpu', 'files': files}
        self.manifest_path = self.root / 'manifest.json'
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.package = self.root / 'package.nupkg'
        with zipfile.ZipFile(self.package, 'w') as archive:
            archive.writestr('manifest.json', self.manifest_path.read_bytes())
            for i in range(26):
                archive.writestr(f'runtimes/win-x64/native/{i}.dll', bytes([i]))
        payloads = {x['name']: x['sha256'] for x in files}
        self.receipt = {'packageSha256': recovery.sha(self.package.read_bytes()),
                        'manifestSha256': recovery.sha(self.manifest_path.read_bytes()), 'source': recovery.PRODUCT,
                        'before': payloads, 'after': payloads.copy(), 'unchanged': True,
                        'capture': {'exit': 0, 'timedOut': False}}
        self.report = {'result': 'PASS', 'rid': 'win-x64', 'completeKeys': 54, 'strictContentMaskKeys': 12,
                       'results': [{'name': n, 'scale': s, 'strictFixedCase': n in recovery.FIXED,
                                    'contentMaskDifference': 0, 'unexplainedWorsePixels': []}
                                   for n in recovery.CASES for s in (1, 1.5, 2)], 'failures': []}
        self.original = {'result': 'FAIL', 'completeKeys': 54, 'strictContentMaskKeys': 12,
                         'failures': [{'name': 'composited-translate', 'scale': s} for s in (1.5, 2)]}
        self.summary = self.root / 'summary.txt'
        self.summary.write_text('FAIL Verify fixed content clipping masks and complete pointwise paint stability\n'
                                + 'PASS control\n' * 110)
        self.producer = {'head_sha': recovery.PRODUCT, 'status': 'completed', 'conclusion': 'failure',
                         'event': 'workflow_dispatch', 'head_branch': 'v0.1.1-preview.7',
                         'path': '.github/workflows/build.yml', 'run_attempt': 1}
        self.qualification = {'head_sha': 'policy', 'event': 'workflow_dispatch', 'path': 'qualified.yml',
                              'run_attempt': 1, 'status': 'completed', 'conclusion': 'success'}
        self.jobs = {'total_count': 2, 'jobs': [{'name': 'qualify-p7-gpu', 'conclusion': 'success',
                     'steps': [{'name': name, 'conclusion': 'success'} for name in recovery.QUALIFICATION_STEPS]},
                     {'name': 'publish', 'conclusion': 'skipped'}]}
        self.write_evidence()

    def write_evidence(self):
        for name, value in [('receipt.json', self.receipt), ('report.json', self.report), ('original.json', self.original)]:
            (self.root / name).write_text(json.dumps(value))

    def run_verify(self, qualification=42):
        def api(path):
            if '/jobs?' in path:
                return self.jobs
            return self.producer if path.endswith(str(recovery.PRODUCER)) else self.qualification
        values = {'api': api, 'TRUSTED_QUALIFICATION': 42, 'TRUSTED_POLICY': 'policy', 'TRUSTED_WORKFLOW': 'qualified.yml',
                  'PACKAGE_SHA': recovery.sha(self.package.read_bytes()), 'MANIFEST_SHA': recovery.sha(self.manifest_path.read_bytes()),
                  'TRUSTED_REPORT_SHA': recovery.sha((self.root / 'report.json').read_bytes()),
                  'TRUSTED_RECEIPT_SHA': recovery.sha((self.root / 'receipt.json').read_bytes()),
                  'ORIGINAL_REPORT_SHA': recovery.sha((self.root / 'original.json').read_bytes()),
                  'SUMMARY_SHA': recovery.sha(self.summary.read_bytes())}
        with patch.multiple(recovery, **values):
            return recovery.verify(self.package, self.manifest_path, self.root, self.summary, self.root / 'original.json', qualification)

    def test_unarmed_rejects_before_any_io(self):
        with patch.object(recovery, 'api', side_effect=AssertionError('unexpected API')):
            with self.assertRaisesRegex(ValueError, 'unarmed'):
                recovery.verify(None, None, None, None, None, 42)

    def test_complete_pinned_evidence(self):
        self.assertEqual(self.run_verify()['nativeFiles'], 26)

    def test_wrong_qualification_or_workflow_rejected(self):
        with self.assertRaises(ValueError): self.run_verify(43)
        self.qualification['path'] = 'other.yml'
        with self.assertRaises(ValueError): self.run_verify()

    def test_incomplete_jobs_or_unexpected_job_rejected(self):
        self.jobs['total_count'] = 3
        with self.assertRaises(ValueError): self.run_verify()
        self.jobs['total_count'] = 2
        self.jobs['jobs'][1]['conclusion'] = 'success'
        with self.assertRaises(ValueError): self.run_verify()

    def test_missing_qualification_step_rejected(self):
        self.jobs['jobs'][0]['steps'][0]['conclusion'] = 'failure'
        with self.assertRaises(ValueError): self.run_verify()

    def test_original_red_and_all_case_identities_are_required(self):
        self.original['failures'].pop()
        self.write_evidence()
        with self.assertRaises(ValueError): self.run_verify()
        self.original['failures'].append({'name': 'composited-translate', 'scale': 2})
        self.report['results'][0] = self.report['results'][1].copy()
        self.write_evidence()
        with self.assertRaises(ValueError): self.run_verify()

    def test_strict_mask_or_unexplained_pixel_rejected(self):
        row = next(x for x in self.report['results'] if x['strictFixedCase'])
        row['contentMaskDifference'] = 1
        self.write_evidence()
        with self.assertRaises(ValueError): self.run_verify()
        row['contentMaskDifference'] = 0
        row['unexplainedWorsePixels'] = [1]
        self.write_evidence()
        with self.assertRaises(ValueError): self.run_verify()

    def test_changed_payload_or_receipt_rejected(self):
        self.receipt['after'] = {}
        self.write_evidence()
        with self.assertRaises(ValueError): self.run_verify()
        self.receipt['after'] = self.receipt['before'].copy()
        with zipfile.ZipFile(self.package, 'a') as archive:
            archive.writestr('runtimes/win-x64/native/0.dll', b'changed')
        self.receipt['packageSha256'] = recovery.sha(self.package.read_bytes())
        self.write_evidence()
        with self.assertRaises(ValueError): self.run_verify()

    def test_workflow_is_unarmed_and_revalidates_before_oidc(self):
        text = (Path(__file__).resolve().parents[1] / '.github/workflows/preview7-gpu-recovery.yml').read_text()
        self.assertEqual(text.count('if: ${{ false &&'), 2)
        self.assertEqual(text.count('python -I scripts/recover_preview7_gpu.py'), 2)
        self.assertEqual(text.count('name: clipping-report-win-x64-gpu'), 2)
        self.assertLess(text.index('name: Revalidate before authentication'), text.index('uses: NuGet/login@v1'))
        self.assertIn("github.ref == 'refs/heads/main'", text)


if __name__ == '__main__':
    unittest.main()
