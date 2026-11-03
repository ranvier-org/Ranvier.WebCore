"""Prepare or verify the allocated AT-SPI candidate; authentication and publication stay in build.yml."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / 'providers/atspi'
IDENTITY = 'Ranvier.WebCore.Accessibility.Atspi'
VERSION = '0.1.1-preview.10'
ARTIFACT = 'atspi-preview10-candidate'
QUALIFICATIONS = {
    'linux-x64': (41604812065, '9a92b3b290aeed18cadde0f90f6443893c288a99'),
    'linux-arm64': (41600991338, 'fdcae76d164daf88ca9e462cc8b272fea4ddf7ba'),
}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


aggregate = load_module('preview10_aggregate', PROVIDER / 'public_aggregate.py')
candidate = load_module('preview10_candidate', PROVIDER / 'release_candidate.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(arguments, **kwargs):
    return subprocess.run(arguments, check=True, timeout=240, **kwargs)


def check_run(run, head):
    result = subprocess.check_output(['gh', 'api', 'repos/ranvier-org/Ranvier.WebCore/actions/runs/' + str(run)],
                                     text=True, timeout=30)
    record = json.loads(result)
    if record['head_sha'] != head or record['conclusion'] != 'success' or record['event'] != 'workflow_dispatch':
        raise ValueError('The selected retained workflow run differs from its reviewed identity.')
    return record


def select_inputs(directory, pins):
    packages = list((directory / 'package').glob('*.nupkg'))
    matches = [path for path in packages if sha(path) == pins['packageSha256']]
    receipt = directory / 'qualification-receipt.json'
    if len(matches) != 1 or not receipt.is_file() or sha(receipt) != pins['receiptSha256']:
        raise ValueError('Require one pinned package-directory input and its exact root qualification receipt.')
    return matches[0], receipt


def absent_public_version():
    url = 'https://api.nuget.org/v3-flatcontainer/' + IDENTITY.lower() + '/' + VERSION + '/' + IDENTITY.lower() + '.' + VERSION + '.nupkg'
    try:
        with urllib.request.urlopen(url, timeout=30):
            raise ValueError('The allocated provider version is already public; refuse another push.')
    except urllib.error.HTTPError as error:
        error.close()
        if error.code != 404:
            raise


def qualify_inputs(work, policy):
    inputs, receipts = {}, {}
    for rid, (run, head) in QUALIFICATIONS.items():
        check_run(run, head)
        directory = work / rid
        artifact = 'unqualified-atspi-' + rid.removeprefix('linux-') + '-' + head
        command(['gh', 'run', 'download', str(run), '--repo', 'ranvier-org/Ranvier.WebCore',
                 '--name', artifact, '--dir', str(directory)])
        inputs[rid], receipts[rid] = select_inputs(directory, policy['rids'][rid])
    payload, manifest = aggregate.prepare(policy, inputs, receipts)
    return inputs, receipts, payload, manifest


def prepare(work):
    policy_path = PROVIDER / 'public-preview10.json'
    policy = json.loads(policy_path.read_text())
    inputs, receipts, _, _ = qualify_inputs(work, policy)
    absent_public_version()
    record = aggregate.pack(policy, inputs, receipts, work / 'feed', work / 'sdk-work')
    layouts = {}
    for rid in ('linux-x64', 'linux-arm64'):
        command([sys.executable, '-I', str(ROOT / 'tests/atspi/consumer.py'), '--package', record['path'],
                 '--rid', rid, '--layout-only', '--output', str(work / ('sdk-' + rid))], cwd=work)
        layouts[rid] = work / ('sdk-' + rid) / 'consumer-receipt.json'
    bundle = work / 'candidate'
    bundle.mkdir()
    shutil.copy2(record['path'], bundle / Path(record['path']).name)
    shutil.copy2(policy_path, bundle / 'selected-cohort.json')
    shutil.copy2(work / 'sdk-work/aggregate-receipt.json', bundle / 'aggregate-receipt.json')
    for rid, path in layouts.items():
        shutil.copy2(path, bundle / (rid + '-layout.json'))
    binding = candidate.record_candidate(work / 'sdk-work/aggregate-receipt.json', policy_path, layouts)
    (bundle / 'release-candidate.json').write_text(json.dumps(binding, indent=2))
    print(json.dumps(binding, indent=2))


def validate_publication_pins(pins):
    if pins.get('schemaVersion') != 1 or pins.get('id') != IDENTITY or pins.get('version') != VERSION:
        raise ValueError('The publication identity differs from the allocated provider.')
    if type(pins.get('candidateRun')) is not int or pins['candidateRun'] <= 0:
        raise ValueError('An independently reviewed candidate run is required.')
    for key, length in [('candidateHead', 40), ('packageSha256', 64), ('candidateReceiptSha256', 64)]:
        if not isinstance(pins.get(key), str) or not re.fullmatch('[0-9a-f]{' + str(length) + '}', pins[key]):
            raise ValueError('An exact reviewed publication pin is required: ' + key)


def verify(work):
    pins = json.loads((PROVIDER / 'preview10-publication.json').read_text())
    validate_publication_pins(pins)
    run = check_run(pins['candidateRun'], pins['candidateHead'])
    if run['path'] != '.github/workflows/build.yml':
        raise ValueError('The reviewed candidate must come from the existing build workflow.')
    bundle = work / 'candidate'
    command(['gh', 'run', 'download', str(pins['candidateRun']), '--repo', 'ranvier-org/Ranvier.WebCore',
             '--name', ARTIFACT, '--dir', str(bundle)])
    policy = json.loads((PROVIDER / 'public-preview10.json').read_text())
    if (bundle / 'selected-cohort.json').read_bytes() != (PROVIDER / 'public-preview10.json').read_bytes():
        raise ValueError('The candidate cohort bytes differ from the reviewed release source.')
    _, _, payload, manifest = qualify_inputs(work, policy)
    package = bundle / (IDENTITY + '.' + VERSION + '.nupkg')
    binding_path = bundle / 'release-candidate.json'
    if sha(package) != pins['packageSha256'] or sha(binding_path) != pins['candidateReceiptSha256']:
        raise ValueError('The candidate bytes differ from the independently reviewed pins.')
    binding = json.loads(binding_path.read_text())
    if binding['package'] != dict(id=IDENTITY, version=VERSION, filename=package.name, sha256=pins['packageSha256']):
        raise ValueError('The candidate package binding differs.')
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or json.loads(archive.read('provider-manifest.json')) != manifest:
            raise ValueError('The candidate manifest or ZIP path set differs.')
        if any(archive.read(name) != data for name, data in payload.items()):
            raise ValueError('The candidate contains changed qualified payload bytes.')
        if {name for name in names if name.endswith('.so')} != {name for name in payload if name.endswith('.so')}:
            raise ValueError('The optional provider must not bundle another native library or Host.')
    # Rebind the copied aggregate record locally without changing the immutable artifact.
    aggregate_record = json.loads((bundle / 'aggregate-receipt.json').read_text())
    if sha(bundle / 'aggregate-receipt.json') != binding['aggregateReceiptSha256']:
        raise ValueError('The original candidate aggregate receipt bytes changed.')
    aggregate_record['path'] = str(package)
    local_record = work / 'local-aggregate-receipt.json'
    local_record.write_text(json.dumps(aggregate_record))
    layouts = {rid: bundle / (rid + '-layout.json') for rid in QUALIFICATIONS}
    checked = candidate.record_candidate(local_record, bundle / 'selected-cohort.json', layouts)
    for field in ('package', 'qualificationInputs', 'sdkLayout', 'cohortFileSha256', 'sourceProvenance'):
        if checked[field] != binding[field]:
            raise ValueError('The retained candidate evidence differs: ' + field)
    absent_public_version()
    export = work / 'export'
    export.mkdir()
    shutil.copy2(package, export / package.name)
    (work / 'verification.json').write_text(json.dumps(dict(packageSha256=sha(package), candidateRun=pins['candidateRun'],
        candidateHead=pins['candidateHead'], inputQualificationRuns=QUALIFICATIONS, sourceProvenance='unverified-caller-claim'), indent=2))
    print('Verified unchanged provider candidate before authentication')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'verify'])
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    (args.work / 'global.json').write_text(json.dumps(dict(sdk=dict(version='10.0.403', rollForward='disable'))))
    globals()[args.mode](args.work.resolve())
