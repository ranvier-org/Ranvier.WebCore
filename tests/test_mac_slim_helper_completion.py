import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('helper_completion', ROOT / 'scripts/complete_mac_slim_helpers.py')
completion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(completion)


class HelperCompletionTests(unittest.TestCase):
    def test_children_exclude_both_acquisition_credentials(self):
        with mock.patch.dict(os.environ, {'GH_TOKEN': 'test-only-gh', 'GITHUB_TOKEN': 'test-only-github',
                                         'COMPLETION_CONTROL': 'retained'}):
            environment = completion.child_environment()
            self.assertNotIn('GH_TOKEN', environment)
            self.assertNotIn('GITHUB_TOKEN', environment)
            self.assertEqual(environment['COMPLETION_CONTROL'], 'retained')

    def test_exact_original_archive_admission(self):
        root = Path('C:/wk/project2/mac-d31-recovery/slim-41733425197')
        if not (root / 'package.zip').exists():
            self.skipTest('Retained actual archives are an external evidence control')
        contract = json.loads(completion.INPUTS.read_text())
        recovery, sidecars = completion.admit_original(contract, root / 'proof.zip', root / 'package.zip')
        self.assertTrue(recovery['phases']['qualify']['passed'])
        self.assertFalse(recovery['phases']['helpers']['passed'])
        self.assertEqual(set(sidecars['helpers']), {'timer', 'page'})

    def test_changed_digest_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'proof.zip'
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                completion.verify_archive(path, '0' * 64)

    def test_changed_member_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'proof.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('receipt.json', '{}')
            with self.assertRaises(ValueError):
                completion.verify_archive(path, completion.sha(path), {'receipt.json': '0' * 64})

    def test_unsafe_paths_reject(self):
        for name in ['../escape', '/absolute']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'proof.zip'
                with zipfile.ZipFile(path, 'w') as archive:
                    row = zipfile.ZipInfo('placeholder')
                    row.filename = name
                    archive.writestr(row, 'bad')
                with self.assertRaises(ValueError):
                    completion.verify_archive(path, completion.sha(path))

    def test_workflow_is_unarmed_read_only_and_has_no_producer_steps(self):
        text = (ROOT / '.github/workflows/macos-preview12-helper-completion.yml').read_text()
        self.assertIn("false && github.event_name == 'workflow_dispatch'", text)
        self.assertIn('contents: read', text)
        self.assertIn('actions: read', text)
        self.assertNotIn('id-token:', text)
        self.assertNotIn('build.py', text)
        self.assertNotIn('actions/cache', text)
        self.assertIn('path: ${{ env.EVIDENCE }}', text)


if __name__ == '__main__':
    unittest.main()
