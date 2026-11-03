"""Configure-command controls without running CMake or a compiler."""
import ast
import json
import pathlib
import tempfile
from types import SimpleNamespace
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class CocoaCompilationDatabase(unittest.TestCase):
    def configure(self, rid='osx-arm64', flavor='gpu', database='valid'):
        module = ast.parse((ROOT / 'scripts/build.py').read_text())
        function, = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'configure']
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            build = root / 'build'
            commands = []

            def run(command, **kwargs):
                commands.append([str(value) for value in command])
                if database != 'missing':
                    rows = [dict(file=str(root / 'RanvierWebCoreAbi.cpp'), command='clang++ -c host.cpp')]
                    if database == 'empty':
                        rows = []
                    elif database == 'duplicate':
                        rows *= 2
                    (build / 'compile_commands.json').write_text(json.dumps(rows), encoding='utf-8')

            system, arch = rid.split('-')
            namespace = dict(build=build, source=root, root=ROOT, system=system, arch=arch, windows=system == 'win',
                             args=SimpleNamespace(rid=rid, flavor=flavor, mac_gpu_spike=False, enable_pdf=True),
                             stable_interpreters=lambda _: [], compiler_launcher_arguments=lambda *_: [], run=run,
                             llvm=root / 'llvm', vcpkg=root / 'vcpkg', installed=root / 'installed',
                             pathlib=pathlib, json=json)
            exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), 'configure-control', 'exec'), namespace)
            namespace['configure']({'PATH': ''})
            return commands

    def test_mac_profiles_export_the_actual_compiler_database(self):
        for flavor in ['slim', 'gpu']:
            command, = self.configure(flavor=flavor)
            self.assertIn('-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', command)

    def test_missing_empty_or_duplicate_host_database_stops_before_native_build(self):
        for database in ['missing', 'empty', 'duplicate']:
            with self.assertRaisesRegex(RuntimeError, 'compiler database'):
                self.configure(database=database)

    def test_other_ports_keep_their_existing_configuration(self):
        for rid in ['linux-x64', 'linux-arm64', 'win-x64', 'win-arm64']:
            command, = self.configure(rid=rid, database='missing')
            self.assertNotIn('-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', command)


if __name__ == '__main__':
    unittest.main()
