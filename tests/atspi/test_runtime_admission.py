"""Filesystem controls for the optional local build-to-runtime lease boundary."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('admission_managed', Path(__file__).with_name('arm64_managed.py'))
managed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(managed)


class RuntimeAdmission(unittest.TestCase):
    def exercise(self, mutate=None):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            asset = work / 'prepared-consumer'
            asset.write_bytes(b'fixture metadata, not a renderer')
            permit = work / 'runtime.json'
            ready = work / 'runtime.json.ready'

            def admit(_):
                data = json.loads(ready.read_text())
                grant = dict(token=data['token'], kind='run-app', leaseId='test-only-boundary')
                if mutate:
                    mutate(grant, asset)
                permit.write_text(json.dumps(grant))

            with patch.object(managed.time, 'sleep', side_effect=admit):
                return managed.await_runtime_admission(permit, work, [asset], timeout=1)

    def test_fresh_token_and_unchanged_prepared_inputs_are_bound(self):
        record = self.exercise()
        self.assertEqual(record['kind'], 'run-app')
        self.assertEqual(len(record['readySha256']), 64)
        self.assertEqual(len(record['permitSha256']), 64)

    def test_wrong_token_kind_or_missing_lease_is_rejected(self):
        for field, value in [('token', 'stale'), ('kind', 'full-build'), ('leaseId', None)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.exercise(lambda grant, _: grant.update({field:value}))

    def test_changed_binary_or_native_input_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.exercise(lambda _, asset: asset.write_bytes(b'changed'))

    def test_existing_or_outside_paths_are_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            permit = work / 'runtime.json'
            permit.write_text('{}')
            with self.assertRaises(ValueError):
                managed.await_runtime_admission(permit, work, [])
            permit.unlink()
            permit.with_suffix('.json.ready').write_text('{}')
            with self.assertRaises(ValueError):
                managed.await_runtime_admission(permit, work, [])
            with self.assertRaises(ValueError):
                managed.await_runtime_admission(work.parent / 'outside-admission.json', work, [])

    def test_missing_runtime_grant_times_out_without_starting_a_process(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            with patch.object(managed.subprocess, 'Popen') as process, self.assertRaises(TimeoutError):
                managed.await_runtime_admission(work / 'runtime.json', work, [], timeout=0)
            process.assert_not_called()


if __name__ == '__main__':
    unittest.main()
