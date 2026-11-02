"""Fail closed until an independently reviewed P7 GPU qualification is pinned."""

import argparse
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

# Deliberately unarmed. A later reviewed change must pin all four values to the
# independently qualified run and its immutable evidence before publication.
TRUSTED_QUALIFICATION = None
TRUSTED_POLICY = None
TRUSTED_WORKFLOW = None
TRUSTED_REPORT_SHA = None
TRUSTED_RECEIPT_SHA = None
QUALIFICATION_STEPS = ('Verify exact producer inputs', 'Qualify complete GPU clipping contract')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPO}/{path}'], timeout=60))


def verify(package, manifest_path, evidence, summary_path, original_report_path, qualification):
    require(all((TRUSTED_QUALIFICATION, TRUSTED_POLICY, TRUSTED_WORKFLOW, TRUSTED_REPORT_SHA, TRUSTED_RECEIPT_SHA)),
            'Recovery is unarmed: reviewed qualification pins are missing')
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
    response = api(f'actions/runs/{qualification}/jobs?per_page=100')
    jobs = response['jobs']
    require(response['total_count'] == len(jobs), 'Qualification job list is incomplete')
    selected = [job for job in jobs if job['name'] == 'qualify-p7-gpu']
    require(len(selected) == 1 and selected[0]['conclusion'] == 'success', 'Qualification job missing')
    steps = {step['name']: step['conclusion'] for step in selected[0]['steps']}
    require(all(steps.get(name) == 'success' for name in QUALIFICATION_STEPS), 'Qualification step missing')
    require(all(job['conclusion'] == 'skipped' for job in jobs if job['name'] != 'qualify-p7-gpu'),
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
    report_bytes = (evidence / 'report.json').read_bytes()
    receipt_bytes = (evidence / 'receipt.json').read_bytes()
    require(sha(report_bytes) == TRUSTED_REPORT_SHA and sha(receipt_bytes) == TRUSTED_RECEIPT_SHA,
            'Qualification evidence SHA mismatch')
    manifest, report, receipt = map(json.loads, (manifest_bytes, report_bytes, receipt_bytes))
    require(manifest['source'] == {'commit': PRODUCT, 'dirty': False, 'builder': 'ci'}
            and manifest['abi'] == 62 and manifest['rid'] == 'win-x64' and manifest['flavor'] == 'gpu',
            'Manifest source or ABI mismatch')
    require(len(manifest['files']) == 26 and len({x['name'] for x in manifest['files']}) == 26,
            'Expected 26 unique native files')
    expected = {x['name']: x['sha256'] for x in manifest['files']}
    require(receipt['packageSha256'] == PACKAGE_SHA and receipt['manifestSha256'] == MANIFEST_SHA
            and receipt['source'] == PRODUCT and receipt['unchanged'] is True
            and receipt['capture']['exit'] == 0 and not receipt['capture']['timedOut']
            and receipt['before'] == receipt['after'] == expected, 'Qualification receipt mismatch')
    require(report['result'] == 'PASS' and report['rid'] == 'win-x64'
            and report['completeKeys'] == 54 and report['strictContentMaskKeys'] == 12
            and len(report['results']) == 54 and not report['failures'], 'Qualification report mismatch')
    keys = {(row['name'], row['scale']) for row in report['results']}
    require(keys == {(name, scale) for name in CASES for scale in (1, 1.5, 2)},
            'Qualification case identity mismatch')
    require(all(row['strictFixedCase'] == (row['name'] in FIXED) for row in report['results']),
            'Qualification strict-mask identity mismatch')
    require(all(not row['unexplainedWorsePixels']
                and (not row['strictFixedCase'] or row['contentMaskDifference'] == 0)
                for row in report['results']), 'Qualification contains a failed pixel or strict mask')
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
            'reportSha256': TRUSTED_REPORT_SHA, 'receiptSha256': TRUSTED_RECEIPT_SHA,
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
