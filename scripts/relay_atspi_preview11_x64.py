"""Validate and relay accepted local evidence; this never executes qualification tests."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'providers/atspi/preview11-x64-relay.json'
MANIFEST = 'qualification-evidence-manifest.json'
ARTIFACT = 'atspi-preview11-local-x64-qualified'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_policy(policy, transport=False):
    require(policy.get('schemaVersion') == 1 and policy.get('proofKind') == 'local-qualified-relayed'
            and policy.get('testsExecutedByRelay') is False, 'The relay must not claim test execution.')
    require(policy.get('rid') == 'linux-x64' and policy.get('nativeVersion') == '0.1.1-preview.11'
            and policy.get('domVersion') == '0.1.0-alpha.58', 'Wrong relay cohort.')
    for name in ['nativeSourceClaim', 'viewSource', 'compileHarnessSource', 'runtimeHarnessSource', 'releaseTargetCommit']:
        require(isinstance(policy.get(name), str) and re.fullmatch('[0-9a-f]{40}', policy[name]), 'Missing source pin: ' + name)
    for name in ['assetSha256', 'evidenceManifestSha256', 'sdkPackageSha256', 'qualificationReceiptSha256', 'hostSha256', 'providerSha256']:
        require(isinstance(policy.get(name), str) and re.fullmatch('[0-9a-f]{64}', policy[name]), 'Missing byte pin: ' + name)
    if transport:
        require(policy.get('armed') is True, 'The local proof receiver is unarmed.')
        for name in ['releaseId', 'assetId', 'assetBytes']:
            require(type(policy.get(name)) is int and policy[name] > 0, 'Missing exact transport pin: ' + name)
        for name in ['assetName', 'releaseAuthor', 'assetUploader']:
            require(isinstance(policy.get(name), str) and re.fullmatch('[A-Za-z0-9_.-]+', policy[name]), 'Missing transport identity: ' + name)


def inventory(archive):
    files = {}
    folded = set()
    with zipfile.ZipFile(archive) as zipped:
        for entry in zipped.infolist():
            name = entry.filename
            path = PurePosixPath(name)
            require(not entry.is_dir() and not stat.S_ISLNK(entry.external_attr >> 16), 'Evidence must contain regular files only.')
            require(name and not path.is_absolute() and path.as_posix() == name and '\\' not in name
                    and not any(part in ('.', '..') or ':' in part or part.endswith(('.', ' ')) for part in path.parts), 'Unsafe evidence path.')
            require(name.casefold() not in folded, 'Duplicate evidence path.')
            folded.add(name.casefold())
            files[name] = zipped.read(entry)
    require(MANIFEST in files, 'The complete evidence manifest is missing.')
    manifest = json.loads(files.pop(MANIFEST))
    require(manifest.get('files') == {name:sha(data) for name, data in files.items()}, 'Evidence manifest members or hashes differ.')
    return files, manifest


def validate_bundle(archive, policy):
    validate_policy(policy)
    require(archive.stat().st_size == policy['assetBytes'] and sha(archive.read_bytes()) == policy['assetSha256'], 'The accepted complete bundle bytes differ.')
    with zipfile.ZipFile(archive) as zipped:
        require(sha(zipped.read(MANIFEST)) == policy['evidenceManifestSha256'], 'The accepted evidence manifest differs.')
    files, manifest = inventory(archive)
    expected = dict(schemaVersion=1, proofKind='local-qualified', rid='linux-x64', abi=63,
                    nativeVersion=policy['nativeVersion'], sourceProvenance='unverified-caller-claim', allSixProfileEvidenceBound=True)
    expected.update({name:policy[name] for name in ['nativeSourceClaim', 'viewSource', 'compileHarnessSource', 'runtimeHarnessSource', 'hostSha256', 'providerSha256']})
    require(all(manifest.get(name) == value for name, value in expected.items()), 'The local qualification source/cohort claims differ.')
    package_path = manifest['packagePath']
    receipt_path = manifest['qualificationReceiptPath']
    require(sha(files[package_path]) == manifest['packageSha256'] == policy['sdkPackageSha256'], 'SDK package pin differs.')
    require(sha(files[receipt_path]) == manifest['qualificationReceiptSha256'] == policy['qualificationReceiptSha256'], 'Qualification receipt pin differs.')
    aggregate = load('relay_aggregate', ROOT / 'providers/atspi/public_aggregate.py')
    pins = dict(packageSha256=policy['sdkPackageSha256'], receiptSha256=policy['qualificationReceiptSha256'])
    cohort = dict(nativeVersion=policy['nativeVersion'], nativeSource=policy['nativeSourceClaim'],
                  providerSourceClaim=policy['nativeSourceClaim'], rids={'linux-x64':pins})
    with tempfile.TemporaryDirectory(prefix='atspi-relay-verify-') as directory:
        directory = Path(directory)
        package = directory / 'provider.nupkg'
        package.write_bytes(files[package_path])
        receipt = directory / 'qualification.json'
        receipt.write_bytes(files[receipt_path])
        checked = aggregate.checked_receipt(receipt, pins, cohort, 'linux-x64')
        aggregate.read_input(package, cohort, 'linux-x64', checked)
    managed_path = manifest['managedReceiptPath']
    require(sha(files[managed_path]) == manifest['managedReceiptSha256'], 'Managed receipt bytes differ.')
    managed = json.loads(files[managed_path])
    require(managed.get('allOwnedProcessesExited') is True and managed.get('tcpClosed') is True
            and managed.get('privateDisplayDirectoryRemoved') is True, 'Local runtime resources were not retired.')
    require(managed['hostSha256'] == policy['hostSha256'] and managed['providerSha256'] == policy['providerSha256']
            and managed['packageSha256'] == policy['sdkPackageSha256'] and managed['domVersion'] == policy['domVersion']
            and managed['sourceRevision'] == policy['nativeSourceClaim'], 'Managed runtime cohort differs.')
    helper = load('relay_managed', ROOT / 'tests/atspi/arm64_managed.py')
    require(set(manifest['rawAssetGraphs']) == {'normal', 'traced'}, 'Both exact raw asset graphs are required.')
    with zipfile.ZipFile(io.BytesIO(files[package_path])) as package:
        package_version = json.loads(package.read('provider-manifest.json'))['version']
    for mode, item in manifest['rawAssetGraphs'].items():
        require(sha(files[item['path']]) == item['sha256'] == managed['assetGraphs'][mode]['sha256'], 'Raw asset graph bytes differ.')
        helper.validate_assets(json.loads(files[item['path']])['libraries'], mode, managed['interopVersion'],
                               package_version,
                               'Ranvier.Private.Accessibility.Atspi.X64Qualification', policy['domVersion'])
    pairs = {(mode, profile) for mode in ('normal', 'traced') for profile in ('present', 'absent', 'no-bus')}
    require(len(managed['runs']) == 6 and {(row['mode'], row['profile']) for row in managed['runs']} == pairs, 'All six local profiles are required.')
    require(set(manifest['runtimeLogs']) == {mode + '-' + profile for mode, profile in pairs}, 'All six raw logs are required.')
    for row in managed['runs']:
        item = manifest['runtimeLogs'][row['mode'] + '-' + row['profile']]
        require(sha(files[item['path']]) == item['sha256'] == row['logSha256'], 'A raw runtime log differs.')
        require(sha(files[item['binaryPath']]) == item['binarySha256'] == row['binarySha256'], 'A prepared ELF differs.')
        binary = files[item['binaryPath']]
        require(binary[:6] == b'\x7fELF\x02\x01' and int.from_bytes(binary[18:20], 'little') == 62, 'Wrong prepared ELF architecture.')
        text = files[item['path']].decode()
        result = next(json.loads(line) for line in text.splitlines() if line.startswith('{'))
        helper.validate_result(result, row['profile'] == 'present')
        require(result == row['result'] and row['nativeBefore'] == row['nativeAfter'], 'Runtime result or native stability differs.')
        require(row['hostSha256'] == row['nativeBefore']['libRanvierWebCoreHost.so'] == policy['hostSha256'], 'Runtime Host pin differs.')
        if row['profile'] != 'absent':
            require(row['nativeBefore']['libRanvierWebCoreAtspi.so'] == policy['providerSha256'], 'Runtime provider pin differs.')
        maps = sorted({line.split()[-1] for line in text.splitlines() if line.startswith('native-map ')})
        require(maps == sorted(row['maps']), 'Actual native maps differ from the run receipt.')
    sdk = json.loads(files[manifest['ordinarySdkReceiptPath']])
    require(sha(files[manifest['ordinarySdkReceiptPath']]) == manifest['ordinarySdkReceiptSha256']
            and sdk['packageSha256'] == policy['sdkPackageSha256'] and sdk['consumer']['loaded'] is True
            and sdk['consumer']['providerSha256'] == policy['providerSha256'], 'Actual ordinary SDK load receipt differs.')
    return files, manifest


def validate_release(release, policy):
    require(release['id'] == policy['releaseId'], 'The release ID differs.')
    require(release['draft'] is True and release['target_commitish'] == policy['releaseTargetCommit']
            and release['author']['login'] == policy['releaseAuthor'], 'The pinned draft proof-only release differs.')
    assets = [asset for asset in release['assets'] if asset['id'] == policy['assetId']]
    require(len(assets) == 1, 'The exact draft asset is missing.')
    asset = assets[0]
    require(asset['name'] == policy['assetName'] and asset['size'] == policy['assetBytes']
            and asset['state'] == 'uploaded' and asset['uploader']['login'] == policy['assetUploader'], 'The draft asset identity differs.')


def receive(policy, work):
    validate_policy(policy, transport=True)
    require(os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch' and os.environ.get('GITHUB_REF') == 'refs/heads/main'
            and re.fullmatch('[0-9a-f]{40}', os.environ.get('GITHUB_SHA', '')), 'Require the exact main dispatch receiver identity.')
    release = json.loads(subprocess.check_output(['gh', 'api', 'repos/ranvier-org/Ranvier.WebCore/releases/' + str(policy['releaseId'])], text=True, timeout=30))
    validate_release(release, policy)
    work.mkdir(parents=True, exist_ok=False)
    archive = work / 'accepted-local-proof.zip'
    with archive.open('wb') as stream:
        subprocess.run(['gh', 'api', '-H', 'Accept: application/octet-stream',
                        'repos/ranvier-org/Ranvier.WebCore/releases/assets/' + str(policy['assetId'])], stdout=stream, check=True, timeout=180)
    files, manifest = validate_bundle(archive, policy)
    output = work / 'validated'
    for name, data in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with zipfile.ZipFile(archive) as zipped:
        (output / MANIFEST).write_bytes(zipped.read(MANIFEST))
    record = dict(schemaVersion=1, proofKind='local-qualified-relayed', testsExecutedByRelay=False,
                  qualificationReceiptSha256=policy['qualificationReceiptSha256'], sdkPackageSha256=policy['sdkPackageSha256'],
                  sourceProvenance='unverified-caller-claim', originalBundleSha256=policy['assetSha256'],
                  releaseId=policy['releaseId'], assetId=policy['assetId'], receiverWorkflow='.github/workflows/build.yml',
                  receiverHead=os.environ['GITHUB_SHA'], receiverEvent=os.environ['GITHUB_EVENT_NAME'])
    (output / 'relay-receipt.json').write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['receive', 'verify-bundle'])
    parser.add_argument('--work', type=Path)
    parser.add_argument('--bundle', type=Path)
    args = parser.parse_args()
    policy = json.loads(POLICY.read_text())
    if args.mode == 'receive':
        if args.work is None:
            parser.error('--work is required')
        receive(policy, args.work)
    else:
        if args.bundle is None:
            parser.error('--bundle is required')
        files, _ = validate_bundle(args.bundle, policy)
        print(json.dumps(dict(scope='offline metadata validation only; no transport or tests', members=len(files), bundleSha256=policy['assetSha256'])))
