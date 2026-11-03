import importlib.util
import os
import platform
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class RecipeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cmake') and os.environ.get('RANVIER_WEBKIT_SOURCE'),
                         'requires CMake and the pinned WebKit source')
    def test_sdk_frameworks_use_sdk_libraries_with_webkit_framework_macro(self):
        root = Path(__file__).resolve().parents[3]
        macros = Path(os.environ['RANVIER_WEBKIT_SOURCE']) / 'Source/cmake/WebKitMacros.cmake'
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            libraries = fixture / 'sdk/lib'
            libraries.mkdir(parents=True)
            for framework in ['Foundation', 'IOSurface', 'Metal']:
                (libraries / ('lib' + framework + '.a')).write_bytes(b'!<arch>\n')
            (fixture / 'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.20)\nproject(SDKContract LANGUAGES CXX)\n'
                f'include("{macros.as_posix()}")\n'
                'macro(_WEBKIT_TARGET target)\n'
                'target_link_libraries(${target} PRIVATE ${${target}_LIBRARIES} ${${target}_PRIVATE_LIBRARIES})\n'
                'set_target_properties(${target} PROPERTIES LINKER_LANGUAGE CXX)\nendmacro()\n'
                'set(ENABLE_WEBCORE ON)\nset(RANVIER_MAC_GPU_SPIKE ON)\nset(USE_GPU_STUB ON)\n'
                f'set(WEBCORE_DIR "{macros.parents[1].as_posix()}/WebCore")\n'
                'add_library(ANGLE::GLES INTERFACE IMPORTED)\nadd_library(ANGLE::EGL INTERFACE IMPORTED)\n'
                'file(WRITE "${CMAKE_BINARY_DIR}/cmakeconfig.h" "")\n'
                f'set(CMAKE_PREFIX_PATH "{(fixture / "sdk").as_posix()}")\n'
                f'include("{(root / "host/RanvierWebCoreHost.cmake").as_posix()}")\n'
                'get_target_property(libraries RanvierWebCoreHost LINK_LIBRARIES)\n'
                'file(WRITE "${CMAKE_BINARY_DIR}/libraries.txt" "${libraries}")\n'
                'file(WRITE "${CMAKE_BINARY_DIR}/private-includes.txt" "${RanvierWebCoreHost_PRIVATE_INCLUDE_DIRECTORIES}")\n')
            build = fixture / 'build'
            result = subprocess.run(['cmake', '-S', str(fixture), '-B', str(build)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            linked = (build / 'libraries.txt').read_text()
            for framework in ['Foundation', 'IOSurface', 'Metal']:
                self.assertIn((libraries / ('lib' + framework + '.a')).as_posix(), linked)
                self.assertNotIn('WebKit::' + framework, linked)
            self.assertIn((macros.parents[1] / 'WebCore/platform/graphics').as_posix(),
                          (build / 'private-includes.txt').read_text())

    def load(self):
        path = Path(__file__).with_name('run.py')
        self.assertTrue(path.exists(), 'one-RID spike recipe is missing')
        spec = importlib.util.spec_from_file_location('mac_spike_recipe', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_other_rid_cannot_start_spike_build(self):
        recipe = self.load()
        with self.assertRaisesRegex(ValueError, 'osx-arm64'):
            recipe.commands('linux-x64', True, Path('/private/spike'), 4)

    def test_build_requires_explicit_spike_opt_in(self):
        recipe = self.load()
        with self.assertRaisesRegex(ValueError, 'opt-in'):
            recipe.commands('osx-arm64', False, Path('/private/spike'), 4)

    def test_recipe_keeps_one_private_source_and_build_and_bounded_jobs(self):
        recipe = self.load()
        result = recipe.commands('osx-arm64', True, Path('/private/spike'), 4)
        self.assertEqual([step['name'] for step in result],
                         ['fetch', 'prepare', 'configure', 'build', 'package'])
        for step in result:
            command = step['command']
            self.assertEqual(command[command.index('--rid') + 1], 'osx-arm64')
            self.assertEqual(command[command.index('--source') + 1], '/private/spike/src')
            self.assertEqual(command[command.index('--build-dir') + 1], '/private/spike/build-mac-gpu-spike')
            self.assertEqual(command[command.index('--jobs') + 1], '4')
            self.assertIn('--mac-gpu-spike', command)
            self.assertIn('--strict', command)
            self.assertEqual(command[command.index('--version') + 1], '0.0.0-project2-mac220.1')

    def test_excessive_parallelism_is_rejected(self):
        recipe = self.load()
        with self.assertRaisesRegex(ValueError, '1.*4'):
            recipe.commands('osx-arm64', True, Path('/private/spike'), 16)

    def test_gl_import_gate_distinguishes_angle_from_system_gl(self):
        recipe = self.load()
        inventory = ['_glGetIntegerv', '_glBindFramebuffer']
        self.assertEqual(recipe.legacy_gl_imports(
            '                 (undefined) external _glGetIntegerv (from OpenGL)', inventory), ['_glGetIntegerv'])
        self.assertEqual(recipe.legacy_gl_imports(
            '                 (undefined) external _GL_GetIntegerv (from libGLESv2)', inventory), [])
        self.assertEqual(recipe.legacy_gl_imports('_glGetIntegervExtra __ZN_glBindFramebuffer', inventory), [])

    def test_native_timeout_preserves_partial_log_and_failure(self):
        recipe = self.load()
        self.assertTrue(callable(getattr(recipe, 'run_step', None)), 'bounded step runner is missing')
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            receipt = {'steps': []}
            with self.assertRaisesRegex(RuntimeError, 'exceeded'):
                recipe.run_step('proof', [sys.executable, '-u', '-c',
                                          'import time; print("partial-native-output", flush=True); time.sleep(10)'],
                                evidence, evidence, receipt, timeout=0.5)
            self.assertIn('partial-native-output', (evidence / 'proof.log').read_text())
            self.assertEqual(receipt['steps'][0]['exit'], None)
            self.assertTrue(receipt['steps'][0]['timedOut'])

    def test_build_cli_rejects_spike_on_other_rid_before_fetch(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary) / 'must-not-exist'
            root = Path(__file__).resolve().parents[3]
            result = subprocess.run([sys.executable, str(root / 'scripts/build.py'), 'fetch',
                                     '--rid', 'win-x64', '--flavor', 'gpu', '--mac-gpu-spike', '--work', str(work)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('requires --rid osx-arm64 --flavor gpu', result.stderr)
            self.assertFalse(work.exists())

    @unittest.skipUnless(shutil.which('cmake'), 'CMake is required for actual preset controls')
    def test_actual_cmake_presets_enable_mac_transport_only_in_gpu_profiles(self):
        root = Path(__file__).resolve().parents[3]
        cases = [('osx-arm64', 'slim', False), ('osx-arm64', 'mac-gpu-spike', True), ('osx-arm64', 'gpu', True),
                 ('win-x64', 'gpu', False), ('linux-x64', 'gpu', False)]
        for rid, preset, expected in cases:
            with self.subTest(rid=rid, preset=preset), tempfile.TemporaryDirectory() as temporary:
                check = Path(temporary) / 'check.cmake'
                check.write_text('if(RANVIER_MAC_GPU_SPIKE)\nmessage(STATUS "MAC_SPIKE=ON")\nelse()\nmessage(STATUS "MAC_SPIKE=OFF")\nendif()\n')
                result = subprocess.run(['cmake', '-DRANVIER_RID=' + rid, '-C',
                                         str(root / 'config' / (preset + '.cmake')), '-P', str(check)],
                                        cwd=temporary, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('MAC_SPIKE=' + ('ON' if expected else 'OFF'), result.stdout + result.stderr)

    @unittest.skipIf(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'Mac execution is coordinator-scheduled')
    def test_other_platform_cannot_execute_or_create_build_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary) / 'must-not-be-created'
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('run.py')),
                                     '--work', str(work), '--mac-gpu-spike', '--execute'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('macOS arm64', result.stderr)
            self.assertFalse(work.exists())


if __name__ == '__main__':
    unittest.main()
