"""Replay unchanged prepared AOT outputs after a local runtime setup failure; never rebuild."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import zipfile

spec = importlib.util.spec_from_file_location('prepared_managed', Path(__file__).with_name('arm64_managed.py'))
managed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(managed)


def validate_prepared_record(record, manifest, native_hash, package_hash, source, dom):
    expected = dict(rid=manifest['rid'], hostSha256=native_hash, providerSha256=manifest['providerSha256'],
                    packageSha256=package_hash, sourceRevision=source, domVersion=dom)
    if any(record.get(key) != value for key, value in expected.items()):
        raise ValueError('Prepared consumer cohort identity differs')
    if record.get('allOwnedProcessesExited') is not True or record.get('runs') != []:
        raise ValueError('Require a terminated setup-only attempt without any claimed profile run')
    if set(record.get('assetGraphs', {})) != {'normal', 'traced'}:
        raise ValueError('Both exact prepared asset graphs are required')
    if not isinstance(record.get('runtimeAdmission', {}).get('readySha256'), str):
        raise ValueError('The original prepared-input checkpoint is required')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--dom-version', required=True)
    parser.add_argument('--xvfb-tcp', action='store_true')
    args = parser.parse_args()
    work = args.work.resolve()
    record_path = work / 'managed-aot-receipt.json'
    record = json.loads(record_path.read_text())
    with zipfile.ZipFile(args.package) as archive:
        manifest = json.loads(archive.read('provider-manifest.json'))
        for name, expected in manifest['payloads'].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError('Prepared provider package payload changed')
    managed.validate_source_claim(manifest, args.source_revision)
    managed.validate_architecture(manifest['rid'], platform.machine())
    validate_prepared_record(record, manifest, managed.sha(args.native), managed.sha(args.package),
                             args.source_revision, args.dom_version)
    ready_path = work / 'runtime-admission.json.ready'
    if managed.sha(ready_path) != record['runtimeAdmission']['readySha256']:
        raise ValueError('The original prepared-input checkpoint bytes changed')
    ready = json.loads(ready_path.read_text())
    if not ready.get('files') or any(managed.sha(Path(name)) != expected for name, expected in ready['files'].items()):
        raise ValueError('A prepared binary, native library, package or graph changed')
    projects = {mode: work / ('publish-' + mode) for mode in ('normal', 'traced')}
    for mode, directory in projects.items():
        graph = record['assetGraphs'][mode]
        if managed.sha(Path(graph['path'])) != graph['sha256']:
            raise ValueError('Prepared asset graph changed')
        libraries = json.loads(Path(graph['path']).read_text())['libraries']
        managed.validate_assets(libraries, mode, record['interopVersion'], manifest['version'], manifest['id'], args.dom_version)
        managed.validate_elf(subprocess.check_output(['readelf', '-h', '-d', str(directory / 'AccessibilityAot')], text=True), manifest['rid'])
        for name, expected in [('libRanvierWebCoreHost.so', manifest['hostSha256']),
                               ('libRanvierWebCoreAtspi.so', manifest['providerSha256'])]:
            if managed.sha(directory / name) != expected:
                raise ValueError('Prepared native asset changed')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt = {key:value for key, value in record.items() if key not in
               ('processes', 'runs', 'allOwnedProcessesExited', 'runtimeAdmission')}
    receipt.update(runs=[], preparedReceiptSha256=managed.sha(record_path), preparedCheckpointSha256=managed.sha(ready_path),
                   reusedPreparedOutputs=True, compileUnits=0,
                   scope='Runtime-only replay after private X11 setup failure; original strict publish and RED are retained')
    managed.run_profiles(output, projects, receipt, tcp_display=args.xvfb_tcp)


if __name__ == '__main__':
    main()
