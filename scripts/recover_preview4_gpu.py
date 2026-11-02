"""Verify the fixed P4 Windows GPU artifact and its independent qualification."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

PRODUCER = 41436552210
QUALIFICATION = 41456798523
PRODUCT = '268e0ca71bd6e754b691b2d996ec207eafce0490'
POLICY = '76ae7139f88ae89c673a5cf82963aa2670401ca1'
PACKAGE = 'Ranvier.WebCore.Native.Gpu.win-x64.0.1.1-preview.4.nupkg'
PACKAGE_SHA = 'ce8b58a71a242fb25a85741f1b506e098c7fd375f7724a91bdf57b40215e56b7'
MANIFEST_SHA = 'b124173e174433ef91b3d164be0d62dd32489f5c327a2800bf6829ee6f61069a'
REPORT_SHA = 'd79bdea09bb3fd8eb94a9a66159fbc6462f617af8bba2902ab9ed18f54c6e58e'
RECEIPT_SHA = '99dd21db6ad63942bd4eda9769ce9f1c68d7609add9ef76aed938fbc55d6b61f'
SUMMARY_SHA = '8d1c3cfce5ead89c19f62145ca4886cab5ca0aa6c9e5b902b92bcb03b3532137'
REPO = 'ranvier-org/Ranvier.WebCore'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPO}/{path}'], timeout=60))


def verify(package, manifest_path, evidence, summary_path):
    producer = api(f'actions/runs/{PRODUCER}')
    qualification = api(f'actions/runs/{QUALIFICATION}')
    require(producer['head_sha'] == PRODUCT and producer['status'] == 'completed'
            and producer['conclusion'] == 'failure' and producer['event'] == 'workflow_dispatch'
            and producer['head_branch'] == 'v0.1.1-preview.4'
            and producer['path'] == '.github/workflows/build.yml' and producer['run_attempt'] == 1,
            'Producer identity or status changed')
    require(qualification['head_sha'] == POLICY and qualification['event'] == 'workflow_dispatch'
            and qualification['status'] == 'completed' and qualification['conclusion'] == 'success',
            'Qualification identity or status changed')
    jobs_response = api(f'actions/runs/{QUALIFICATION}/jobs?per_page=100')
    jobs = jobs_response['jobs']
    require(jobs_response['total_count'] == len(jobs), 'Qualification job list is incomplete')
    selected = [job for job in jobs if job['name'] == 'diagnose-p4-clipping']
    require(len(selected) == 1 and selected[0]['conclusion'] == 'success', 'Qualification job missing')
    steps = {step['name']: step['conclusion'] for step in selected[0]['steps']}
    for name in ['Verify diagnostic guards and bounded cleanup',
                 'Replay exact failed package and retain full pixels and adapter identity']:
        require(steps.get(name) == 'success', 'Qualification step missing: ' + name)
    require(all(job['conclusion'] == 'skipped' for job in jobs if job['name'] != 'diagnose-p4-clipping'),
            'Qualification unexpectedly ran another job')
    summary_bytes = summary_path.read_bytes()
    require(sha(summary_bytes) == SUMMARY_SHA, 'Producer summary SHA mismatch')
    summary = summary_bytes.decode('utf-8').splitlines()
    failures = [line for line in summary if line.startswith('FAIL ')]
    require(len(summary) == 103 and len(failures) == 1
            and 'Verify fixed content clipping masks and complete pointwise paint stability' in failures[0]
            and sum(line.startswith('PASS ') for line in summary) == 102, 'Producer catalogue mismatch')
    package_bytes, manifest_bytes = package.read_bytes(), manifest_path.read_bytes()
    require(sha(package_bytes) == PACKAGE_SHA and sha(manifest_bytes) == MANIFEST_SHA, 'Artifact SHA mismatch')
    report_bytes = (evidence / 'background-content-clipping-regression.json').read_bytes()
    receipt_bytes = (evidence / 'receipt.json').read_bytes()
    require(sha(report_bytes) == REPORT_SHA and sha(receipt_bytes) == RECEIPT_SHA, 'Evidence SHA mismatch')
    manifest, report, receipt = map(json.loads, (manifest_bytes, report_bytes, receipt_bytes))
    require(manifest['source'] == {'commit': PRODUCT, 'dirty': False, 'builder': 'ci'}, 'Manifest source mismatch')
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
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate package member')
        require(archive.read('manifest.json') == manifest_bytes, 'Package manifest mismatch')
        prefix = 'runtimes/win-x64/native/'
        actual_names = {name[len(prefix):] for name in names if name.startswith(prefix) and not name.endswith('/')}
        require(actual_names == set(expected), 'Native payload set mismatch')
        for item in manifest['files']:
            payload = archive.read(prefix + item['name'])
            require(len(payload) == item['bytes'] and sha(payload) == item['sha256'], 'Native payload mismatch')
    return {'packageSha256': PACKAGE_SHA, 'manifestSha256': MANIFEST_SHA,
            'producer': PRODUCER, 'qualification': QUALIFICATION, 'product': PRODUCT, 'policy': POLICY,
            'reportSha256': REPORT_SHA, 'receiptSha256': RECEIPT_SHA,
            'producerSummarySha256': SUMMARY_SHA, 'producerGroupsPassed': 102, 'nativeFiles': len(expected)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--producer-summary', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--export', type=Path)
    args = parser.parse_args()
    receipt = verify(args.package, args.manifest, args.evidence, args.producer_summary)
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
