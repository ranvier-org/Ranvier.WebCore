"""Pack the public AT-SPI provider for a tagged WebCore release from the providers built in the same run."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
IDENTITY = 'Ranvier.WebCore.Accessibility.Atspi'
RIDS = {'linux-x64': 62, 'linux-arm64': 183}
SDK = '10.0.403'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def elf_machine(data):
    if data[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Expected a 64-bit little-endian ELF module')
    return int.from_bytes(data[18:20], 'little')


def read_build(directory, rid, version):
    """A per-RID build directory holds libRanvierWebCoreAtspi.so and build-receipt.json written on that RID's runner."""
    receipt = json.loads((directory / 'build-receipt.json').read_text(encoding='utf-8'))
    provider = (directory / 'libRanvierWebCoreAtspi.so').read_bytes()
    if elf_machine(provider) != RIDS[rid]:
        raise ValueError('The provider architecture does not match ' + rid)
    expected = dict(rid=rid, version=version, abi=receipt.get('abi'), providerSha256=digest(provider))
    if {key: receipt.get(key) for key in expected} != expected or type(receipt.get('abi')) is not int:
        raise ValueError('The build receipt does not describe this provider for ' + rid)
    for key in ['hostSha256', 'protocolPassed', 'consumerPassed', 'directStylePassed']:
        if key not in receipt:
            raise ValueError('The build receipt lacks ' + key)
    if not (receipt['protocolPassed'] and receipt['consumerPassed'] and receipt['directStylePassed']):
        raise ValueError('The provider for ' + rid + ' did not pass its runtime checks')
    return provider, receipt


def payload_for(builds, version, abi):
    header = (ROOT.parents[1] / 'host/RanvierWebCoreAbi.h').read_bytes()
    payload = {
        'include/RanvierAtspi.h': (ROOT / 'RanvierAtspi.h').read_bytes(),
        'include/RanvierWebCoreAbi.h': header,
        'NOTICE.md': (ROOT / 'PUBLIC-NOTICE.md').read_bytes(),
        'PUBLIC-README.md': (ROOT / 'PUBLIC-README.md').read_bytes(),
        'THIRD-PARTY.md': (ROOT / 'THIRD-PARTY.md').read_bytes(),
        'licenses/LGPL-2.1.txt': (ROOT / 'licenses/LGPL-2.1.txt').read_bytes(),
    }
    runtimes = {}
    for rid, (provider, receipt) in builds.items():
        payload[f'runtimes/{rid}/native/libRanvierWebCoreAtspi.so'] = provider
        runtimes[rid] = {key: receipt[key] for key in ['rid', 'abi', 'providerSha256', 'hostSha256']}
    manifest = dict(schemaVersion=2, id=IDENTITY, version=version, nativeVersion=version, abi=abi,
                    hostBundled=False, requiredCapability='accessibility-text-style', runtimes=runtimes,
                    payloads={name: digest(data) for name, data in payload.items()})
    payload['provider-manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    return payload, manifest


def emit(payload, version, output, work, dotnet):
    destination = output / f'{IDENTITY}.{version}.nupkg'
    if destination.exists():
        raise FileExistsError(destination)
    if work.exists():
        shutil.rmtree(work)
    files = work / 'payload'
    files.mkdir(parents=True)
    package = ET.Element('package')
    metadata = ET.SubElement(package, 'metadata')
    for name, value in [('id', IDENTITY), ('version', version), ('authors', 'Ranvier'),
                        ('description', 'Optional native AT-SPI modules for the matching Ranvier.WebCore Linux host.'),
                        ('readme', 'PUBLIC-README.md')]:
        ET.SubElement(metadata, name).text = value
    ET.SubElement(metadata, 'license', type='file').text = 'NOTICE.md'
    ET.SubElement(metadata, 'repository', type='git', url='https://github.com/ranvier-org/Ranvier.WebCore')
    entries = ET.SubElement(package, 'files')
    for name, data in payload.items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Unsafe payload path ' + name)
        target = files / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        parent = path.parent.as_posix()
        ET.SubElement(entries, 'file', src=str(target), target='' if parent == '.' else parent)
    nuspec = work / 'provider.nuspec'
    ET.ElementTree(package).write(nuspec, encoding='utf-8', xml_declaration=True)
    project = ET.Element('Project', Sdk='Microsoft.NET.Sdk')
    properties = ET.SubElement(project, 'PropertyGroup')
    for name, value in [('TargetFramework', 'net10.0'), ('IsPackable', 'true'), ('IncludeBuildOutput', 'false'),
                        ('EnableDefaultItems', 'false'), ('NuspecFile', str(nuspec))]:
        ET.SubElement(properties, name).text = value
    ET.ElementTree(project).write(work / 'Provider.csproj', encoding='utf-8', xml_declaration=True)
    (work / 'NuGet.Config').write_text('<configuration><packageSources><clear/></packageSources></configuration>')
    environment = dict(os.environ, NUGET_PACKAGES=str(work / 'cache'), DOTNET_CLI_USE_MSBUILD_SERVER='0')
    for command in ([dotnet, 'restore', str(work / 'Provider.csproj'), '--configfile', str(work / 'NuGet.Config')],
                    [dotnet, 'pack', str(work / 'Provider.csproj'), '-c', 'Release', '--no-restore', '--no-build',
                     '-o', str(work / 'packed')]):
        subprocess.run(command, check=True, env=environment, cwd=work)
    packed = work / 'packed' / destination.name
    with zipfile.ZipFile(packed) as archive:
        if any(archive.read(name) != data for name, data in payload.items()):
            raise ValueError('SDK packaging changed payload bytes')
        if any(name.endswith('.nuspec') and b'<dependency' in archive.read(name) for name in archive.namelist()):
            raise ValueError('The provider package must not add package dependencies')
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(packed, destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--build', action='append', required=True, metavar='RID=DIRECTORY')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--dotnet', default='dotnet')
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?', args.version):
        raise ValueError('Invalid package version ' + args.version)
    directories = dict(item.split('=', 1) for item in args.build)
    if set(directories) != set(RIDS):
        raise ValueError('Supply exactly the linux-x64 and linux-arm64 provider builds')
    builds = {rid: read_build(Path(path), rid, args.version) for rid, path in directories.items()}
    abis = {receipt['abi'] for _, receipt in builds.values()}
    if len(abis) != 1:
        raise ValueError('Both provider builds must target one host ABI')
    payload, manifest = payload_for(builds, args.version, abis.pop())
    destination = emit(payload, args.version, args.output.resolve(), args.work.resolve(), args.dotnet)
    print(json.dumps(dict(path=str(destination), sha256=digest(destination.read_bytes()), manifest=manifest), indent=1))


if __name__ == '__main__':
    main()
