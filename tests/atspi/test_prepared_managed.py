"""Prepared-runtime metadata negatives; these do not represent renderer execution."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('prepared_replay', Path(__file__).with_name('run_prepared_managed.py'))
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class PreparedIdentity(unittest.TestCase):
    def setUp(self):
        self.manifest = dict(rid='linux-x64', providerSha256='b' * 64)
        self.record = dict(rid='linux-x64', hostSha256='a' * 64, providerSha256='b' * 64,
                           packageSha256='c' * 64, sourceRevision='d' * 40, domVersion='0.1.0-alpha.58',
                           allOwnedProcessesExited=True, runs=[], assetGraphs=dict(normal={}, traced={}),
                           runtimeAdmission=dict(readySha256='e' * 64))

    def validate(self, record):
        replay.validate_prepared_record(record, self.manifest, 'a' * 64, 'c' * 64, 'd' * 40, '0.1.0-alpha.58')

    def test_exact_setup_only_prepared_cohort_is_accepted(self):
        self.validate(self.record)

    def test_mixed_rid_host_provider_package_source_and_dom_are_rejected(self):
        for key, value in [('rid', 'linux-arm64'), ('hostSha256', 'f' * 64), ('providerSha256', 'f' * 64),
                           ('packageSha256', 'f' * 64), ('sourceRevision', 'f' * 40), ('domVersion', '0.1.0-alpha.57')]:
            with self.subTest(field=key), self.assertRaises(ValueError):
                self.validate(dict(self.record, **{key:value}))

    def test_live_children_existing_runs_missing_graph_and_missing_checkpoint_are_rejected(self):
        for key, value in [('allOwnedProcessesExited', False), ('runs', [{}]),
                           ('assetGraphs', dict(normal={})), ('runtimeAdmission', {})]:
            with self.subTest(field=key), self.assertRaises(ValueError):
                self.validate(dict(self.record, **{key:value}))

    def test_display_modes_cannot_share_ownership(self):
        with patch.object(replay.managed.subprocess, 'Popen') as process, self.assertRaises(ValueError):
            replay.managed.run_profiles(Path('.'), {}, {}, existing_display=':90', tcp_display=True)
        process.assert_not_called()


if __name__ == '__main__':
    unittest.main()
