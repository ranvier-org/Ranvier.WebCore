"""Retain public GPU output/input captures from the exact already-qualified d31 package."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CAPTURES = ({'cycle' + str(index) + '-' + phase + '.bmp' for index in range(3) for phase in ['before', 'after']}
    | {'input-' + str(scale) + '-' + phase + '.bmp' for scale in [10, 15, 20] for phase in ['first', 'flipped', 'scrolled']})
EXPECTED_STEPS = {'presenter-sdk', 'presenter-flags', 'compile-spike', 'public-spike',
                  'compile-texture_input', 'public-texture_input', 'reject-software', 'reject-steady-base-repaint'}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_public_receipt(receipt, native):
    if receipt.get('passed') is not True or receipt.get('nativeBefore') != native or receipt.get('nativeAfter') != native:
        raise ValueError('Public capture replay did not preserve the exact native set')
    steps = receipt['steps']
    if len(steps) != len(EXPECTED_STEPS) or {row['name'] for row in steps} != EXPECTED_STEPS:
        raise ValueError('Public output/input/negative step set differs')
    for row in steps:
        if row['name'] == 'reject-steady-base-repaint':
            if row['exit'] != 1 or row.get('expectedFailure') != 'MAC_GPU_SPIKE FAIL transform and opacity animation reuse base backing':
                raise ValueError('The unchanged repaint negative was not rejected')
        elif row['exit'] != 0:
            raise ValueError('A public capture replay step failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['producer-root', 'output', 'work']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64' or platform.mac_ver()[0].split('.')[0] != '26':
        raise ValueError('Require actual macOS26 ARM64')
    acquisition = load('capture_acquisition', ROOT / 'scripts/complete_mac_slim_helpers.py')
    builder = load('capture_native_package', ROOT / 'tests/controls/build_cocoa_sidecars.py')
    collector = load('capture_collector', ROOT / 'scripts/collect_mac_recovery_proof.py')
    pins = json.loads((ROOT / 'scripts/mac_gpu_capture_inputs.json').read_text())
    product, output, work = args.producer_root.resolve(strict=True), args.output.resolve(), args.work.resolve()
    control_head, product_head = builder.clean_source(ROOT), builder.clean_source(product)
    roots = [ROOT, product, output, work]
    if output.exists() or work.exists() or any(a != b and (a.is_relative_to(b) or b.is_relative_to(a))
            for index, a in enumerate(roots) for b in roots[index + 1:]):
        raise ValueError('Require fresh separate owned replay and product/controller roots')
    if product_head != pins['productSource']:
        raise ValueError('Require exact immutable F sources')
    output.mkdir(parents=True)
    work.mkdir(parents=True)
    receipt = dict(schemaVersion=1, boundary='immutable-d31-gpu-public-capture-replay-v1',
        productSource=product_head, controlSource=control_head, run=os.environ['GITHUB_RUN_ID'],
        originalRun=pins['originalRun'], originalController=pins['originalControllerSource'],
        originalProofArtifact=pins['originalProofArtifact'], originalProofSha256=pins['originalProofSha256'],
        packageArtifact=pins['packageArtifact'], packageArchiveSha256=pins['packageArchiveSha256'],
        packageSha256=pins['packageSha256'], originalTransportComplete=False,
        engineBuild=False, hostBuild=False, helperBuild=False, catalogueRepeated=False, glyphRepeated=False,
        steps=[], passed=False, publication=False)
    native = None
    error = None
    try:
        original_run = acquisition.api('actions/runs/' + str(pins['originalRun']))
        if (original_run['head_sha'] != pins['originalControllerSource'] or original_run['run_attempt'] != 1
                or original_run['event'] != 'workflow_dispatch' or original_run['head_branch'] != 'main'
                or original_run['path'] != '.github/workflows/macos-preview12-recovery.yml'
                or original_run['status'] != 'completed' or original_run['conclusion'] != 'failure'):
            raise ValueError('Original recovery identity differs')
        (output / 'original-run.json').write_text(json.dumps(original_run, indent=2))
        for name, artifact, digest in [('original-proof', pins['originalProofArtifact'], pins['originalProofSha256']),
                                       ('package', pins['packageArtifact'], pins['packageArchiveSha256'])]:
            metadata = acquisition.api('actions/artifacts/' + str(artifact))
            if (metadata['expired'] or metadata['workflow_run']['id'] != pins['originalRun']
                    or metadata['workflow_run']['head_sha'] != pins['originalControllerSource']
                    or metadata['digest'] != 'sha256:' + digest):
                raise ValueError('Original artifact metadata differs')
            (output / (name + '-artifact.json')).write_text(json.dumps(metadata, indent=2))
            acquisition.api('actions/artifacts/' + str(artifact) + '/zip', output / (name + '.zip'))
            acquisition.verify_archive(output / (name + '.zip'), digest)
        for key in ['GH_TOKEN', 'GITHUB_TOKEN']:
            os.environ.pop(key, None)
        receipt['acquisitionCredentialsRemoved'] = True
        with zipfile.ZipFile(output / 'original-proof.zip') as archive:
            old = json.loads(archive.read('recovery-receipt.json'))
            old_helpers = json.loads(archive.read('sidecars/producer-sidecars.json'))
            glyph_bytes = archive.read('glyph-proof/orientation.json')
            glyph = json.loads(glyph_bytes)
            if (old['productSource'] != product_head or old['controlSource'] != pins['originalControllerSource']
                    or old['workflowRun'] != str(pins['originalRun']) or old['flavor'] != 'gpu'
                    or old['accepted'] is not True or old_helpers['status'] != 'compiled'
                    or old_helpers['nativeUnchanged'] is not True or old_helpers['sourcesUnchanged'] is not True
                    or old['phases']['qualify']['nativeBefore'] != pins['native']
                    or old['phases']['qualify']['nativeAfter'] != pins['native']):
                raise ValueError('Original product/helper/runtime boundary differs')
            for name in ['build', 'helpers', 'qualify']:
                phase = old['phases'][name]
                if not all(phase.get(key) is True for key in ['passed', 'productClean', 'builderClean']) or phase['identityErrors']:
                    raise ValueError('Original source or phase qualification failed')
            if (old['phases']['build']['native'] != pins['native'] or old['phases']['build']['packageSha256'] != pins['packageSha256']
                    or len(glyph['rows']) != 4 or any(row['uprightMaskIoU'] != 1.0 for row in glyph['rows'])
                    or any(glyph[field] for field in ['inversionObserved', 'cpuOrientationSuspect', 'gpuOrientationSuspect'])):
                raise ValueError('Original package or independent glyph qualification differs')
            receipt.update(originalPhases={name: True for name in ['build', 'helpers', 'qualify']}, originalAccepted=True,
                originalGlyphPinned=True, originalGlyphReceiptSha256=hashlib.sha256(glyph_bytes).hexdigest())
        compiler, binary, compiler_sha = builder.cxx_compiler(subprocess.check_output(
            ['xcrun', '--find', 'clang++'], text=True, timeout=30, env=acquisition.child_environment()).strip())
        sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True,
                                      timeout=30, env=acquisition.child_environment()).strip()
        if compiler_sha != old_helpers['appkitCompilerSha256'] or sdk != old_helpers['appkitSdk']:
            raise ValueError('Replay requires the actual original compiler binary and SDK')
        receipt.update(compilerInvocation=str(compiler), compilerResolvedPath=str(binary), compilerSha256=compiler_sha,
                       sdk=sdk, headerSha256=builder.sha(product / 'host/RanvierWebCoreAbi.h'))
        if receipt['headerSha256'] != old_helpers['headerSha256'] or old_helpers['declarations'] != 349 or old_helpers['abi'] != 64:
            raise ValueError('Replay requires the original canonical349 header')
        with zipfile.ZipFile(output / 'package.zip') as archive:
            files = acquisition.members(archive)
            if len(files) != 1 or next(iter(files.values())) != pins['packageSha256']:
                raise ValueError('Original package archive differs')
            name = next(iter(files))
            package = output / name
            package.write_bytes(archive.read(name))
        with zipfile.ZipFile(package) as archive:
            acquisition.members(archive)
            archive.extractall(work / 'stage')
        manifest, native, before = builder.admit_stage(work / 'stage')
        if (before != pins['native'] or manifest['source']['commit'] != product_head or manifest['flavor'] != 'gpu'
                or manifest['version'] != '0.1.1-preview.12' or not builder.package_matches(package, manifest)):
            raise ValueError('Replay native package differs from original qualified payload')
        receipt['nativeBefore'] = before
        environment = acquisition.child_environment() | {'RANVIER_ABI_TEST_EXPECTED': '64'}
        public = work / 'mac-gpu-public-qualification'
        command = [sys.executable, '-B', '-I', product / 'tests/gpu/mac/qualify_package.py',
                   '--native-directory', native, '--output', public]
        row = dict(name='public-output-input', argv=[str(value) for value in command])
        receipt['steps'].append(row)
        log = output / 'public-output-input.log'
        with log.open('wb') as stream:
            child = subprocess.Popen(row['argv'], cwd=product, env=environment, stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            row['pid'] = child.pid
            try:
                row['exit'] = child.wait(timeout=1800)
            finally:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=10)
                row.update(groupKillRequested=True, directChildReaped=True)
        row['logSha256'] = builder.sha(log)
        if row['exit']:
            raise RuntimeError('Public capture replay failed')
        public_receipt = json.loads((public / 'receipt.json').read_text())
        validate_public_receipt(public_receipt, before)
        for step in public_receipt['steps']:
            if builder.sha(public / (step['name'] + '.log')) != step['logSha256']:
                raise ValueError('Raw public step log differs from its receipt')
        captures = {path.name: builder.sha(path) for path in public.glob('*.bmp')}
        if set(captures) != EXPECTED_CAPTURES:
            raise ValueError('The exact fifteen runtime pixel captures are required')
        if any(not path.read_bytes().startswith(b'BM') for path in public.glob('*.bmp')):
            raise ValueError('Require actual SDL bitmap captures')
        prefix = 'product-gates/mac-gpu-public-qualification/'
        receipt['rawCaptureMembers'] = {prefix + name: digest for name, digest in captures.items()}
        receipt['rawLogMembers'] = {prefix + path.name: builder.sha(path) for path in public.glob('*.log')}
        if set(path.removesuffix('.log') for path in (Path(name).name for name in receipt['rawLogMembers'])) != EXPECTED_STEPS:
            raise ValueError('The complete raw qualifier logs are required')
        receipt.update(publicReceipt=prefix + 'receipt.json', publicReceiptSha256=builder.sha(public / 'receipt.json'), passed=True)
    except BaseException as failure:
        error = failure
        receipt['error'] = repr(failure)
    finally:
        receipt['nativeAfter'] = builder.snapshot(native) if native is not None else None
        receipt['nativeUnchanged'] = native is not None and receipt['nativeAfter'] == receipt['nativeBefore']
        receipt['productClean'] = builder.clean_source(product) == product_head
        receipt['controlClean'] = builder.clean_source(ROOT) == control_head
        processes = subprocess.check_output(['ps', '-axo', 'pid=,ppid=,command='], text=True, env=acquisition.child_environment())
        (output / 'processes-after.log').write_text(processes)
        remaining = [line for line in processes.splitlines() if int(line.split(None, 1)[0]) != os.getpid()
                     and any(str(root) in line for root in [output, work])]
        receipt['ownedProcessesExited'] = not remaining
        receipt['remainingOwnedProcesses'] = remaining
        receipt['packageUnchanged'] = 'nativeBefore' in receipt and builder.sha(package) == pins['packageSha256']
        receipt['passed'] = receipt['passed'] and all(receipt[key] for key in [
            'nativeUnchanged', 'productClean', 'controlClean', 'ownedProcessesExited', 'packageUnchanged'])
        (output / 'capture-replay.json').write_text(json.dumps(receipt, indent=2) + '\n')
        collector.collect(output, work, 'gpu')
    if error is not None or not receipt['passed']:
        raise RuntimeError('Capture replay failed; original product evidence remains separate') from error


if __name__ == '__main__':
    main()
