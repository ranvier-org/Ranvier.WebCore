"""Exercise retained and temporary driver setup without compiling or loading a runtime."""
import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class DriverReached(Exception):
    pass


class AbiDriverWorkspace(unittest.TestCase):
    def invoke(self, retained):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            stage = base / 'stage'
            stage.mkdir()
            (stage / 'manifest.json').write_text(json.dumps(dict(abi=64, rid='osx-arm64')))
            evidence = base / 'evidence'
            argv = ['abi_tests.py', '--stage', str(stage), '--source', str(base / 'webkit'), '--expected-abi', '64']
            if retained:
                argv += ['--evidence-directory', str(evidence)]
            visited = []

            def command(args, **kwargs):
                visited.append([str(value) for value in args])
                if args[0] == 'dotnet':
                    output = Path(args[args.index('-o') + 1])
                    output.mkdir(parents=True)
                    (output / 'setup-control.txt').write_text('driver admitted')
                    raise DriverReached(output)
                return subprocess.CompletedProcess(args, 0)

            with patch.object(sys, 'argv', argv), patch('subprocess.run', side_effect=command), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(DriverReached) as stopped:
                    runpy.run_path(str(ROOT / 'scripts/abi_tests.py'), run_name='__main__')
            output = stopped.exception.args[0]
            self.assertEqual([Path(row[2]).name for row in visited[:2]], ['generate_native.py', 'domgen.py'])
            if retained:
                self.assertEqual(output, evidence.resolve() / 'driver')
                self.assertEqual((output / 'setup-control.txt').read_text(), 'driver admitted')
            else:
                self.assertFalse(output.parent.exists())

    def test_retained_evidence_context_reaches_driver_and_preserves_output(self):
        self.invoke(True)

    def test_temporary_context_reaches_driver_and_cleans_on_failure(self):
        self.invoke(False)


if __name__ == '__main__':
    unittest.main()
