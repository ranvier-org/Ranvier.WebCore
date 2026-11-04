"""Qualify unchanged preview12 Linux GPU producer bytes with the corrected ABI test."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPO = 'ranvier-org/Ranvier.WebCore'
PRODUCT = 'd31c3631ed4bbe6520f7f5f7c7e7d34499c38122'
TEST_SOURCE = 'f2d5b2b4c0b0404586097696907dc36e83dc87b9'
VERSION = '0.1.1-preview.12'
RIDS = ('linux-x64', 'linux-arm64')
FAILED_GROUP = 'Verify Linux same-document transition snapshot pixels'
# The linux-x64 producer also exceeded the 16 MiB third-round growth bound by 132 KiB. The exact log is pinned
# per RID, and the qualification catalogue reruns web_animations.py against the unchanged package bytes.
GROWTH_GROUP = 'Verify Web Animations creation against the Chromium oracle'
TEST_CHANGES = {'.github/workflows/build.yml', 'tests/abi/test_abi_expectation.py',
                'tests/atspi/protocol_errors.py', 'tests/atspi/run.py', 'tests/atspi/test_protocol_errors.py',
                'tests/gpu/linux_view_transition_pixels.py', 'tests/gpu/test_linux_transition_abi.py'}


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


def admit_policy(policy, phase):
    require(policy.get('schemaVersion') == 1 and policy.get('armed') is True, 'Recovery policy is unarmed')
    require(policy.get('productSource') == PRODUCT and policy.get('testSource') == TEST_SOURCE
            and policy.get('version') == VERSION and revision(policy.get('controllerSource')), 'Recovery source/version differs')
    require(type(policy.get('producerRun')) is int and policy['producerRun'] > 0, 'An actual producer run is required')
    require(set(policy.get('rids', {})) == set(RIDS), 'Both original Linux producer packages must be pinned')
    for rid, record in policy['rids'].items():
        require(digest(record.get('packageSha256')) and digest(record.get('summarySha256'))
                and digest(record.get('failureLogSha256')), 'Original package and failure evidence hashes are required')
        require('growthFailureLogSha256' not in record or rid == 'linux-x64' and digest(record['growthFailureLogSha256']),
                'Retained growth failure log hash is malformed')
        for key, name in [('packageArtifact', f'package-{rid}-gpu'), ('probeArtifact', f'probe-logs-{rid}-gpu')]:
            artifact = record.get(key, {})
            require(type(artifact.get('id')) is int and artifact['id'] > 0 and artifact.get('name') == name
                    and digest(artifact.get('sha256')), 'Exact producer artifact identity is required')
    if phase == 'export':
        qualification = policy.get('qualification', {})
        require(policy.get('publicationEnabled') is True and type(qualification.get('run')) is int
                and revision(qualification.get('workflowSource')) and digest(qualification.get('policySha256'))
                and set(qualification.get('rids', {})) == set(RIDS), 'Publication remains disabled pending reviewed qualification')
        for rid, record in qualification['rids'].items():
            require(type(record.get('id')) is int and record['id'] > 0
                    and record.get('name') == f'qualified-preview12-{rid}'
                    and digest(record.get('sha256')) and digest(record.get('receiptSha256')), 'Qualification artifact is unallocated')


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPO}/{path}'], timeout=90))


def check_producer(policy):
    run = api(f"actions/runs/{policy['producerRun']}")
    require(run['head_sha'] == PRODUCT and run['head_branch'] == 'v' + VERSION
            and run['event'] == 'workflow_dispatch' and run['path'] == '.github/workflows/build.yml'
            and run['run_attempt'] == 1 and run['status'] == 'completed' and run['conclusion'] == 'failure',
            'Original immutable producer identity/outcome differs')
    response = api(f"actions/runs/{policy['producerRun']}/jobs?per_page=100")
    require(response['total_count'] == len(response['jobs']), 'Producer job response is incomplete')
    for rid in RIDS:
        jobs = [job for job in response['jobs'] if job['name'].startswith('native (' + rid + ',')]
        require(len(jobs) == 1 and jobs[0]['conclusion'] == 'failure', 'Original Linux producer failure is missing')
    return run


def pinned_artifact(record, run_id, source, directory):
    metadata = api(f"actions/artifacts/{record['id']}")
    require(metadata['name'] == record['name'] and metadata['expired'] is False
            and metadata['workflow_run']['id'] == run_id and metadata['workflow_run']['head_sha'] == source
            and metadata.get('digest') == 'sha256:' + record['sha256'], 'Remote artifact identity differs')
    path = directory / (str(record['id']) + '.zip')
    with path.open('wb') as stream:
        subprocess.run(['gh', 'api', f"repos/{REPO}/actions/artifacts/{record['id']}/zip"], stdout=stream, check=True, timeout=240)
    require(sha(path) == record['sha256'], 'Downloaded artifact digest differs')
    return path


def safe_names(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)) and len(names) == len({name.casefold() for name in names}), 'Duplicate archive member')
    for name in names:
        path = PurePosixPath(name)
        require(not path.is_absolute() and '\\' not in name and path.as_posix() == name.rstrip('/')
                and not any(part in {'.', '..'} or ':' in part for part in path.parts), 'Unsafe archive member')
    return names


def verify_package(package, rid, expected_sha):
    require(rid in RIDS and sha(package) == expected_sha, 'Original package SHA differs')
    with zipfile.ZipFile(package) as archive:
        names = safe_names(archive)
        manifest = json.loads(archive.read('manifest.json'))
        require((manifest['rid'], manifest['flavor'], manifest['abi'], manifest['version']) == (rid, 'gpu', 64, VERSION)
                and type(manifest['abi']) is int
                and manifest['source'] == dict(commit=PRODUCT, dirty=False, builder='ci'), 'Product manifest differs')
        records = {item['name']: item for item in manifest['files']}
        prefix = f'runtimes/{rid}/native/'
        require(len(records) == len(manifest['files']) and 'libRanvierWebCoreHost.so' in records
                and {name[len(prefix):] for name in names if name.startswith(prefix) and not name.endswith('/')} == records.keys()
                and manifest['total_bytes'] == sum(item['bytes'] for item in records.values()), 'Complete native payload set differs')
        for name, record in records.items():
            payload = archive.read(prefix + name)
            require(len(payload) == record['bytes'] and hashlib.sha256(payload).hexdigest() == record['sha256'], 'Native payload bytes differ')
        nuspecs = [name for name in names if name.endswith('.nuspec') and '/' not in name]
        require(len(nuspecs) == 1, 'Native package identity is ambiguous')
        metadata = {node.tag.rsplit('}', 1)[-1]: node.text for node in ET.fromstring(archive.read(nuspecs[0])).iter()}
        require(metadata.get('id') == 'Ranvier.WebCore.Native.Gpu.' + rid and metadata.get('version') == VERSION, 'Package ID/version differs')
    return manifest


def source_admission(source, controller):
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == controller,
            'Recovery controller checkout differs')
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip() == TEST_SOURCE,
            'Corrected consumer checkout differs')
    for path in [ROOT, source]:
        require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=path, text=True), 'Source checkout is dirty')
    changed = set(subprocess.check_output(['git', 'diff', '--name-only', PRODUCT, TEST_SOURCE], cwd=source, text=True).splitlines())
    require(changed == TEST_CHANGES, 'Product versus corrected test source has an unreviewed change')
    spec = importlib.util.spec_from_file_location('recovery_probe_plan', source / 'scripts/probes.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_summary(archive, record, expected):
    with zipfile.ZipFile(archive) as stream:
        safe_names(stream)
        summary = stream.read('summary.txt')
        require(hashlib.sha256(summary).hexdigest() == record['summarySha256'], 'Original summary hash differs')
        lines = summary.decode('utf-8').splitlines()
        require(len(lines) == len(expected), 'Original probe inventory is incomplete')
        failed, retained = [], []
        for line, entry in zip(lines, expected):
            match = re.fullmatch(r'(PASS|FAIL)\s+[0-9.]+ s\s+(.+)', line)
            require(match is not None, 'Unrecognized original summary row')
            outcome, rest = match.groups()
            if outcome == 'PASS':
                require(rest == entry['name'], 'Original probe name/order differs')
            elif entry['name'] == GROWTH_GROUP and 'growthFailureLogSha256' in record:
                require(rest.startswith(GROWTH_GROUP + '  '), 'Unexpected original producer failure')
                log_name = rest.rsplit(', ', 1)[-1]
                require(re.fullmatch('[a-zA-Z0-9.-]+\\.log', log_name) is not None, 'Original failure log path differs')
                data = stream.read(log_name)
                require(hashlib.sha256(data).hexdigest() == record['growthFailureLogSha256']
                        and b'web_animations.py' in data and b'AssertionError: memory flat across rounds' in data,
                        'Original failure is not the retained pinned growth RED')
                retained.append(entry['name'])
            else:
                require(entry['name'] == FAILED_GROUP and rest.startswith(FAILED_GROUP + '  '), 'Unexpected original producer failure')
                log_name = rest.rsplit(', ', 1)[-1]
                require(re.fullmatch('[a-zA-Z0-9.-]+\\.log', log_name) is not None, 'Original failure log path differs')
                data = stream.read(log_name)
                require(hashlib.sha256(data).hexdigest() == record['failureLogSha256'] and b'linux_view_transition_pixels.py' in data
                        and b'== 63' in data and b'AssertionError' in data, 'Original failure is not the retained ABI guard RED')
                failed.append(entry['name'])
        require(failed == [FAILED_GROUP], 'Exactly the known original ABI guard failure is required')
        return retained


def snapshot(directory):
    return {path.relative_to(directory).as_posix(): sha(path) for path in sorted(directory.rglob('*')) if path.is_file()}


def group_state(group, expected_host, work, verified):
    rss, mappings = 0, []
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            stat = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(stat[2]) != group:
                continue
            rss += int((directory / 'statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
            for line in (directory / 'maps').read_text().splitlines():
                fields = line.split(maxsplit=5)
                if len(fields) != 6 or not fields[5].endswith('/libRanvierWebCoreHost.so'):
                    continue
                path = Path(fields[5]).resolve(strict=True)
                info = path.stat()
                require(path.is_relative_to(work) and info.st_ino == int(fields[4]), 'Actually mapped Host path/inode differs')
                identity = (str(path), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                if identity not in verified:
                    require(sha(path) == expected_host, 'Actually mapped Host differs from the package')
                    verified[identity] = expected_host
                environment = dict(item.split('=', 1) for item in (directory / 'environ').read_text().split('\0') if '=' in item)
                command = (directory / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
                mappings.append(dict(pid=int(directory.name), startTicks=stat[19], path=str(path), sha256=expected_host,
                                     command=command, mode=environment.get('RANVIER_WEBCORE_PROBE', 'normal')))
                break
        except (OSError, IndexError, ProcessLookupError):
            continue
    return rss, mappings


def live_group(group):
    result = []
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            stat = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(stat[2]) == group and stat[0] != 'Z':
                result.append(dict(pid=int(directory.name), startTicks=stat[19]))
        except (OSError, IndexError):
            continue
    return result


def execute(name, command, output, environment, source, expected_host, work, timeout):
    spec = importlib.util.spec_from_file_location('recovery_owned_child', source / 'scripts/qualify_producer_gpu_clipping.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    row = dict(name=name, argv=[str(value) for value in command], mappings=[])
    child = None
    try:
        with (output / (name + '.log')).open('wb') as stream:
            child = module.OwnedChild(row['argv'], stream, environment, source)
            deadline = time.monotonic() + timeout
            seen = {}
            verified = {}
            while child.process.poll() is None:
                rss, mappings = group_state(child.process.pid, expected_host, work, verified)
                row['peakResidentBytes'] = max(rss, row.get('peakResidentBytes', 0))
                seen.update({(item['pid'], item['startTicks']): item for item in mappings})
                require(rss <= 8 * 1024 ** 3 and time.monotonic() < deadline, 'Owned qualification memory/deadline guard')
                time.sleep(0.05)
            row.update(exit=child.process.returncode, mappings=list(seen.values()))
    finally:
        try:
            if child:
                child.close()
                row['primaryReaped'] = child.process.returncode is not None
                deadline = time.monotonic() + 5
                remaining = live_group(child.process.pid)
                while remaining and time.monotonic() < deadline:
                    time.sleep(0.05)
                    remaining = live_group(child.process.pid)
                row['ownedGroupNoLiveMembers'] = not remaining
                row['remainingOwnedMembers'] = remaining
        except Exception as error:
            row['cleanupFailure'] = repr(error)
        finally:
            (output / (name + '.json')).write_text(json.dumps(row, indent=2) + '\n', encoding='utf-8')
    require(row.get('exit') == 0 and row.get('primaryReaped') is True and row.get('ownedGroupNoLiveMembers') is True
            and not row.get('cleanupFailure'),
            'Qualification step or owned cleanup failed: ' + name)
    return row


def original_inputs(policy, rid, output):
    record = policy['rids'][rid]
    package_zip = pinned_artifact(record['packageArtifact'], policy['producerRun'], PRODUCT, output)
    package = output / f'Ranvier.WebCore.Native.Gpu.{rid}.{VERSION}.nupkg'
    with zipfile.ZipFile(package_zip) as archive:
        require([name for name in safe_names(archive) if not name.endswith('/')] == [package.name], 'Package artifact has unexpected members')
        package.write_bytes(archive.read(package.name))
    manifest = verify_package(package, rid, record['packageSha256'])
    probes = pinned_artifact(record['probeArtifact'], policy['producerRun'], PRODUCT, output)
    return package, manifest, probes


def qualify(args, policy):
    rid = args.rid
    require(sys.platform == 'linux' and platform.machine() == {'linux-x64': 'x86_64', 'linux-arm64': 'aarch64'}[rid], 'Use the actual matching Linux architecture')
    source = args.test_source.resolve(strict=True)
    plan = source_admission(source, policy['controllerSource'])
    check_producer(policy)
    output = args.output.resolve()
    require(not output.exists() and not output.is_relative_to(source) and not output.is_relative_to(ROOT), 'Require a fresh owned qualification directory')
    output.mkdir(parents=True)
    receipt = dict(accepted=False, productSource=PRODUCT, testSource=TEST_SOURCE, controllerSource=policy['controllerSource'],
                   producerRun=policy['producerRun'], qualificationPolicySha256=sha(args.policy), rid=rid, steps=[])
    try:
        package, manifest, original_logs = original_inputs(policy, rid, output)
        verify_summary(original_logs, policy['rids'][rid], [entry for entry in plan.PROBES if plan.applies(entry, rid, 'gpu')])
        stage = output / 'work/out/gpu'
        stage.mkdir(parents=True)
        native = stage / f'runtimes/{rid}/native'
        with zipfile.ZipFile(package) as archive:
            for name in safe_names(archive):
                if name == 'manifest.json' or name.startswith(f'runtimes/{rid}/native/') and not name.endswith('/'):
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
        before = snapshot(native)
        receipt.update(packageSha256=sha(package), nativeBefore=before)
        temporary = output / 'temporary'
        temporary.mkdir()
        environment = dict(os.environ, RANVIER_ABI_TEST_EXPECTED='64', EGL_PLATFORM='surfaceless', LIBGL_ALWAYS_SOFTWARE='1',
                           MSBUILDDISABLENODEREUSE='1', DOTNET_CLI_USE_MSBUILD_SERVER='0', UseSharedCompilation='false',
                           TMPDIR=str(temporary), TEMP=str(temporary), TMP=str(temporary))
        for key in ['LD_PRELOAD', 'DOTNET_STARTUP_HOOKS', 'GH_TOKEN', 'NUGET_API_KEY']:
            environment.pop(key, None)
        environment['LD_LIBRARY_PATH'] = str(native)
        host = before['libRanvierWebCoreHost.so']
        commands = [('smoke', [sys.executable, '-B', '-I', source / 'scripts/smoke.py', '--package', package, '--expect-commit', PRODUCT], 300),
                    ('packaged-gpu-api', [sys.executable, '-B', '-I', source / 'scripts/check_package_api.py', '--gpu', '--package', package, '--expected-abi', '64'], 900),
                    ('abi-catalogue', [sys.executable, '-B', '-I', source / 'scripts/abi_tests.py', '--stage', stage,
                                       '--source', args.webkit_source.resolve(strict=True), '--expected-abi', '64',
                                       '--evidence-directory', output / 'abi-evidence'], 1800)]
        for name, command, timeout in commands:
            receipt['steps'].append(execute(name, command, output, environment, source, host, output, timeout))
        modes = {item['mode'] for step in receipt['steps'] for item in step['mappings'] if 'RanvierWebCoreAbi.Driver.dll' in item['command']}
        require(modes == {'normal', 'teardown'}, 'Both actual managed driver processes need package-bound Host mappings')
        require(b'abi tests passed' in (output / 'abi-catalogue.log').read_bytes(), 'Full catalogue terminal marker is absent')
        require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=source, text=True), 'Qualification changed corrected source')
        receipt['accepted'] = True
    except Exception as error:
        receipt['failure'] = repr(error)
        raise
    finally:
        if 'nativeBefore' in receipt:
            receipt['nativeAfter'] = snapshot(native)
            receipt['accepted'] = receipt['accepted'] and receipt['nativeAfter'] == receipt['nativeBefore']
        (output / 'qualification.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    require(receipt['accepted'], 'Qualification did not preserve original native bytes')


def export(args, policy):
    plan = source_admission(args.test_source.resolve(strict=True), policy['controllerSource'])
    check_producer(policy)
    q = policy['qualification']
    run = api(f"actions/runs/{q['run']}")
    require(run['status'] == 'completed' and run['conclusion'] == 'success' and run['head_sha'] == q['workflowSource']
            and run['path'] == '.github/workflows/preview12-linux-gpu-recovery.yml' and run['run_attempt'] == 1,
            'Actual successful qualification run is not the reviewed run')
    jobs = api(f"actions/runs/{q['run']}/jobs?per_page=100")
    require(jobs['total_count'] == len(jobs['jobs']), 'Qualification jobs are incomplete')
    output = args.output.resolve()
    require(not output.exists(), 'Require a fresh pre-authentication export')
    output.mkdir(parents=True)
    for rid in RIDS:
        selected = [job for job in jobs['jobs'] if job['name'] == 'qualify-' + rid]
        require(len(selected) == 1 and selected[0]['conclusion'] == 'success', 'Actual RID qualification did not pass')
        package, manifest, logs = original_inputs(policy, rid, output)
        verify_summary(logs, policy['rids'][rid], [entry for entry in plan.PROBES if plan.applies(entry, rid, 'gpu')])
        proof = pinned_artifact(q['rids'][rid], q['run'], q['workflowSource'], output)
        with zipfile.ZipFile(proof) as archive:
            safe_names(archive)
            raw = archive.read('qualification.json')
            require(hashlib.sha256(raw).hexdigest() == q['rids'][rid]['receiptSha256'], 'Qualification receipt digest differs')
            receipt = json.loads(raw)
        expected = {item['name']: item['sha256'] for item in manifest['files']}
        require(receipt.get('accepted') is True and receipt['productSource'] == PRODUCT and receipt['testSource'] == TEST_SOURCE
                and receipt['controllerSource'] == policy['controllerSource'] and receipt['producerRun'] == policy['producerRun']
                and receipt['qualificationPolicySha256'] == q['policySha256'] and receipt['rid'] == rid
                and receipt['packageSha256'] == policy['rids'][rid]['packageSha256']
                and receipt['nativeBefore'] == receipt['nativeAfter'] == expected
                and [step['name'] for step in receipt['steps']] == ['smoke', 'packaged-gpu-api', 'abi-catalogue']
                and all(step['exit'] == 0 and step['primaryReaped'] is True and step['ownedGroupNoLiveMembers'] is True
                        for step in receipt['steps']), 'Qualification evidence differs')
        destination = output / 'export'
        destination.mkdir(exist_ok=True)
        shutil.copy2(package, destination / package.name)
        require(sha(destination / package.name) == policy['rids'][rid]['packageSha256'], 'Export modified producer package')
    (output / 'pre-authentication.json').write_text(json.dumps(dict(verified=True, productSource=PRODUCT, testSource=TEST_SOURCE,
        controllerSource=policy['controllerSource'], qualificationRun=q['run'], packages={rid: policy['rids'][rid]['packageSha256'] for rid in RIDS}), indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['qualify', 'export'])
    for name in ['policy', 'test-source', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--rid', choices=RIDS)
    parser.add_argument('--webkit-source', type=Path)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text())
    admit_policy(policy, args.phase)
    if args.phase == 'qualify':
        require(args.rid is not None and args.webkit_source is not None, 'RID and original pinned WebKit fixtures are required')
        qualify(args, policy)
    else:
        export(args, policy)


if __name__ == '__main__':
    main()
