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
    def invoke(self, flavor, dirty=False, tagged=False, rids=('win-x64',), dry_run=True):
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

        arguments = ['release.py', '--flavor', flavor, '--work', str(ROOT / 'artifacts/release-proof')]
        for rid in rids:
            arguments.extend(['--rid', rid])
        if dry_run:
            arguments.append('--dry-run')
        transcript = io.StringIO()
        with patch.object(sys, 'argv', arguments), patch('subprocess.run', side_effect=run), contextlib.redirect_stdout(transcript):
            try:
                runpy.run_path(str(ROOT / 'scripts/release.py'), run_name='__main__')
            except SystemExit as completed:
                code = completed.code
            else:
                code = None
        self.transcript = transcript.getvalue()
        return code, calls

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

    def test_slim_release_checks_the_packaged_api_surface_after_smoke(self):
        code, calls = self.invoke('slim')
        self.assertIsNone(code)
        smoke_index = next(index for index, command in enumerate(calls) if any(value.endswith('smoke.py') for value in command))
        probe_index = next(index for index, command in enumerate(calls) if any(value.endswith('check_package_api.py') for value in command))
        self.assertGreater(probe_index, smoke_index)
        smoke, probe = calls[smoke_index], calls[probe_index]
        self.assertEqual(probe[probe.index('--package') + 1], smoke[smoke.index('--package') + 1])
        _, calls = self.invoke('lean')
        self.assertFalse(any(any(value.endswith('check_package_api.py') for value in command) for command in calls))

    def test_windows_gpu_release_checks_shared_frames_from_the_packed_payload(self):
        code, calls = self.invoke('gpu')
        self.assertIsNone(code)
        smoke_index = next(index for index, command in enumerate(calls) if any(value.endswith('smoke.py') for value in command))
        frame_checks = [(index, command) for index, command in enumerate(calls)
                        if any(value.endswith('check_package_api.py') for value in command)]
        self.assertEqual(len(frame_checks), 1)
        index, probe = frame_checks[0]
        self.assertGreater(index, smoke_index)
        self.assertIn('--gpu', probe)
        smoke = calls[smoke_index]
        self.assertEqual(probe[probe.index('--package') + 1], smoke[smoke.index('--package') + 1])

    def test_only_windows_x64_gpu_release_uses_automatic_only_guidance(self):
        self.invoke('gpu', dry_run=False)
        self.assertIn('automatically dispatches', self.transcript)
        self.assertNotIn('gh workflow run', self.transcript)
        for rids in [('linux-x64',), ('osx-arm64',), ('win-arm64',), ('win-x64', 'linux-x64')]:
            with self.subTest(rids=rids):
                self.invoke('gpu', rids=rids, dry_run=False)
                self.assertIn('gh workflow run', self.transcript)
                self.assertIn('--field flavor=gpu', self.transcript)
                self.assertIn('--field rids=' + ','.join(rids), self.transcript)

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
