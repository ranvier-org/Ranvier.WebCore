"""Build the ABI-matched managed package and the native aggregates from checked native artifacts: Ranvier.WebCore.Native
(the GPU runtimes, with the CPU host where a runtime has no GPU build), its Ranvier.WebCore.Native.Gpu alias, and
Ranvier.WebCore.Native.Cpu (the Slim runtimes)."""

import argparse
import json
import pathlib
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
RIDS = ('win-x64', 'win-arm64', 'linux-x64', 'linux-arm64', 'osx-arm64')
GPU_RIDS = ('win-x64', 'linux-x64', 'linux-arm64', 'osx-arm64')
# The runtime package of a flavor is Ranvier.WebCore.Native<suffix>.<rid>; build.py, release.py and the build workflow
# name them with the same suffixes. The GPU flavor is the default package.
FLAVOR_SUFFIX = {'slim': '.Cpu', 'gpu': '', 'lean': '.Lean'}
PACKAGE_PREFIX = {flavor: 'Ranvier.WebCore.Native' + FLAVOR_SUFFIX[flavor] for flavor in ('slim', 'gpu')}


def runtime_package(packages, flavor, rid, version):
    return packages / f'{PACKAGE_PREFIX[flavor]}.{rid}.{version}.nupkg'


def read_manifests(packages, version, flavor, rids):
    manifests = []
    for rid in rids:
        path = runtime_package(packages, flavor, rid, version)
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read('manifest.json'))
        if (manifest['rid'], manifest['version'], manifest['flavor']) != (rid, version, flavor):
            raise ValueError(f'{path.name}: runtime, version or flavor differs')
        manifests.append(manifest)
    return manifests


def validate_identity(manifests, expected_identity):
    identities = {(m['abi'], m['webkit'], m['source']['commit']) for m in manifests}
    if len(identities) != 1:
        raise ValueError('native artifacts must come from one ABI, WebKit pin and source commit')
    if identities != {expected_identity}:
        raise ValueError('native artifacts do not match the managed checkout identity')
    if any(m['source']['dirty'] for m in manifests):
        raise ValueError('native artifacts must come from clean source trees')
    return manifests[0]['abi']


def validate_runtimes(packages, version, expected_identity):
    return validate_identity(read_manifests(packages, version, 'slim', RIDS), expected_identity)


def has_gpu_runtimes(packages, version, expected_identity):
    """True when the GPU runtimes are present and agree with the Slim runtimes; a partial GPU set raises."""
    present = [rid for rid in GPU_RIDS if runtime_package(packages, 'gpu', rid, version).exists()]
    if not present:
        return False
    if len(present) != len(GPU_RIDS):
        missing = sorted(set(GPU_RIDS) - set(present))
        raise ValueError(f'GPU aggregate needs every GPU runtime; missing {missing}')
    # The Slim runtimes outside GPU_RIDS serve those runtimes in the GPU aggregate.
    fallback = read_manifests(packages, version, 'slim', [rid for rid in RIDS if rid not in GPU_RIDS])
    validate_identity(read_manifests(packages, version, 'gpu', GPU_RIDS) + fallback, expected_identity)
    return True


def checkout_identity():
    subprocess.run(['git', 'diff', '--quiet', 'HEAD'], cwd=ROOT, check=True)
    pins = json.loads((ROOT / 'pins.json').read_text())
    source = (ROOT / 'host/RanvierWebCoreAbi.cpp').read_text()
    abi = int(re.search(r'rv_abi_version\(void\)\s*\{\s*return (\d+);', source).group(1))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    return abi, pins['webkit']['commit'], revision


def build(packages, version):
    identity = checkout_identity()
    abi = validate_runtimes(packages, version, identity)
    projects = ['packaging/cpu/Ranvier.WebCore.Native.Cpu.Meta.csproj', 'src/Ranvier.WebCore/Ranvier.WebCore.fsproj']
    gpu = has_gpu_runtimes(packages, version, identity)
    if gpu:
        # The default aggregate, then its alias under the GPU aggregate's former name, which depends on it.
        projects += ['packaging/Ranvier.WebCore.Native.Meta.csproj', 'packaging/gpu/Ranvier.WebCore.Native.Gpu.Meta.csproj']
    packages = packages.resolve()
    with tempfile.TemporaryDirectory(prefix='ranvier-pack-') as temporary:
        config = pathlib.Path(temporary) / 'NuGet.Config'
        document = ET.Element('configuration')
        sources = ET.SubElement(document, 'packageSources')
        ET.SubElement(sources, 'clear')
        ET.SubElement(sources, 'add', key='checked-native', value=str(packages))
        ET.SubElement(sources, 'add', key='nuget.org', value='https://api.nuget.org/v3/index.json')
        ET.ElementTree(document).write(config, encoding='utf-8', xml_declaration=True)
        for project in projects:
            subprocess.run(['dotnet', 'restore', str(ROOT / project), '--configfile', str(config),
                            f'-p:Version={version}'], check=True)
            subprocess.run(['dotnet', 'pack', str(ROOT / project), '--no-restore', '-c', 'Release',
                            '-o', str(packages), f'-p:Version={version}'], check=True)
    print(f'Packed managed interop and the CPU aggregate version {version}, ABI {abi}, all {len(RIDS)} RIDs'
          + (f'; the default aggregate over {len(GPU_RIDS)} GPU RIDs with the CPU fallback, and its .Gpu alias'
             if gpu else '; no default aggregate without the GPU runtimes'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages', required=True, type=pathlib.Path)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    build(args.packages, args.version)
