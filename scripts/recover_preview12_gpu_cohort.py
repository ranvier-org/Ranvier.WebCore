"""Export the four unchanged preview12 GPU packages after distinct platform gates."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


slim = load(ROOT / 'scripts/recover_preview12_slim.py', 'slim_cohort_control')
require, sha, digest, revision = slim.require, slim.sha, slim.digest, slim.revision
PRODUCT, VERSION, WEBKIT, REPO = slim.PRODUCT, slim.VERSION, slim.WEBKIT, slim.REPO
RIDS = ('win-x64', 'linux-x64', 'linux-arm64', 'osx-arm64')
ORIGINAL_MAC_RUN = 41741551521
ORIGINAL_MAC_CONTROL = '131a73e1a1189afecf83a40ee50226da7a04e2c3'
CAPTURE_PREFIX = 'product-gates/mac-gpu-public-qualification/'
CAPTURES = ({f'cycle{index}-{phase}.bmp' for index in range(3) for phase in ('before', 'after')}
            | {f'input-{scale}-{phase}.bmp' for scale in (10, 15, 20) for phase in ('first', 'flipped', 'scrolled')})
# The immutable test at PRODUCT asserts ABI63 before any pixel work; corrected test G changes only that assertion.
WINDOWS_GUARD = 'Verify Windows same-document transition snapshot pixels'
WINDOWS_PROBE_STEP = 'Run the probes'
PUBLIC_STEPS = {'presenter-sdk', 'presenter-flags', 'compile-spike', 'public-spike',
                'compile-texture_input', 'public-texture_input', 'reject-software', 'reject-steady-base-repaint'}


def admit_policy(policy):
    require(policy.get('schemaVersion') == 1 and policy.get('armed') is True
            and policy.get('publicationEnabled') is True, 'GPU cohort publication is unarmed')
    require(policy.get('productSource') == PRODUCT and policy.get('version') == VERSION
            and revision(policy.get('controllerSource')), 'GPU cohort source/version differs')
    require(set(policy.get('packageHashes', {})) == set(RIDS)
            and all(digest(value) for value in policy['packageHashes'].values()), 'All four package hashes are required')
    require(type(policy.get('producerRun')) is int and policy['producerRun'] > 0, 'Original producer run is required')
    slim.admit_artifact_record(policy['windowsArtifact'], 'package-win-x64-gpu')
    probes = policy.get('windowsProbes', {})
    slim.admit_artifact_record(probes.get('artifact', {}), 'probe-logs-win-x64-gpu')
    require(digest(probes.get('summarySha256')) and digest(probes.get('failureLogSha256')),
            'Windows probe summary and ABI guard log hashes are required')
    mac = policy['mac']
    require(mac.get('originalRun') == ORIGINAL_MAC_RUN and mac.get('originalController') == ORIGINAL_MAC_CONTROL,
            'Original Mac recovery identity differs')
    for key, name in [('packageArtifact', 'package-osx-arm64-gpu'), ('proofArtifact', 'immutable-d31-mac-gpu-recovery-proof'),
                      ('replayArtifact', 'immutable-d31-mac-gpu-capture-replay')]:
        record = mac[key]
        require(type(record.get('id')) is int and record['id'] > 0 and digest(record.get('sha256'))
                and record.get('name') == name, 'Exact Mac artifact identity is required')
    require(type(mac.get('replayRun')) is int and mac['replayRun'] > 0 and revision(mac.get('replayController'))
            and digest(mac.get('replayReceiptSha256')) and digest(mac.get('originalReceiptSha256'))
            and digest(mac.get('originalGlyphReceiptSha256')),
            'Actual Mac capture replay is required')
    linux = policy['linux']
    require(linux.get('producerRun') == policy['producerRun'] and linux.get('productSource') == PRODUCT
            and revision(linux.get('controllerSource')), 'Linux qualification lineage differs')
    for rid in ('linux-x64', 'linux-arm64'):
        require(linux['rids'][rid]['packageSha256'] == policy['packageHashes'][rid], 'Linux cohort package differs')


def verify_package(package, rid, expected):
    require(rid in RIDS and sha(package) == expected, 'GPU package hash/RID differs')
    with zipfile.ZipFile(package) as archive:
        names = slim.safe_names(archive)
        require(slim.package_identity(archive)[:2] == ('Ranvier.WebCore.Native.Gpu.' + rid, VERSION), 'GPU package identity differs')
        manifest = json.loads(archive.read('manifest.json'))
        require((manifest.get('rid'), manifest.get('flavor'), manifest.get('version'), manifest.get('abi'), manifest.get('webkit'))
                == (rid, 'gpu', VERSION, 64, WEBKIT) and type(manifest['abi']) is int
                and manifest.get('source') == dict(commit=PRODUCT, dirty=False, builder='ci'), 'GPU product manifest differs')
        records = {row['name']: row for row in manifest['files']}
        prefix = f'runtimes/{rid}/native/'
        require(records and len(records) == len(manifest['files'])
                and {name[len(prefix):] for name in names if name.startswith(prefix) and not name.endswith('/')} == records.keys()
                and manifest['total_bytes'] == sum(row['bytes'] for row in records.values()), 'Complete GPU payload differs')
        host = 'RanvierWebCoreHost.dll' if rid.startswith('win-') else 'libRanvierWebCoreHost.' + ('dylib' if rid == 'osx-arm64' else 'so')
        require(host in records, 'GPU Host is missing')
        for name, row in records.items():
            parts = PurePosixPath(name).parts
            require('\\' not in name and PurePosixPath(name).as_posix() == name and not name.startswith('/')
                    and parts and not any(part in ('.', '..') or ':' in part for part in parts), 'Unsafe GPU payload name')
            data = archive.read(prefix + name)
            require(len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], 'GPU payload bytes differ')
            if name.endswith(('.dll', '.so', '.dylib')):
                slim.native_format(data, rid)
    return manifest


def admit_windows_run(run, jobs):
    """Admits the producer's Windows job when packaging succeeded and the probe step is its only failure."""
    slim.repo_run(run)
    require(run.get('head_sha') == PRODUCT and run.get('head_branch') == 'v' + VERSION
            and run.get('event') == 'workflow_dispatch' and run.get('path') == '.github/workflows/build.yml'
            and run.get('run_attempt') == 1 and run.get('status') == 'completed' and run.get('conclusion') == 'failure',
            'Original GPU producer identity/outcome differs')
    require(jobs.get('total_count') == len(jobs.get('jobs', [])), 'Producer jobs are incomplete')
    selected = [job for job in jobs['jobs'] if job['name'].startswith('native (win-x64,')]
    require(len(selected) == 1 and selected[0].get('conclusion') == 'failure', 'Actual Windows native job outcome differs')
    steps = selected[0].get('steps', [])
    package = [step for step in steps if step.get('name') == 'Package']
    failures = [step.get('name') for step in steps if step.get('conclusion') not in ('success', 'skipped')]
    require(len(package) == 1 and package[0].get('conclusion') == 'success' and failures == [WINDOWS_PROBE_STEP],
            'Windows producer failure was not solely the probe step after packaging')


def verify_windows_probes(archive_path, record, expected):
    """Requires every Windows probe to pass except the pinned ABI63 transition guard."""
    with zipfile.ZipFile(archive_path) as archive:
        slim.safe_names(archive)
        summary = archive.read('summary.txt')
        require(hashlib.sha256(summary).hexdigest() == record['summarySha256'], 'Windows probe summary hash differs')
        lines = summary.decode('utf-8').splitlines()
        require(len(lines) == len(expected), 'Windows probe inventory is incomplete')
        failed = []
        for line, entry in zip(lines, expected):
            match = re.fullmatch(r'(PASS|FAIL)\s+[0-9.]+ s\s+(.+)', line)
            require(match is not None, 'Unrecognized Windows summary row')
            outcome, rest = match.groups()
            if outcome == 'PASS':
                require(rest == entry['name'], 'Windows probe name/order differs')
                continue
            require(entry['name'] == WINDOWS_GUARD and rest.startswith(WINDOWS_GUARD + '  '), 'Unexpected Windows producer failure')
            log_name = rest.rsplit(', ', 1)[-1]
            require(re.fullmatch('[a-zA-Z0-9.-]+\\.log', log_name) is not None, 'Windows failure log path differs')
            data = archive.read(log_name)
            require(hashlib.sha256(data).hexdigest() == record['failureLogSha256'] and b'windows_view_transition_pixels.py' in data
                    and b'== 63' in data and b'AssertionError' in data, 'Windows failure is not the retained ABI guard RED')
            failed.append(entry['name'])
        require(failed == [WINDOWS_GUARD], 'Exactly the known Windows ABI guard failure is required')


def one_package(archive_path, output):
    with zipfile.ZipFile(archive_path) as archive:
        names = slim.safe_names(archive)
        packages = [name for name in names if name.endswith('.nupkg')]
        require(len(packages) == 1, 'Original package artifact is ambiguous')
        destination = output / Path(packages[0]).name
        require(not destination.exists(), 'Package destination already exists')
        destination.write_bytes(archive.read(packages[0]))
    return destination


def admit_mac_original(receipt, manifest):
    require(receipt.get('productSource') == PRODUCT and receipt.get('controlSource') == ORIGINAL_MAC_CONTROL
            and str(receipt.get('workflowRun')) == str(ORIGINAL_MAC_RUN)
            and receipt.get('flavor') == 'gpu' and receipt.get('version') == VERSION and receipt.get('accepted') is True,
            'Original Mac product/control receipt differs')
    for name in ('build', 'helpers', 'qualify'):
        phase = receipt['phases'][name]
        require(phase.get('passed') is True and phase.get('productClean') is True
                and phase.get('builderClean') is True and phase.get('identityErrors') == [], 'Original Mac phase did not pass')
    qualification = receipt['phases']['qualify']
    expected = {row['name']: row['sha256'] for row in manifest['files']}
    require(qualification.get('nativeBefore') == qualification.get('nativeAfter') == expected,
            'Original Mac native payload changed')
    require(qualification.get('gpuGlyph', {}).get('passed') is True
            and qualification['gpuGlyph'].get('source') == PRODUCT, 'Original Mac glyph gate did not pass')


def admit_mac_job(response):
    require(response.get('total_count') == len(response.get('jobs', [])), 'Original Mac job inventory is incomplete')
    selected = [job for job in response['jobs'] if job.get('name') == 'recover']
    require(len(selected) == 1 and selected[0].get('conclusion') == 'failure', 'Original Mac recovery job differs')
    steps = selected[0]['steps']
    expected = {'Recover the warm immutable product', 'Retain immutable product package',
                'Retain immutable product manifest', 'Build matching helpers',
                'Collect the independent immutable product gates', 'Always retain original SDK and helper proof'}
    for name in expected:
        matches = [step for step in steps if step.get('name') == name]
        require(len(matches) == 1 and matches[0].get('conclusion') == 'success', 'Original Mac product/proof step failed')
    failures = [step.get('name') for step in steps if step.get('conclusion') not in ('success', 'skipped')]
    require(failures == ['Consolidate the explicit owned proof root'], 'Original Mac failure was not solely proof consolidation')


def verify_glyph(archive, record, output):
    raw = archive.read('glyph-proof/orientation.json')
    require(hashlib.sha256(raw).hexdigest() == record['originalGlyphReceiptSha256'], 'Original glyph receipt digest differs')
    oracle = ROOT / 'tests/gpu/mac/glyph_orientation.py'
    require(sha(oracle) == 'cf246c50c7d000f0fa6f149fe5e65061eb46d6cbdfdd489267ebb7dae7d7299b', 'Canonical F glyph oracle differs')
    output.mkdir()
    labels = ('original-1', 'asymmetric-10', 'asymmetric-15', 'asymmetric-20')
    names = [f'{label}-{kind}.bmp' for label in labels for kind in ('cpu', 'gpu')]
    names += ['cg-copy-identity.bgra', 'cg-copy-flipped.bgra']
    for name in names:
        (output / name).write_bytes(archive.read('glyph-proof/' + name))
    replay = output / 'recomputed.json'
    with (output / 'oracle.log').open('wb') as stream:
        result = subprocess.run([sys.executable, '-B', '-I', str(oracle), '--captures', str(output), '--output', str(replay)],
                                stdout=stream, stderr=subprocess.STDOUT, timeout=60)
    require(result.returncode == 0, 'Canonical F glyph oracle rejected original captures')
    report = json.loads(raw)
    require(json.loads(replay.read_text(encoding='utf-8')) == report
            and [row['label'] for row in report['rows']] == list(labels)
            and all(row['sameDimensions'] is True and row['uprightMaskIoU'] == 1.0
                    and row['cpuBounds'] == row['gpuBounds'] and row['cpuInk'] == row['gpuInk'] > 0
                    for row in report['rows']), 'Original glyph receipt/pixels differ from recomputed oracle')


def mac_inputs(policy, output):
    record = policy['mac']
    original = slim.api(f'actions/runs/{ORIGINAL_MAC_RUN}')
    slim.repo_run(original)
    require(original.get('status') == 'completed' and original.get('conclusion') == 'failure'
            and original.get('head_sha') == ORIGINAL_MAC_CONTROL and original.get('event') == 'workflow_dispatch'
            and original.get('path') == '.github/workflows/macos-preview12-recovery.yml' and original.get('run_attempt') == 1,
            'Original Mac transport failure identity differs')
    admit_mac_job(slim.jobs(ORIGINAL_MAC_RUN))
    package_zip = slim.artifact(record['packageArtifact'], ORIGINAL_MAC_RUN, ORIGINAL_MAC_CONTROL, output)
    package = one_package(package_zip, output)
    manifest = verify_package(package, 'osx-arm64', policy['packageHashes']['osx-arm64'])
    proof = slim.artifact(record['proofArtifact'], ORIGINAL_MAC_RUN, ORIGINAL_MAC_CONTROL, output)
    with zipfile.ZipFile(proof) as archive:
        slim.safe_names(archive)
        raw = archive.read('recovery-receipt.json')
        require(hashlib.sha256(raw).hexdigest() == record['originalReceiptSha256'], 'Original Mac receipt hash differs')
        admit_mac_original(json.loads(raw), manifest)
        verify_glyph(archive, record, output / 'glyph-oracle')
    run = slim.api(f"actions/runs/{record['replayRun']}")
    slim.repo_run(run)
    require(run.get('status') == 'completed' and run.get('conclusion') == 'success'
            and run.get('head_sha') == record['replayController'] and run.get('event') == 'workflow_dispatch'
            and run.get('head_branch') == 'main' and run.get('run_attempt') == 1
            and run.get('path') == '.github/workflows/macos-preview12-capture-replay.yml', 'Actual Mac capture replay differs')
    replay = slim.artifact(record['replayArtifact'], record['replayRun'], record['replayController'], output)
    verify_mac_replay(replay, record, manifest, policy['packageHashes']['osx-arm64'])
    return package


def verify_mac_replay(path, record, manifest, package_sha):
    with zipfile.ZipFile(path) as archive:
        names = slim.safe_names(archive)
        raw = archive.read('capture-replay.json')
        require(hashlib.sha256(raw).hexdigest() == record['replayReceiptSha256'], 'Mac replay receipt hash differs')
        receipt = json.loads(raw)
        expected = {row['name']: row['sha256'] for row in manifest['files']}
        require(receipt.get('schemaVersion') == 1 and receipt.get('boundary') == 'immutable-d31-gpu-public-capture-replay-v1'
                and receipt.get('productSource') == PRODUCT and receipt.get('controlSource') == record['replayController']
                and str(receipt.get('run')) == str(record['replayRun']) and receipt.get('originalRun') == ORIGINAL_MAC_RUN
                and receipt.get('originalController') == ORIGINAL_MAC_CONTROL
                and receipt.get('originalProofArtifact') == record['proofArtifact']['id']
                and receipt.get('originalProofSha256') == record['proofArtifact']['sha256']
                and receipt.get('originalGlyphReceiptSha256') == record['originalGlyphReceiptSha256']
                and receipt.get('packageArtifact') == record['packageArtifact']['id']
                and receipt.get('packageArchiveSha256') == record['packageArtifact']['sha256']
                and receipt.get('packageSha256') == package_sha, 'Mac replay lineage differs')
        require(receipt.get('nativeBefore') == receipt.get('nativeAfter') == expected
                and all(receipt.get(key) is True for key in ('nativeUnchanged', 'productClean', 'controlClean',
                    'originalAccepted', 'originalGlyphPinned', 'passed'))
                and receipt.get('originalPhases') == dict(build=True, helpers=True, qualify=True)
                and all(receipt.get(key) is False for key in ('originalTransportComplete', 'engineBuild', 'hostBuild',
                    'helperBuild', 'catalogueRepeated', 'glyphRepeated')), 'Mac replay scope or unchanged payload differs')
        require(receipt.get('packageUnchanged') is True and receipt.get('acquisitionCredentialsRemoved') is True
                and receipt.get('ownedProcessesExited') is True and receipt.get('remainingOwnedProcesses') == []
                and len(receipt.get('steps', [])) == 1 and receipt['steps'][0].get('name') == 'public-output-input'
                and all(step.get('exit') == 0 and step.get('groupKillRequested') is True
                        and step.get('directChildReaped') is True and digest(step.get('logSha256'))
                        for step in receipt['steps']), 'Mac capture replay step or cleanup failed')
        require(hashlib.sha256(archive.read('public-output-input.log')).hexdigest() == receipt['steps'][0]['logSha256'],
                'Mac replay command log differs')
        with archive.open('original-proof.zip') as stream:
            require(hashlib.file_digest(stream, 'sha256').hexdigest() == record['proofArtifact']['sha256'],
                    'Retained original Mac proof differs')
        prefix = CAPTURE_PREFIX
        captures, logs = receipt.get('rawCaptureMembers', {}), receipt.get('rawLogMembers', {})
        require(set(captures) == {prefix + name for name in CAPTURES}
                and set(logs) == {prefix + name + '.log' for name in PUBLIC_STEPS}, 'Mac raw output/input proof is missing')
        for name, expected_sha in {**captures, **logs}.items():
            require(name.startswith(prefix) and name in names and digest(expected_sha)
                    and hashlib.sha256(archive.read(name)).hexdigest() == expected_sha, 'Mac raw capture/log bytes differ')
        require(receipt.get('publicReceipt') == prefix + 'receipt.json', 'Mac public receipt path differs')
        public_raw = archive.read(receipt['publicReceipt'])
        require(hashlib.sha256(public_raw).hexdigest() == receipt.get('publicReceiptSha256'), 'Mac public receipt digest differs')
        public = json.loads(public_raw)
        require(public.get('passed') is True and public.get('nativeBefore') == public.get('nativeAfter') == expected
                and len(public.get('steps', [])) == len(PUBLIC_STEPS)
                and {step['name'] for step in public['steps']} == PUBLIC_STEPS, 'Mac public qualifier scope differs')
        for step in public['steps']:
            if step['name'] == 'reject-steady-base-repaint':
                require(step.get('exit') == 1 and step.get('expectedFailure')
                        == 'MAC_GPU_SPIKE FAIL transform and opacity animation reuse base backing', 'Mac repaint negative differs')
            else:
                require(step.get('exit') == 0, 'Mac public qualifier step failed')
            require(step.get('logSha256') == logs[prefix + step['name'] + '.log'], 'Mac public step log differs')
        seal = json.loads(archive.read('artifact-members.json'))
        require(seal.get('schemaVersion') == 1 and seal.get('layout') == 'mac-recovery-proof-root-v1', 'Mac replay seal schema differs')
        members = seal['members']
        require(set(members) == {name for name in names if not name.endswith('/') and name != 'artifact-members.json'},
                'Mac replay member seal is incomplete')
        for name, expected_sha in members.items():
            data = archive.read(name)
            require(expected_sha == hashlib.sha256(data).hexdigest(), 'Mac replay sealed bytes differ')


def export(args, policy):
    admit_policy(policy)
    slim.source_identity(ROOT, policy['controllerSource'])
    linux_root = args.linux_controller.resolve(strict=True)
    slim.source_identity(linux_root, policy['linux']['controllerSource'])
    linux = load(linux_root / 'scripts/recover_preview12_linux_gpu.py', 'qualified_linux_gpu_control')
    linux.admit_policy(policy['linux'], 'export')
    output = args.output.resolve()
    require(not output.exists() and not output.is_relative_to(ROOT), 'Require fresh GPU export outside controller source')
    output.mkdir(parents=True)
    linux.export(argparse.Namespace(test_source=args.test_source, output=output / 'linux'), policy['linux'])
    run = slim.api(f"actions/runs/{policy['producerRun']}")
    admit_windows_run(run, slim.jobs(policy['producerRun']))
    windows_dir = output / 'windows'
    windows_dir.mkdir()
    windows_zip = slim.artifact(policy['windowsArtifact'], policy['producerRun'], PRODUCT, windows_dir)
    windows = one_package(windows_zip, windows_dir)
    verify_package(windows, 'win-x64', policy['packageHashes']['win-x64'])
    probe_zip = slim.artifact(policy['windowsProbes']['artifact'], policy['producerRun'], PRODUCT, windows_dir)
    plan = load(args.test_source.resolve(strict=True) / 'scripts/probes.py', 'windows_probe_plan')
    verify_windows_probes(probe_zip, policy['windowsProbes'],
                          [entry for entry in plan.PROBES if plan.applies(entry, 'win-x64', 'gpu')])
    mac_dir = output / 'mac'
    mac_dir.mkdir()
    mac = mac_inputs(policy, mac_dir)
    destination = output / 'export'
    destination.mkdir()
    packages = [windows, mac, *(output / 'linux/export').glob('*.nupkg')]
    require(len(packages) == 4, 'Exactly four GPU native packages are required')
    seen = set()
    for package in packages:
        with zipfile.ZipFile(package) as archive:
            rid = json.loads(archive.read('manifest.json'))['rid']
        require(rid not in seen and rid in RIDS, 'GPU cohort RID duplicates or differs')
        verify_package(package, rid, policy['packageHashes'][rid])
        seen.add(rid)
        target = destination / package.name
        shutil.copy2(package, target)
        require(sha(target) == policy['packageHashes'][rid], 'GPU export changed producer bytes')
    require(seen == set(RIDS), 'GPU cohort is incomplete')
    slim.save(output / 'pre-authentication.json', dict(verified=True, productSource=PRODUCT,
        controllerSource=policy['controllerSource'], packageHashes=policy['packageHashes'],
        originalMacTransportComplete=False, captureReplayRun=policy['mac']['replayRun']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['export'])
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--linux-controller', type=Path, required=True)
    parser.add_argument('--test-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args, json.loads(args.policy.read_text(encoding='utf-8')))


if __name__ == '__main__':
    main()
