"""Exercise the release CLI without invoking builds, GitHub writes or authentication."""

import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HEAD = 'a' * 40


class ReleaseTests(unittest.TestCase):
    def invoke(self, flavor, dirty=False, tagged=False):
        calls = []

        def run(command, **kwargs):
            command = [str(value) for value in command]
            calls.append(command)
            output = ''
            if command[:3] == ['git', 'status', '--porcelain']:
                output = ' M tracked.file' if dirty else ''
            elif command[:3] == ['git', 'rev-parse', 'HEAD']:
                output = HEAD
            elif command[:3] == ['git', 'branch', '-r']:
                output = 'origin/main'
            elif command[:3] == ['git', 'ls-remote', '--tags']:
                output = HEAD if tagged else ''
            return subprocess.CompletedProcess(command, 0, stdout=output, stderr='')

        arguments = ['release.py', '--rid', 'win-x64', '--flavor', flavor, '--dry-run', '--work', str(ROOT / 'artifacts/release-proof')]
        with patch.object(sys, 'argv', arguments), patch('subprocess.run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as completed:
                runpy.run_path(str(ROOT / 'scripts/release.py'), run_name='__main__')
        return completed.exception.code, calls

    def test_gpu_dry_run_builds_and_checks_the_gpu_package(self):
        code, calls = self.invoke('gpu')
        self.assertIsNone(code)
        smoke = next(command for command in calls if any(value.endswith('smoke.py') for value in command))
        version = json.loads((ROOT / 'pins.json').read_text())['package']['version']
        self.assertEqual(Path(smoke[smoke.index('--package') + 1]).name,
                         f'Ranvier.WebCore.Native.Gpu.win-x64.{version}.nupkg')
        self.assertEqual(smoke[smoke.index('--expect-commit') + 1], HEAD)
        self.assertEqual(smoke[smoke.index('--expect-version') + 1], version)
        self.assertEqual(smoke[smoke.index('--expect-flavor') + 1], 'gpu')
        prepare = next(command for command in calls if 'prepare' in command)
        self.assertIn('--strict', prepare)
        for command in calls:
            if any(value.endswith('build.py') for value in command):
                self.assertEqual(command[command.index('--flavor') + 1], 'gpu')
                self.assertEqual(command[command.index('--version') + 1], version)
        self.assertFalse(any(command[0] == 'gh' for command in calls))

    def test_existing_slim_and_lean_package_names_remain_unchanged(self):
        version = json.loads((ROOT / 'pins.json').read_text())['package']['version']
        for flavor, suffix in [('slim', ''), ('lean', '.Lean')]:
            with self.subTest(flavor=flavor):
                code, calls = self.invoke(flavor)
                self.assertIsNone(code)
                smoke = next(command for command in calls if any(value.endswith('smoke.py') for value in command))
                self.assertEqual(Path(smoke[smoke.index('--package') + 1]).name,
                                 f'Ranvier.WebCore.Native{suffix}.win-x64.{version}.nupkg')

    def test_gpu_release_still_rejects_dirty_source(self):
        code, calls = self.invoke('gpu', dirty=True)
        self.assertIsInstance(code, str)
        self.assertIn('working tree has changes', code)
        self.assertFalse(any(any(value.endswith('build.py') for value in command) for command in calls))

    def test_gpu_release_still_rejects_an_existing_version_tag(self):
        code, calls = self.invoke('gpu', tagged=True)
        self.assertIsInstance(code, str)
        self.assertIn('exists on the remote', code)
        self.assertFalse(any(command[0] == 'gh' for command in calls))


if __name__ == '__main__':
    unittest.main()
