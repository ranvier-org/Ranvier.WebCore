import importlib.util
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('sccache_cache_policy', ROOT / 'scripts/sccache_cache_policy.py')
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class SccacheCachePolicyTests(unittest.TestCase):
    def eligible(self, **overrides):
        values = {
            'usage_bytes': 9_000_000_000,
            'preflight_usage_bytes': 9_000_000_000,
            'cache_bytes': 100 * 1024 * 1024,
            'cache_objects': 1,
            'event_name': 'push',
            'ref': 'refs/heads/main',
            'cohort': 'windows-x64-release',
            'compile_succeeded': True,
            'weekly_key_exists': False,
            'previous_prefix_pruned': True,
        }
        values.update(overrides)
        return policy.decide_save(**values)

    def test_allows_a_bounded_main_release_save_with_headroom(self):
        result = self.eligible()
        self.assertTrue(result.save)
        self.assertEqual(result.reason, 'eligible')

    def test_skips_when_usage_api_is_unavailable(self):
        result = self.eligible(usage_bytes=None)
        self.assertFalse(result.save)
        self.assertEqual(result.reason, 'usage-unavailable')

    def test_usage_reader_fails_closed_when_the_api_is_unavailable(self):
        def unavailable(_request, timeout):
            self.assertEqual(timeout, 20)
            raise OSError('offline')

        self.assertIsNone(policy.fetch_cache_usage('https://api.github.test/usage', 'secret', unavailable))

    def test_usage_reader_accepts_only_a_valid_github_usage_payload(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps({'active_caches_size_in_bytes': 9_000_000_000,
                                   'active_caches_count': 18}).encode()

        def open_usage(request, timeout):
            self.assertEqual(request.get_header('Authorization'), 'Bearer test-token')
            self.assertEqual(timeout, 20)
            return Response()

        self.assertEqual(policy.fetch_cache_usage('https://api.github.test/usage', 'test-token', open_usage),
                         9_000_000_000)
        self.assertIsNone(policy.fetch_cache_usage('https://api.github.test/usage', '', open_usage))

    def test_usage_reader_rejects_non_documented_or_malformed_usage_payloads(self):
        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return self.payload

        for payload in [
            json.dumps({'total_cache_size_in_bytes': 9_000_000_000}).encode(),
            json.dumps({'active_caches_size_in_bytes': -1}).encode(),
            json.dumps({'active_caches_size_in_bytes': '9000000000'}).encode(),
            b'not json',
        ]:
            with self.subTest(payload=payload):
                usage = policy.fetch_cache_usage('https://api.github.test/usage', 'test-token',
                                                lambda *_args, **_kwargs: Response(payload))
                self.assertIsNone(usage)

    def test_skips_when_concurrent_cache_growth_consumes_reserved_headroom(self):
        result = self.eligible(preflight_usage_bytes=9_000_000_000, usage_bytes=9_500_000_000)
        self.assertFalse(result.save)
        self.assertEqual(result.reason, 'insufficient-headroom')

    def test_budget_uses_the_final_read_after_prefix_cleanup(self):
        self.assertEqual(policy.combine_usage_reads(9_000_000_000, 9_500_000_000), 9_500_000_000)
        self.assertEqual(policy.combine_usage_reads(9_500_000_000, 9_000_000_000), 9_000_000_000)
        self.assertIsNone(policy.combine_usage_reads(None, 9_000_000_000))
        self.assertIsNone(policy.combine_usage_reads(9_000_000_000, None))

    def test_preflight_and_final_gate_make_two_api_reads_and_use_the_final_growth(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'cache'
            object_key = 'af' + '1' * 62
            object_path = cache / object_key[0] / object_key[1] / object_key
            object_path.parent.mkdir(parents=True)
            object_path.write_bytes(b'cache object')
            output = Path(directory) / 'github-output'
            with patch.object(policy, 'fetch_cache_usage', side_effect=[9_000_000_000, 9_500_000_000]) as fetch:
                policy.main(['preflight', '--usage-url', 'https://api.github.test/usage', '--token', 'secret',
                             '--github-output', str(output)])
                first_output = output.read_text()
                policy.main(['gate', '--cache-dir', str(cache), '--usage-url', 'https://api.github.test/usage',
                             '--token', 'secret', '--cohort', policy.SUPPORTED_COHORT, '--compile-succeeded',
                             '--previous-prefix-pruned', '--preflight-usage', '9000000000',
                             '--event-name', 'push', '--ref', 'refs/heads/main',
                             '--github-output', str(output)])
            self.assertEqual(fetch.call_count, 2)
            self.assertIn('budget_ok=true', first_output)
            self.assertIn('usage_available=true', first_output)
            self.assertIn('save=false', output.read_text())
            self.assertIn('reason=insufficient-headroom', output.read_text())

    def test_final_gate_cli_allows_save_after_successful_compile_and_all_other_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'cache'
            object_key = 'af' + '1' * 62
            object_path = cache / object_key[0] / object_key[1] / object_key
            object_path.parent.mkdir(parents=True)
            object_path.write_bytes(b'cache object')
            output = Path(directory) / 'github-output'
            with patch.object(policy, 'fetch_cache_usage', return_value=9_000_000_000):
                policy.main(['gate', '--cache-dir', str(cache), '--usage-url', 'https://api.github.test/usage',
                             '--token', 'secret', '--cohort', policy.SUPPORTED_COHORT,
                             '--preflight-usage', '9000000000', '--event-name', 'push', '--ref', 'refs/heads/main',
                             '--compile-succeeded', '--previous-prefix-pruned', '--github-output', str(output)])
            self.assertIn('save=true', output.read_text())
            self.assertIn('reason=eligible', output.read_text())

    def test_prefix_cleanup_deletes_only_old_main_sccache_entries(self):
        entries = [
            {'id': 10, 'key': policy.CACHE_PREFIX + '2026-W43', 'ref': 'refs/heads/main'},
            {'id': 11, 'key': policy.CACHE_PREFIX + '2026-W44', 'ref': 'refs/heads/main'},
            {'id': 12, 'key': policy.CACHE_PREFIX + '2026-W43', 'ref': 'refs/heads/codex/other'},
            {'id': 13, 'key': 'webkit-tree-main', 'ref': 'refs/heads/main'},
        ]
        deleted = []

        class Response:
            def __init__(self, payload=b''):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return self.payload

        def api(request, timeout):
            self.assertEqual(timeout, 20)
            if request.get_method() == 'GET':
                self.assertIn('ref=refs%2Fheads%2Fmain', request.full_url)
                return Response(json.dumps({'total_count': len(entries), 'actions_caches': entries}).encode())
            deleted.append(request.full_url.rsplit('/', 1)[-1])
            return Response()

        result = policy.cleanup_main_prefix('https://api.github.test', 'test-token', 'ranvier-org/Ranvier.WebCore',
                                            policy.CACHE_PREFIX + '2026-W44', 'push', 'refs/heads/main', api)
        self.assertTrue(result.success)
        self.assertEqual(result.deleted_count, 1)
        self.assertEqual(deleted, ['10'])

    def test_prefix_cleanup_refuses_non_main_without_calling_the_api(self):
        def unexpected(*_args, **_kwargs):
            self.fail('cleanup must not call the API for an untrusted ref')

        result = policy.cleanup_main_prefix('https://api.github.test', 'test-token', 'ranvier-org/Ranvier.WebCore',
                                            policy.CACHE_PREFIX + '2026-W44', 'pull_request',
                                            'refs/pull/7/merge', unexpected)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, 'untrusted-writer')

    def test_saved_cache_size_is_verified_against_the_exact_main_entry(self):
        entries = [{'id': 15, 'key': policy.CACHE_PREFIX + '2026-W44', 'ref': 'refs/heads/main',
                    'size_in_bytes': 250 * 1024 * 1024}]

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return json.dumps({'total_count': 1, 'actions_caches': entries}).encode()

        def api(request, timeout):
            self.assertEqual(request.get_method(), 'GET')
            self.assertIn('key=' + policy.CACHE_PREFIX, request.full_url)
            self.assertIn('ref=refs%2Fheads%2Fmain', request.full_url)
            return Response()

        result = policy.verify_saved_cache_size(
            'https://api.github.test', 'test-token', 'ranvier-org/Ranvier.WebCore', entries[0]['key'],
            'push', 'refs/heads/main', api)
        self.assertTrue(result.verified)
        self.assertFalse(result.deleted)
        self.assertEqual(result.size_bytes, 250 * 1024 * 1024)

    def test_oversized_saved_cache_is_deleted_by_its_exact_main_cache_id(self):
        entries = [{'id': 16, 'key': policy.CACHE_PREFIX + '2026-W44', 'ref': 'refs/heads/main',
                    'size_in_bytes': 256 * 1024 * 1024 + 1}]
        deleted = []

        class Response:
            def __init__(self, payload=b''):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return self.payload

        def api(request, timeout):
            if request.get_method() == 'GET':
                return Response(json.dumps({'total_count': 1, 'actions_caches': entries}).encode())
            deleted.append(request.full_url)
            return Response()

        result = policy.verify_saved_cache_size(
            'https://api.github.test', 'test-token', 'ranvier-org/Ranvier.WebCore', entries[0]['key'],
            'push', 'refs/heads/main', api)
        self.assertFalse(result.verified)
        self.assertTrue(result.deleted)
        self.assertEqual(result.reason, 'archive-too-large')
        self.assertEqual(deleted, ['https://api.github.test/repos/ranvier-org/Ranvier.WebCore/actions/caches/16'])

    def test_skips_an_archive_over_the_hard_size_limit(self):
        result = self.eligible(cache_bytes=256 * 1024 * 1024 + 1)
        self.assertFalse(result.save)
        self.assertEqual(result.reason, 'archive-too-large')

    def test_skips_a_cache_with_no_compiler_objects_even_when_metadata_has_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'cache'
            cache.mkdir()
            (cache / 'stats.json').write_text('{"requests": 0}')
            self.assertGreater(policy.cache_directory_size(cache), 0)
            self.assertEqual(policy.cache_object_count(cache), 0)
            output = Path(directory) / 'github-output'
            with patch.object(policy, 'fetch_cache_usage', return_value=9_000_000_000):
                policy.main(['gate', '--cache-dir', str(cache), '--usage-url', 'https://api.github.test/usage',
                             '--token', 'secret', '--cohort', policy.SUPPORTED_COHORT,
                             '--preflight-usage', '9000000000', '--event-name', 'push', '--ref', 'refs/heads/main',
                             '--compile-succeeded', '--previous-prefix-pruned', '--github-output', str(output)])
            self.assertIn('save=false', output.read_text())
            self.assertIn('reason=empty-cache', output.read_text())

    def test_sccache_bucket_object_shape_is_counted_as_compiler_output(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'cache'
            object_key = 'af' + '1' * 62
            object_path = cache / object_key[0] / object_key[1] / object_key
            object_path.parent.mkdir(parents=True)
            object_path.write_bytes(b'compiled object')
            self.assertEqual(policy.cache_object_count(cache), 1)

            malformed = cache / 'stats' / 'not-a-cache-key'
            malformed.parent.mkdir()
            malformed.write_bytes(b'ignored metadata')
            wrong_bucket = cache / 'b' / object_key[1] / object_key
            wrong_bucket.parent.mkdir(parents=True)
            wrong_bucket.write_bytes(b'not a valid bucket entry')
            self.assertEqual(policy.cache_object_count(cache), 1)

    def test_skips_writes_outside_the_single_trusted_cohort(self):
        for event, ref, cohort in [
            ('pull_request', 'refs/pull/12/merge', 'windows-x64-release'),
            ('push', 'refs/heads/feature', 'windows-x64-release'),
            ('push', 'refs/heads/main', 'windows-arm64-release'),
        ]:
            with self.subTest(event=event, ref=ref, cohort=cohort):
                result = self.eligible(event_name=event, ref=ref, cohort=cohort)
                self.assertFalse(result.save)
                self.assertEqual(result.reason, 'untrusted-writer')

    def test_skips_failed_compile_existing_weekly_entry_or_unpruned_old_prefix(self):
        for overrides, reason in [
            ({'compile_succeeded': False}, 'compile-failed'),
            ({'weekly_key_exists': True}, 'weekly-key-exists'),
            ({'previous_prefix_pruned': False}, 'prefix-cleanup-failed'),
        ]:
            with self.subTest(reason=reason):
                result = self.eligible(**overrides)
                self.assertFalse(result.save)
                self.assertEqual(result.reason, reason)

    def test_pins_the_reviewed_windows_binary_release(self):
        self.assertEqual(policy.SCCACHE_VERSION, '0.19.0')
        self.assertEqual(policy.SCCACHE_ARCHIVE_SHA256,
                         '28be8c61f6b2c89b9eb2869f6af7f78e6f992e78a8abae0ce855fcc129cbeac1')
        self.assertEqual(policy.ARCHIVE_MEMBER,
                         'sccache-v0.19.0-x86_64-pc-windows-msvc/sccache.exe')

    def test_weekly_cache_key_uses_utc_iso_week_without_a_commit_sha(self):
        self.assertEqual(policy.weekly_cache_key(datetime(2021, 1, 1, tzinfo=timezone.utc)),
                         policy.CACHE_PREFIX + '2020-W53')

    def test_installs_only_the_checksum_verified_windows_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'fixture.zip'
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('sccache-v0.19.0-x86_64-pc-windows-msvc/sccache.exe',
                                 b'pinned executable fixture')
                package.writestr('../../unexpected.exe', b'do not extract')
            payload = archive.read_bytes()

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    return False

                def read(self):
                    return payload

            with patch.object(policy, 'SCCACHE_ARCHIVE_SHA256', hashlib.sha256(payload).hexdigest()):
                executable = policy.install_sccache(Path(directory) / 'out', lambda *_args, **_kwargs: Response())
            self.assertEqual(executable.read_bytes(), b'pinned executable fixture')
            self.assertEqual(list(executable.parent.iterdir()), [executable])
            self.assertFalse((Path(directory) / 'unexpected.exe').exists())

    def test_rejects_a_checksum_mismatch_before_extracting_sccache(self):
        with tempfile.TemporaryDirectory() as directory:
            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    return False

                def read(self):
                    return b'not the pinned archive'

            with self.assertRaisesRegex(ValueError, 'SHA-256'), \
                    patch.object(policy, 'SCCACHE_ARCHIVE_SHA256', '0' * 64):
                policy.install_sccache(Path(directory) / 'out', lambda *_args, **_kwargs: Response())
            self.assertFalse((Path(directory) / 'out').exists())

    def test_cache_directory_size_counts_nested_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'one').write_bytes(b'123')
            nested = root / 'nested'
            nested.mkdir()
            (nested / 'two').write_bytes(b'4567')
            self.assertEqual(policy.cache_directory_size(root), 7)

    def test_cache_directory_size_fails_closed_when_directory_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(policy.cache_directory_size(Path(directory) / 'missing'))
            result = self.eligible(cache_bytes=None)
            self.assertFalse(result.save)
            self.assertEqual(result.reason, 'cache-size-unavailable')


if __name__ == '__main__':
    unittest.main()
