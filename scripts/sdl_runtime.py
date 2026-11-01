"""Fetch the pinned SDL runtime used by the Windows native GPU acceptance executable."""

import argparse
import hashlib
from pathlib import Path
import urllib.request
import zipfile

VERSION = '2026.1002.1'
PACKAGE = f'ppy.sdl3-cs.{VERSION}.nupkg'
URL = f'https://api.nuget.org/v3-flatcontainer/ppy.sdl3-cs/{VERSION}/{PACKAGE}'
SHA256 = 'c5450151ffb6abf479d9cf6d36f331ff53ae3fbd4c6335f4ca86e6e104963568'
MEMBER = 'runtimes/win-x64/native/SDL3.dll'


def extract_runtime(archive, destination, expected_sha256):
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise ValueError(f'{archive}: SHA-256 {actual}, expected {expected_sha256}')
    with zipfile.ZipFile(archive) as package:
        payload = package.read(MEMBER)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / 'SDL3.dll'
    target.write_bytes(payload)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    archive = args.out / PACKAGE
    if not archive.exists():
        with urllib.request.urlopen(URL, timeout=120) as response:
            payload = response.read()
        actual = hashlib.sha256(payload).hexdigest()
        if actual != SHA256:
            raise ValueError(f'{URL}: SHA-256 {actual}, expected {SHA256}')
        archive.write_bytes(payload)
    target = extract_runtime(archive, args.out, SHA256)
    print(f'SDL3 {VERSION}: verified {SHA256}, staged {target}')


if __name__ == '__main__':
    main()
