"""Prints the build-win-slim object targets whose recorded dependencies include any of the given source files.

Reads ninja's dependency log read-only (`ninja -t deps`), so the build directory is not modified. Paths may use
either slash style and may be relative to C:/wk/src. Use the printed targets as the units a private builder must
recompile when a source patch changes those files (headers included).

  python -I units_for_headers.py Source/WebCore/loader/EmptyClients.h Source/WebCore/loader/EmptyFrameLoaderClient.h
  python -I units_for_headers.py --json <files...>        a JSON object: file -> sorted targets, plus "all"
"""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

BUILD = Path('C:/wk/build-win-slim')
SOURCE = Path('C:/wk/src')


def normalize(path):
    return os.path.normcase(os.path.normpath(str(path)))


parser = argparse.ArgumentParser()
parser.add_argument('files', nargs='+')
parser.add_argument('--json', action='store_true')
parser.add_argument('--build', default=str(BUILD))
arguments = parser.parse_args()
build = Path(arguments.build)
cache = (build / 'CMakeCache.txt').read_text()
ninja = re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$', cache, re.M).group(1)
watched = {}
for name in arguments.files:
    path = Path(name)
    if not path.is_absolute():
        path = SOURCE / path
    watched[normalize(path)] = name
before = {p: p.stat().st_mtime_ns for p in [build / '.ninja_deps', build / '.ninja_log'] if p.exists()}
output = subprocess.run([ninja, '-C', str(build), '-t', 'deps'], capture_output=True, text=True, check=True).stdout
assert before == {p: p.stat().st_mtime_ns for p in before}, 'the ninja logs changed during the scan'
hits = {name: set() for name in watched.values()}
target = None
for line in output.splitlines():
    if line and not line.startswith(' '):
        target = line.split(':', 1)[0].strip()
        continue
    dependency = line.strip()
    if not dependency or target is None:
        continue
    resolved = Path(dependency)
    if not resolved.is_absolute():
        resolved = build / resolved
    key = normalize(resolved)
    if key in watched:
        hits[watched[key]].add(target.replace('\\', '/'))
every = sorted(set().union(*hits.values()))
if arguments.json:
    print(json.dumps({**{name: sorted(t) for name, t in hits.items()}, 'all': every}, indent=1))
else:
    for name, targets in hits.items():
        print(f'# {name}: {len(targets)} targets')
    for item in every:
        print(item)
