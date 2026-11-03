"""Prepare and run a reviewed public Cocoa CPU contract bundle without compilation."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import struct
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
MAC_BASE_LIBRARIES = {'libRanvierWebCoreHost.dylib', 'libWebCore.dylib', 'libJavaScriptCore.dylib', 'libWebGPU.dylib'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sealed_file(root, record):
    name = record['path']
    path = PurePosixPath(name)
    if not name or path.is_absolute() or path.as_posix() != name or any(part in {'.', '..'} or ':' in part for part in path.parts):
        raise ValueError('Unsafe sidecar path')
    resolved = (root / name).resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()) or sha(resolved) != record['sha256']:
        raise ValueError('Sidecar file identity differs')
    return resolved


def policy_admission(policy):
    if policy.get('schemaVersion') != 1 or policy.get('armed') is not True:
        raise ValueError('The public Cocoa policy is unarmed')
    native = policy['native']
    if (native.get('id') not in {'Ranvier.WebCore.Native.osx-arm64', 'Ranvier.WebCore.Native.Gpu.osx-arm64'}
            or type(native.get('abi')) is not int or native['abi'] != 64
            or type(native.get('declarations')) is not int or native['declarations'] != 349):
        raise ValueError('Expected the reviewed ABI64/349 macOS ARM64 package')
    if not isinstance(native.get('version'), str) or not native['version']:
        raise ValueError('An allocated exact Native version is required')
    if not re.fullmatch('[0-9a-f]{40}', native.get('source') or ''):
        raise ValueError('An exact Native source commit is required')
    for value in [native.get('packageSha256'), native.get('auditSha256'), policy.get('interopPackageSha256'),
                  policy.get('headerSha256'), policy.get('sidecarManifestSha256')]:
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
            raise ValueError('Reviewed package, audit, header and sidecar SHA256 values are required')
    if not re.fullmatch('[0-9a-f]{40}', policy.get('controllerSource') or ''):
        raise ValueError('An exact reviewed controller source commit is required')


def validate_package(policy, package):
    if sha(package) != policy['native']['packageSha256']:
        raise ValueError('Signed package bytes differ from the reviewed policy')
    with zipfile.ZipFile(package) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError('Duplicate package member')
        manifest = json.loads(archive.read('manifest.json'))
        expected = policy['native']
        nuspecs = [name for name in archive.namelist() if name.endswith('.nuspec') and '/' not in name]
        if len(nuspecs) != 1:
            raise ValueError('Require one native package identity')
        metadata = {node.tag.rsplit('}', 1)[-1]: node.text for node in ET.fromstring(archive.read(nuspecs[0])).iter()}
        if metadata.get('id') != expected['id'] or metadata.get('version') != expected['version']:
            raise ValueError('Native package ID/version differs')
        flavor = 'gpu' if '.Gpu.' in expected['id'] else 'slim'
        if (manifest.get('rid'), manifest.get('flavor'), manifest.get('version'), manifest.get('abi')) != (
                'osx-arm64', flavor, expected['version'], 64):
            raise ValueError('Package manifest cohort differs')
        if manifest.get('source', {}).get('commit') != expected['source'] or manifest['source'].get('dirty') is not False:
            raise ValueError('Package source must match the reviewed clean cohort')
        prefix = 'runtimes/osx-arm64/native/'
        records = {item['name']: item for item in manifest['files']}
        if len({name.casefold() for name in records}) != len(records):
            raise ValueError('Case-colliding native package paths')
        if manifest.get('total_bytes') != sum(item['bytes'] for item in manifest['files']):
            raise ValueError('Native manifest total size differs')
        required = set(MAC_BASE_LIBRARIES)
        if flavor == 'gpu':
            required |= {'libEGL.dylib', 'libGLESv2.dylib'}
        if not required <= set(records):
            raise ValueError('The complete supported native dylib closure is required')
        if len(records) != len(manifest['files']) or set(records) != {
                name[len(prefix):] for name in archive.namelist() if name.startswith(prefix) and not name.endswith('/')}:
            raise ValueError('Complete package manifest/payload set differs')
        for name, record in records.items():
            path = PurePosixPath(name)
            if path.is_absolute() or path.as_posix() != name or any(part in {'.', '..'} or ':' in part for part in path.parts):
                raise ValueError('Unsafe native package path')
            data = archive.read(prefix + name)
            if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('Native package payload bytes differ')
    return manifest


def validate_sidecars(policy, manifest, path):
    if sha(path) != policy['sidecarManifestSha256']:
        raise ValueError('Producer-built sidecar manifest differs')
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if (data.get('schemaVersion'), data.get('boundary')) != (1, 'public-Host-unchanged-sidecars-v1'):
        raise ValueError('A producer-built public Host sidecar bundle is required')
    if type(data.get('abi')) is not int or data['abi'] != 64 or type(data.get('declarations')) is not int or data['declarations'] != 349:
        raise ValueError('Require the exact ABI64/349 producer sidecars')
    expected_hashes = {item['name']: item['sha256'] for item in manifest['files']}
    if (data.get('nativePackageSha256') != policy['native']['packageSha256']
            or data.get('nativeSource') != policy['native']['source']
            or data.get('nativeBefore') != expected_hashes or data.get('nativeAfter') != expected_hashes
            or data.get('hostReplaced') is not False or data.get('headerReconstruction') is not False
            or data.get('engineCompilation') is not False):
        raise ValueError('Sidecars do not preserve the exact signed native cohort')
    for key in ['producerConfigurationSha256', 'consumedInputsArchiveSha256', 'compilerSha256', 'compileCommandsSha256']:
        if not re.fullmatch('[0-9a-f]{64}', data.get(key) or ''):
            raise ValueError('Complete producer compiler/configuration/input provenance is required')
    if data.get('strictLink') is not True or data.get('sourceEquivalenceReviewed') is not True:
        raise ValueError('Sidecar source equivalence and strict linkage require review')
    helpers = data['helpers']
    if set(helpers) != {'timer', 'page', 'motion', 'contrast'}:
        raise ValueError('Require all four matching sidecars')
    return data, {key: sealed_file(Path(path).parent, record) for key, record in helpers.items()}


def commands(native, helpers, output, owner_proof=None, owner_proof_sha=None):
    timer = [sys.executable, '-I', str(ROOT / 'tests/abi/cocoa_timer_contract.py'), '--native-directory', str(native),
             '--helper', str(helpers['timer'])]
    proof = [] if owner_proof is None else ['--owner-assertion-proof', str(owner_proof),
                                           '--owner-assertion-proof-sha256', owner_proof_sha]
    rows = [('timers-eight', timer + proof + ['--output', str(output / 'timers-eight.json')])]
    for period in ['0.01', '0.1', '1']:
        rows.append(('timer-fairness-' + period, timer + ['--mode', '72-fast-repeat-fairness',
                     '--repeat-milliseconds', period, '--output', str(output / ('fairness-' + period + '.json'))]))
    common = ['--native-directory', str(native), '--abi-source', str(ROOT / 'tests/abi'),
              '--page-helper', str(helpers['page'])]
    rows.append(('motion-135', [sys.executable, '-I', str(ROOT / 'tests/controls/cocoa_progress_paths.py'),
                 *common, '--system-helper', str(helpers['motion']), '--output', str(output / 'motion')]))
    contrast = [sys.executable, '-I', str(ROOT / 'tests/controls/cocoa_contrast_paths.py'), *common,
                '--system-helper', str(helpers['contrast']), '--scoped-helper']
    rows += [('contrast-default-83', [*contrast, '--output', str(output / 'contrast-default')]),
             ('contrast-reverse-83', [*contrast, '--first-system-more', '--output', str(output / 'contrast-reverse')])]
    rows.append(('contrast-paired-order', [sys.executable, '-I', str(ROOT / 'tests/controls/cocoa_contrast_order.py'),
                 '--reports', str(output / 'contrast-default/contrast-paths.json'),
                 str(output / 'contrast-reverse/contrast-paths.json'), '--output', str(output / 'contrast-order.json')]))
    debug = [sys.executable, '-I', str(ROOT / 'tests/abi/cocoa_timer_contract.py'), '--native-directory', str(native),
             '--helper', str(helpers['timer']), '--mode', 'cross-thread-destroy-contract',
             '--output', str(output / 'owner-debugger.json')]
    rows.append(('fresh-owner-branch', ['xcrun', 'lldb', '--batch', '-o', 'settings set target.disable-aslr false',
                 '-o', 'settings set target.process.stop-on-exec false',
                 '-o', 'command script import ' + shlex.quote(str(ROOT / 'tests/controls/cocoa_owner_probe_lldb.py')),
                 '-o', 'breakpoint set -n rv_test_wtf_timer_destroy_unchecked',
                 '-o', 'breakpoint command add -F cocoa_owner_probe_lldb.before_destroy 1',
                 '-o', 'run', '-o', 'script cocoa_owner_probe_lldb.verify(lldb.debugger)',
                 '-o', 'thread backtrace all', '-o', 'process kill', '--', *debug]))
    return rows


def resident_tree_bytes(pid):
    raw = subprocess.check_output(['ps', '-axo', 'pid=,ppid=,rss='], text=True, timeout=10)
    records = {int(p): (int(parent), int(rss) * 1024) for p, parent, rss in (line.split() for line in raw.splitlines())}
    selected = {pid}
    while True:
        expanded = selected | {p for p, (parent, _) in records.items() if parent in selected}
        if expanded == selected:
            return sum(records[p][1] for p in selected if p in records)
        selected = expanded


def run_groups(rows, output, environment):
    spec = importlib.util.spec_from_file_location('public_cocoa_owned', ROOT / 'scripts/qualify_producer_gpu_clipping.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = []
    for name, command in rows:
        row = dict(name=name, argv=command)
        results.append(row)
        log = output / (name + '.log')
        try:
            with log.open('wb') as stream:
                child = module.OwnedChild(command, stream, environment, ROOT)
                try:
                    deadline = time.monotonic() + 360
                    while child.process.poll() is None:
                        memory = resident_tree_bytes(child.process.pid)
                        row['peakResidentBytes'] = max(memory, row.get('peakResidentBytes', 0))
                        if memory > 8 * 1024 ** 3 or time.monotonic() > deadline:
                            raise RuntimeError('Owned child memory/deadline limit')
                        time.sleep(0.1)
                    row['exit'] = child.process.returncode
                finally:
                    child.close()
                    row['childrenReaped'] = True
        except Exception as error:
            row['failure'] = repr(error)
        if log.exists():
            row['logSha256'] = sha(log)
        print(json.dumps(row), flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['policy', 'package', 'audit', 'interop', 'sidecars', 'output']:
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--owner-proof', type=Path)
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text(encoding='utf-8'))
    policy_admission(policy)
    manifest = validate_package(policy, args.package)
    if sha(args.audit) != policy['native']['auditSha256'] or sha(args.interop) != policy['interopPackageSha256']:
        raise ValueError('Public audit/Interop identity differs')
    with zipfile.ZipFile(args.interop) as archive:
        header = archive.read('include/RanvierWebCoreAbi.h')
        nuspecs = [name for name in archive.namelist() if name.endswith('.nuspec') and '/' not in name]
        if len(nuspecs) != 1:
            raise ValueError('Require one canonical Interop package identity')
        metadata = {node.tag.rsplit('}', 1)[-1]: node.text for node in ET.fromstring(archive.read(nuspecs[0])).iter()}
        if metadata.get('id') != 'Ranvier.WebCore' or metadata.get('version') != policy['native']['version']:
            raise ValueError('Interop must match the exact Native package cohort')
    if hashlib.sha256(header).hexdigest() != policy['headerSha256']:
        raise ValueError('Canonical public header identity differs')
    names = re.findall(rb'RV_EXPORT\s+[^;]*?\b(rv_\w+)\s*\([^;]*?\)\s*;', header, re.S)
    if len(names) != 349 or len(set(names)) != 349:
        raise ValueError('Require all 349 canonical public declarations')
    sidecars, helpers = validate_sidecars(policy, manifest, args.sidecars)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True)
    if head != policy['controllerSource'] or dirty:
        raise ValueError('Controller checkout differs from the reviewed source')
    native = args.output / 'baseline-native'
    planned = commands(native, helpers, args.output, args.owner_proof, policy.get('reviewedOwnerProofSha256'))
    signatures = [('verify-public-signature', ['dotnet', 'nuget', 'verify', str(args.package), '--all']),
                  ('verify-interop-signature', ['dotnet', 'nuget', 'verify', str(args.interop), '--all'])]
    loaded_command = [('loaded-abi64-349', [sys.executable, '-I', str(ROOT / 'tests/controls/public_cocoa_loaded_abi.py'),
                      '--native-directory', str(native), '--header', str(args.output / 'RanvierWebCoreAbi.h'),
                      '--output', str(args.output / 'loaded-abi.json')])]
    if args.plan_only:
        print(json.dumps(dict(scope='Admission/command plan only; no compiler, native load or execution',
                              commands=[*signatures, *loaded_command, *planned]), indent=2))
        return 0
    if sys.platform != 'darwin':
        raise ValueError('Actual macOS is required')
    import platform
    if platform.machine() != 'arm64' or platform.mac_ver()[0].split('.')[0] != '26':
        raise ValueError('This recipe requires the reviewed macOS26 ARM64 profile')
    if args.output.resolve().is_relative_to(ROOT.resolve()) or args.output.exists():
        raise ValueError('Require a fresh owned output outside the source checkout')
    args.output.mkdir(parents=True)
    native.mkdir()
    (args.output / 'RanvierWebCoreAbi.h').write_bytes(header)
    with zipfile.ZipFile(args.package) as archive:
        for record in manifest['files']:
            target = native / record['name']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read('runtimes/osx-arm64/native/' + record['name']))
    for path in native.glob('*.dylib'):
        magic, architecture = struct.unpack_from('<II', path.read_bytes())
        if (magic, architecture) != (0xfeedfacf, 0x100000c):
            raise ValueError('Require actual thin ARM64 Mach-O native libraries')
    environment = dict(os.environ, RANVIER_ABI_TEST_EXPECTED='64', DYLD_LIBRARY_PATH=str(native.resolve()))
    environment.pop('DYLD_INSERT_LIBRARIES', None)
    environment.pop('DYLD_FRAMEWORK_PATH', None)
    before = {p.relative_to(native).as_posix(): sha(p) for p in native.rglob('*') if p.is_file()}
    helper_before = {name: sha(path) for name, path in helpers.items()}
    receipt = dict(scope='Exact signed public native CPU implementation contracts; no GPU or publication claim',
                   nativePackageSha256=sha(args.package), nativeBefore=before, groups=[], accepted=False,
                   controllerSource=head, helperBefore=helper_before, ownerAdmission='UNARMED_PENDING_REVIEW')
    receipt['platform'] = dict(macVersion=platform.mac_ver()[0], machine=platform.machine(), python=sys.version)
    try:
        signature = run_groups(signatures, args.output, environment)
        receipt['groups'].extend(signature)
        if any(row.get('exit') != 0 or row.get('failure') for row in signature):
            raise ValueError('Public package signature verification failed; native execution refused')
        if args.owner_proof:
            expected = policy.get('reviewedOwnerProofSha256')
            if not expected or sha(args.owner_proof) != expected:
                raise ValueError('Fresh exact-runtime owner proof has not been independently pinned')
            receipt['ownerAdmission'] = 'REVIEWED_EXACT_RUNTIME_CONTEXTUAL'
        loaded = run_groups(loaded_command, args.output, environment)
        receipt['groups'].extend(loaded)
        if any(row.get('exit') != 0 or row.get('failure') for row in loaded):
            raise ValueError('Actual loaded ABI/export/image admission failed; helper calls refused')
        receipt['groups'].extend(run_groups(planned, args.output, environment))
        for name, report, count in [('motion', 'motion/progress-paths.json', 135),
                                     ('contrast-default', 'contrast-default/contrast-paths.json', 83),
                                     ('contrast-reverse', 'contrast-reverse/contrast-paths.json', 83)]:
            path = args.output / report
            if path.exists():
                data = json.loads(path.read_text(encoding='utf-8'))
                receipt[name] = dict(assertions=data.get('assertions'), failures=data.get('failures'))
                if data.get('assertions') != count or data.get('failures'):
                    receipt[name]['admissionFailed'] = True
            else:
                receipt[name] = dict(admissionFailed=True, missing=True)
        receipt['accepted'] = bool(args.owner_proof) and not any(
            row.get('exit') != 0 or row.get('failure') for row in receipt['groups']) and not any(
            receipt[name].get('admissionFailed') for name in ['motion', 'contrast-default', 'contrast-reverse'])
    except Exception as error:
        receipt['failure'] = repr(error)
    finally:
        receipt['nativeAfter'] = {p.relative_to(native).as_posix(): sha(p) for p in native.rglob('*') if p.is_file()}
        receipt['helperAfter'] = {name: sha(path) for name, path in helpers.items()}
        receipt['inputsUnchanged'] = receipt['nativeAfter'] == before and receipt['helperAfter'] == helper_before
        receipt['accepted'] = receipt['accepted'] and receipt['inputsUnchanged']
        (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return 0 if receipt['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
