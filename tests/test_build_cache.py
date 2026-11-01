import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'build_cache.py'
OLD_TIME = 1_700_000_000
FRESH_TIME = OLD_TIME + 300


def git(directory, *args):
    return subprocess.run(
        ['git', '-C', str(directory), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


class BuildCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ranvier-build-cache-')
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.repository = self.root / 'repository'
        self.build = self.root / 'build'
        self.source.mkdir()
        self.repository.mkdir()
        self.build.mkdir()
        self.prefix = self.source / 'JavaScriptCorePrefix.h'
        self.canonical = b'#pragma once\n#define CACHE_TEST 1\n'
        self.prefix.write_bytes(self.canonical)
        (self.source / '.gitattributes').write_text('* text eol=crlf\n', encoding='ascii')
        self.init_git(self.source)
        self.init_git(self.repository)
        (self.build / 'build.ninja').write_text('# fixture\n', encoding='utf-8')
        self.set_mtime(self.prefix, OLD_TIME)

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def init_git(directory):
        git(directory, 'init', '-q')
        git(directory, 'config', 'user.email', 'cache-test@example.invalid')
        git(directory, 'config', 'user.name', 'Cache Test')
        git(directory, 'config', 'core.autocrlf', 'true')
        git(directory, 'config', 'core.safecrlf', 'false')
        if any(path.name != '.git' for path in directory.iterdir()):
            git(directory, 'add', '--', '.')
            git(directory, 'commit', '-q', '-m', 'fixture')

    @staticmethod
    def set_mtime(path, seconds):
        os.utime(path, (seconds, seconds))

    def run_cache(self, command, clear_unknown=False):
        args = [
            sys.executable, '-I', str(SCRIPT), command,
            '--build', str(self.build),
            '--source', str(self.source),
            '--repository', str(self.repository),
        ]
        if clear_unknown:
            args.append('--clear-unknown')
        return subprocess.run(args, capture_output=True, text=True, check=False)

    def manifest(self):
        return json.loads((self.build / 'ranvier-sources.json').read_text(encoding='utf-8'))

    def test_lf_to_crlf_preserves_git_blob_but_not_cached_timestamp(self):
        self.assertEqual(git(self.source, 'status', '--porcelain'), '')
        self.assertEqual(self.run_cache('record').returncode, 0)
        old_blob = git(self.source, 'rev-parse', 'HEAD:JavaScriptCorePrefix.h')
        self.assertEqual(self.manifest()['trees']['webkit']['JavaScriptCorePrefix.h'][0], old_blob)

        self.prefix.write_bytes(self.canonical.replace(b'\n', b'\r\n'))
        # Verify Git's eol filter maps CRLF to the LF index blob, then exercise the clean-index path.
        git(self.source, 'update-index', '--assume-unchanged', 'JavaScriptCorePrefix.h')
        self.assertEqual(git(self.source, 'status', '--porcelain'), '')
        canonical_hash = subprocess.run(
            ['git', '-C', str(self.source), 'hash-object', '--path=JavaScriptCorePrefix.h', '--stdin'],
            input=self.canonical.replace(b'\n', b'\r\n'),
            capture_output=True,
            check=True,
        ).stdout.decode().strip()
        self.assertEqual(canonical_hash, old_blob)
        self.set_mtime(self.prefix, FRESH_TIME)

        result = self.run_cache('normalise')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(int(self.prefix.stat().st_mtime), FRESH_TIME, result.stdout)

    def test_unchanged_raw_bytes_still_reuse_the_recorded_timestamp(self):
        self.assertEqual(self.run_cache('record').returncode, 0)
        self.assertEqual(
            self.manifest()['trees']['webkit']['JavaScriptCorePrefix.h'][2],
            hashlib.sha256(self.canonical).hexdigest(),
        )
        self.set_mtime(self.prefix, FRESH_TIME)
        result = self.run_cache('normalise')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(int(self.prefix.stat().st_mtime), OLD_TIME, result.stdout)

    def test_legacy_manifest_without_raw_identity_is_a_cache_miss(self):
        self.assertEqual(self.run_cache('record').returncode, 0)
        manifest = self.manifest()
        manifest['format'] = 1
        manifest['trees']['webkit']['JavaScriptCorePrefix.h'] = manifest['trees']['webkit']['JavaScriptCorePrefix.h'][:2]
        (self.build / 'ranvier-sources.json').write_text(json.dumps(manifest), encoding='utf-8')
        self.set_mtime(self.prefix, FRESH_TIME)

        result = self.run_cache('normalise', clear_unknown=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(int(self.prefix.stat().st_mtime), FRESH_TIME, result.stdout)
        self.assertGreaterEqual(self.manifest()['format'], 2)

    def test_missing_manifest_requires_explicit_clear_and_clears_build_outputs(self):
        sentinel = self.build / 'stale-object.obj'
        sentinel.write_bytes(b'stale object')
        without_clear = self.run_cache('normalise')
        self.assertNotEqual(without_clear.returncode, 0)
        self.assertTrue(sentinel.exists())

        with_clear = self.run_cache('normalise', clear_unknown=True)
        self.assertEqual(with_clear.returncode, 0, with_clear.stderr)
        self.assertFalse(sentinel.exists())
        self.assertEqual(int(self.prefix.stat().st_mtime), OLD_TIME)


if __name__ == '__main__':
    unittest.main()
