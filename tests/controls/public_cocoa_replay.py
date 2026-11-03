"""Run the signed Cocoa cohort using reviewed producer helpers and an immutable controller."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import time
import urllib.request
import zipfile


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def extract_artifact(path, output):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate artifact member')
        for info in archive.infolist():
            name = PurePosixPath(info.filename)
            if (name.is_absolute() or '\\' in info.filename or any(part in {'.', '..'} or ':' in part for part in name.parts)
                    or (info.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('Unsafe artifact member')
        archive.extractall(output)


def processes():
    text = subprocess.check_output(['ps', '-axo', 'pid=,ppid=,pgid=,lstart='], text=True, timeout=10)
    return {int(parts[0]): (int(parts[1]), int(parts[2]), ' '.join(parts[3:]))
            for line in text.splitlines() if len(parts := line.split()) == 8}


def run_controller(command, stream, environment):
    child = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                             env=environment, start_new_session=True)
    owned = {}

    def capture():
        current = processes()
        selected = ({child.pid} if child.poll() is None else set()) | {
            pid for pid, identity in owned.items() if pid in current and current[pid][1:] == identity[1:]}
        while True:
            expanded = selected | {pid for pid, (parent, _, _) in current.items() if parent in selected}
            if expanded == selected:
                break
            selected = expanded
        owned.update({pid: current[pid] for pid in selected if pid in current})
        return current

    try:
        deadline = time.monotonic() + 3600
        while child.poll() is None:
            capture()
            if time.monotonic() >= deadline:
                raise TimeoutError('The entire public controller exceeded its owned deadline')
            time.sleep(0.2)
        return child.returncode
    finally:
        try:
            current = capture()
        except (OSError, subprocess.SubprocessError):
            current = {}
        groups = {identity[1] for pid, identity in owned.items() if pid in current and current[pid][1:] == identity[1:]}
        if child.poll() is None:
            groups.add(child.pid)
        for group in groups:
            if group == os.getpgrp():
                raise RuntimeError('Refusing to terminate the workflow parent group')
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        child.wait(timeout=10)


def default_reference(report):
    rows = [row for row in report.get('rows', []) if 'label' in row]
    if (report.get('assertions') != 59 or report.get('failures') or len(rows) != 6
            or len({row['label'] for row in rows}) != 6
            or any(row.get('vectorProfile') is not False for row in rows)):
        raise ValueError('Require the complete scoped legacy appearance reference')
    return dict(scope='Default legacy appearance references; no page-contrast isolation claim',
                assertions=59, images={row['label']: row['sha256'] for row in rows})


def run_default_references(source, output, inputs, environment):
    native = output / 'contracts/baseline-native'
    helpers = output / 'sidecars'
    records = inputs['sidecarManifest']['helpers']
    common = [sys.executable, '-B', '-I', str(source / 'tests/controls/cocoa_contrast_paths.py'),
              '--native-directory', str(native), '--abi-source', str(source / 'tests/abi'),
              '--page-helper', str(helpers / records['page']['path']),
              '--system-helper', str(helpers / records['contrast']['path']), '--scoped-helper', '--legacy-only']
    rows = [('legacy-default-59', [*common, '--output', str(output / 'legacy-default')]),
            ('legacy-reverse-59', [*common, '--first-system-more', '--output', str(output / 'legacy-reverse')])]
    worker = ('import importlib.util,json,os,sys; from pathlib import Path; '
              'spec=importlib.util.spec_from_file_location("canonical",sys.argv[1]); '
              'm=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); '
              'rows=m.run_groups(json.loads(sys.argv[2]),Path(sys.argv[3]),dict(os.environ)); '
              'Path(sys.argv[3],"legacy-groups.json").write_text(json.dumps(rows,indent=2),encoding="utf-8"); '
              'sys.exit(any(r.get("exit")!=0 or r.get("failure") for r in rows))')
    command = [sys.executable, '-B', '-I', '-c', worker, str(source / 'tests/controls/public_cocoa_contracts.py'),
               json.dumps(rows), str(output)]
    environment = dict(environment, RANVIER_ABI_TEST_EXPECTED='64', DYLD_LIBRARY_PATH=str(native))
    environment.pop('DYLD_INSERT_LIBRARIES', None)
    environment.pop('DYLD_FRAMEWORK_PATH', None)
    before = {p.relative_to(native).as_posix(): sha(p) for p in native.rglob('*') if p.is_file()}
    helpers_before = {name: sha(helpers / record['path']) for name, record in records.items()}
    with (output / 'legacy-controller.log').open('wb') as stream:
        code = run_controller(command, stream, environment)
    after = {p.relative_to(native).as_posix(): sha(p) for p in native.rglob('*') if p.is_file()}
    helpers_after = {name: sha(helpers / record['path']) for name, record in records.items()}
    result = dict(exit=code, nativeUnchanged=before == after,
                  helpersUnchanged=helpers_before == helpers_after, references={})
    for order in ['default', 'reverse']:
        directory = output / ('legacy-' + order)
        report = default_reference(json.loads((directory / 'contrast-paths.json').read_text()))
        for label, digest in report['images'].items():
            if sha(directory / (label + '.rgba')) != digest:
                raise ValueError('Legacy reference image bytes differ')
        result['references'][order] = report
    result['freshOrderImagesEqual'] = result['references']['default']['images'] == result['references']['reverse']['images']
    result['acceptedAsReferences'] = code == 0 and result['nativeUnchanged'] and result['helpersUnchanged']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['inputs', 'source', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    inputs = json.loads(args.inputs.read_text())
    if inputs.get('armed') is not True:
        raise ValueError('Public Cocoa replay is unarmed')
    policy = inputs['policy']
    source = args.source.resolve(strict=True)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if head != policy['controllerSource'] or not re.fullmatch('[a-f0-9]{40}', head):
        raise ValueError('Immutable controller source differs')
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(source):
        raise ValueError('Require a fresh owned replay directory')
    output.mkdir(parents=True)
    receipt = dict(accepted=False, controllerSource=head, inputsSha256=sha(args.inputs), packages={})
    try:
        artifact = inputs['artifact']
        if type(artifact['id']) is not int or artifact['id'] <= 0 or not re.fullmatch('[a-f0-9]{64}', artifact['sha256']):
            raise ValueError('Require the independently audited producer artifact ID and SHA256')
        archive = output / 'producer-artifact.zip'
        with archive.open('wb') as stream:
            subprocess.run(['gh', 'api', f"repos/ranvier-org/Ranvier.WebCore/actions/artifacts/{artifact['id']}/zip"],
                           stdout=stream, check=True, timeout=180)
        if sha(archive) != artifact['sha256']:
            raise ValueError('Producer artifact bytes differ from independent review')
        helpers = output / 'sidecars'
        extract_artifact(archive, helpers)
        archive.unlink()
        sidecars = helpers / 'reviewed-consumer-sidecars.json'
        sidecars.write_text(json.dumps(inputs['sidecarManifest'], indent=2) + '\n', encoding='utf-8')
        if sha(sidecars) != policy['sidecarManifestSha256']:
            raise ValueError('Reviewed sidecar seal serialization differs')
        paths = {}
        for name, package_id, expected in [('native', policy['native']['id'], policy['native']['packageSha256']),
                                            ('interop', 'Ranvier.WebCore', policy['interopPackageSha256'])]:
            version = policy['native']['version']
            if not re.fullmatch('[A-Za-z0-9.-]+', package_id) or not re.fullmatch('[A-Za-z0-9.-]+', version):
                raise ValueError('Invalid public package identity')
            url = f'https://api.nuget.org/v3-flatcontainer/{package_id.lower()}/{version.lower()}/{package_id.lower()}.{version.lower()}.nupkg'
            path = output / (name + '.nupkg')
            with urllib.request.urlopen(url, timeout=120) as response, path.open('wb') as stream:
                while block := response.read(1024 * 1024):
                    stream.write(block)
            if sha(path) != expected:
                raise ValueError('Actual public package differs: ' + name)
            paths[name] = path
            receipt['packages'][name] = dict(url=url, sha256=expected)
        paths['policy'] = output / 'reviewed-policy.json'
        paths['policy'].write_text(json.dumps(policy, indent=2) + '\n', encoding='utf-8')
        paths['audit'] = output / 'reviewed-public-audit.json'
        paths['audit'].write_text(inputs['auditText'], encoding='utf-8')
        if sha(paths['audit']) != policy['native']['auditSha256']:
            raise ValueError('Public audit receipt bytes differ')
        command = [sys.executable, '-B', '-I', str(source / 'tests/controls/public_cocoa_contracts.py'),
                   '--policy', str(paths['policy']), '--package', str(paths['native']), '--interop', str(paths['interop']),
                   '--audit', str(paths['audit']), '--sidecars', str(sidecars), '--output', str(output / 'contracts')]
        if inputs.get('ownerProofText') is not None:
            proof = output / 'reviewed-owner-proof.json'
            proof.write_text(inputs['ownerProofText'], encoding='utf-8')
            command += ['--owner-proof', str(proof)]
        environment = dict(os.environ)
        environment.pop('GH_TOKEN', None)
        with (output / 'controller.log').open('wb') as stream:
            receipt['controllerExit'] = run_controller(command, stream, environment)
        contract = output / 'contracts/receipt.json'
        data = json.loads(contract.read_text()) if contract.is_file() else {}
        admission = {row['name']: row for row in data.get('groups', [])}
        if data.get('inputsUnchanged') is True and all(name in admission and admission[name].get('exit') == 0 and not admission[name].get('failure')
               for name in ['verify-public-signature', 'verify-interop-signature', 'loaded-abi64-349']):
            receipt['defaultAppearance'] = run_default_references(source, output, inputs, environment)
        receipt['accepted'] = (receipt['controllerExit'] == 0 and data.get('accepted') is True
                               and receipt.get('defaultAppearance', {}).get('acceptedAsReferences') is True)
    except Exception as error:
        receipt['failure'] = repr(error)
        raise
    finally:
        (output / 'replay-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return 0 if receipt['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
