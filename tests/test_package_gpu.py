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
            library = 'libRanvierWebCoreHost.so' if rid.startswith('linux') else 'RanvierWebCoreHost.dll'
            package.writestr(f'runtimes/{rid}/native/{library}', b'packaged host')
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
            for flavor, rid in [('slim', 'win-x64'), ('gpu', 'osx-arm64'), ('gpu', 'win-arm64')]:
                with self.subTest(flavor=flavor, rid=rid), patch('subprocess.run') as run:
                    with self.assertRaisesRegex(ValueError, 'supported GPU'):
                        probe.verify(self.package(Path(directory), flavor, rid), gpu=True)
                    run.assert_not_called()

    def test_linux_gpu_package_checks_the_extracted_egl_payload_headlessly(self):
        with tempfile.TemporaryDirectory() as directory:
            for rid in ['linux-x64', 'linux-arm64']:
                calls = []

                def execute(command, **kwargs):
                    calls.append((command, kwargs))
                    self.assertEqual(Path(command[-1]).read_bytes(), b'packaged host')

                with self.subTest(rid=rid), patch('subprocess.run', side_effect=execute):
                    probe.verify(self.package(Path(directory), rid=rid), gpu=True)
                self.assertEqual(len(calls), 1)
                command, options = calls[0]
                self.assertTrue(Path(command[2]).as_posix().endswith('tests/gpu/linux_egl.py'))
                self.assertEqual(options['env']['EGL_PLATFORM'], 'surfaceless')
                self.assertEqual(options['env']['LIBGL_ALWAYS_SOFTWARE'], '1')


if __name__ == '__main__':
    unittest.main()
