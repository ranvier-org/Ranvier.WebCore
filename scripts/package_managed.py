"""Build the ABI-matched managed and five-runtime aggregate packages from checked native artifacts."""

import argparse
import json
import pathlib
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
RIDS = ('win-x64', 'win-arm64', 'linux-x64', 'linux-arm64', 'osx-arm64')


def validate_runtimes(packages, version):
    manifests = []
    for rid in RIDS:
        path = packages / f'Ranvier.WebCore.Native.{rid}.{version}.nupkg'
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read('manifest.json'))
        if (manifest['rid'], manifest['version'], manifest['flavor']) != (rid, version, 'slim'):
            raise ValueError(f'{path.name}: runtime, version or flavor differs')
        manifests.append(manifest)
    identities = {(m['abi'], m['webkit'], m['source']['commit']) for m in manifests}
    if len(identities) != 1:
        raise ValueError('native artifacts must come from one ABI, WebKit pin and source commit')
    if any(m['source']['dirty'] for m in manifests):
        raise ValueError('native artifacts must come from clean source trees')
    return manifests[0]['abi']


def build(packages, version):
    abi = validate_runtimes(packages, version)
    packages = packages.resolve()
    with tempfile.TemporaryDirectory(prefix='ranvier-pack-') as temporary:
        config = pathlib.Path(temporary) / 'NuGet.Config'
        document = ET.Element('configuration')
        sources = ET.SubElement(document, 'packageSources')
        ET.SubElement(sources, 'clear')
        ET.SubElement(sources, 'add', key='checked-native', value=str(packages))
        ET.SubElement(sources, 'add', key='nuget.org', value='https://api.nuget.org/v3/index.json')
        ET.ElementTree(document).write(config, encoding='utf-8', xml_declaration=True)
        for project in ('packaging/Ranvier.WebCore.Native.Meta.csproj',
                        'src/Ranvier.WebCore/Ranvier.WebCore.fsproj'):
            subprocess.run(['dotnet', 'restore', str(ROOT / project), '--configfile', str(config),
                            f'-p:Version={version}'], check=True)
            subprocess.run(['dotnet', 'pack', str(ROOT / project), '--no-restore', '-c', 'Release',
                            '-o', str(packages), f'-p:Version={version}'], check=True)
    print(f'Packed managed interop and native aggregate version {version}, ABI {abi}, all {len(RIDS)} RIDs')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages', required=True, type=pathlib.Path)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    build(args.packages, args.version)
