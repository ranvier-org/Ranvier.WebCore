import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class SdlRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.directory = Path(self.workspace.name)

    def runtime_module(self):
        path = ROOT / 'scripts/sdl_runtime.py'
        self.assertTrue(path.exists(), 'The GPU acceptance dependency must have a pinned fetch helper')
        spec = importlib.util.spec_from_file_location('sdl_runtime', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def archive(self, member='runtimes/win-x64/native/SDL3.dll'):
        path = self.directory / 'sdl.nupkg'
        with zipfile.ZipFile(path, 'w') as package:
            package.writestr(member, b'fixture SDL runtime')
            package.writestr('../../unexpected.dll', b'do not extract')
        return path

    def test_extracts_only_the_verified_windows_x64_runtime(self):
        module = self.runtime_module()
        archive = self.archive()
        destination = self.directory / 'out'
        runtime = module.extract_runtime(archive, destination, hashlib.sha256(archive.read_bytes()).hexdigest())
        self.assertEqual(runtime, destination / 'SDL3.dll')
        self.assertEqual(runtime.read_bytes(), b'fixture SDL runtime')
        self.assertEqual(list(destination.iterdir()), [runtime])
        self.assertFalse((self.directory / 'unexpected.dll').exists())

    def test_rejects_hash_mismatch_before_creating_the_runtime(self):
        module = self.runtime_module()
        destination = self.directory / 'out'
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            module.extract_runtime(self.archive(), destination, '0' * 64)
        self.assertFalse(destination.exists())

    def test_rejects_an_archive_without_the_windows_x64_member(self):
        module = self.runtime_module()
        archive = self.archive('runtimes/linux-x64/native/libSDL3.so')
        with self.assertRaises(KeyError):
            module.extract_runtime(archive, self.directory / 'out', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
