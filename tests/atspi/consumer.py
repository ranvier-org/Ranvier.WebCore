"""Publish an ordinary PackageReference consumer and load its exact optional native asset."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--native', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--dotnet', default='dotnet')
    args = parser.parse_args()
    args.output = args.output.resolve()
    with zipfile.ZipFile(args.package) as archive:
        manifest = json.loads(archive.read('provider-manifest.json'))
        for name, expected in manifest['payloads'].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError('Package payload hash mismatch: ' + name)
    if hashlib.sha256(args.native.read_bytes()).hexdigest() != manifest['hostSha256']:
        raise ValueError('Consumer host does not match the reviewed package cohort.')
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
    subprocess.run([args.dotnet, 'publish', str(project / 'Consumer.csproj'), '-c', 'Release', '-m:1', '/nr:false',
        '-r', manifest['rid'], '--self-contained', 'false', '-o', str(publish),
        '--configfile', str(config), '-p:NuGetAudit=false',
        '-p:RestorePackagesPath=' + str(args.output / 'packages'),
        '-p:AtspiPackageId=' + manifest['id'], '-p:AtspiPackageVersion=' + manifest['version']], check=True)
    shutil.copy2(args.native, publish / args.native.name)
    result = subprocess.run([args.dotnet, str(publish / 'Consumer.dll'), manifest['providerSha256']], check=True, capture_output=True, text=True)
    receipt = dict(scope='ordinary PackageReference publish and load; no renderer/window/protocol qualification',
        packageSha256=hashlib.sha256(args.package.read_bytes()).hexdigest(), manifest=manifest,
        consumer=json.loads(result.stdout))
    (args.output / 'consumer-receipt.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
