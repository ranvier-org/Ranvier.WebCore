import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class FailureRetention(unittest.TestCase):
    def test_dependency_capsule_survives_a_compile_failure(self):
        spec = importlib.util.spec_from_file_location('timer_builder', ROOT / 'tests/abi/build_cocoa_timer_contract.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build, source, runtime = [root / name for name in ['build', 'source', 'runtime']]
            for path in [build, source, runtime]:
                path.mkdir()
            compiler, probe, header = [root / name for name in ['clang', 'probe.cpp', 'config.h']]
            for path in [compiler, probe, header, build / 'cmakeconfig.h']:
                path.write_bytes(b'exact fixture input')
            hashes = {}
            for name in ['libJavaScriptCore.dylib', 'libRanvierWebCoreHost.dylib']:
                path = runtime / name
                path.write_bytes(b'not executable')
                hashes[name] = module.sha(path)
            runtime_hashes = root / 'runtime.json'
            runtime_hashes.write_text(json.dumps(hashes))
            host = root / 'RanvierWebCoreAbi.cpp'
            (build / 'compile_commands.json').write_text(json.dumps([dict(file=str(host), directory=str(root),
                arguments=[str(compiler), '-c', str(host), '-o', str(root / 'old.o')])]))
            output = root / 'output'

            class Child:
                def __init__(self, command, **kwargs):
                    self.code = 0 if '-M' in command else 1
                    if '-M' in command:
                        escaped = lambda p: p.as_posix().replace(' ', '\\ ')
                        Path(command[command.index('-MF') + 1]).write_text('probe: ' + escaped(probe) + ' ' + escaped(header))
                def wait(self, **kwargs):
                    return self.code
                def poll(self):
                    return self.code

            argv = ['builder', '--build', str(build), '--webkit-source', str(source), '--runtime', str(runtime),
                    '--runtime-hashes', str(runtime_hashes), '--probe-source', str(probe), '--output', str(output), '--public-sidecar']
            with patch.object(module.sys, 'argv', argv), patch.object(module.sys, 'platform', 'darwin'), \
                    patch.object(module.platform, 'machine', return_value='arm64'), \
                    patch.object(module.platform, 'mac_ver', return_value=('26.0', (), '')), \
                    patch.object(module.subprocess, 'Popen', Child), \
                    patch.dict(os.environ, {'RANVIER_COCOA_OWNED_GROUP': '1'}):
                with self.assertRaisesRegex(AssertionError, 'compile:'):
                    module.main()
            receipt = json.loads((output / 'build-receipt.json').read_text())
            self.assertEqual(receipt['status'], 'failed')
            self.assertEqual(receipt['consumedInputsArchiveSha256'], module.sha(output / 'consumed-inputs.zip'))
            self.assertTrue(receipt['runtimeUnchanged'] and receipt['inputsUnchanged'])
            with zipfile.ZipFile(output / 'consumed-inputs.zip') as archive:
                for path in [probe, header, build / 'cmakeconfig.h', build / 'compile_commands.json']:
                    self.assertEqual(archive.read('inputs/' + path.resolve().as_posix().lstrip('/')), path.read_bytes())


if __name__ == '__main__':
    unittest.main()
