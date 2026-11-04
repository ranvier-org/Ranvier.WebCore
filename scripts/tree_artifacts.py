"""Carries GPU build trees from one release tag's run to the next as workflow artifacts (docs/CI.md, "GPU build trees").

  tree_artifacts.py pack     --build DIR --output FILE                  write the tree as a gzip tar, keeping file times
  tree_artifacts.py restore  --build DIR --exact KEY --prefixes LINES    restore the best artifact into DIR's parent

The Actions cache holds no GPU tree: those trees do not fit beside the Slim trees within the repository's 10 GB, and
a tag run restores only the default branch's entries. An artifact is reachable from any later run and has its own
storage. An artifact is named by its tree's cache key, so restore applies the cache's own order: the exact key, else
the newest artifact under the first matching restore prefix.
"""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

MEMBER = 'tree.tar.gz'
# Every live artifact: the repository keeps about 4,200 over its 90-day retention, at 100 a page.
PAGES = 100


def tar_command():
    """GNU tar from Git for Windows on Windows, which handles the tree's long paths; the system tar elsewhere."""
    if os.name == 'nt':
        git_tar = pathlib.Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Git/usr/bin/tar.exe'
        if git_tar.exists():
            return [str(git_tar), '--force-local']
    return ['tar']


def pack(build: pathlib.Path, output: pathlib.Path):
    build = build.resolve()
    # Forward slashes: GNU tar on Windows reads a backslash in a path as an escape.
    subprocess.run([*tar_command(), '-czf', output.resolve().as_posix(), '-C', build.parent.as_posix(), build.name], check=True)


def choose(artifacts, exact, prefixes):
    """The artifact to restore: the unexpired one named `exact`, else the newest whose name starts with the first
    prefix any unexpired artifact matches; None without a match."""
    live = [a for a in artifacts if not a['expired']]
    for artifact in live:
        if artifact['name'] == exact:
            return artifact
    for prefix in prefixes:
        matches = [a for a in live if a['name'].startswith(prefix)]
        if matches:
            return max(matches, key=lambda a: a['created_at'])
    return None


def api(url, token):
    request = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}',
                                                   'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def listed(repository, token, exact, widest):
    """The repository's artifacts named `exact`, then those under `widest`, from the newest PAGES pages."""
    base = f"{os.environ.get('GITHUB_API_URL', 'https://api.github.com')}/repos/{repository}/actions/artifacts"
    found = api(f'{base}?per_page=100&name={exact}', token)['artifacts']
    for page in range(1, PAGES + 1):
        artifacts = api(f'{base}?per_page=100&page={page}', token)['artifacts']
        found += [a for a in artifacts if a['name'].startswith(widest)]
        if len(artifacts) < 100:
            break
    return found


def unpack(archive: pathlib.Path, build: pathlib.Path):
    """Streams the tarball out of the artifact zip into tar, so the tree and the tarball are never both on disk."""
    with zipfile.ZipFile(archive) as outer, outer.open(MEMBER) as member:
        tar = subprocess.Popen([*tar_command(), '-xzf', '-', '-C', build.parent.as_posix()], stdin=subprocess.PIPE)
        shutil.copyfileobj(member, tar.stdin, 1 << 20)
        tar.stdin.close()
        if tar.wait() != 0:
            raise RuntimeError(f'tar exited with {tar.returncode}')


def download(repository, artifact_id, target: pathlib.Path):
    """Through gh, which drops the token on the redirect to the pre-signed storage URL that rejects it."""
    with open(target, 'wb') as out:
        subprocess.run(['gh', 'api', f'repos/{repository}/actions/artifacts/{artifact_id}/zip'], stdout=out, check=True)


def restore(build: pathlib.Path, exact, prefixes, repository, token):
    """The restored artifact's key, or '' after a miss or a failure; a failure leaves no partial tree."""
    build = build.resolve()
    try:
        artifact = choose(listed(repository, token, exact, prefixes[-1]), exact, prefixes)
        if artifact is None:
            print(f'tree_artifacts: no artifact for {exact}', flush=True)
            return ''
        print(f"tree_artifacts: restoring {artifact['name']} ({artifact['size_in_bytes'] >> 20} MB)", flush=True)
        with tempfile.TemporaryDirectory(dir=build.parent) as temporary:
            archive = pathlib.Path(temporary) / 'artifact.zip'
            download(repository, artifact['id'], archive)
            shutil.rmtree(build, ignore_errors=True)
            unpack(archive, build)
        return artifact['name']
    except (OSError, RuntimeError, KeyError, ValueError, zipfile.BadZipFile, urllib.error.URLError,
            subprocess.CalledProcessError) as error:
        print(f'tree_artifacts: restore failed, building without a tree: {error}', flush=True)
        shutil.rmtree(build, ignore_errors=True)
        return ''


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('pack')
    p.add_argument('--build', required=True, type=pathlib.Path)
    p.add_argument('--output', required=True, type=pathlib.Path)
    r = sub.add_parser('restore')
    r.add_argument('--build', required=True, type=pathlib.Path)
    r.add_argument('--exact', required=True)
    r.add_argument('--prefixes', required=True, help='the restore prefixes, one per line, narrowest first')
    args = parser.parse_args()
    if args.command == 'pack':
        pack(args.build, args.output)
        return
    prefixes = [line.strip() for line in args.prefixes.splitlines() if line.strip()]
    matched = restore(args.build, args.exact, prefixes, os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as out:
            out.write(f'matched-key={matched}\n')


if __name__ == '__main__':
    sys.exit(main())
