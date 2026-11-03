import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('retained_replay', Path(__file__).with_name('replay_retained.py'))
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class RetainedInputs(unittest.TestCase):
    def test_exact_bytes_are_required_before_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'engine').write_bytes(b'qualified-engine')
            expected = {'engine': hashlib.sha256(b'qualified-engine').hexdigest()}
            replay.verify_files(root, expected)
            (root / 'engine').write_bytes(b'another-engine')
            with self.assertRaisesRegex(ValueError, 'Retained input mismatch'):
                replay.verify_files(root, expected)
            (root / 'engine').unlink()
            with self.assertRaisesRegex(ValueError, 'Retained input mismatch'):
                replay.verify_files(root, expected)


if __name__ == '__main__':
    unittest.main()
