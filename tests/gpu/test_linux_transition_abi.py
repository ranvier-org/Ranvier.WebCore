import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


class Accepted(Exception):
    pass


class TransitionAbiAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name('linux_view_transition_pixels.py')
        spec = importlib.util.spec_from_file_location('linux_transition_pixels_test', path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def invoke(self, host_abi):
        class Native:
            def __init__(self, directory):
                pass

            def bind(self, name, result, arguments):
                return lambda: host_abi

            def call(self, name, arguments, *values):
                raise Accepted()

        with patch.object(self.module, 'Native', Native):
            self.module.run('unused')

    def test_default_accepts_abi63(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(Accepted):
            self.invoke(63)

    def test_explicit_abi64_accepts_matching_host(self):
        with patch.dict(os.environ, {'RANVIER_ABI_TEST_EXPECTED': '64'}, clear=True), self.assertRaises(Accepted):
            self.invoke(64)

    def test_explicit_abi64_rejects_abi63_host(self):
        with patch.dict(os.environ, {'RANVIER_ABI_TEST_EXPECTED': '64'}, clear=True), self.assertRaises(AssertionError):
            self.invoke(63)

    def test_malformed_explicit_abi_is_rejected(self):
        with patch.dict(os.environ, {'RANVIER_ABI_TEST_EXPECTED': 'invalid'}, clear=True), self.assertRaises(ValueError):
            self.invoke(64)


if __name__ == '__main__':
    unittest.main()
