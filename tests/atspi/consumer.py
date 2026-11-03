"""Publish an ordinary PackageReference consumer and load its exact optional native asset."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile


def select_runtime(manifest, rid):
    schema = manifest.get('schemaVersion', 1)
    if type(schema) is not int or schema not in [1, 2]:
        raise ValueError('Unsupported provider manifest schema.')
    if type(manifest.get('abi')) is not int or manifest['abi'] != 63 or manifest.get('hostBundled') is not False:
        raise ValueError('Require the ABI63 optional provider without a bundled Host.')
    if schema == 2:
        runtimes = manifest.get('runtimes')
        if not rid or not isinstance(runtimes, dict) or rid not in runtimes:
            raise ValueError('Select an explicit RID present in the aggregate manifest.')
        selected = runtimes[rid]
    else:
        if rid is not None and rid != manifest.get('rid'):
            raise ValueError('Selected RID differs from the per-RID manifest.')
        rid = manifest.get('rid')
        selected = manifest
    if (rid not in ['linux-x64', 'linux-arm64'] or not isinstance(selected, dict)
            or selected.get('rid') != rid or type(selected.get('abi')) is not int or selected['abi'] != 63):
        raise ValueError('Selected runtime RID/ABI record is malformed.')
    for field in ['hostSha256', 'providerSha256']:
        if not isinstance(selected.get(field), str) or not re.fullmatch('[0-9a-f]{64}', selected[field]):
            raise ValueError('Selected runtime requires an exact lowercase ' + field + '.')
    return selected


def verify_selected_asset(publish, selected):
    module = publish / 'libRanvierWebCoreAtspi.so'
    if not module.is_file() or hashlib.sha256(module.read_bytes()).hexdigest() != selected['providerSha256']:
        raise ValueError('Published provider differs from the selected runtime hash.')
    data = module.read_bytes()
    if data[:6] != b'\x7fELF\x02\x01' or len(data) < 20 or int.from_bytes(data[18:20], 'little') != {'linux-x64': 62, 'linux-arm64': 183}[selected['rid']]:
        raise ValueError('Published provider ELF architecture differs from the selected RID.')
    if {path.name for path in publish.glob('*.so')} != {'libRanvierWebCoreAtspi.so'}:
        raise ValueError('Optional SDK publish unexpectedly bundled another native library.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--native', type=Path, help='Matching Host required for actual load; omitted for layout-only checks.')
    parser.add_argument('--rid', choices=['linux-x64', 'linux-arm64'], help='Required for aggregate manifests; per-RID manifests retain their default.')
    parser.add_argument('--layout-only', action='store_true', help='Verify SDK RID asset selection without executing or bundling a Host.')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--dotnet', default='dotnet')
    args = parser.parse_args()
    if not args.layout_only and args.native is None:
        parser.error('--native is required unless --layout-only is explicit')
    args.output = args.output.resolve()
    with zipfile.ZipFile(args.package) as archive:
        manifest = json.loads(archive.read('provider-manifest.json'))
        for name, expected in manifest['payloads'].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError('Package payload hash mismatch: ' + name)
    selected = select_runtime(manifest, args.rid)
    if args.native is not None and hashlib.sha256(args.native.read_bytes()).hexdigest() != selected['hostSha256']:
        raise ValueError('Consumer Host does not match the selected package record.')
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).resolve().parent / 'consumer'
    project = args.output / 'source'
    shutil.copytree(source, project)
    feed = args.output / 'feed'
    feed.mkdir()
    shutil.copy2(args.package, feed)
    config = args.output / 'NuGet.Config'
    import xml.etree.ElementTree as ET
    root = ET.Element('configuration')
    sources = ET.SubElement(root, 'packageSources')
    ET.SubElement(sources, 'clear')
    ET.SubElement(sources, 'add', key='owned-provider', value=str(feed.resolve()))
    ET.SubElement(sources, 'add', key='nuget', value='https://api.nuget.org/v3/index.json')
    config.write_bytes(ET.tostring(root))
    publish = args.output / 'publish'
    subprocess.run([args.dotnet, 'publish', str(project / 'Consumer.csproj'), '-c', 'Release',
        '-r', selected['rid'], '--self-contained', 'false', '-o', str(publish), '-m:1', '/nr:false', '-p:UseSharedCompilation=false',
        '--configfile', str(config), '-p:NuGetAudit=false',
        '-p:RestorePackagesPath=' + str(args.output / 'packages'),
        '-p:AtspiPackageId=' + manifest['id'], '-p:AtspiPackageVersion=' + manifest['version']], check=True, timeout=180)
    verify_selected_asset(publish, selected)
    consumer = None
    if not args.layout_only:
        shutil.copy2(args.native, publish / 'libRanvierWebCoreHost.so')
        result = subprocess.run([args.dotnet, str(publish / 'Consumer.dll'), selected['providerSha256']], check=True, capture_output=True, text=True, timeout=30)
        consumer = json.loads(result.stdout)
        if hashlib.sha256((publish / 'libRanvierWebCoreAtspi.so').read_bytes()).hexdigest() != selected['providerSha256'] or hashlib.sha256((publish / 'libRanvierWebCoreHost.so').read_bytes()).hexdigest() != selected['hostSha256']:
            raise ValueError('Consumer execution changed native inputs.')
    receipt = dict(scope='ordinary PackageReference asset selection only' if args.layout_only else 'ordinary PackageReference publish and load; no renderer/window/protocol qualification',
        packageSha256=hashlib.sha256(args.package.read_bytes()).hexdigest(), manifest=manifest,
        selectedRid=selected['rid'], selectedRuntime=selected, executed=not args.layout_only, consumer=consumer)
    (args.output / 'consumer-receipt.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
