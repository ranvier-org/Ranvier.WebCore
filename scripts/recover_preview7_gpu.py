"""Verify the immutable P7 Windows GPU producer and its pinned qualification."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

REPO = 'ranvier-org/Ranvier.WebCore'
PRODUCER = 41498246594
PRODUCT = '6f10bea17d7a1f22e5e97d472819c055fba3ef06'
PACKAGE = 'Ranvier.WebCore.Native.Gpu.win-x64.0.1.1-preview.7.nupkg'
PACKAGE_SHA = 'aa9ca63366cf04c3c9e7b27d90c0758f5129bf5c64532e7540c27f857b8adb41'
MANIFEST_SHA = 'd659c45fde66a7ea91339a57ad198452512285124458c87c9effc1d4aca18b40'
SUMMARY_SHA = '53522a9ec4fa01a041eb3ccb6eb477c05026bf50e8baee282f1f068dabeaabf9'
ORIGINAL_REPORT_SHA = '14d1bf2f5ac620f4b0dd01a26c8de822d6847eca84ea17b957bdc4f46db79c94'
CASES = {'bordered-half-phase', 'zero-origin', 'borderless-half-phase', 'negative-origin',
         'fractional-border-padding', 'nested-offset', 'translate-fractional', 'scale-fractional',
         'rotate-quarter', 'rotate-oblique', 'composited-translate', 'always-composited',
         'ancestor-scroll', 'local-background-scroll', 'padding-box', 'fragment-slice',
         'fragment-clone', 'rounded-border-control'}
FIXED = {'bordered-half-phase', 'negative-origin', 'nested-offset', 'always-composited'}

TRUSTED_QUALIFICATION = 41541720378
TRUSTED_POLICY = '4d99783d1a90863bfdeaffccb8e032edded846de'
TRUSTED_WORKFLOW = '.github/workflows/p7-windows-qualification.yml'
EVIDENCE_SHA = json.loads(Path(__file__).with_name('preview7_windows_evidence.json').read_text())
QUALIFICATION_STEPS = ('Check qualification contract', 'Check numeric evidence persistence',
                       'Check per-format primitive policy controls', 'Qualify exact P7 Windows artifact')
PROFILE = 'ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11-10.0.26100.33648)'
SOURCE_SHA = {
    '.github/workflows/p7-windows-qualification.yml': '84f15f30dc5cbbde5da4f50a741a9f8bfe3ab793dffa0ce0ac5475c76956956c',
    'scripts/qualify_p7_clipping.py': '662558478dcb1267da7fdb10984692bcbd8ded4ddd3ec721a08d8d49bf90ee43',
    'scripts/capture_p7_clipping.py': '5e44c3e1a2602635042bd1cfcabb24b27f6ff11cbe844242b5910d5b9ef9362c',
    'tests/p7_gpu_qualification/cases.json': '77d7472d0cd458e439adf6b3b38e379437bc0f632390394a1666e05e314c71b1',
    'tests/p7_gpu_qualification/baseline-a9.json': '787743d5a92863d0d576592ab9c5e5aedf03ca8feaafba444dedd93c43d70d1d',
    'tests/p7_gpu_qualification/gpu_pixel_gate_v3.py': 'e13e7889839688b4a0e87c809489fcf7ba0d6bd91749173741ede93d863634c3',
    'tests/p7_gpu_qualification/sampler_format_policy.py': 'ff9b73d9b5d1deed82b098724596aae8078ea79a4aed445c6c12996b3fce1dc9',
    'tests/p7_gpu_qualification/sampler_format_probe.py': 'b70ec77b5e50a7f0c77a1e2e95cb4d3978f296ed11d423b6ee07c36aed2a4054',
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPO}/{path}'], timeout=60))


def verify(package, manifest_path, evidence, summary_path, original_report_path, qualification):
    require(qualification == TRUSTED_QUALIFICATION, 'Qualification run does not match the trusted pin')
    producer = api(f'actions/runs/{PRODUCER}')
    qualified = api(f'actions/runs/{qualification}')
    require(producer['head_sha'] == PRODUCT and producer['status'] == 'completed'
            and producer['conclusion'] == 'failure' and producer['event'] == 'workflow_dispatch'
            and producer['head_branch'] == 'v0.1.1-preview.7'
            and producer['path'] == '.github/workflows/build.yml' and producer['run_attempt'] == 1,
            'Producer identity or status changed')
    require(qualified['head_sha'] == TRUSTED_POLICY and qualified['event'] == 'workflow_dispatch'
            and qualified['path'] == TRUSTED_WORKFLOW and qualified['run_attempt'] == 1
            and qualified['status'] == 'completed' and qualified['conclusion'] == 'success',
            'Qualification identity or status changed')
    for name, digest in SOURCE_SHA.items():
        content = api(f'contents/{name}?ref={TRUSTED_POLICY}')
        require(content['encoding'] == 'base64' and sha(base64.b64decode(content['content'])) == digest,
                f'Qualification source SHA mismatch: {name}')
    response = api(f'actions/runs/{qualification}/jobs?per_page=100')
    jobs = response['jobs']
    require(response['total_count'] == len(jobs), 'Qualification job list is incomplete')
    selected = [job for job in jobs if job['name'] == 'qualify']
    require(len(selected) == 1 and selected[0]['conclusion'] == 'success', 'Qualification job missing')
    steps = {step['name']: step['conclusion'] for step in selected[0]['steps']}
    require(all(steps.get(name) == 'success' for name in QUALIFICATION_STEPS), 'Qualification step missing')
    require(all(job['conclusion'] == 'skipped' for job in jobs if job['name'] != 'qualify'),
            'Qualification unexpectedly ran another job')
    summary = summary_path.read_bytes()
    require(sha(summary) == SUMMARY_SHA, 'Producer summary SHA mismatch')
    lines = summary.decode('utf-8').splitlines()
    failures = [line for line in lines if line.startswith('FAIL ')]
    require(len(lines) == 111 and sum(line.startswith('PASS ') for line in lines) == 110
            and len(failures) == 1 and 'Verify fixed content clipping masks and complete pointwise paint stability' in failures[0],
            'Producer catalogue mismatch')
    original = original_report_path.read_bytes()
    require(sha(original) == ORIGINAL_REPORT_SHA, 'Original failed report SHA mismatch')
    old_report = json.loads(original)
    require(old_report['result'] == 'FAIL' and old_report['completeKeys'] == 54
            and old_report['strictContentMaskKeys'] == 12 and len(old_report['failures']) == 2
            and {(x['name'], x['scale']) for x in old_report['failures']}
            == {('composited-translate', 1.5), ('composited-translate', 2)},
            'Original failure evidence mismatch')
    package_bytes, manifest_bytes = package.read_bytes(), manifest_path.read_bytes()
    require(sha(package_bytes) == PACKAGE_SHA and sha(manifest_bytes) == MANIFEST_SHA, 'Artifact SHA mismatch')
    for name, digest in EVIDENCE_SHA.items():
        require(sha((evidence / name).read_bytes()) == digest, f'Qualification evidence SHA mismatch: {name}')
    manifest = json.loads(manifest_bytes)
    report = json.loads((evidence / 'original-report.json').read_bytes())
    receipt = json.loads((evidence / 'qualification.json').read_bytes())
    model = json.loads((evidence / 'model.json').read_bytes())
    sampler = json.loads((evidence / 'policy/sampler-format-probe.json').read_bytes())
    precision = json.loads((evidence / 'policy/vertex-fragment-precision.json').read_bytes())
    require(manifest['source'] == {'commit': PRODUCT, 'dirty': False, 'builder': 'ci'}
            and manifest['abi'] == 62 and manifest['rid'] == 'win-x64' and manifest['flavor'] == 'gpu',
            'Manifest source or ABI mismatch')
    require(len(manifest['files']) == 26 and len({x['name'] for x in manifest['files']}) == 26,
            'Expected 26 unique native files')
    expected = {x['name']: x['sha256'] for x in manifest['files']}
    require(receipt['packageSha256'] == PACKAGE_SHA and receipt['manifestSha256'] == MANIFEST_SHA
            and receipt['source'] == PRODUCT and receipt['nativeUnchanged'] is True
            and receipt['samplerFormatsDiagnostic'] is True and receipt['profile'] == PROFILE,
            'Qualification receipt mismatch')
    require(report['result'] == 'FAIL' and report['rid'] == 'win-x64'
            and report['completeKeys'] == 54 and report['strictContentMaskKeys'] == 12
            and len(report['results']) == 54 and {(x['name'], x['scale']) for x in report['failures']}
            == {('composited-translate', 1.5), ('composited-translate', 2)}, 'Qualification report mismatch')
    keys = {(row['name'], row['scale']) for row in report['results']}
    require(keys == {(name, scale) for name in CASES for scale in (1, 1.5, 2)},
            'Qualification case identity mismatch')
    require(all(row['strictFixedCase'] == (row['name'] in FIXED) for row in report['results']),
            'Qualification strict-mask identity mismatch')
    require(all((row['name'] == 'composited-translate' and row['scale'] in (1.5, 2))
                or (not row['unexplainedWorsePixels'] and
                    (not row['strictFixedCase'] or row['contentMaskDifference'] == 0))
                for row in report['results']), 'Unexpected failed pixel or strict mask')
    require(model['result'] == 'PASS' and len(model['cases']) == 2
            and {(x['scale'], x['pixels']) for x in model['cases']} == {(1.5, 1080000), (2, 1920000)}
            and model['expectedGeneratedBeforeCaptureLoad'] and not model['pixelGoldenInputs'], 'Model mismatch')
    require(sampler['renderer'] == precision['renderer'] == PROFILE and sampler['runtimeUnchanged']
            and precision['nativeUnchanged'] and sampler['controlsPass'] and sampler['negativeControlsPass']
            and sampler['policy']['result'] == 'PASS' and sampler['policy']['samplesPerDestination'] == 1048576
            and sampler['policy']['historicalCrossDrawResult'] == 'FAIL', 'Sampler qualification mismatch')
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate package member')
        require(archive.read('manifest.json') == manifest_bytes, 'Package manifest mismatch')
        prefix = 'runtimes/win-x64/native/'
        actual = {name[len(prefix):] for name in names if name.startswith(prefix) and not name.endswith('/')}
        require(actual == set(expected), 'Native payload set mismatch')
        for item in manifest['files']:
            payload = archive.read(prefix + item['name'])
            require(len(payload) == item['bytes'] and sha(payload) == item['sha256'], 'Native payload mismatch')
    return {'packageSha256': PACKAGE_SHA, 'manifestSha256': MANIFEST_SHA, 'producer': PRODUCER,
            'qualification': qualification, 'product': PRODUCT, 'policy': TRUSTED_POLICY,
            'evidenceSha256': EVIDENCE_SHA, 'qualificationSourceSha256': SOURCE_SHA, 'profile': PROFILE,
            'producerSummarySha256': SUMMARY_SHA, 'originalReportSha256': ORIGINAL_REPORT_SHA,
            'producerGroupsPassed': 110, 'nativeFiles': 26}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--producer-summary', type=Path, required=True)
    parser.add_argument('--original-report', type=Path, required=True)
    parser.add_argument('--qualification', type=int, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--export', type=Path)
    args = parser.parse_args()
    receipt = verify(args.package, args.manifest, args.evidence, args.producer_summary, args.original_report, args.qualification)
    if args.export:
        args.export.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.package, args.export / PACKAGE)
        shutil.copyfile(args.manifest, args.export / 'manifest.json')
        require(sha((args.export / PACKAGE).read_bytes()) == PACKAGE_SHA, 'Export changed')
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
