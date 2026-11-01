import importlib.util
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_package_api', ROOT / 'scripts/check_package_api.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class PackagedGpuTests(unittest.TestCase):
    def setUp(self):
        self.assertIn('gpu', inspect.signature(probe.verify).parameters,
                      'Packaged GPU payloads need a shared-frame acceptance mode')

    def package(self, directory, flavor='gpu', rid='win-x64'):
        archive = directory / 'runtime.nupkg'
        with zipfile.ZipFile(archive, 'w') as package:
            package.writestr('manifest.json', json.dumps({'rid': rid, 'flavor': flavor}))
            package.writestr(f'runtimes/{rid}/native/RanvierWebCoreHost.dll', b'packaged host')
        return archive

    def test_gpu_package_runs_shared_frame_lifetime_checks_on_the_extracted_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def execute(command, **kwargs):
                calls.append(command)
                if '--native' in command:
                    native = Path(command[command.index('--native') + 1])
                    self.assertEqual((native / 'RanvierWebCoreHost.dll').read_bytes(), b'packaged host')

            with patch('subprocess.run', side_effect=execute):
                probe.verify(self.package(Path(directory)), gpu=True)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0][2].endswith('sdl_runtime.py'))
        self.assertTrue(Path(calls[1][2]).as_posix().endswith('tests/gpu/run.py'))
        self.assertEqual(calls[1][-2:], ['--teardown', 'all'])

    def test_gpu_package_gate_rejects_the_wrong_flavor_or_rid_without_running_it(self):
        with tempfile.TemporaryDirectory() as directory:
            for flavor, rid in [('slim', 'win-x64'), ('gpu', 'linux-x64'), ('gpu', 'win-arm64')]:
                with self.subTest(flavor=flavor, rid=rid), patch('subprocess.run') as run:
                    with self.assertRaisesRegex(ValueError, 'Windows x64 GPU'):
                        probe.verify(self.package(Path(directory), flavor, rid), gpu=True)
                    run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
