"""Qualify and export seven immutable-F Slim packages; never build an engine or publish."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = 'ranvier-org/Ranvier.WebCore'
PRODUCT = 'd31c3631ed4bbe6520f7f5f7c7e7d34499c38122'
VERSION = '0.1.1-preview.12'
WEBKIT = 'b95c91b1c0ee43cc86d25ff7af73038f67a88e04'
PRODUCER_RUN = 41719479076
ORIGINAL_RIDS = ('win-x64', 'win-arm64', 'linux-x64', 'linux-arm64')
RIDS = (*ORIGINAL_RIDS, 'osx-arm64')
HELPER_SOURCE = '3f187c76e404ace64791d8996591ca8bd97183bf'
HELPER_BLOBS = {'tests/controls/build_cocoa_sidecars.py': 'd2ff164b0ce774ed5c129e95046028083d411425',
                'tests/abi/build_cocoa_timer_contract.py': '55fd1261c444226578383efbb91accc9696cd1d6'}
PACKAGE_IDS = {'Ranvier.WebCore', 'Ranvier.WebCore.Native', *(f'Ranvier.WebCore.Native.{rid}' for rid in RIDS)}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def revision(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{40}', value) is not None


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def admit_policy(policy, phase):
    require(policy.get('schemaVersion') == 1 and policy.get('armed') is True, 'Slim recovery is unarmed')
    require(policy.get('productSource') == PRODUCT and policy.get('version') == VERSION
            and policy.get('producerRun') == PRODUCER_RUN and revision(policy.get('controllerSource')), 'Product/controller identity differs')
    require(set(policy.get('original', {})) == set(ORIGINAL_RIDS), 'Exactly four original native RIDs are required')
    for rid, record in policy['original'].items():
        admit_artifact_record(record.get('artifact'), f'package-{rid}-slim')
        require(digest(record.get('packageSha256')), 'Original package SHA is unallocated')
    mac = policy.get('macRecovery', {})
    require(type(mac.get('run')) is int and mac['run'] > 0 and revision(mac.get('workflowSource')),
            'Actual Mac recovery run and H are required')
    for key, name in [('packageArtifact', 'package-osx-arm64-slim'), ('proofArtifact', 'immutable-d31-mac-slim-recovery-proof')]:
        admit_artifact_record(mac.get(key), name)
    require(all(digest(mac.get(key)) for key in ['packageSha256', 'recoveryReceiptSha256', 'sidecarReceiptSha256']),
            'Mac package and independent receipt hashes are unallocated')
    require(isinstance(mac.get('proofPrefix'), str) and safe_prefix(mac['proofPrefix']), 'Exact Mac proof member prefix is unallocated')
    completion = mac.get('helperCompletion')
    if completion is not None:
        require(type(completion.get('run')) is int and completion['run'] > 0 and revision(completion.get('workflowSource'))
                and digest(completion.get('receiptSha256')) and digest(completion.get('inputsContractSha256')),
                'Actual separate Mac helper completion is unallocated')
        admit_artifact_record(completion.get('artifact'), 'immutable-d31-mac-slim-helper-completion')
    if phase == 'export':
        q = policy.get('qualification') or {}
        require(policy.get('publicationEnabled') is True and type(q.get('run')) is int and q['run'] > 0
                and revision(q.get('workflowSource')) and digest(q.get('policySha256')),
                'Publication remains unarmed pending actual qualification')
        admit_artifact_record(q.get('proofArtifact'), 'qualified-preview12-slim')
        admit_artifact_record(q.get('packagesArtifact'), 'package-preview12-slim-recovered')
        require(digest(q.get('receiptSha256')) and set(q.get('packageHashes', {})) == PACKAGE_IDS
                and all(digest(value) for value in q['packageHashes'].values()), 'Seven reviewed package hashes are required')


def admit_artifact_record(record, name):
    require(isinstance(record, dict) and type(record.get('id')) is int and record['id'] > 0
            and record.get('name') == name and digest(record.get('sha256')), 'Exact artifact identity is unallocated')


def api(route):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPO}/{route}'], timeout=90))


def jobs(run):
    result = api(f'actions/runs/{run}/jobs?per_page=100')
    require(result['total_count'] == len(result['jobs']), 'Incomplete job inventory')
    return result


def repo_run(run):
    require(run.get('repository', {}).get('full_name') == REPO and run.get('head_repository', {}).get('full_name') == REPO,
            'Run repository/owner lineage differs')


def admit_original_run(run, response):
    repo_run(run)
    require(run.get('id') == PRODUCER_RUN and run.get('head_sha') == PRODUCT and run.get('head_branch') == 'v' + VERSION
            and run.get('event') == 'push' and run.get('path') == '.github/workflows/build.yml'
            and run.get('run_attempt') == 1 and run.get('status') == 'completed', 'Original producer run identity differs')
    require(response.get('total_count') == len(response.get('jobs', [])), 'Incomplete original jobs')
    selected = {}
    for rid in RIDS:
        rows = [job for job in response['jobs'] if job['name'].startswith('native (' + rid + ',')]
        require(len(rows) == 1 and rows[0].get('status') == 'completed', 'Missing or ambiguous native producer job')
        require(rows[0].get('conclusion') == ('cancelled' if rid == 'osx-arm64' else 'success'), 'Original native job outcome differs')
        if rid in ORIGINAL_RIDS:
            for name in ['Package', 'Check the staged files and paint a page', 'Verify mutation observation delivery and ownership', 'Run the probes']:
                steps = [step for step in rows[0].get('steps', []) if step['name'] == name]
                require(len(steps) == 1 and steps[0].get('conclusion') == 'success', 'An original required native gate did not pass: ' + name)
        selected[rid] = rows[0]
    return selected


def safe_names(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)) == len({name.casefold() for name in names}), 'Duplicate archive member')
    for name in names:
        require(archive.getinfo(name).orig_filename == name, 'Noncanonical original archive member')
        path = PurePosixPath(name)
        require(name and not path.is_absolute() and '\\' not in name and path.as_posix() == name.rstrip('/')
                and not any(part in {'.', '..'} or ':' in part for part in path.parts), 'Unsafe archive member')
        require((archive.getinfo(name).external_attr >> 16) & 0o170000 != 0o120000, 'Symlink archive member')
    return names


def safe_prefix(value):
    if value == '':
        return True
    path = PurePosixPath(value)
    return (value.endswith('/') and not path.is_absolute() and path.as_posix() + '/' == value
            and '\\' not in value and not any(part in {'.', '..'} or ':' in part for part in path.parts))


def artifact(record, run, source, output):
    metadata = api(f"actions/artifacts/{record['id']}")
    require(metadata.get('id') == record['id'] and metadata.get('name') == record['name'] and metadata.get('expired') is False
            and metadata.get('workflow_run', {}).get('id') == run
            and metadata['workflow_run'].get('head_sha') == source
            and metadata.get('digest') == 'sha256:' + record['sha256'], 'Artifact run/source/name/digest lineage differs')
    path = output / f"artifact-{record['id']}.zip"
    with path.open('wb') as stream:
        subprocess.run(['gh', 'api', f"repos/{REPO}/actions/artifacts/{record['id']}/zip"], stdout=stream, check=True, timeout=300)
    require(sha(path) == record['sha256'], 'Downloaded artifact differs')
    return path


def package_identity(archive):
    names = safe_names(archive)
    nuspec, = [name for name in names if '/' not in name and name.endswith('.nuspec')]
    root = ET.fromstring(archive.read(nuspec))
    fields = {node.tag.rsplit('}', 1)[-1]: node.text for node in root.iter()}
    dependencies = {}
    for node in root.iter():
        if node.tag.rsplit('}', 1)[-1] == 'dependency':
            require(node.get('id') not in dependencies, 'Duplicate dependency declaration')
            dependencies[node.get('id')] = node.get('version')
    return fields.get('id'), fields.get('version'), dependencies


def native_format(data, rid):
    if rid.startswith('win-'):
        require(len(data) >= 64 and data[:2] == b'MZ', 'Expected PE native library')
        offset = struct.unpack_from('<I', data, 60)[0]
        require(len(data) >= offset + 24 and data[offset:offset + 4] == b'PE\0\0'
                and struct.unpack_from('<H', data, offset + 4)[0] == (0x8664 if rid == 'win-x64' else 0xaa64)
                and struct.unpack_from('<H', data, offset + 22)[0] & 0x2000, 'Wrong PE architecture or non-DLL')
    elif rid.startswith('linux-'):
        require(len(data) >= 20 and data[:6] == b'\x7fELF\x02\x01'
                and struct.unpack_from('<HH', data, 16) == (3, 62 if rid == 'linux-x64' else 183), 'Wrong ELF architecture/type')
    else:
        require(len(data) >= 16 and struct.unpack_from('<II', data) == (0xfeedfacf, 0x100000c)
                and struct.unpack_from('<I', data, 12)[0] == 6, 'Wrong Mach-O architecture/type')


def verify_native(package, rid, expected_sha):
    require(sha(package) == expected_sha and rid in RIDS, 'Native package hash/RID differs')
    with zipfile.ZipFile(package) as archive:
        names = safe_names(archive)
        require(package_identity(archive)[:2] == (f'Ranvier.WebCore.Native.{rid}', VERSION), 'Native package identity differs')
        manifest = json.loads(archive.read('manifest.json'))
        require((manifest.get('rid'), manifest.get('flavor'), manifest.get('version'), manifest.get('abi'), manifest.get('webkit'))
                == (rid, 'slim', VERSION, 64, WEBKIT) and type(manifest['abi']) is int
                and manifest.get('source') == dict(commit=PRODUCT, dirty=False, builder='ci'), 'Native manifest F/cohort differs')
        records = {row['name']: row for row in manifest['files']}
        prefix = f'runtimes/{rid}/native/'
        require(len(records) == len(manifest['files']) and records
                and {name[len(prefix):] for name in names if name.startswith(prefix) and not name.endswith('/')} == records.keys()
                and manifest['total_bytes'] == sum(row['bytes'] for row in records.values()), 'Incomplete native payload')
        host = 'RanvierWebCoreHost.dll' if rid.startswith('win-') else 'libRanvierWebCoreHost.' + ('dylib' if rid == 'osx-arm64' else 'so')
        require(host in records, 'Native Host is missing')
        for name, row in records.items():
            require(PurePosixPath(name).as_posix() == name and not name.startswith('/') and '..' not in PurePosixPath(name).parts, 'Unsafe native manifest name')
            data = archive.read(prefix + name)
            require(len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], 'Native payload bytes differ')
            if name.endswith(('.dll', '.so', '.dylib')):
                native_format(data, rid)
    return manifest


def extract_package(archive_path, name, destination):
    with zipfile.ZipFile(archive_path) as archive:
        require([value for value in safe_names(archive) if not value.endswith('/')] == [name], 'Unexpected package artifact members')
        path = destination / name
        path.write_bytes(archive.read(name))
    return path


def verify_mac_proof(proof, record, manifest, package, partial=False):
    with zipfile.ZipFile(proof) as archive:
        names = safe_names(archive)
        prefix = record['proofPrefix']
        require(safe_prefix(prefix), 'Unsafe Mac proof prefix')
        raw = archive.read(prefix + 'recovery-receipt.json')
        require(hashlib.sha256(raw).hexdigest() == record['recoveryReceiptSha256'], 'Mac recovery receipt differs')
        receipt = json.loads(raw)
        require(receipt.get('accepted') is (not partial) and receipt.get('publication') is False
                and receipt.get('productSource') == PRODUCT and receipt.get('controlSource') == record['workflowSource']
                and receipt.get('workflowRun') == str(record['run']) and receipt.get('flavor') == 'slim'
                and receipt.get('version') == VERSION and receipt.get('reviewedHelperSource') == HELPER_SOURCE
                and receipt.get('helperBlobs') == HELPER_BLOBS, 'Mac F/H/helper identity differs')
        phases = receipt.get('phases', {})
        require(set(phases) == {'build', 'helpers', 'qualify'} and all(phase.get('passed') is (not partial or name != 'helpers')
                and phase.get('productClean') is True and phase.get('builderClean') is True
                and phase.get('identityErrors') == [] for name, phase in phases.items()), 'Mac independent phases did not pass')
        expected = {row['name']: row['sha256'] for row in manifest['files']}
        with zipfile.ZipFile(package) as native_archive:
            manifest_sha = hashlib.sha256(native_archive.read('manifest.json')).hexdigest()
        require(phases['build'].get('native') == expected and phases['build'].get('packageSha256') == sha(package)
                and phases['build'].get('manifestSha256') == manifest_sha, 'Mac package/build proof differs')
        gates = [row for row in receipt.get('commands', []) if row.get('phase') == 'qualify']
        require([row.get('name') for row in gates] == ['smoke', 'mutation', 'probes']
                and all(row.get('exit') == 0 and row.get('directChildReaped') is True for row in gates), 'Mac actual qualification gates differ')
        product_root = receipt['productRoot']
        require(product_root != receipt['controlRoot'] and product_root.startswith('/'), 'Mac product/controller roots are not distinct')
        expected_gates = [
            ['-B', product_root + '/scripts/build.py', 'smoke', '--rid', 'osx-arm64', '--flavor', 'slim', '--version', VERSION, '--work', '/Users/runner/rw'],
            ['-I', product_root + '/tests/abi/mutation_observation.py', '--native-directory', '/Users/runner/rw/out/slim/runtimes/osx-arm64/native'],
            ['-I', product_root + '/scripts/probes.py', 'run', '--rid', 'osx-arm64', '--flavor', 'slim', '--work', '/Users/runner/rw', '--expected-abi', '64']]
        require([row.get('argv', [])[1:] for row in gates] == expected_gates, 'Mac gates did not execute the complete original F commands')
        base = prefix + 'sidecars/'
        raw = archive.read(base + 'producer-sidecars.json')
        require(hashlib.sha256(raw).hexdigest() == record['sidecarReceiptSha256'], 'Mac sidecar receipt differs')
        sidecars = json.loads(raw)
        require((sidecars.get('boundary'), sidecars.get('status'), sidecars.get('abi'), sidecars.get('declarations'))
                == ('producer-Host-unchanged-sidecars-v1', 'failed' if partial else 'compiled', 64, 349)
                and sidecars.get('nativeSource') == PRODUCT and sidecars.get('controllerSource') == record['workflowSource']
                and sidecars.get('producerSourceAfter') == PRODUCT and sidecars.get('controllerSourceAfter') == record['workflowSource']
                and sidecars.get('sourcesUnchanged') is True and sidecars.get('controllerTrackedDirty') is False
                and sidecars.get('unsignedPackageSha256') == sha(package)
                and sidecars.get('nativeBefore') == sidecars.get('nativeAfter') == expected and sidecars.get('nativeUnchanged') is True
                and all(sidecars.get(key) is False for key in ['hostReplaced', 'headerReconstruction', 'engineCompilation']),
                'Mac unchanged-Host sidecar boundary differs')
        artifacts = sidecars.get('artifacts', {})
        require({name[len(base):] for name in names if name.startswith(base) and not name.endswith('/')}
                == set(artifacts) | {'producer-sidecars.json'}, 'Incomplete Mac sidecar artifact set')
        for name, expected_sha in artifacts.items():
            require(hashlib.sha256(archive.read(base + name)).hexdigest() == expected_sha, 'Mac helper evidence mutation')
        require(set(sidecars.get('helpers', {})) == ({'timer', 'page'} if partial else {'timer', 'page', 'motion', 'contrast'}), 'Missing Mac helper')
        for helper in sidecars['helpers'].values():
            data = archive.read(base + helper['path'])
            require(hashlib.sha256(data).hexdigest() == helper['sha256'], 'Mac helper binary differs')
            native_format(data, 'osx-arm64')
        for name in ['timer', 'page']:
            compiled = json.loads(archive.read(base + f'{name}/build-receipt.json'))
            capsule = archive.read(base + f'{name}/consumed-inputs.zip')
            require(compiled.get('status') == 'compiled' and compiled.get('inputsUnchanged') is True
                    and compiled.get('runtimeUnchanged') is True
                    and compiled.get('runtimeBefore') == compiled.get('runtimeAfter') == {key: value for key, value in expected.items() if key.endswith('.dylib')}
                    and compiled.get('inputsBefore') and compiled.get('inputsBefore') == compiled.get('inputsAfter')
                    and all(compiled.get(key) is False for key in ['hostReplaced', 'headerReconstruction', 'engineCompilation'])
                    and all(digest(compiled.get(key)) for key in ['compilerSha256', 'compileCommandsSha256', 'producerConfigurationSha256'])
                    and hashlib.sha256(capsule).hexdigest() == compiled.get('consumedInputsArchiveSha256'), 'Mac compiler capsule differs')
            require([row.get('name') for row in compiled.get('steps', [])] == ['dependencies', 'compile', 'link', 'final-install-name',
                    'sign-helper', 'verify-helper-signature', 'helper-dependencies'] and all(row.get('exit') == 0 for row in compiled['steps']),
                    'Mac helper compile/link/signature steps differ')
            require(any('-Wl,-undefined,error' in command and '-Wl,-install_name,@rpath/libTestWebCore.dylib' in command
                        for command in compiled.get('commands', [])), 'Mac helper strict-link boundary differs')
            with zipfile.ZipFile(io.BytesIO(capsule)) as captured:
                members = safe_names(captured)
                require(members and captured.testzip() is None, 'Invalid consumed SDK archive')
                for member in members:
                    if member.endswith('/'):
                        continue
                    require(member.startswith('inputs/'), 'Invalid consumed SDK input path')
                    source = '/' + member.removeprefix('inputs/')
                    require(hashlib.sha256(captured.read(member)).hexdigest() == compiled['inputsBefore'].get(source),
                            'Consumed SDK input bytes differ')
                omitted = set(compiled['inputsBefore']) - {'/' + member.removeprefix('inputs/') for member in members if not member.endswith('/')}
                runtime_prefix = '/Users/runner/rw/out/slim/runtimes/osx-arm64/native/'
                for path in omitted:
                    value = compiled['inputsBefore'][path]
                    require((path.endswith('/clang') and value == compiled['compilerSha256']) or
                            (path.startswith(runtime_prefix) and expected.get(path.removeprefix(runtime_prefix)) == value),
                            'Consumed SDK input missing')
        retained = {name: dict(path=sidecars['helpers'][name]['path'], sha256=sidecars['helpers'][name]['sha256'],
                              receiptSha256=hashlib.sha256(archive.read(base + name + '/build-receipt.json')).hexdigest(),
                              capsuleSha256=hashlib.sha256(archive.read(base + name + '/consumed-inputs.zip')).hexdigest()) for name in ['timer', 'page']}
        summary = dict(recoveryReceiptSha256=record['recoveryReceiptSha256'], sidecarReceiptSha256=record['sidecarReceiptSha256'],
                       productSource=PRODUCT, controlSource=record['workflowSource'], run=record['run'], originalAccepted=not partial,
                       headerSha256=sidecars.get('headerSha256'), compilerSha256=sidecars.get('appkitCompilerSha256'), sdk=sidecars.get('appkitSdk'),
                       retainedTimerPage=retained)
        if partial:
            require('motion-compile' in sidecars.get('error', '') and b'gxx_personality' in archive.read(base + 'motion-compile.log'),
                    'Original helper failure is not the retained C++ driver RED')
            return summary
        appkit = sidecars.get('appkitConsumedInputs', {})
        require(set(appkit) == {'motion', 'contrast'} and sidecars.get('appkitInputs'), 'Missing AppKit consumed SDK evidence')
        for name, capture in appkit.items():
            data = archive.read(base + capture['path'])
            require(hashlib.sha256(data).hexdigest() == capture['sha256'], 'AppKit consumed SDK hash differs')
            with zipfile.ZipFile(io.BytesIO(data)) as captured:
                require(safe_names(captured) and captured.testzip() is None, 'Invalid AppKit SDK capsule')
            commands = [row for row in sidecars.get('commands', []) if row.get('name') in [name + '-compile', name + '-sign', name + '-verify']]
            require([row.get('name') for row in commands] == [name + '-compile', name + '-sign', name + '-verify']
                    and all(row.get('exit') == 0 for row in commands)
                    and '-Wl,-undefined,error' in commands[0].get('argv', []), 'AppKit strict build/signature gates differ')
        return summary


def verify_helper_completion(proof, completion, original, prior, manifest, package):
    with zipfile.ZipFile(proof) as archive:
        names = safe_names(archive)
        raw = archive.read('helper-completion.json')
        require(hashlib.sha256(raw).hexdigest() == completion['receiptSha256'], 'Helper completion receipt differs')
        receipt = json.loads(raw)
        expected = {row['name']: row['sha256'] for row in manifest['files']}
        require(receipt.get('boundary') == 'immutable-d31-slim-stitched-helper-completion-v1'
                and receipt.get('accepted') is True and receipt.get('status') == 'compiled'
                and receipt.get('productSource') == PRODUCT and receipt.get('helperControlSource') == completion['workflowSource']
                and receipt.get('completionRun') == str(completion['run']) and receipt.get('originalRun') == original['run']
                and receipt.get('originalControllerSource') == original['workflowSource']
                and receipt.get('originalPhases') == dict(build=True, helpers=False, qualify=True)
                and receipt.get('originalProofPrefix') == original['proofPrefix']
                and receipt.get('helperBuilderGitBlob') == 'f626b86e23f8e78e5b08adcf17b58c7ec1efbf67'
                and receipt.get('inputsContractSha256') == completion['inputsContractSha256']
                and receipt.get('headerSha256') == prior['headerSha256'] and receipt.get('abi') == 64 and receipt.get('declarations') == 349,
                'Stitched helper F/original H/completion H identities differ')
        require(all(receipt.get(key) is False for key in ['productBuildRepeated', 'nativeGatesRepeated', 'engineCompilation',
                    'timerPageRecompiled', 'publication', 'runtimeConsumerQualification'])
                and all(receipt.get(key) is True for key in ['nativeUnchanged', 'sourcesUnchanged', 'archivesUnchanged', 'packageUnchanged',
                    'compilerUnchanged', 'originalConsumedInputsVerified', 'originalConsumedInputsUnchanged', 'acquisitionCredentialsRemoved'])
                and receipt.get('nativeBefore') == receipt.get('nativeAfter') == expected
                and receipt.get('packageSha256') == sha(package) and receipt.get('compilerSha256') == prior['compilerSha256']
                and receipt.get('sdk') == prior['sdk'] and PurePosixPath(receipt.get('compilerInvocation', '')).name == 'clang++',
                'Stitched helper boundary or unchanged inputs differ')
        members = receipt.get('members', {})
        alias = verify_completion_members(archive, receipt, package)
        require(members.get('proof.zip') == original['proofArtifact']['sha256']
                and members.get('package.zip') == original['packageArtifact']['sha256'], 'Completion substituted original artifacts')
        helpers = receipt.get('helpers', {})
        require(set(helpers) == {'timer', 'page', 'motion', 'contrast'}, 'Stitched helper inventory differs')
        for name in ['timer', 'page']:
            helper = helpers[name]
            old = prior['retainedTimerPage'][name]
            require(helper.get('reusedFromRun') == original['run'] and helper.get('path') == 'retained-sidecars/' + old['path']
                    and helper.get('sha256') == old['sha256']
                    and hashlib.sha256(archive.read(helper['path'])).hexdigest() == old['sha256']
                    and helper.get('receipt') == f'retained-sidecars/{name}/build-receipt.json'
                    and helper.get('capsule') == f'retained-sidecars/{name}/consumed-inputs.zip'
                    and hashlib.sha256(archive.read(helper['receipt'])).hexdigest() == old['receiptSha256']
                    and hashlib.sha256(archive.read(helper['capsule'])).hexdigest() == old['capsuleSha256'], 'Timer/page was replaced or recompiled')
        control = json.loads(archive.read('driver-control/driver-diagnostic.json'))
        require(control.get('result') == 'PASS' and control.get('source') == completion['workflowSource']
                and control.get('compilerSha256') == prior['compilerSha256'] and control.get('oldStrictLinkFailed') is True
                and control.get('newStrictLinkPassed') is True and control.get('actualProbe') == 0
                and control.get('helperSha256') == hashlib.sha256(archive.read('driver-control/new.dylib')).hexdigest()
                and all(control.get(key) is True for key in ['sourceUnchanged', 'compilerUnchanged', 'probeUnchanged'])
                and control.get('engineBuild') is False and control.get('nativePackageLoaded') is False, 'Actual C++ driver control did not pass')
        commands = receipt.get('commands', [])
        require([row.get('name') for row in commands] == ['driver-control', 'motion-dependencies', 'motion-compile', 'motion-sign', 'motion-verify',
                    'contrast-dependencies', 'contrast-compile', 'contrast-sign', 'contrast-verify']
                and all(row.get('exit') == 0 and row.get('directChildReaped') is True for row in commands), 'Completion compile/signature gates differ')
        for name in ['motion', 'contrast']:
            helper = helpers[name]
            require(helper.get('compiledInRun') == str(completion['run'])
                    and helper.get('path') == 'libRanvierCocoa' + name.title() + '.dylib'
                    and helper.get('capsule') == name + '-consumed-inputs.zip'
                    and hashlib.sha256(archive.read(helper['path'])).hexdigest() == helper.get('sha256')
                    and hashlib.sha256(archive.read(helper['capsule'])).hexdigest() == helper.get('capsuleSha256'), 'New AppKit helper identity differs')
            native_format(archive.read(helper['path']), 'osx-arm64')
            with zipfile.ZipFile(io.BytesIO(archive.read(helper['capsule']))) as capsule:
                require(set(safe_names(capsule)) == {'inputs/' + path.lstrip('/') for path in helper.get('inputs', {})}
                        and helper.get('inputs'), 'AppKit consumed input set differs')
                for path, expected_sha in helper['inputs'].items():
                    require(hashlib.sha256(capsule.read('inputs/' + path.lstrip('/'))).hexdigest() == expected_sha, 'AppKit consumed input bytes differ')
            compile_row, = [row for row in commands if row['name'] == name + '-compile']
            require(compile_row['argv'][0] == receipt['compilerInvocation'] and '-Wl,-undefined,error' in compile_row['argv'], 'AppKit C++ driver/strict link differs')
        return dict(run=completion['run'], controllerSource=completion['workflowSource'], receiptSha256=completion['receiptSha256'],
                    originalRun=original['run'], runtimeConsumerQualification=False, stitchedHelpersCompiled=True,
                    uploadByteComplete=alias is None, packageMetadataAlias=alias)


def verify_completion_members(archive, receipt, package):
    actual = {name for name in safe_names(archive) if not name.endswith('/')}
    members = receipt.get('members', {})
    expected = set(members) | {'helper-completion.json'}
    require(actual <= expected, 'Unexpected completion artifact member')
    missing = expected - actual
    alias = None
    if missing:
        name = 'stage/_rels/.rels'
        source = f'package/Ranvier.WebCore.Native.osx-arm64.{VERSION}.nupkg'
        digest = 'ffdb43dc427c61c172c7c6fa4dc013990649998e9b53fba3193774ce122140d7'
        require(missing == {name} and receipt.get('originalRun') == 41733425197 and members.get(name) == digest
                and source in actual and hashlib.sha256(archive.read(source)).hexdigest() == sha(package),
                'Unqualified missing completion member')
        with zipfile.ZipFile(io.BytesIO(archive.read(source))) as original_package:
            safe_names(original_package)
            require(hashlib.sha256(original_package.read('_rels/.rels')).hexdigest() == digest, 'Package metadata alias differs')
        alias = dict(missingMember=name, sourcePackageMember=source, innerMember='_rels/.rels', sha256=digest,
                     boundary='Single ancillary package metadata member; no artifact or receipt rewritten')
    for name, expected_sha in members.items():
        if name not in missing:
            require(hashlib.sha256(archive.read(name)).hexdigest() == expected_sha, 'Completion artifact member differs')
    return alias


def origins(policy, output):
    original_jobs = admit_original_run(api(f'actions/runs/{PRODUCER_RUN}'), jobs(PRODUCER_RUN))
    packages = output / 'packages'
    packages.mkdir()
    manifests = {}
    for rid in ORIGINAL_RIDS:
        record = policy['original'][rid]
        raw = artifact(record['artifact'], PRODUCER_RUN, PRODUCT, output)
        package = extract_package(raw, f'Ranvier.WebCore.Native.{rid}.{VERSION}.nupkg', packages)
        manifests[rid] = verify_native(package, rid, record['packageSha256'])
    mac = policy['macRecovery']
    run = api(f"actions/runs/{mac['run']}")
    repo_run(run)
    completion = mac.get('helperCompletion')
    require(run.get('head_sha') == mac['workflowSource'] and run.get('event') == 'workflow_dispatch'
            and run.get('head_branch') == 'main' and run.get('path') == '.github/workflows/macos-preview12-recovery.yml'
            and run.get('run_attempt') == 1 and run.get('status') == 'completed' and run.get('conclusion') == ('failure' if completion else 'success'),
            'Mac recovery workflow/run identity differs')
    response = jobs(mac['run'])
    selected = [job for job in response['jobs'] if job['name'] == 'recover']
    require(len(selected) == 1 and selected[0]['conclusion'] == ('failure' if completion else 'success'), 'Mac recovery job outcome differs')
    raw = artifact(mac['packageArtifact'], mac['run'], mac['workflowSource'], output)
    package = extract_package(raw, f'Ranvier.WebCore.Native.osx-arm64.{VERSION}.nupkg', packages)
    manifests['osx-arm64'] = verify_native(package, 'osx-arm64', mac['packageSha256'])
    proof = artifact(mac['proofArtifact'], mac['run'], mac['workflowSource'], output)
    mac_proof = verify_mac_proof(proof, mac, manifests['osx-arm64'], package, partial=bool(completion))
    if completion:
        run = api(f"actions/runs/{completion['run']}")
        repo_run(run)
        require(run.get('head_sha') == completion['workflowSource'] and run.get('event') == 'workflow_dispatch'
                and run.get('head_branch') == 'main' and run.get('path') == '.github/workflows/macos-preview12-helper-completion.yml'
                and run.get('run_attempt') == 1 and run.get('status') == 'completed' and run.get('conclusion') == 'success', 'Completion workflow/run differs')
        selected = [job for job in jobs(completion['run'])['jobs'] if job['name'] == 'complete']
        require(len(selected) == 1 and selected[0]['conclusion'] == 'success', 'Actual helper completion job did not pass')
        completed = artifact(completion['artifact'], completion['run'], completion['workflowSource'], output)
        mac_proof['helperCompletion'] = verify_helper_completion(completed, completion, mac, mac_proof, manifests['osx-arm64'], package)
    return packages, manifests, dict(originalJobs=original_jobs, mac=mac_proof)


def source_identity(root, expected, allow_generated=False):
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() == expected
            and not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=root, text=True), 'Source checkout differs or is dirty')
    allowed = ('packaging/obj/', 'packaging/bin/', 'src/Ranvier.WebCore/obj/', 'src/Ranvier.WebCore/bin/',
               'tests/recovery/InteropMetadata/obj/', 'tests/recovery/InteropMetadata/bin/')
    for ignored in (False, True):
        argv = ['git', 'ls-files', '--others', '--exclude-standard', '-z']
        if ignored:
            argv.insert(3, '--ignored')
        paths = subprocess.check_output(argv, cwd=root).decode().split('\0')
        require(all(not path or (allow_generated and path.startswith(allowed)) for path in paths),
                'Unexpected untracked or ignored source input')
    for parent in root.resolve().parents:
        require(not any(p.name.casefold() in {'directory.build.props', 'directory.build.targets', 'directory.packages.props',
                                              'directory.build.rsp', 'msbuild.rsp'}
                        for p in parent.iterdir()), 'Unexpected ancestor MSBuild import')


def source_inputs(product):
    paths = ['scripts/package_managed.py', 'src/Ranvier.WebCore/Ranvier.WebCore.fsproj',
             'packaging/Ranvier.WebCore.Native.Meta.csproj', 'tests/abi/generate_native.py', 'tests/abi/Native.fs',
             'tests/abi/NativeDom.fs', 'tests/abi/Traversal.fs', 'host/RanvierWebCoreAbi.h', 'host/RanvierWebCoreDom.h', 'gen/dom-api.json']
    return dict(product={name: sha(product / name) for name in paths}, controller={name: sha(ROOT / name) for name in
        ['scripts/recover_preview12_slim.py', 'tests/recovery/InteropMetadata/Program.cs', 'tests/recovery/InteropMetadata/InteropMetadata.csproj']})


def signature_manifest(product):
    spec = importlib.util.spec_from_file_location('F_native_generator', product / 'tests/abi/generate_native.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    header = (product / 'host/RanvierWebCoreAbi.h').read_text(encoding='utf-8')
    expected = {}
    for name, returns, parameters in generator.declarations(header):
        require(name not in expected, 'Duplicate canonical declaration')
        values = []
        for ctype, pname in parameters:
            kind, attributes = generator.parameter(ctype, pname)
            kind = {'double': 'float', 'double&': 'float&'}.get(kind, kind)
            values.append(dict(type=kind, input='In' in attributes, output='Out' in attributes,
                               marshal='30' if 'LPUTF8Str' in attributes else ''))
        expected[name] = dict(returns=generator.return_type(returns), parameters=values)
    require(len(expected) == 349, 'Require all 349 canonical signatures')
    return expected


def verify_signatures(actual, expected, binary_sha):
    require(len(expected) == 349 and actual.get('assemblySha256') == binary_sha
            and set(actual.get('functions', {})) == set(expected), 'Compiled signature inventory/binary differs')
    for name, signature in expected.items():
        actual_function = actual['functions'][name]
        require(actual_function.get('signature') == signature and actual_function.get('library') == 'RanvierWebCoreHost'
                and actual_function.get('convention') == 256, 'Compiled managed signature differs: ' + name)


def verify_aggregate_dependencies(dependencies):
    require(dependencies == {f'Ranvier.WebCore.Native.{rid}': '[' + VERSION + ']' for rid in RIDS}, 'Aggregate dependencies differ')


def admit_qualification_run(run, response, expected):
    repo_run(run)
    require(run.get('id') == expected['run'] and run.get('head_sha') == expected['workflowSource']
            and run.get('path') == '.github/workflows/preview12-slim-recovery.yml'
            and run.get('event') == 'workflow_dispatch' and run.get('head_branch') == 'main'
            and run.get('run_attempt') == 1 and run.get('status') == 'completed' and run.get('conclusion') == 'success', 'Qualification workflow/run differs')
    require(response.get('total_count') == len(response.get('jobs', [])), 'Qualification jobs are incomplete')
    selected = [job for job in response['jobs'] if job['name'] == 'qualify-slim-preview12']
    require(len(selected) == 1 and selected[0]['conclusion'] == 'success', 'Qualification job did not pass')


def verify_managed(packages, product, inspector):
    interop = packages / f'Ranvier.WebCore.{VERSION}.nupkg'
    aggregate = packages / f'Ranvier.WebCore.Native.{VERSION}.nupkg'
    with zipfile.ZipFile(aggregate) as archive:
        require(package_identity(archive)[:2] == ('Ranvier.WebCore.Native', VERSION), 'Aggregate identity differs')
        verify_aggregate_dependencies(package_identity(archive)[2])
        require(not any(name.startswith(('runtimes/', 'lib/')) for name in safe_names(archive)), 'Aggregate must contain dependencies, not runtime/code payload')
    with zipfile.ZipFile(interop) as archive:
        require(package_identity(archive)[:2] == ('Ranvier.WebCore', VERSION), 'Interop identity differs')
        project = ET.parse(product / 'src/Ranvier.WebCore/Ranvier.WebCore.fsproj')
        fsharp_core, = [node.get('Version') for node in project.iter('PackageReference') if node.get('Update') == 'FSharp.Core']
        require(package_identity(archive)[2] == {'FSharp.Core': fsharp_core}, 'Interop dependency metadata differs from F')
        require(not any(name.startswith('runtimes/') for name in safe_names(archive)), 'Interop contains a native payload')
        for member, source in [('include/RanvierWebCoreAbi.h', 'host/RanvierWebCoreAbi.h'),
                               ('include/RanvierWebCoreDom.h', 'host/RanvierWebCoreDom.h'), ('model/dom-api.json', 'gen/dom-api.json')]:
            require(archive.read(member) == (product / source).read_bytes(), 'Packaged header/model differs from F')
        binary = archive.read('lib/net10.0/Ranvier.WebCore.dll')
    verify_signatures(inspector, signature_manifest(product), hashlib.sha256(binary).hexdigest())
    return dict(interopSha256=sha(interop), aggregateSha256=sha(aggregate), assemblySha256=hashlib.sha256(binary).hexdigest(),
                exactSignatureCount=349, signedPublic=False)


def child(name, argv, output, cwd, environment, timeout=600):
    row = dict(name=name, argv=[str(value) for value in argv], cwd=str(cwd))
    process = None
    try:
        with (output / (name + '.log')).open('wb') as stream:
            process = subprocess.Popen(row['argv'], cwd=cwd, env=environment, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            row.update(pid=process.pid, started=time.time())
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                resident = 0
                for directory in Path('/proc').iterdir():
                    if directory.name.isdigit():
                        try:
                            fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
                            if int(fields[2]) == process.pid:
                                resident += int((directory / 'statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
                        except (OSError, IndexError):
                            pass
                row['peakResidentBytes'] = max(resident, row.get('peakResidentBytes', 0))
                require(resident <= 8 * 1024 ** 3 and time.monotonic() < deadline, 'Owned child memory/deadline limit')
                time.sleep(.1)
            row['exit'] = process.returncode
    finally:
        if process:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)
            row.update(groupKillRequested=True, directChildReaped=True)
            deadline = time.monotonic() + 5
            while True:
                live = []
                for directory in Path('/proc').iterdir():
                    if directory.name.isdigit():
                        try:
                            fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
                            if int(fields[2]) == process.pid and fields[0] != 'Z':
                                live.append(dict(pid=int(directory.name), startTicks=fields[19]))
                        except (OSError, IndexError):
                            pass
                if not live or time.monotonic() >= deadline:
                    break
                time.sleep(.05)
            row.update(ownedGroupNoLiveMembers=not live, remainingOwnedMembers=live)
        save(output / (name + '.json'), row)
    require(row.get('exit') == 0 and row.get('ownedGroupNoLiveMembers') is True, 'Managed qualification failed: ' + name)
    return row


def verify_restore(product, packages, cache, manifests):
    path = product / 'packaging/obj/project.assets.json'
    assets = json.loads(path.read_text())
    expected = {f'Ranvier.WebCore.Native.{rid}/{VERSION}'.casefold() for rid in RIDS}
    actual = [name.casefold() for name in assets['libraries'] if name.casefold().split('/', 1)[0] == 'ranvier.webcore.native'
              or name.casefold().startswith('ranvier.webcore.native.')]
    require(len(actual) == len(expected) and set(actual) == expected, 'Managed restore native graph differs')
    resolved = {name.casefold(): row for name, row in assets['libraries'].items()}
    result = {}
    for rid in RIDS:
        name = f'Ranvier.WebCore.Native.{rid}'
        row = resolved[(name + '/' + VERSION).casefold()]
        require(row.get('type') == 'package', 'Native restore library is not a package')
        folder = (cache / row['path']).resolve()
        require(folder.is_relative_to(cache.resolve()) and folder != cache.resolve(), 'Native restore cache path escapes cache')
        package = folder / f'{name}.{VERSION}.nupkg'.lower()
        metadata = json.loads((folder / '.nupkg.metadata').read_text())
        require(Path(metadata['source']).resolve() == packages.resolve() and sha(package) == sha(packages / f'{name}.{VERSION}.nupkg'),
                'Native restore used a public fallback or changed package')
        result[rid] = dict(packageSha256=sha(package), source=metadata['source'])
    return result


def qualify(args, policy):
    require(sys.platform == 'linux', 'Qualification uses the reviewed Linux managed packaging host')
    product = args.product_root.resolve(strict=True)
    source_identity(ROOT, policy['controllerSource'])
    source_identity(product, PRODUCT)
    output = args.output.resolve()
    require(not output.exists() and not any(output.is_relative_to(path) for path in [product, ROOT]), 'Require a fresh separate output')
    output.mkdir(parents=True)
    receipt = dict(accepted=False, signedPublic=False, productSource=PRODUCT, controllerSource=policy['controllerSource'],
                   producerRun=PRODUCER_RUN, policySha256=sha(args.policy), sourceInputs=source_inputs(product), steps=[])
    try:
        packages, manifests, origin = origins(policy, output)
        before = {path.name: sha(path) for path in packages.glob('*.nupkg')}
        receipt.update(origin=origin, nativeManifests=manifests, nativePackagesBefore=before)
        sdk = output / 'sdk'
        sdk.mkdir()
        save(sdk / 'global.json', dict(sdk=dict(version='10.0.403', rollForward='disable', allowPrerelease=False)))
        cache = output / 'cache'
        temp = output / 'temporary'
        temp.mkdir()
        environment = dict(os.environ, NUGET_PACKAGES=str(cache), DOTNET_CLI_HOME=str(output / 'dotnet-home'),
                           TMPDIR=str(temp), TEMP=str(temp), TMP=str(temp), DOTNET_PROCESSOR_COUNT='2', DOTNET_GCServer='0',
                           DOTNET_GCHeapHardLimit='100000000', MSBUILDDISABLENODEREUSE='1', DOTNET_CLI_USE_MSBUILD_SERVER='0',
                           DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER='1', UseSharedCompilation='false')
        for key in ['GH_TOKEN', 'GITHUB_TOKEN', 'NUGET_API_KEY', 'DOTNET_STARTUP_HOOKS', 'LD_PRELOAD']:
            environment.pop(key, None)
        receipt['steps'].append(child('generated-signatures', [sys.executable, '-B', '-I', product / 'tests/abi/generate_native.py', 'check'], output, sdk, environment))
        receipt['steps'].append(child('canonical-managed-pack', [sys.executable, '-B', '-I', product / 'scripts/package_managed.py',
                                     '--packages', packages, '--version', VERSION], output, sdk, environment, 1200))
        receipt['restore'] = verify_restore(product, packages, cache, manifests)
        require(all(sha(packages / name) == value for name, value in before.items()), 'Managed build modified a native package')
        expected = output / 'expected-signatures.json'
        save(expected, signature_manifest(product))
        interop_dll = output / 'Ranvier.WebCore.dll'
        with zipfile.ZipFile(packages / f'Ranvier.WebCore.{VERSION}.nupkg') as archive:
            interop_dll.write_bytes(archive.read('lib/net10.0/Ranvier.WebCore.dll'))
        tool = ROOT / 'tests/recovery/InteropMetadata/InteropMetadata.csproj'
        inspector_output = output / 'inspector'
        receipt['steps'].append(child('inspector-build', ['dotnet', 'build', tool, '-c', 'Release', '-o', inspector_output,
                                     '-m:1', '/nr:false', '-p:UseSharedCompilation=false'], output, sdk, environment))
        report = output / 'interop-metadata.json'
        receipt['steps'].append(child('inspector-run', ['dotnet', inspector_output / 'InteropMetadata.dll', interop_dll, expected, report], output, sdk, environment))
        receipt['managed'] = verify_managed(packages, product, json.loads(report.read_text()))
        all_packages = {path.name.removesuffix('.' + VERSION + '.nupkg'): sha(path) for path in packages.glob('*.nupkg')}
        require(set(all_packages) == PACKAGE_IDS, 'Exactly seven phase packages are required')
        receipt.update(packages=all_packages, expectedSignaturesSha256=sha(expected), inspectorReportSha256=sha(report),
                       inspectorSourceSha256=sha(ROOT / 'tests/recovery/InteropMetadata/Program.cs'), accepted=True)
    except BaseException as error:
        receipt.update(accepted=False, failureType=type(error).__name__, failure=str(error))
        raise
    finally:
        if 'nativePackagesBefore' in receipt:
            try:
                receipt['nativePackagesAfter'] = {name: sha(output / 'packages' / name) for name in receipt['nativePackagesBefore']}
                receipt['accepted'] &= receipt['nativePackagesAfter'] == receipt['nativePackagesBefore']
            except Exception as error:
                receipt.update(accepted=False, nativeIdentityError=repr(error))
        try:
            source_identity(product, PRODUCT, allow_generated=True)
            source_identity(ROOT, policy['controllerSource'], allow_generated=True)
            receipt['sourcesUnchanged'] = source_inputs(product) == receipt['sourceInputs']
            receipt['accepted'] &= receipt['sourcesUnchanged']
        except Exception as error:
            receipt.update(accepted=False, sourcesUnchanged=False, sourceError=repr(error))
        save(output / 'qualification.json', receipt)
    require(receipt['accepted'], 'Qualification did not preserve source/native identity')


def export(args, policy):
    product = args.product_root.resolve(strict=True)
    source_identity(product, PRODUCT)
    source_identity(ROOT, policy['controllerSource'])
    output = args.output.resolve()
    require(not output.exists() and not any(output.is_relative_to(path) for path in [product, ROOT]), 'Require a fresh separate export')
    output.mkdir(parents=True)
    packages, manifests, origin = origins(policy, output)
    q = policy['qualification']
    run = api(f"actions/runs/{q['run']}")
    admit_qualification_run(run, jobs(q['run']), q)
    proof = artifact(q['proofArtifact'], q['run'], q['workflowSource'], output)
    with zipfile.ZipFile(proof) as archive:
        safe_names(archive)
        raw = archive.read('qualification.json')
        require(hashlib.sha256(raw).hexdigest() == q['receiptSha256'], 'Qualification receipt differs')
        receipt = json.loads(raw)
        report_raw = archive.read('interop-metadata.json')
        require(hashlib.sha256(report_raw).hexdigest() == receipt.get('inspectorReportSha256'), 'Inspector report differs')
        report = json.loads(report_raw)
        expected_raw = archive.read('expected-signatures.json')
        require(hashlib.sha256(expected_raw).hexdigest() == receipt.get('expectedSignaturesSha256')
                and json.loads(expected_raw) == signature_manifest(product), 'Qualification canonical signature source differs')
    require(receipt.get('accepted') is True and receipt.get('signedPublic') is False and receipt.get('sourcesUnchanged') is True
            and receipt.get('productSource') == PRODUCT and receipt.get('controllerSource') == policy['controllerSource']
            and receipt.get('producerRun') == PRODUCER_RUN and receipt.get('policySha256') == q['policySha256']
            and receipt.get('sourceInputs') == source_inputs(product)
            and receipt.get('origin') == origin and receipt.get('nativeManifests') == manifests
            and receipt.get('packages') == q['packageHashes']
            and receipt.get('nativePackagesBefore') == receipt.get('nativePackagesAfter') == {path.name: sha(path) for path in packages.glob('*.nupkg')}
            and receipt.get('inspectorSourceSha256') == sha(ROOT / 'tests/recovery/InteropMetadata/Program.cs')
            and [step['name'] for step in receipt.get('steps', [])] == ['generated-signatures', 'canonical-managed-pack', 'inspector-build', 'inspector-run']
            and all(step.get('exit') == 0 and step.get('directChildReaped') is True and step.get('ownedGroupNoLiveMembers') is True
                    for step in receipt['steps']), 'Qualification evidence differs')
    compiled = artifact(q['packagesArtifact'], q['run'], q['workflowSource'], output)
    destination = output / 'export'
    destination.mkdir()
    with zipfile.ZipFile(compiled) as archive:
        names = [name for name in safe_names(archive) if not name.endswith('/')]
        require(set(names) == {name + '.' + VERSION + '.nupkg' for name in PACKAGE_IDS}, 'Qualification package set differs')
        for name in names:
            path = destination / name
            path.write_bytes(archive.read(name))
            identifier = name.removesuffix('.' + VERSION + '.nupkg')
            require(sha(path) == q['packageHashes'][identifier], 'Qualified package bytes differ')
    for rid in RIDS:
        native = destination / f'Ranvier.WebCore.Native.{rid}.{VERSION}.nupkg'
        require(sha(native) == sha(packages / native.name), 'Qualification substituted a native producer package')
        verify_native(native, rid, sha(native))
    verify_managed(destination, product, report)
    source_identity(product, PRODUCT)
    source_identity(ROOT, policy['controllerSource'])
    save(output / 'pre-authentication.json', dict(verified=True, signedPublic=False, productSource=PRODUCT,
         controllerSource=policy['controllerSource'], qualificationRun=q['run'], packages=q['packageHashes']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['qualify', 'export'])
    for name in ['policy', 'product-root', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text())
    admit_policy(policy, args.phase)
    (qualify if args.phase == 'qualify' else export)(args, policy)


if __name__ == '__main__':
    main()
