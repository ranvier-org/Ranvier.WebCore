import importlib.util
from pathlib import Path
import signal
import sys
import unittest

directory = Path(__file__).parent / 'abi'
sys.path.insert(0, str(directory))
spec = importlib.util.spec_from_file_location('cocoa_timer_contract', directory / 'cocoa_timer_contract.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OwnerAssertionVerdict(unittest.TestCase):
    def test_fatal_after_explicit_ownership_violation(self):
        self.assertTrue(module.expected_owner_assertion(-signal.SIGILL, 'WTF_TIMER_NEGATIVE_BEFORE_OWNER_VIOLATION\n'))

    def test_success_is_not_an_expected_failure(self):
        self.assertFalse(module.expected_owner_assertion(0, 'WTF_TIMER_NEGATIVE_BEFORE_OWNER_VIOLATION\n'))

    def test_unrelated_failure_is_not_accepted(self):
        self.assertFalse(module.expected_owner_assertion(-9, 'WTF_TIMER_NEGATIVE_BEFORE_OWNER_VIOLATION\n'))

    def test_timeout_is_not_accepted(self):
        self.assertFalse(module.expected_owner_assertion(-999, 'WTF_TIMER_NEGATIVE_BEFORE_OWNER_VIOLATION\n'))

    def test_crash_before_admission_is_not_accepted(self):
        self.assertFalse(module.expected_owner_assertion(-signal.SIGILL, 'unrelated crash'))

    def test_returned_destructor_is_not_accepted(self):
        self.assertFalse(module.expected_owner_assertion(-signal.SIGILL, 'WTF_TIMER_NEGATIVE_BEFORE_OWNER_VIOLATION\nWTF_TIMER_NEGATIVE_DESTRUCTOR_RETURNED\n'))


if __name__ == '__main__':
    unittest.main()
