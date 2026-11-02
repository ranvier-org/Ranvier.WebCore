"""Extract exactly the selected native host from a verified producer artifact."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile


def validate_union_metadata(manifest, expected_source, rid, exports):
    if not re.fullmatch('[0-9a-f]{40}', expected_source or ''):
        raise ValueError('A final union source commit pin is required.')
    if manifest.get('abi') != 63:
        raise ValueError('The final host must declare ABI63.')
    source = manifest.get('source') or {}
    if manifest.get('rid') != rid or source.get('commit') != expected_source or source.get('dirty') is not False:
        raise ValueError('The artifact manifest must declare the requested RID and clean final union source.')
    required = {'rv_host_ime_surrounding', 'rv_host_ime_delete_surrounding', 'rv_ax_text_style_run'}
    if not required.issubset(exports):
        raise ValueError('The host lacks final171+182 union exports: ' + ', '.join(sorted(required - exports)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--rid', choices=['linux-x64', 'linux-arm64'], required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-abi63-union', action='store_true')
    parser.add_argument('--expected-source')
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
                manifest = json.loads(archive.read('manifest.json')) if args.require_abi63_union else None
                candidates.append((path, archive.read(member), manifest))
    if len(candidates) != 1:
        raise ValueError('The artifact must contain exactly one package for the selected RID.')
    package, data, manifest = candidates[0]
    actual = hashlib.sha256(data).hexdigest()
    if actual != args.expected_sha256:
        raise ValueError('The producer native host differs from the reviewed artifact.')
    if args.require_abi63_union:
        machine = {'linux-x64': 62, 'linux-arm64': 183}[args.rid]
        if data[:6] != b'\x7fELF\x02\x01' or int.from_bytes(data[18:20], 'little') != machine:
            raise ValueError('The union host ELF architecture differs from the requested RID.')
        with tempfile.TemporaryDirectory(prefix='atspi-union-gate-') as temporary:
            binary = Path(temporary) / 'host.so'
            binary.write_bytes(data)
            symbols = subprocess.check_output(['nm', '-D', '--defined-only', str(binary)], text=True)
        exports = {line.split()[-1] for line in symbols.splitlines() if line.split()}
        validate_union_metadata(manifest, args.expected_source, args.rid, exports)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'libRanvierWebCoreHost.so').write_bytes(data)
    receipt = dict(rid=args.rid, nativeSha256=actual,
        packageSha256=hashlib.sha256(package.read_bytes()).hexdigest(), packageName=package.name)
    if args.require_abi63_union:
        receipt.update(manifestDeclaredSource=manifest['source']['commit'], unionExportGatePassed=True,
            sourceProvenance='artifact-manifest-claim; compare independent producer receipts')
    (args.output / 'producer-receipt.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
