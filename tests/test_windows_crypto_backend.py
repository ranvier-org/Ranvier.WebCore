import ast
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


class WindowsCryptoBackendTests(unittest.TestCase):
    def settings(self, rid, flavor):
        cmake = shutil.which('cmake')
        if not cmake:
            candidate = Path('C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/'
                             'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe')
            cmake = str(candidate) if candidate.is_file() else None
        if not cmake:
            self.skipTest('CMake is not installed')
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'settings.cmake'
            output = Path(directory) / 'settings.txt'
            script.write_text('file(WRITE "${OUTPUT}" "${PORT};${USE_CRYPTO_STUB};${USE_NETWORK_STUB};'
                              '${USE_ANGLE_STUB};${USE_GPU_STUB}")\n')
            result = subprocess.run([cmake, f'-DRANVIER_RID={rid}', f'-DOUTPUT={output.as_posix()}',
                                     '-C', str(ROOT / f'config/{flavor}.cmake'), '-P', str(script)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return output.read_text().split(';')

    def test_windows_flavors_enable_crypto_and_preserve_network_and_rendering(self):
        for rid in ['win-x64', 'win-arm64']:
            for flavor, gpu_stub in [('slim', 'ON'), ('gpu', 'OFF')]:
                with self.subTest(rid=rid, flavor=flavor):
                    self.assertEqual(self.settings(rid, flavor), ['Win', 'OFF', 'ON', gpu_stub, gpu_stub])

    def test_windows_selection_preserves_other_port_settings(self):
        for rid, port in [('linux-x64', 'WPE'), ('osx-arm64', 'Mac')]:
            with self.subTest(rid=rid):
                settings = self.settings(rid, 'slim')
                self.assertEqual(settings[:3], [port, 'ON', 'ON'])

    def test_package_dependency_closure_keeps_the_imported_crypto_dll(self):
        tree = ast.parse((ROOT / 'scripts/build.py').read_text())
        closure = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'closure')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            libraries = base / 'bin'
            libraries.mkdir()
            provider = base / 'triplet/bin'
            provider.mkdir(parents=True)
            for name in ['RanvierWebCoreHost.dll', 'WebCore.dll']:
                (libraries / name).write_bytes(b'host')
            (provider / 'crypto-57.dll').write_bytes(b'provider')
            imports = {'RanvierWebCoreHost.dll': ['WebCore.dll'],
                       'WebCore.dll': ['crypto-57.dll', 'KERNEL32.dll'], 'crypto-57.dll': []}
            namespace = dict(build=base, triplet=base / 'triplet', system='win', host='RanvierWebCoreHost.dll',
                             imports=lambda path: imports[path.name])
            exec(compile(ast.Module(body=[closure], type_ignores=[]), 'scripts/build.py', 'exec'), namespace)
            result = dict(namespace['closure']())
            self.assertEqual(set(result), {'RanvierWebCoreHost.dll', 'WebCore.dll', 'crypto-57.dll'})
            self.assertEqual(result['crypto-57.dll'], provider / 'crypto-57.dll')

    def test_windows_package_carries_the_pinned_provider_notice(self):
        project = ET.parse(ROOT / 'packaging/Ranvier.WebCore.Native.csproj')
        notices = [item for item in project.findall('.//None')
                   if item.get('Include') == 'licenses/LibreSSL-4.2.1.txt']
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].get('PackagePath'), 'licenses/')
        self.assertEqual(notices[0].get('Pack'), 'true')
        self.assertIn('win-x64', notices[0].get('Condition', ''))
        self.assertIn('win-arm64', notices[0].get('Condition', ''))
        license_file = ROOT / 'packaging/licenses/LibreSSL-4.2.1.txt'
        self.assertEqual(hashlib.sha256(license_file.read_bytes()).hexdigest(),
                         '9853507b8821c3f277aa60bf554eade41441ef06b2df538d247183ad28789b7f')


if __name__ == '__main__':
    unittest.main()
