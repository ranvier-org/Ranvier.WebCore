"""Summarize per-RID qualification only after validating every underlying receipt."""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import zipfile
from pathlib import Path


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def build_summary(stage, manifest, package_sha, source, version, names, exports, style, protocols, sdk, managed, rid='linux-arm64'):
    require(rid in ('linux-arm64', 'linux-x64'), 'Unsupported qualification RID')
    require(stage['rid'] == rid and stage['manifestDeclaredSource'] == source and stage['unionExportGatePassed'], 'Producer identity or union gate differs')
    require(manifest['rid'] == rid and manifest['abi'] == 63 and manifest['hostSha256'] == stage['nativeSha256'], 'Provider package host differs')
    require(manifest['callerClaimedProviderSourceRevision'] == source and manifest['sourceProvenance'] == 'unverified-caller-claim', 'Provider source claim differs')
    require(len(names) == len(set(names)) == 347 and names[-3:] == ['rv_host_ime_surrounding', 'rv_host_ime_delete_surrounding', 'rv_ax_text_style_run'] and set(names).issubset(exports), 'The ABI347 declaration/export set differs')
    require(len(style) >= 23 and all(row.get('passed') is True for row in style), 'Direct style assertions did not all pass')
    counts = {}
    for label in ('direct', 'queued', 'session'):
        report, process = protocols[label]
        require(report['assertions'] >= 84 and all(row.get('passed') is True for row in report['rows']), 'Protocol assertions failed: ' + label)
        require(process['allOwnedProcessesExited'] and process['nativeBefore'] == process['nativeAfter'] == stage['nativeSha256'] and process['providerSha256'] == manifest['providerSha256'], 'Protocol process/runtime evidence differs: ' + label)
        counts[label] = report['assertions']
    require(sdk['packageSha256'] == package_sha and sdk['consumer']['loaded'] is True and sdk['consumer']['providerSha256'] == manifest['providerSha256'], 'Ordinary SDK consumer differs')
    require(managed['rid'] == rid and managed['hostSha256'] == stage['nativeSha256'] and managed['providerSha256'] == manifest['providerSha256'] and managed['packageSha256'] == package_sha and managed['sourceRevision'] == source and managed['allOwnedProcessesExited'], 'Managed AOT cohort differs')
    runs = {}
    for mode in ('normal', 'traced'):
        runs[mode] = {}
        for profile in ('present', 'absent', 'no-bus'):
            matching = [row for row in managed['runs'] if row['mode'] == mode and row['profile'] == profile]
            require(len(matching) == 1, 'Managed AOT profile missing or duplicated')
            row = matching[0]
            expected = profile == 'present'
            require(row['result'] == dict(windows=3, directHosts=3, expectedAttached=expected, dynamicCodeSupported=False), 'Managed AOT lifecycle differs')
            require(row['nativeBefore'] == row['nativeAfter'] and row['nativeBefore']['libRanvierWebCoreHost.so'] == stage['nativeSha256'] and row['nonBmpStyle'] == expected, 'Managed AOT native or style evidence differs')
            if profile != 'absent':
                require(row['nativeBefore']['libRanvierWebCoreAtspi.so'] == manifest['providerSha256'], 'Managed AOT provider differs')
            else:
                require('libRanvierWebCoreAtspi.so' not in row['nativeBefore'], 'Absent profile includes provider')
            runs[mode][profile] = dict(passed=True, windows=3, directHosts=3, expectedAttached=expected,
                                       dynamicCodeSupported=False, nativeUnchanged=True, ownedProcessesExited=True,
                                       nonBmpStyle=expected)
    return {'schemaVersion': 1, 'rid': rid, 'abi': 63, 'nativeVersion': version,
            'nativeSource': source, 'providerSourceClaim': source, 'hostSha256': stage['nativeSha256'],
            'providerSha256': manifest['providerSha256'], 'packageSha256': package_sha,
            'checks': {'nativeExports': len(names), 'directStyleAssertions': len(style),
                       'protocolAssertions': counts, 'ordinarySdkConsumer': True, 'managedAot': runs},
            'scope': 'Per-RID qualification summary; source and provider revision are caller/artifact claims, not authenticated review.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--native-artifacts', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--rid', choices=('linux-arm64', 'linux-x64'), default='linux-arm64')
    args = parser.parse_args()
    work = args.work
    stage = json.loads((work / 'native/producer-receipt.json').read_text())
    candidates = [path for path in args.native_artifacts.rglob('*.nupkg') if sha(path) == stage['packageSha256']]
    require(len(candidates) == 1, 'The producer package receipt is missing or ambiguous')
    with zipfile.ZipFile(candidates[0]) as archive:
        native_manifest = json.loads(archive.read('manifest.json'))
    require(native_manifest['rid'] == args.rid and native_manifest['abi'] == 63
            and native_manifest['source']['commit'] == args.source and native_manifest['source']['dirty'] is False,
            'The producer manifest differs from the staged source and ABI')
    require(sha(work / 'native/libRanvierWebCoreHost.so') == stage['nativeSha256'], 'The staged host changed')
    with zipfile.ZipFile(args.package) as archive:
        manifest = json.loads(archive.read('provider-manifest.json'))
    spec = importlib.util.spec_from_file_location('generate_native', Path(__file__).resolve().parents[1] / 'abi/generate_native.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    names = [row[0] for row in generator.declarations(generator.HEADER.read_text(encoding='utf-8'))]
    symbols = subprocess.check_output(['nm', '-D', '--defined-only', str(work / 'native/libRanvierWebCoreHost.so')], text=True)
    exports = {line.split()[-1] for line in symbols.splitlines() if line.split()}
    style = json.loads((work / 'direct-style-report.json').read_text())
    protocols = {}
    for label, directory in [('direct', 'protocol'), ('queued', 'protocol-queued'), ('session', 'protocol-session')]:
        protocols[label] = (json.loads((work / directory / 'client-report.json').read_text()), json.loads((work / directory / 'receipt.json').read_text()))
    sdk = json.loads((work / 'consumer/consumer-receipt.json').read_text())
    managed = json.loads((work / 'managed-aot/managed-aot-receipt.json').read_text())
    result = build_summary(stage, manifest, sha(args.package), args.source, native_manifest['version'], names, exports, style, protocols, sdk, managed, args.rid)
    output = work / 'qualification-receipt.json'
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps({'path': str(output), 'sha256': sha(output)}))


if __name__ == '__main__':
    main()
