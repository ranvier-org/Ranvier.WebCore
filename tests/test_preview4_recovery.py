import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).resolve().parents[1] / 'scripts/recover_preview4_gpu.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        files = [{'name': f'{i}.dll', 'bytes': 1, 'sha256': recovery.sha(bytes([i]))} for i in range(26)]
        self.manifest = {'source': {'commit': recovery.PRODUCT, 'dirty': False, 'builder': 'ci'}, 'files': files}
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
                       'results': [{} for _ in range(54)], 'failures': []}
        self.write_evidence()
        self.jobs = {'total_count': 2, 'jobs': [{'name': 'diagnose-p4-clipping', 'conclusion': 'success', 'steps': [
            {'name': 'Verify diagnostic guards and bounded cleanup', 'conclusion': 'success'},
            {'name': 'Replay exact failed package and retain full pixels and adapter identity', 'conclusion': 'success'}]},
            {'name': 'publish', 'conclusion': 'skipped'}]}
        self.producer = {'head_sha': recovery.PRODUCT, 'status': 'completed', 'conclusion': 'failure',
                         'event': 'workflow_dispatch', 'head_branch': 'v0.1.1-preview.4',
                         'path': '.github/workflows/build.yml', 'run_attempt': 1}
        self.qualification = {'head_sha': recovery.POLICY, 'event': 'workflow_dispatch',
                              'status': 'completed', 'conclusion': 'success'}
        self.summary = self.root / 'summary.txt'
        self.summary.write_text('FAIL Verify fixed content clipping masks and complete pointwise paint stability\n'
                                + 'PASS control\n' * 102)

    def write_evidence(self):
        (self.root / 'receipt.json').write_text(json.dumps(self.receipt))
        (self.root / 'background-content-clipping-regression.json').write_text(json.dumps(self.report))

    def run_verify(self):
        def api(path):
            if '/jobs?' in path:
                return self.jobs
            return self.producer if path.endswith(str(recovery.PRODUCER)) else self.qualification
        with patch.object(recovery, 'api', side_effect=api), \
             patch.object(recovery, 'PACKAGE_SHA', recovery.sha(self.package.read_bytes())), \
             patch.object(recovery, 'MANIFEST_SHA', recovery.sha(self.manifest_path.read_bytes())), \
             patch.object(recovery, 'REPORT_SHA', recovery.sha((self.root / 'background-content-clipping-regression.json').read_bytes())), \
             patch.object(recovery, 'RECEIPT_SHA', recovery.sha((self.root / 'receipt.json').read_bytes())), \
             patch.object(recovery, 'SUMMARY_SHA', recovery.sha(self.summary.read_bytes())):
            return recovery.verify(self.package, self.manifest_path, self.root, self.summary)

    def test_complete_fixed_evidence(self):
        self.assertEqual(self.run_verify()['nativeFiles'], 26)

    def test_failed_or_wrong_source_qualification_refused(self):
        for key, value in [('conclusion', 'failure'), ('head_sha', 'wrong'), ('event', 'push')]:
            with self.subTest(key=key):
                original = self.qualification[key]
                self.qualification[key] = value
                with self.assertRaises(ValueError):
                    self.run_verify()
                self.qualification[key] = original

    def test_unexpected_job_or_missing_guard_refused(self):
        self.jobs['total_count'] = 3
        with self.assertRaises(ValueError):
            self.run_verify()
        self.jobs['total_count'] = 2
        self.jobs['jobs'][1]['conclusion'] = 'success'
        with self.assertRaises(ValueError):
            self.run_verify()

    def test_extra_producer_failure_refused(self):
        self.summary.write_text(self.summary.read_text().replace('PASS control', 'FAIL control', 1))
        with self.assertRaises(ValueError):
            self.run_verify()
        self.jobs['jobs'][1]['conclusion'] = 'skipped'
        self.jobs['jobs'][0]['steps'][0]['conclusion'] = 'failure'
        with self.assertRaises(ValueError):
            self.run_verify()

    def test_changed_payload_receipt_or_failed_report_refused(self):
        self.receipt['after'] = {}
        self.write_evidence()
        with self.assertRaises(ValueError):
            self.run_verify()
        self.receipt['after'] = self.receipt['before'].copy()
        self.report['failures'] = ['unexpected']
        self.write_evidence()
        with self.assertRaises(ValueError):
            self.run_verify()

    def test_corrupt_package_refused_even_if_outer_hash_is_updated(self):
        with zipfile.ZipFile(self.package, 'a') as archive:
            archive.writestr('runtimes/win-x64/native/0.dll', b'changed')
        self.receipt['packageSha256'] = recovery.sha(self.package.read_bytes())
        self.write_evidence()
        with self.assertRaises(ValueError):
            self.run_verify()


if __name__ == '__main__':
    unittest.main()
