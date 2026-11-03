import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('abi_policy', ROOT / 'tests/abi/abi_expectation.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class ProducerCohort(unittest.TestCase):
    def manifest(self, abi=64):
        return dict(abi=abi, rid='osx-arm64', flavor='gpu', source=dict(commit='a' * 40, dirty=False))

    def test_explicit64_is_bound_to_real_head_and_stage_and_scoped(self):
        self.assertEqual(policy.producer_environment(self.manifest(), 64, 'a' * 40, 'osx-arm64', 'gpu'),
                         {policy.ENVIRONMENT: '64'})

    def test_legacy_default63_requires_a63_stage(self):
        self.assertEqual(policy.producer_environment(self.manifest(63), None, 'a' * 40, 'osx-arm64', 'gpu'),
                         {policy.ENVIRONMENT: '63'})
        with self.assertRaises(ValueError):
            policy.producer_environment(self.manifest(), None, 'a' * 40, 'osx-arm64', 'gpu')

    def test_mismatched_source_dirty_rid_flavor_and_unknown_abi_fail_closed(self):
        for change in [dict(source=dict(commit='b' * 40, dirty=False)), dict(source=dict(commit='a' * 40, dirty=True)),
                       dict(rid='win-x64'), dict(flavor='slim'), dict(abi=63)]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                policy.producer_environment(self.manifest() | change, 64, 'a' * 40, 'osx-arm64', 'gpu')
        with self.assertRaises(ValueError):
            policy.producer_environment(self.manifest(65), 65, 'a' * 40, 'osx-arm64', 'gpu')


if __name__ == '__main__':
    unittest.main()
