import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github/workflows/build.yml').read_text()


class SccachePowerShellFallbackTests(unittest.TestCase):
    def test_failed_optional_install_resets_native_exit_before_github_wrapper(self):
        shell = shutil.which('pwsh')
        self.assertIsNotNone(shell, 'the Windows native job must have pwsh for the fallback contract test')
        step_start = WORKFLOW.index('      - name: Install and configure sccache\n')
        block = WORKFLOW[step_start:]
        match = re.search(r'^        run: \|\n((?:^          .*\n|^\s*\n)+)', block, re.MULTILINE)
        self.assertIsNotNone(match, 'the pinned-tool setup must remain a PowerShell literal block')
        body = textwrap.dedent('\n'.join(line[10:] for line in match.group(1).splitlines()))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, stub in enumerate((
                'function python { $global:LASTEXITCODE = 17 }',
                "function python { throw 'simulated terminating installer error' }",
            )):
                with self.subTest(stub=stub):
                    script_path = root / f'fallback-{index}.ps1'
                    # GitHub's built-in pwsh wrapper exits with the last native command's status.
                    script_path.write_text(stub + '\n' + body
                                           + "\nif (Test-Path variable:\\LASTEXITCODE) { exit $LASTEXITCODE }\n")
                    env = dict(os.environ)
                    for name in ('GITHUB_PATH', 'GITHUB_ENV', 'GITHUB_OUTPUT'):
                        env[name] = str(root / f'{index}-{name.lower()}')
                        Path(env[name]).write_text('')
                    result = subprocess.run(
                        [shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(script_path)],
                        env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('available=false', Path(env['GITHUB_OUTPUT']).read_text())
                    self.assertIn('pinned sccache could not be installed', result.stdout.lower())


if __name__ == '__main__':
    unittest.main()
