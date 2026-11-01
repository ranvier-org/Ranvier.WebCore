"""Bound and fail closed when deciding whether to persist the Windows sccache archive."""

from dataclasses import dataclass
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

SCCACHE_VERSION = '0.19.0'
SCCACHE_ARCHIVE = f'sccache-v{SCCACHE_VERSION}-x86_64-pc-windows-msvc.zip'
SCCACHE_URL = f'https://github.com/mozilla/sccache/releases/download/v{SCCACHE_VERSION}/{SCCACHE_ARCHIVE}'
SCCACHE_ARCHIVE_SHA256 = '28be8c61f6b2c89b9eb2869f6af7f78e6f992e78a8abae0ce855fcc129cbeac1'

REPOSITORY_BUDGET_BYTES = 10_000_000_000
RESERVED_HEADROOM_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
LOCAL_CACHE_SIZE = '192M'
SAVE_THRESHOLD_BYTES = REPOSITORY_BUDGET_BYTES - RESERVED_HEADROOM_BYTES
USAGE_REFRESH_SECONDS = 300
SUPPORTED_COHORT = 'windows-x64-release'
CACHE_PREFIX = 'sccache-win-x64-release-clang23-v1-'
ARCHIVE_MEMBER = f'sccache-v{SCCACHE_VERSION}-x86_64-pc-windows-msvc/sccache.exe'
EXECUTABLE_NAME = 'sccache.exe'


@dataclass(frozen=True)
class Decision:
    save: bool
    reason: str


@dataclass(frozen=True)
class CleanupResult:
    success: bool
    deleted_count: int
    reason: str


@dataclass(frozen=True)
class VerifyResult:
    verified: bool
    deleted: bool
    size_bytes: int | None
    reason: str


def weekly_cache_key(instant=None):
    """Return the stable sccache key for the UTC ISO week, independent of commit SHA."""
    instant = instant or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    week = instant.astimezone(timezone.utc).isocalendar()
    return f'{CACHE_PREFIX}{week.year}-W{week.week:02d}'


def combine_usage_reads(preflight_usage_bytes, final_usage_bytes):
    """Require both observations and gate on the final post-build/post-cleanup reading.

    GitHub refreshes usage asynchronously (about every five minutes). The later read is the
    relevant one after removing the prior sccache prefix; the repository reserve absorbs
    bounded concurrent writes and any remaining reporting lag.
    """
    values = (preflight_usage_bytes, final_usage_bytes)
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
        return None
    return final_usage_bytes


def decide_save(*, usage_bytes, preflight_usage_bytes, cache_bytes, cache_objects, event_name, ref, cohort,
                compile_succeeded, weekly_key_exists, previous_prefix_pruned):
    """Return whether one weekly cache archive may be saved, with a stable diagnostic reason."""
    if event_name != 'push' or ref != 'refs/heads/main' or cohort != SUPPORTED_COHORT:
        return Decision(False, 'untrusted-writer')
    if not compile_succeeded:
        return Decision(False, 'compile-failed')
    if weekly_key_exists:
        return Decision(False, 'weekly-key-exists')
    usage = combine_usage_reads(preflight_usage_bytes, usage_bytes)
    if usage is None:
        return Decision(False, 'usage-unavailable')
    if usage > SAVE_THRESHOLD_BYTES:
        return Decision(False, 'insufficient-headroom')
    if not isinstance(cache_bytes, int) or isinstance(cache_bytes, bool) or cache_bytes < 0:
        return Decision(False, 'cache-size-unavailable')
    if not isinstance(cache_objects, int) or isinstance(cache_objects, bool) or cache_objects < 0:
        return Decision(False, 'cache-objects-unavailable')
    if cache_objects == 0:
        return Decision(False, 'empty-cache')
    if cache_bytes > MAX_ARCHIVE_BYTES:
        return Decision(False, 'archive-too-large')
    if not previous_prefix_pruned:
        return Decision(False, 'prefix-cleanup-failed')
    return Decision(True, 'eligible')


def cache_directory_size(directory):
    """Return the sum of regular files below directory, or None if it cannot be measured."""
    root = Path(directory)
    if not root.is_dir():
        return None
    try:
        return sum(path.stat().st_size for path in root.rglob('*') if path.is_file())
    except OSError:
        return None


def cache_object_count(directory):
    """Count nonempty sccache disk-cache objects, excluding metadata and unrelated files.

    sccache 0.19.0 stores each object under two one-character hex bucket directories,
    followed by a 64-character lowercase hex key. A tiny real clang-cl compile produced
    `a/f/af...` with the bucket characters matching the key prefix.
    """
    root = Path(directory)
    if not root.is_dir():
        return None
    count = 0
    try:
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            key = path.name
            if (len(key) == 64 and all(char in '0123456789abcdef' for char in key)
                    and path.parent.name == key[1] and path.parent.parent.name == key[0]
                    and path.stat().st_size > 0):
                count += 1
        return count
    except OSError:
        return None


def fetch_cache_usage(url, token, opener=urllib.request.urlopen):
    """Read the GitHub repository cache usage count without exposing credentials in errors."""
    if not url or not token:
        return None
    request = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {token}',
            'X-GitHub-Api-Version': '2022-11-28',
        },
    )
    try:
        with opener(request, timeout=20) as response:
            payload = json.loads(response.read())
        usage = payload['active_caches_size_in_bytes']
        if not isinstance(usage, int) or isinstance(usage, bool) or usage < 0:
            return None
        return usage
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        return None


def install_sccache(destination, opener=urllib.request.urlopen):
    """Download and verify the pinned official Windows archive, then extract only sccache.exe."""
    with opener(SCCACHE_URL, timeout=120) as response:
        archive = response.read()
    actual = hashlib.sha256(archive).hexdigest()
    if actual != SCCACHE_ARCHIVE_SHA256:
        raise ValueError(f'{SCCACHE_URL}: SHA-256 {actual} does not match the pinned release')
    with zipfile.ZipFile(io.BytesIO(archive)) as package:
        executable_payload = package.read(ARCHIVE_MEMBER)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    executable = destination / EXECUTABLE_NAME
    executable.write_bytes(executable_payload)
    return executable


def cleanup_main_prefix(api_url, token, repository, current_key, event_name, ref,
                        opener=urllib.request.urlopen):
    """Delete only obsolete cache IDs under the approved prefix and main ref."""
    if event_name != 'push' or ref != 'refs/heads/main':
        return CleanupResult(False, 0, 'untrusted-writer')
    if not api_url or not token or not repository or not current_key.startswith(CACHE_PREFIX):
        return CleanupResult(False, 0, 'cleanup-input-invalid')
    headers = {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    entries = []
    try:
        page = 1
        while True:
            query = urllib.parse.urlencode({'per_page': 100, 'ref': 'refs/heads/main', 'page': page})
            request = urllib.request.Request(
                f'{api_url.rstrip("/")}/repos/{repository}/actions/caches?{query}', headers=headers)
            with opener(request, timeout=20) as response:
                payload = json.loads(response.read())
            records = payload['actions_caches']
            if not isinstance(records, list):
                return CleanupResult(False, 0, 'cleanup-response-invalid')
            for entry in records:
                if not isinstance(entry, dict) or not {'id', 'key', 'ref'} <= entry.keys():
                    return CleanupResult(False, 0, 'cleanup-response-invalid')
                if (entry['ref'] == 'refs/heads/main' and isinstance(entry['key'], str)
                        and entry['key'].startswith(CACHE_PREFIX) and entry['key'] != current_key):
                    cache_id = entry['id']
                    if not isinstance(cache_id, int) or isinstance(cache_id, bool) or cache_id <= 0:
                        return CleanupResult(False, 0, 'cleanup-response-invalid')
                    entries.append(cache_id)
            if len(records) < 100:
                break
            page += 1
        for cache_id in entries:
            request = urllib.request.Request(
                f'{api_url.rstrip("/")}/repos/{repository}/actions/caches/{cache_id}',
                headers=headers, method='DELETE')
            with opener(request, timeout=20) as response:
                response.read()
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        return CleanupResult(False, 0, 'cleanup-api-unavailable')
    return CleanupResult(True, len(entries), 'pruned')


def verify_saved_cache_size(api_url, token, repository, current_key, event_name, ref,
                            opener=urllib.request.urlopen):
    """Verify one saved main entry and delete it by exact ID if its stored archive is oversized."""
    if event_name != 'push' or ref != 'refs/heads/main':
        return VerifyResult(False, False, None, 'untrusted-writer')
    if not api_url or not token or not repository or not current_key.startswith(CACHE_PREFIX):
        return VerifyResult(False, False, None, 'verify-input-invalid')
    headers = {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    query = urllib.parse.urlencode({'key': current_key, 'per_page': 100, 'ref': 'refs/heads/main'})
    try:
        request = urllib.request.Request(
            f'{api_url.rstrip("/")}/repos/{repository}/actions/caches?{query}', headers=headers)
        with opener(request, timeout=20) as response:
            payload = json.loads(response.read())
        records = payload['actions_caches']
        if not isinstance(records, list):
            return VerifyResult(False, False, None, 'verify-response-invalid')
        entry = next((item for item in records if isinstance(item, dict)
                      and item.get('key') == current_key and item.get('ref') == 'refs/heads/main'), None)
        if entry is None:
            return VerifyResult(False, False, None, 'saved-entry-not-found')
        cache_id, size = entry.get('id'), entry.get('size_in_bytes')
        if (not isinstance(cache_id, int) or isinstance(cache_id, bool) or cache_id <= 0
                or not isinstance(size, int) or isinstance(size, bool) or size < 0):
            return VerifyResult(False, False, None, 'verify-response-invalid')
        if size <= MAX_ARCHIVE_BYTES:
            return VerifyResult(True, False, size, 'within-limit')
        delete = urllib.request.Request(
            f'{api_url.rstrip("/")}/repos/{repository}/actions/caches/{cache_id}',
            headers=headers, method='DELETE')
        with opener(delete, timeout=20) as response:
            response.read()
        return VerifyResult(False, True, size, 'archive-too-large')
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        return VerifyResult(False, False, None, 'verify-api-unavailable')


def _write_output(path, decision):
    if path:
        with open(path, 'a', encoding='utf-8', newline='') as output:
            output.write(f'save={str(decision.save).lower()}\n')
            output.write(f'reason={decision.reason}\n')


def _write_preflight(path, usage):
    available = isinstance(usage, int) and not isinstance(usage, bool) and usage >= 0
    budget_ok = available and usage <= SAVE_THRESHOLD_BYTES
    if path:
        with open(path, 'a', encoding='utf-8', newline='') as output:
            output.write(f'usage_bytes={usage if available else ""}\n')
            output.write(f'usage_available={str(available).lower()}\n')
            output.write(f'budget_ok={str(budget_ok).lower()}\n')
    print(f'sccache cache preflight budget_ok={str(budget_ok).lower()}')


def _write_cleanup(path, result):
    if path:
        with open(path, 'a', encoding='utf-8', newline='') as output:
            output.write(f'previous_prefix_pruned={str(result.success).lower()}\n')
            output.write(f'cleanup_deleted_count={result.deleted_count}\n')
            output.write(f'cleanup_reason={result.reason}\n')
    print(f'sccache cache cleanup success={str(result.success).lower()} '
          f'deleted={result.deleted_count} reason={result.reason}')


def _write_verify(path, result):
    if path:
        with open(path, 'a', encoding='utf-8', newline='') as output:
            output.write(f'verified={str(result.verified).lower()}\n')
            output.write(f'verified_size_bytes={result.size_bytes if result.size_bytes is not None else ""}\n')
            output.write(f'removed_oversized_cache={str(result.deleted).lower()}\n')
            output.write(f'verify_reason={result.reason}\n')
    print(f'sccache cache verified={str(result.verified).lower()} size={result.size_bytes} '
          f'deleted={str(result.deleted).lower()} reason={result.reason}')


def _parse_usage(value):
    if not value or not value.isdecimal():
        return None
    return int(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    install = subparsers.add_parser('install', help='download the pinned Windows x64 sccache release')
    install.add_argument('--out', type=Path, required=True)
    preflight = subparsers.add_parser('preflight', help='read cache usage before the native build')
    preflight.add_argument('--usage-url', default=os.environ.get('SCCACHE_USAGE_URL'))
    preflight.add_argument('--token', default=os.environ.get('GITHUB_TOKEN'))
    preflight.add_argument('--github-output', default=os.environ.get('GITHUB_OUTPUT'))
    cleanup = subparsers.add_parser('cleanup', help='prune obsolete entries in the exact main sccache prefix')
    cleanup.add_argument('--api-url', default=os.environ.get('GITHUB_API_URL'))
    cleanup.add_argument('--token', default=os.environ.get('GITHUB_TOKEN'))
    cleanup.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'))
    cleanup.add_argument('--current-key', required=True)
    cleanup.add_argument('--event-name', default=os.environ.get('GITHUB_EVENT_NAME', ''))
    cleanup.add_argument('--ref', default=os.environ.get('GITHUB_REF', ''))
    cleanup.add_argument('--github-output', default=os.environ.get('GITHUB_OUTPUT'))
    verify = subparsers.add_parser('verify', help='check the saved main cache size and remove only an oversized key')
    verify.add_argument('--api-url', default=os.environ.get('GITHUB_API_URL'))
    verify.add_argument('--token', default=os.environ.get('GITHUB_TOKEN'))
    verify.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'))
    verify.add_argument('--current-key', required=True)
    verify.add_argument('--event-name', default=os.environ.get('GITHUB_EVENT_NAME', ''))
    verify.add_argument('--ref', default=os.environ.get('GITHUB_REF', ''))
    verify.add_argument('--github-output', default=os.environ.get('GITHUB_OUTPUT'))
    key = subparsers.add_parser('key', help='write the stable UTC ISO-week cache key')
    key.add_argument('--github-output', default=os.environ.get('GITHUB_OUTPUT'))
    gate = subparsers.add_parser('gate', help='make a final fail-closed Actions-cache save decision')
    gate.add_argument('--cache-dir', type=Path, required=True)
    gate.add_argument('--usage-url', default=os.environ.get('SCCACHE_USAGE_URL'))
    gate.add_argument('--token', default=os.environ.get('GITHUB_TOKEN'))
    gate.add_argument('--cohort', default='')
    gate.add_argument('--compile-succeeded', action='store_true')
    gate.add_argument('--weekly-key-exists', action='store_true')
    gate.add_argument('--previous-prefix-pruned', action='store_true')
    gate.add_argument('--preflight-usage', default='')
    gate.add_argument('--event-name', default=os.environ.get('GITHUB_EVENT_NAME', ''))
    gate.add_argument('--ref', default=os.environ.get('GITHUB_REF', ''))
    gate.add_argument('--github-output', default=os.environ.get('GITHUB_OUTPUT'))
    args = parser.parse_args(argv)
    if args.command == 'install':
        executable = install_sccache(args.out)
        print(f'sccache {SCCACHE_VERSION}: verified {SCCACHE_ARCHIVE_SHA256}, staged {executable}')
        return 0
    if args.command == 'preflight':
        usage = fetch_cache_usage(args.usage_url, args.token)
        _write_preflight(args.github_output, usage)
        return 0
    if args.command == 'cleanup':
        result = cleanup_main_prefix(args.api_url, args.token, args.repository, args.current_key,
                                     args.event_name, args.ref)
        _write_cleanup(args.github_output, result)
        return 0
    if args.command == 'verify':
        result = verify_saved_cache_size(args.api_url, args.token, args.repository, args.current_key,
                                         args.event_name, args.ref)
        _write_verify(args.github_output, result)
        return 0
    if args.command == 'key':
        value = weekly_cache_key()
        if args.github_output:
            with open(args.github_output, 'a', encoding='utf-8', newline='') as output:
                output.write(f'key={value}\n')
        print(f'key={value}')
        return 0
    usage = fetch_cache_usage(args.usage_url, args.token)
    size = cache_directory_size(args.cache_dir)
    objects = cache_object_count(args.cache_dir)
    decision = decide_save(
        usage_bytes=usage,
        preflight_usage_bytes=_parse_usage(args.preflight_usage),
        cache_bytes=size,
        cache_objects=objects,
        event_name=args.event_name,
        ref=args.ref,
        cohort=args.cohort,
        compile_succeeded=args.compile_succeeded,
        weekly_key_exists=args.weekly_key_exists,
        previous_prefix_pruned=args.previous_prefix_pruned,
    )
    _write_output(args.github_output, decision)
    print(f'sccache cache save={str(decision.save).lower()} objects={objects} reason={decision.reason}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
