"""Verify frozen P7 Linux GPU artifacts and their exact consumer qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

PRODUCER = 41514646288
QUALIFICATION = 41535027181
SOURCE = '6f10bea17d7a1f22e5e97d472819c055fba3ef06'
POLICY = '9bf4e551bd3aa60e3c7e966d319b271479ad8d58'
EXPECTED = {
    'linux-x64': ('690a8101984277db2f46a9083bc78ca989377244e30dfecd6a6607e372407b05', '43ac3a8a57a9b1b42f2443387cd6f917003af9e60f36d9f476446d36eb273d56', 'ff62691a1553041cdb9d1d051ded12b129d5099809d006d4da2fa140e8409180'),
    'linux-arm64': ('627eca0f4b2d6299c7a5ed76bd2e790495922131263138bc2e7c1725d1a131ec', '373fac1ea2faeb814eab5e465865d3ef7f9bf7063508eb42d8fde93222c6e019', 'b4fb8533c580952e488a9010ccf9215e87210447c6fb2bd890d8051af25a1348'),
}
EVIDENCE = {
    'receipt.json': 'a63dc4905ee1f1edfa36962c5b24c7932d2b493db12bb656d5904574e912bc01',
    'canonical-original.json': '72d867f812dcff04e17bc0c7f24d9b12936dbd06aeeab49b34f40e242bec1469',
    'mesa-qualified.json': 'eb493320943bdfb3bd6f17f106af5477573822bdf916ba65b059fe3690556262',
    'mesa-shift-negative.json': 'f036dc6947ab4161c7ab02ce1695edd7ac6d7d77273a976eb23874446e3ba27a',
    'profile.log': 'c8725b2468c0b5c87f138d0eb0cc8e171cbcd70ad8392a50f62e466f6aae8f1a',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_profile(profile):
    require(profile['version'] == 'OpenGL ES 3.2 Mesa 25.2.8-0ubuntu0.24.04.4'
            and profile['renderer'] == 'llvmpipe (LLVM 20.1.2, 256 bits)'
            and profile['vendor'] == 'Mesa' and profile['subpixelBits'] == 8, 'Mesa profile mismatch')
    rows = profile['shaderPrecision']
    require(len(rows) == 6 and {(x['shader'], x['kind'], x['bits']) for x in rows} == {
        (shader, kind, bits) for shader in ('vertex', 'fragment')
        for kind, bits in (('low', 10), ('medium', 10), ('high', 23))}, 'Shader precision mismatch')


def api(path):
    output = subprocess.check_output(['gh', 'api', 'repos/ranvier-org/Ranvier.WebCore/' + path], text=True)
    return json.loads(output)


def check_remote():
    producer = api(f'actions/runs/{PRODUCER}')
    require(producer['head_sha'] == SOURCE and producer['event'] == 'workflow_dispatch'
            and producer['path'] == '.github/workflows/build.yml' and producer['run_attempt'] == 1
            and producer['status'] == 'completed' and producer['conclusion'] == 'failure', 'Producer run mismatch')
    jobs = api(f'actions/runs/{PRODUCER}/jobs?per_page=100')
    require(jobs['total_count'] == len(jobs['jobs']), 'Incomplete producer jobs')
    require(len({x['name'] for x in jobs['jobs']}) == len(jobs['jobs']), 'Duplicate producer job names')
    outcomes = {x['name']: x['conclusion'] for x in jobs['jobs']}
    require(outcomes.get('native (linux-x64, ubuntu-24.04, /mnt/rw)') == 'failure'
            and outcomes.get('native (linux-arm64, ubuntu-24.04-arm, /mnt/rw)') == 'success'
            and outcomes.get('publish') == 'skipped', 'Producer job outcomes changed')
    qualification = api(f'actions/runs/{QUALIFICATION}')
    require(qualification['head_sha'] == POLICY and qualification['event'] == 'push'
            and qualification['path'] == '.github/workflows/p7-linux-profile.yml'
            and qualification['run_attempt'] == 1 and qualification['status'] == 'completed'
            and qualification['conclusion'] == 'success', 'Qualification run mismatch')
    qjobs = api(f'actions/runs/{QUALIFICATION}/jobs?per_page=100')
    require(qjobs['total_count'] == len(qjobs['jobs']) == 1, 'Qualification job list mismatch')
    job = qjobs['jobs'][0]
    require(job['name'] == 'profile' and job['conclusion'] == 'success', 'Qualification job failed')
    steps = {x['name']: x['conclusion'] for x in job['steps']}
    require(steps.get('Query exact artifact host context and verify capture equivalence') == 'success', 'Qualification step missing')


def verify_package(rid, package, manifest, summary):
    package_hash, manifest_hash, summary_hash = EXPECTED[rid]
    require((sha(package), sha(manifest), sha(summary)) == (package_hash, manifest_hash, summary_hash), 'Producer artifact SHA mismatch')
    data = json.loads(manifest.read_text())
    require(data['source'] == {'commit': SOURCE, 'dirty': False, 'builder': 'ci'}
            and (data['rid'], data['flavor'], data['abi'], data['version']) == (rid, 'gpu', 62, '0.1.1-preview.7'), 'Manifest mismatch')
    require(len(data['files']) == 1 and data['files'][0]['name'] == 'libRanvierWebCoreHost.so', 'Native member mismatch')
    lines = summary.read_text().splitlines()
    failed = [line for line in lines if line.startswith('FAIL ')]
    require(len(lines) == 109 if rid == 'linux-x64' else len(lines) == 108, 'Producer group count mismatch')
    require((len(failed) == 1 and 'Verify fixed content clipping' in failed[0]) if rid == 'linux-x64' else not failed, 'Producer failures mismatch')
    require(sum(x.startswith('PASS ') for x in lines) == 108, 'Producer pass count mismatch')
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate archive member')
        require(archive.read('manifest.json') == manifest.read_bytes(), 'Embedded manifest mismatch')
        name = f'runtimes/{rid}/native/libRanvierWebCoreHost.so'
        native = [x for x in names if x.startswith(f'runtimes/{rid}/native/') and not x.endswith('/')]
        require(native == [name], 'Native payload set mismatch')
        payload = archive.read(name)
        row = data['files'][0]
        require(len(payload) == row['bytes'] and hashlib.sha256(payload).hexdigest() == row['sha256'], 'Native payload mismatch')
    return data


def verify_evidence(directory, original_report):
    require(sha(original_report) == EVIDENCE['canonical-original.json'], 'Original producer report mismatch')
    for name, digest in EVIDENCE.items():
        require(sha(directory / name) == digest, 'Qualification evidence mismatch: ' + name)
    receipt = json.loads((directory / 'receipt.json').read_text())
    require(receipt['sourceCommit'] == SOURCE and receipt['packageSha256'] == EXPECTED['linux-x64'][0]
            and receipt['nativeBefore'] == receipt['nativeAfter'] == 'c8c30f8ae6ea8d9d79bca9d40fcbf747176354e62437f6d9d74ec33230ca5f6d'
            and receipt['result'] == 'PASS' and receipt['unchangedCaptures'] == 54
            and receipt['canonicalOriginalExit'] == 1 and receipt['canonicalKnownPromotedRed'] == 2
            and receipt['canonicalStrictPass'] == 12 and receipt['canonicalOtherControlsPass'] == 52
            and receipt['qualifiedTargetPixels'] == 3000000 and receipt['qualifiedTargetFailures'] == 0, 'Consumer receipt mismatch')
    require(len(receipt['profiles']) >= 1, 'Missing actual profile')
    for profile in receipt['profiles']:
        check_profile(profile)
    original = json.loads(original_report.read_text())
    require(original['result'] == 'FAIL' and original['completeKeys'] == 54 and original['strictContentMaskKeys'] == 12
            and len(original['failures']) == 2 and {(x['name'], x['scale']) for x in original['failures']}
            == {('composited-translate', 1.5), ('composited-translate', 2)}
            and all(not x['strictFixedCase'] for x in original['failures']), 'Original gate mismatch')
    model = json.loads((directory / 'mesa-qualified.json').read_text())
    require(model['result'] == 'PASS' and len(model['cases']) == 2
            and {(x['scale'], x['checkedPixels'], x['failures']) for x in model['cases']}
            == {(1.5, 1080000, 0), (2, 1920000, 0)}, 'Mesa model mismatch')
    negative = json.loads((directory / 'mesa-shift-negative.json').read_text())
    require(negative['result'] == 'FAIL' and negative['mutation'] == 'shift' and len(negative['cases']) == 2
            and all(x['failures'] > 0 for x in negative['cases']), 'Negative control mismatch')


def main():
    parser = argparse.ArgumentParser()
    for option in ('x64-package', 'x64-manifest', 'x64-summary', 'arm64-package', 'arm64-manifest', 'arm64-summary', 'original-report', 'qualification-dir', 'export'):
        parser.add_argument('--' + option, required=True, type=Path)
    args = parser.parse_args()
    check_remote()
    verify_package('linux-x64', args.x64_package, args.x64_manifest, args.x64_summary)
    verify_package('linux-arm64', args.arm64_package, args.arm64_manifest, args.arm64_summary)
    verify_evidence(args.qualification_dir, args.original_report)
    args.export.mkdir(parents=True, exist_ok=False)
    for package in (args.x64_package, args.arm64_package):
        shutil.copy2(package, args.export / package.name)
        require(sha(args.export / package.name) == sha(package), 'Export changed')
    receipt = {'producer': PRODUCER, 'qualification': QUALIFICATION, 'source': SOURCE, 'result': 'PASS',
               'packages': {rid: hashes[0] for rid, hashes in EXPECTED.items()},
               'scope': 'Original Linux x64 FAIL retained; qualified Mesa x64 profile and original ARM64 passing producer'}
    (args.export.parent / 'verification.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
