"""Extract exactly the selected native host from a verified producer artifact."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--rid', choices=['linux-x64', 'linux-arm64'], required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{64}', args.expected_sha256):
        raise ValueError('A reviewed exact native SHA256 is required.')
    member = 'runtimes/' + args.rid + '/native/libRanvierWebCoreHost.so'
    candidates = []
    for path in args.artifacts.rglob('*.nupkg'):
        with zipfile.ZipFile(path) as archive:
            if member in archive.namelist():
                if archive.namelist().count(member) != 1:
                    raise ValueError('The native package has duplicate host entries.')
                candidates.append((path, archive.read(member)))
    if len(candidates) != 1:
        raise ValueError('The artifact must contain exactly one package for the selected RID.')
    package, data = candidates[0]
    actual = hashlib.sha256(data).hexdigest()
    if actual != args.expected_sha256:
        raise ValueError('The producer native host differs from the reviewed artifact.')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'libRanvierWebCoreHost.so').write_bytes(data)
    receipt = dict(rid=args.rid, nativeSha256=actual,
        packageSha256=hashlib.sha256(package.read_bytes()).hexdigest(), packageName=package.name)
    (args.output / 'producer-receipt.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
