import ast
from pathlib import Path
import tempfile
import shutil
import subprocess
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


def configure_for(source, directory):
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'configure')
    captured = []
    args = SimpleNamespace(rid='linux-x64', flavor='slim', enable_pdf=False)
    namespace = {'build': directory, 'source': ROOT, 'root': ROOT, 'args': args,
                 'stable_interpreters': lambda _: [], 'windows': False, 'arch': 'x64',
                 'run': lambda command, **_: captured.append([str(x) for x in command])}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'actual_configure', 'exec'), namespace)
    return namespace['configure'], args, captured


class PrintingConfiguration(unittest.TestCase):
    def test_explicit_disable_clears_a_previously_enabled_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            configure, args, captured = configure_for((ROOT / 'scripts/build.py').read_text(), Path(directory))
            args.enable_pdf = True
            configure({})
            args.enable_pdf = False
            configure({})
            cache = None
            for command in captured:
                for argument in command:
                    if argument.startswith('-DRANVIER_ENABLE_PDF='):
                        cache = argument.split('=', 1)[1]
            self.assertEqual(cache, 'OFF')
            self.assertIn('-DRANVIER_ENABLE_PDF=ON', captured[0])

    def test_default_restores_pdf_after_a_disabled_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            configure, args, captured = configure_for((ROOT / 'scripts/build.py').read_text(), Path(directory))
            args.enable_pdf = False
            configure({})
            del args.enable_pdf
            configure({})
            self.assertIn('-DRANVIER_ENABLE_PDF=ON', captured[1])

    @unittest.skipUnless(shutil.which('cmake') and shutil.which('ninja'), 'CMake/Ninja are not installed')
    def test_actual_cmake_properties_are_per_source_without_pch(self):
        hook = (ROOT / 'host/RanvierWebCoreHost.cmake').read_text().split('if (ENABLE_WEBCORE)\n', 1)[1]
        hook = hook.split('    set(RanvierWebCoreHost_SOURCES', 1)[0]
        with tempfile.TemporaryDirectory(prefix='print177-cmake-') as directory:
            source = Path(directory)
            (source / 'RanvierPrintGlue.cpp').write_text('')
            cmake = ('cmake_minimum_required(VERSION 3.25)\nproject(PrintProperties NONE)\n'
                     'add_library(WebCore INTERFACE)\n'
                     'set(WebCore_EMBEDDER_SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/RanvierPrintGlue.cpp")\n'
                     + hook
                     + 'get_source_file_property(defs "${CMAKE_CURRENT_SOURCE_DIR}/RanvierPrintGlue.cpp" TARGET_DIRECTORY WebCore COMPILE_DEFINITIONS)\n'
                     + 'get_source_file_property(skip "${CMAKE_CURRENT_SOURCE_DIR}/RanvierPrintGlue.cpp" TARGET_DIRECTORY WebCore SKIP_PRECOMPILE_HEADERS)\n'
                     + 'get_target_property(global_defs WebCore COMPILE_DEFINITIONS)\n'
                     + 'file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/actual.txt" CONTENT "$<GENEX_EVAL:${defs}>|${skip}|${global_defs}")\n')
            (source / 'CMakeLists.txt').write_text(cmake)
            for enabled in ('ON', 'OFF'):
                subprocess.run([shutil.which('cmake'), '-G', 'Ninja', '-S', str(source), '-B', str(source / 'build'),
                                '-DRANVIER_ENABLE_PDF=' + enabled], check=True, capture_output=True)
                actual = (source / 'build/actual.txt').read_text()
                self.assertEqual(actual, 'RANVIER_ENABLE_PDF=' + ('1' if enabled == 'ON' else '0') + '|ON|global_defs-NOTFOUND')

    def test_source_configuration_honors_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            configure, args, captured = configure_for((ROOT / 'scripts/build.py').read_text(), Path(directory))
            args.enable_pdf = True
            configure({})
            self.assertIn('-DRANVIER_ENABLE_PDF=ON', captured[0])


if __name__ == '__main__':
    unittest.main()
