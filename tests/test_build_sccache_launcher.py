import ast
import importlib.util
from pathlib import Path
import pathlib
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('sccache_cache_policy', ROOT / 'scripts/sccache_cache_policy.py')
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class BuildSccacheLauncherTests(unittest.TestCase):
    def configure_command(self, rid, sccache):
        tree = ast.parse((ROOT / 'scripts/build.py').read_text())
        configure = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'configure')
        launcher_arguments = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                                  and node.name == 'compiler_launcher_arguments')
        calls = []
        namespace = {
            'build': Path('C:/rw/build'),
            'source': Path('C:/rw/src'),
            'pathlib': pathlib,
            'args': SimpleNamespace(rid=rid, flavor='gpu'),
            'windows': rid.startswith('win-'),
            'arch': rid.split('-')[1],
            'llvm': Path('C:/rw/tools/llvm/bin'),
            'vcpkg': Path('C:/rw/vcpkg'),
            'installed': Path('C:/rw/build/vcpkg_installed'),
            'root': ROOT,
            'stable_interpreters': lambda _env: [],
            'run': lambda command, **kwargs: calls.append((command, kwargs)),
        }
        exec(compile(ast.Module(body=[launcher_arguments, configure], type_ignores=[]), 'scripts/build.py', 'exec'),
             namespace)
        namespace['configure']({'PATH': '', 'RANVIER_SCCACHE': sccache})
        return calls[0][0]

    def sccache_environment(self):
        tree = ast.parse((ROOT / 'scripts/build.py').read_text())
        helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == 'sccache_environment')
        namespace = {}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), 'scripts/build.py', 'exec'), namespace)
        return namespace['sccache_environment']

    def test_configure_uses_the_pinned_launcher_only_for_windows_x64(self):
        command = self.configure_command('win-x64', r'C:\rw\tools\sccache\sccache.exe')
        self.assertIn('-DCMAKE_C_COMPILER_LAUNCHER=C:/rw/tools/sccache/sccache.exe', command)
        self.assertIn('-DCMAKE_CXX_COMPILER_LAUNCHER=C:/rw/tools/sccache/sccache.exe', command)

    def test_configure_leaves_other_rids_and_unset_launcher_unchanged(self):
        command = self.configure_command('win-arm64', r'C:\rw\tools\sccache\sccache.exe')
        self.assertFalse(any('COMPILER_LAUNCHER' in str(arg) for arg in command))

    def test_windows_x64_clears_both_launcher_cache_values_when_sccache_is_unavailable(self):
        command = self.configure_command('win-x64', '')
        self.assertIn('-DCMAKE_C_COMPILER_LAUNCHER=', command)
        self.assertIn('-DCMAKE_CXX_COMPILER_LAUNCHER=', command)

    def test_empty_windows_x64_launcher_args_clear_a_warm_cmake_cache(self):
        cmake = shutil.which('cmake')
        if not cmake:
            cmake = str(Path('C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/'
                             'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'))
            if not Path(cmake).is_file():
                cmake = None
        if not cmake:
            self.skipTest('CMake is not installed')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            (source / 'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(CacheProbe NONE)\n')
            build = root / 'build'
            first = subprocess.run([cmake, '-S', str(source), '-B', str(build),
                                    '-DCMAKE_C_COMPILER_LAUNCHER=C:/rw/tools/sccache/sccache.exe',
                                    '-DCMAKE_CXX_COMPILER_LAUNCHER=C:/rw/tools/sccache/sccache.exe'],
                                   capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            cache = build / 'CMakeCache.txt'
            self.assertIn('CMAKE_C_COMPILER_LAUNCHER:UNINITIALIZED=C:/rw/tools/sccache/sccache.exe',
                          cache.read_text())
            clear = self.configure_command('win-x64', '')
            launchers = [str(arg) for arg in clear if 'COMPILER_LAUNCHER=' in str(arg)]
            second = subprocess.run([cmake, '-S', str(source), '-B', str(build), *launchers],
                                    capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            contents = cache.read_text()
            self.assertIn('CMAKE_C_COMPILER_LAUNCHER:UNINITIALIZED=\n', contents)
            self.assertIn('CMAKE_CXX_COMPILER_LAUNCHER:UNINITIALIZED=\n', contents)

    def test_windows_vcvars_environment_preserves_sccache_configuration_only(self):
        passed = {
            'RANVIER_SCCACHE': r'C:\rw\tools\sccache\sccache.exe',
            'SCCACHE_DIR': r'C:\rw\sccache-cache',
            'SCCACHE_CACHE_SIZE': '192M',
            'UNRELATED_SECRET': 'do not forward',
        }
        self.assertEqual(self.sccache_environment()(passed), {
            'RANVIER_SCCACHE': r'C:\rw\tools\sccache\sccache.exe',
            'SCCACHE_DIR': r'C:\rw\sccache-cache',
            'SCCACHE_CACHE_SIZE': '192M',
        })


if __name__ == '__main__':
    unittest.main()
