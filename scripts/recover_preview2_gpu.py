"""Verify a fixed existing package without changing its product provenance."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import shutil
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_package(package, manifest_file, contract):
    require(isinstance(contract.get('testSource'), str)
            and re.fullmatch('[0-9a-f]{40}', contract['testSource']), 'Reviewed test source is not pinned')
    require(file_digest(package) == contract['packageSha256'], 'Fixed package SHA256 mismatch')
    require(package.stat().st_size == contract['packageBytes'], 'Fixed package byte count mismatch')
    manifest_bytes = manifest_file.read_bytes()
    require(digest(manifest_bytes) == contract['manifestSha256'], 'Fixed manifest SHA256 mismatch')
    manifest = json.loads(manifest_bytes)
    require(manifest.get('source') == {'commit': contract['productSource'], 'dirty': False, 'builder': 'ci'},
            'Product source must remain the exact clean CI commit')
    for name in ['version', 'abi', 'webkit', 'rid', 'flavor']:
        require(manifest.get(name) == contract[name], 'Product manifest mismatch: ' + name)
    require(manifest['files'] == contract['payloadFiles'], 'Fixed payload manifest differs')
    prefix = 'runtimes/' + contract['rid'] + '/native/'
    expected = {prefix + item['name']: item for item in manifest['files']}
    require(len(expected) == len(manifest['files']), 'Duplicate payload manifest entry')
    for item in manifest['files']:
        name = item['name']
        path = PurePosixPath(name)
        require(name and not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name,
                'Unsafe native payload path')
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate package ZIP member')
        require(archive.read('manifest.json') == manifest_bytes, 'Artifact and packaged manifests differ')
        for name, expected_sha in contract.get('headers', {}).items():
            require(digest(archive.read(name)) == expected_sha, 'Public header differs: ' + name)
        actual = {name for name in names if name.startswith(prefix) and not name.endswith('/')}
        require(actual == set(expected), 'Native payload set differs')
        payloads = {}
        total = 0
        for name, item in expected.items():
            info = archive.getinfo(name)
            require((info.external_attr >> 16) & 0o170000 != 0o120000, 'Native payload symlink')
            require(info.file_size == item['bytes'], 'Native payload size differs: ' + name)
            with archive.open(info) as stream:
                actual_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
            require(actual_sha == item['sha256'], 'Native payload SHA256 differs: ' + name)
            payloads[item['name']] = actual_sha
            total += info.file_size
        require(total == manifest['total_bytes'], 'Native payload total differs')
        specs = [name for name in names if name.endswith('.nuspec')]
        require(len(specs) == 1, 'Expected one package specification')
        metadata = ET.fromstring(archive.read(specs[0])).find('{*}metadata')
        require(metadata is not None, 'Package metadata absent')
        require(metadata.find('{*}id').text == contract['packageId'], 'Package ID mismatch')
        require(metadata.find('{*}version').text == contract['version'], 'Package version mismatch')
        repository = metadata.find('{*}repository')
        require(repository is not None and repository.get('commit') == contract['productSource'],
                'Package repository source differs')
    return {'productSource': contract['productSource'], 'testSource': contract['testSource'],
            'packageSha256': contract['packageSha256'], 'payloads': payloads,
            'publicationReady': False, 'scope': 'Offline artifact identity only; full catalogue and public cohort required'}


def download(url, destination, expected_sha, maximum_bytes):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_suffix(destination.suffix + '.partial')
        deadline = time.monotonic() + 120
        try:
            with urllib.request.urlopen(url, timeout=30) as response, temporary.open('xb') as output:
                require(response.status == 200, 'Download must return HTTP200')
                size = 0
                while block := response.read(1024 * 1024):
                    size += len(block)
                    require(size <= maximum_bytes and time.monotonic() <= deadline,
                            'Download exceeded its byte or time bound')
                    output.write(block)
            require(file_digest(temporary) == expected_sha, 'Downloaded SHA256 mismatch')
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    require(destination.stat().st_size <= maximum_bytes and file_digest(destination) == expected_sha,
            'Cached download SHA256 or size mismatch')


def verify_public_packages(cache, contract, offline=False):
    expected = contract['publicPackages']
    require(len(expected) == 7 and len({item['id'] for item in expected}) == 7, 'Public package cohort must contain seven distinct IDs')
    records = []
    for item in expected:
        require(re.fullmatch('[A-Za-z0-9.-]+', item['id']), 'Public package ID is unsafe')
        target = cache / (item['id'] + '.nupkg')
        require(target.is_file() or not offline, 'Public package missing: ' + item['id'])
        if not target.exists():
            lower = item['id'].lower()
            url = f"https://api.nuget.org/v3-flatcontainer/{lower}/{contract['version']}/{lower}.{contract['version']}.nupkg"
            download(url, target, item['sha256'], item['bytes'])
        require(target.stat().st_size == item['bytes'] and file_digest(target) == item['sha256'],
                'Public package SHA256 or byte count mismatch: ' + item['id'])
        records.append(dict(item))
    return {'publicPackages': records, 'publicationReady': False}


def verify_catalogue(summary, contract):
    records = []
    for line in summary.read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'PASS\s+(\d+(?:\.\d+)?)\s+s\s+(.+)', line)
        require(match is not None, 'Catalogue contains a failed or malformed result')
        require(math.isfinite(float(match[1])), 'Catalogue duration is invalid')
        records.append(match[2])
    require(len(records) == contract['catalogueGroups'] and records == contract['catalogueNames']
            and len(records) == len(set(records)), 'Catalogue is incomplete, duplicated or reordered')
    return {'catalogueGroupsPassed': len(records), 'catalogueNames': records,
            'summarySha256': file_digest(summary), 'publicationReady': False}


def verify_test_source(test_root, contract):
    def git(*arguments):
        return subprocess.check_output(['git', '-C', str(test_root), *arguments], timeout=30).decode().strip()
    require(git('rev-parse', 'HEAD') == contract['testSource'], 'Test checkout commit mismatch')
    require(not git('status', '--porcelain=v1', '--untracked-files=no'), 'Test checkout has tracked modifications')
    changed = git('diff', '--name-only', contract['productSource'], contract['testSource']).splitlines()
    require(changed == ['tests/gpu/NativeFrameAcceptance.cpp', 'tests/gpu/run.py'],
            'Test checkout includes changes outside the reviewed fixture and compiler link')
    return {'productSource': contract['productSource'], 'testSource': contract['testSource'],
            'changedFiles': changed, 'publicationReady': False}


def bounded_command(command, cwd, log, timeout, env=None):
    require(command and math.isfinite(timeout) and timeout > 0, 'Invalid bounded command')
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    cleanup = []
    timed_out = False
    with log.open('xb') as output:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT, **options)
        try:
            code = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            timed_out = isinstance(error, subprocess.TimeoutExpired)
            code = 124 if timed_out else 130
            if os.name == 'nt':
                try:
                    killed = subprocess.run(['taskkill', '/T', '/F', '/PID', str(process.pid)],
                                            stdout=output, stderr=subprocess.STDOUT, timeout=3)
                    cleanup.append({'taskkillExit': killed.returncode})
                except subprocess.TimeoutExpired:
                    cleanup.append({'taskkillTimedOut': True})
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    cleanup.append({'parentKillTimedOut': True})
    receipt = {'command': command, 'cwd': str(cwd), 'processId': process.pid, 'timeoutSeconds': timeout,
               'durationSeconds': round(time.monotonic() - started, 3), 'exit': code,
               'timedOut': timed_out, 'processEnded': process.poll() is not None,
               'cleanup': cleanup, 'logSha256': file_digest(log)}
    if not receipt['processEnded']:
        receipt['exit'] = 125
    return receipt


def qualify(package, manifest_file, test_root, work, evidence, contract):
    require(not work.exists() and not evidence.exists(), 'Recovery work and evidence directories must be fresh')
    work.mkdir(parents=True)
    evidence.mkdir(parents=True)
    receipt = {'productSource': contract['productSource'], 'testSource': contract['testSource'],
               'orchestratorSource': os.environ.get('GITHUB_SHA'), 'publicationReady': False, 'steps': []}
    try:
        receipt['testCheckout'] = verify_test_source(test_root, contract)
        receipt['packageBefore'] = verify_package(package, manifest_file, contract)
        orchestrator = Path(__file__).resolve().parents[1]
        actual_head = subprocess.check_output(['git', '-C', str(orchestrator), 'rev-parse', 'HEAD'], timeout=30).decode().strip()
        require(actual_head == receipt['orchestratorSource'], 'Orchestrator checkout differs from workflow commit')
        require(not subprocess.check_output(['git', '-C', str(orchestrator), 'status', '--porcelain=v1', '--untracked-files=no'], timeout=30).strip(),
                'Orchestrator checkout has tracked modifications')
        stage = work / 'out/gpu'
        native_prefix = 'runtimes/' + contract['rid'] + '/native/'
        with zipfile.ZipFile(package) as archive:
            for item in contract['payloadFiles']:
                target = stage / native_prefix / item['name']
                require(target.resolve().is_relative_to((stage / native_prefix).resolve()), 'Unsafe staged payload path')
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(native_prefix + item['name']) as original, target.open('xb') as destination:
                    shutil.copyfileobj(original, destination)
        (stage / 'manifest.json').write_bytes(manifest_file.read_bytes())
        require(len(contract['fonts']) == len({font['path'] for font in contract['fonts']}) == 5,
                'Expected five distinct pinned font assets')
        for font in contract['fonts']:
            path = PurePosixPath(font['path'])
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in font['path'] and ':' not in font['path'], 'Unsafe font asset path')
            url = 'https://raw.githubusercontent.com/WebKit/WebKit/' + contract['webkit'] + '/' + font['path']
            download(url, work / 'src' / font['path'], font['sha256'], 4 * 1024 * 1024)
        receipt['fonts'] = contract['fonts']
        receipt['publicCohort'] = verify_public_packages(work / 'public', contract)
        environment = dict(os.environ, DOTNET_CLI_USE_MSBUILD_SERVER='0', MSBUILDDISABLENODEREUSE='1')
        commands = [
            ('smoke', [sys.executable, '-I', str(test_root / 'scripts/smoke.py'), '--package', str(package),
                       '--expect-commit', contract['productSource'], '--expect-version', contract['version'], '--expect-flavor', 'gpu'], 180),
            ('packed-gpu', [sys.executable, '-I', str(test_root / 'scripts/check_package_api.py'), '--gpu', '--package', str(package)], 300),
            ('full-catalogue', [sys.executable, '-I', str(test_root / 'scripts/probes.py'), 'run', '--rid', 'win-x64', '--flavor', 'gpu',
                                '--work', str(work), '--logs', str(evidence / 'probe-logs')], 1800),
        ]
        for name, command, deadline in commands:
            print('Recovery step started: ' + name, flush=True)
            step = bounded_command(command, test_root, evidence / (name + '.log'), deadline, environment)
            receipt['steps'].append({'name': name, **step})
            require(step['exit'] == 0 and step['processEnded'] and not step['timedOut'], 'Recovery proof failed: ' + name)
            print('Recovery step passed: ' + name, flush=True)
        receipt['catalogue'] = verify_catalogue(evidence / 'probe-logs/summary.txt', contract)
        receipt['testCheckoutAfter'] = verify_test_source(test_root, contract)
        receipt['packageAfter'] = verify_package(package, manifest_file, contract)
        native = stage / native_prefix
        actual = {path.relative_to(native).as_posix(): file_digest(path) for path in native.rglob('*') if path.is_file()}
        require(actual == {item['name']: item['sha256'] for item in contract['payloadFiles']}, 'Staged product bytes changed during proof')
        receipt['stagedPayloadsAfter'] = actual
        receipt['publicCohortAfter'] = verify_public_packages(work / 'public', contract, offline=True)
        receipt['proofFiles'] = {path.relative_to(evidence).as_posix(): file_digest(path) for path in evidence.rglob('*') if path.is_file()}
        export = work / 'export'
        export.mkdir()
        shutil.copyfile(package, export / contract['package'])
        shutil.copyfile(manifest_file, export / 'manifest.json')
        require(file_digest(export / contract['package']) == contract['packageSha256'], 'Exported artifact changed')
        receipt['publicationReady'] = True
        (export / 'qualification.json').write_text(json.dumps(receipt, indent=2) + '\n')
        return receipt
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        (evidence / 'qualification.json').write_text(json.dumps(receipt, indent=2) + '\n')


def verify_publication(export, evidence, contract):
    verify_package(export / contract['package'], export / 'manifest.json', contract)
    receipt = json.loads((export / 'qualification.json').read_text())
    require(receipt == json.loads((evidence / 'qualification.json').read_text()), 'Qualification receipts differ')
    require(receipt['publicationReady'] is True and receipt['productSource'] == contract['productSource']
            and receipt['testSource'] == contract['testSource'] and receipt['orchestratorSource'] == os.environ.get('GITHUB_SHA'),
            'Qualification provenance differs from this workflow')
    steps = receipt['steps']
    require([step['name'] for step in steps] == ['smoke', 'packed-gpu', 'full-catalogue']
            and all(step['exit'] == 0 and step['processEnded'] and not step['timedOut'] for step in steps),
            'Qualification did not complete all three actual proof commands')
    full = steps[2]['command']
    require(len(full) == 12 and full[3:8] == ['run', '--rid', 'win-x64', '--flavor', 'gpu']
            and full[8] == '--work' and full[10] == '--logs', 'Catalogue invocation was filtered or changed')
    catalogue = verify_catalogue(evidence / 'probe-logs/summary.txt', contract)
    require(catalogue == receipt['catalogue'], 'Catalogue proof differs')
    require(receipt['publicCohort']['publicPackages'] == receipt['publicCohortAfter']['publicPackages'] == contract['publicPackages'],
            'Public package cohort proof differs')
    payloads = {item['name']: item['sha256'] for item in contract['payloadFiles']}
    require(receipt['packageBefore']['payloads'] == receipt['packageAfter']['payloads'] == receipt['stagedPayloadsAfter'] == payloads,
            'Qualified native payloads differ')
    actual_files = {path.relative_to(evidence).as_posix(): file_digest(path)
                    for path in evidence.rglob('*') if path.is_file() and path != evidence / 'qualification.json'}
    require(actual_files == receipt['proofFiles'], 'Proof file set or SHA256 differs')
    probe_logs = list((evidence / 'probe-logs').glob('*.log'))
    require(len(probe_logs) == contract['catalogueGroups'] and all(path.stat().st_size for path in probe_logs),
            'Proof file catalogue logs are incomplete')
    return {'publicationReady': True, 'productSource': contract['productSource'], 'testSource': contract['testSource'],
            'orchestratorSource': receipt['orchestratorSource'], 'packageSha256': contract['packageSha256'],
            'catalogueGroupsPassed': catalogue['catalogueGroupsPassed'], 'proofFilesRehashed': len(actual_files)}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    verify = sub.add_parser('verify')
    verify.add_argument('--package', required=True, type=Path)
    verify.add_argument('--manifest', required=True, type=Path)
    public = sub.add_parser('public')
    public.add_argument('--cache', required=True, type=Path)
    public.add_argument('--offline', action='store_true')
    catalogue = sub.add_parser('catalogue')
    catalogue.add_argument('--summary', required=True, type=Path)
    source = sub.add_parser('source')
    source.add_argument('--test-root', required=True, type=Path)
    qualification = sub.add_parser('qualify')
    qualification.add_argument('--package', required=True, type=Path)
    qualification.add_argument('--manifest', required=True, type=Path)
    qualification.add_argument('--test-root', required=True, type=Path)
    qualification.add_argument('--work', required=True, type=Path)
    qualification.add_argument('--evidence', required=True, type=Path)
    qualification.add_argument('--contract', required=True, type=Path)
    publication = sub.add_parser('publication')
    publication.add_argument('--export', required=True, type=Path)
    publication.add_argument('--evidence', required=True, type=Path)
    command = sub.add_parser('command')
    command.add_argument('--log', required=True, type=Path)
    command.add_argument('--timeout', required=True, type=float)
    command.add_argument('--receipt', required=True, type=Path)
    command.add_argument('argv', nargs=argparse.REMAINDER)
    for child in [verify, public, catalogue, source, publication]:
        child.add_argument('--contract', required=True, type=Path)
        child.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text()) if args.command != 'command' else None
    if args.command == 'qualify':
        receipt = qualify(args.package.resolve(), args.manifest.resolve(), args.test_root.resolve(),
                          args.work.resolve(), args.evidence.resolve(), contract)
        print(json.dumps({'publicationReady': receipt['publicationReady'],
                          'catalogue': receipt['catalogue']['catalogueGroupsPassed']}))
        return 0
    elif args.command == 'command':
        command = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
        receipt = bounded_command(command, Path.cwd(), args.log, args.timeout)
    elif args.command == 'verify':
        receipt = verify_package(args.package, args.manifest, contract)
    elif args.command == 'public':
        receipt = verify_public_packages(args.cache, contract, args.offline)
    elif args.command == 'catalogue':
        receipt = verify_catalogue(args.summary, contract)
    elif args.command == 'publication':
        receipt = verify_publication(args.export, args.evidence, contract)
    else:
        receipt = verify_test_source(args.test_root, contract)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
    return receipt['exit'] if args.command == 'command' else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, ET.ParseError) as error:
        print('Recovery verification refused: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
