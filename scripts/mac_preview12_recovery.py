"""Recover immutable d31 Mac packages with a separately identified helper builder."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys

PRODUCT_SOURCE = 'd31c3631ed4bbe6520f7f5f7c7e7d34499c38122'
VERSION = '0.1.1-preview.12'
CONTROL = Path(__file__).resolve().parents[1]
SLIM_RUN = 41719479076
PREWARM_RUN = 41720640443
HELPER_SOURCE = '3f187c76e404ace64791d8996591ca8bd97183bf'
HELPER_BLOBS = {
    'tests/controls/build_cocoa_sidecars.py': 'd2ff164b0ce774ed5c129e95046028083d411425',
    'tests/abi/build_cocoa_timer_contract.py': '55fd1261c444226578383efbb91accc9696cd1d6',
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(root, expected=None):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True)
    if dirty or not re.fullmatch('[0-9a-f]{40}', head) or expected is not None and head != expected:
        raise ValueError('Require the exact clean checkout: ' + str(root))
    return head


def helper_identity(control):
    actual = {name: subprocess.check_output(['git', 'rev-parse', 'HEAD:' + name], cwd=control, text=True).strip()
              for name in HELPER_BLOBS}
    if actual != HELPER_BLOBS:
        raise ValueError('Require the separately reviewed helper implementation')
    return actual


def admit_compile_database(build, product, control):
    entries = json.loads((build / 'compile_commands.json').read_text())
    selected = [entry for entry in entries if Path(entry.get('file', '')).name == 'RanvierWebCoreAbi.cpp']
    if len(selected) != 1:
        raise ValueError('Require exactly one producer Host compile command')
    entry = selected[0]
    cwd = Path(entry['directory']).resolve(strict=True)
    command = entry.get('arguments') or shlex.split(entry['command'])
    source = (cwd / entry['file']).resolve(strict=True)
    if (cwd != build.resolve() or not isinstance(command, list) or not command
            or any(not isinstance(word, str) or word.startswith('@') or str(control.resolve()) in word for word in command)
            or command.count('-c') != 1 or command.count('-o') != 1
            or sha(source) != sha(product / 'host/RanvierWebCoreAbi.cpp')):
        raise ValueError('Host compile command does not match the actual product source and isolated builder')
    return dict(source=str(source), sourceSha256=sha(source), directory=str(cwd), arguments=command,
                compileDatabaseSha256=sha(build / 'compile_commands.json'))


def require_warm_plan(text):
    compilations = [line for line in text.splitlines() if re.search(r'\bBuilding\s+(?:CXX|C|OBJCXX|OBJC|Swift)\s+', line)]
    unexpected = [line for line in compilations if 'RanvierWebCoreHost.dir/' not in line]
    if unexpected:
        raise ValueError('Warm recovery would compile engine inputs; retain the plan for a separate producer decision: ' + '\n'.join(unexpected[:20]))
    return dict(hostCompileEdges=len(compilations), engineCompileEdges=0)


def require_run(run, branch, event):
    if (run.get('head_sha') != PRODUCT_SOURCE or run.get('head_branch') != branch or run.get('event') != event
            or run.get('path') != '.github/workflows/build.yml'):
        raise ValueError('Original producer run identity differs')


def failed_mac_job(jobs):
    selected = [job for job in jobs if job.get('name', '').startswith('native (osx-arm64,')]
    if len(selected) != 1 or selected[0].get('status') != 'completed' or selected[0].get('conclusion') != 'failure':
        raise ValueError('Do not duplicate a healthy, live, missing or ambiguous immutable-F Mac job')
    return selected[0]


def recovery_boundary(flavor):
    def api(route):
        return json.loads(subprocess.check_output(['gh', 'api', 'repos/ranvier-org/Ranvier.WebCore/' + route], text=True, timeout=30))
    def jobs(run):
        value = api('actions/runs/' + str(run) + '/jobs?per_page=100')
        if value['total_count'] != len(value['jobs']):
            raise ValueError('The complete producer job list is required')
        return value['jobs']
    slim = api('actions/runs/' + str(SLIM_RUN))
    require_run(slim, 'v' + VERSION, 'push')
    if flavor == 'slim':
        return dict(slimRun=SLIM_RUN, failedJob=failed_mac_job(jobs(SLIM_RUN)))
    if slim['status'] != 'completed':
        raise ValueError('Wait for the original Slim run and its automatic GPU decision to finish')
    prewarm = api('actions/runs/' + str(PREWARM_RUN))
    require_run(prewarm, 'main', 'workflow_dispatch')
    prewarm_job = failed_mac_job(jobs(PREWARM_RUN))
    listing = api('actions/workflows/build.yml/runs?event=workflow_dispatch&branch=v' + VERSION + '&per_page=100')
    candidates = listing['workflow_runs']
    if listing['total_count'] != len(candidates):
        raise ValueError('The complete immutable-tag dispatch list is required')
    checked = []
    for run in candidates:
        if run.get('head_sha') != PRODUCT_SOURCE:
            continue
        require_run(run, 'v' + VERSION, 'workflow_dispatch')
        if run['status'] != 'completed':
            raise ValueError('An immutable-F GPU dispatch is still active; no overlapping recovery')
        run_jobs = jobs(run['id'])
        if any(job.get('name', '').startswith('native (osx-arm64,') for job in run_jobs):
            checked.append(dict(run=run['id'], failedJob=failed_mac_job(run_jobs)))
    if slim.get('conclusion') == 'success' and not checked:
        raise ValueError('Wait for the automatically dispatched tag GPU Mac job; no absent-list shortcut')
    return dict(slimRun=SLIM_RUN, prewarmRun=PREWARM_RUN, prewarmFailedJob=prewarm_job, tagGpuRuns=checked)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['build', 'helpers', 'qualify'], required=True)
    parser.add_argument('--producer-root', type=Path, required=True)
    parser.add_argument('--control-source', required=True)
    parser.add_argument('--flavor', choices=['slim', 'gpu'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64' or platform.mac_ver()[0].split('.')[0] != '26':
        raise ValueError('Require macOS26 ARM64')
    product = args.producer_root.resolve(strict=True)
    control = CONTROL.resolve(strict=True)
    output = args.output.resolve()
    work = Path('/Users/runner/rw')
    build, source, stage = work / ('build-' + args.flavor), work / 'src', work / 'out' / args.flavor
    if (product.is_relative_to(control) or control.is_relative_to(product)
            or any(output.is_relative_to(path) for path in [product, control, work])):
        raise ValueError('Keep builder and evidence outside the original product checkout and producer tree')
    identity(product, PRODUCT_SOURCE)
    identity(control, args.control_source)
    helper_blobs = helper_identity(control)
    if args.control_source != os.environ.get('GITHUB_SHA'):
        raise ValueError('Builder source must match the executing workflow head')
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output / 'recovery-receipt.json'
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else dict(
        scope='Immutable d31 warm Mac recovery; product F and helper builder H remain separate; no publication',
        productSource=PRODUCT_SOURCE, controlSource=args.control_source, flavor=args.flavor,
        reviewedHelperSource=HELPER_SOURCE, helperBlobs=helper_blobs,
        productRoot=str(product), controlRoot=str(control), workflowRun=os.environ.get('GITHUB_RUN_ID'),
        version=VERSION, publication=False, phases={}, commands=[])
    receipt['restoredCacheKey'] = os.environ.get('RANVIER_RESTORED_CACHE_KEY')
    if (receipt['productSource'] != PRODUCT_SOURCE or receipt['controlSource'] != args.control_source
            or receipt['flavor'] != args.flavor or args.phase in receipt['phases']):
        raise ValueError('Recovery phase identity differs or this phase already ran')
    phase = dict(passed=False)
    receipt['phases'][args.phase] = phase
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', MSBUILDDISABLENODEREUSE='1',
                       DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER='1')
    for name in ['GH_TOKEN', 'GITHUB_TOKEN']:
        environment.pop(name, None)

    def run(name, command, timeout=900, extra_env=None):
        log = output / (name + '.log')
        row = dict(name=name, argv=[str(word) for word in command], log=str(log), phase=args.phase)
        receipt['commands'].append(row)
        receipt_path.write_text(json.dumps(receipt, indent=2))
        with log.open('wb') as stream:
            child = subprocess.Popen(row['argv'], cwd=product, env=environment | (extra_env or {}),
                                     stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            row['pid'] = child.pid
            try:
                row['exit'] = child.wait(timeout=timeout)
            finally:
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                child.wait(timeout=10)
                row['ownedProcessGroupKillRequested'] = True
                row['directChildReaped'] = True
                row['logSha256'] = sha(log)
        if row['exit']:
            raise RuntimeError(name + ' failed; see ' + str(log))
        return log.read_text(errors='replace')

    def product_build(step):
        return [sys.executable, '-B', product / 'scripts/build.py', step, '--rid', 'osx-arm64',
                '--flavor', args.flavor, '--version', VERSION, '--work', work]

    try:
        if args.phase == 'build':
            phase['originalProducerBoundary'] = recovery_boundary(args.flavor)
            cached = build / 'CMakeCache.txt'
            phase['cachedConfigurationSha256'] = sha(cached) if cached.exists() else None
            if not cached.exists():
                raise ValueError('No warm producer configuration was restored; no cold engine fallback')
            shutil.copy2(cached, output / 'original-CMakeCache.txt')
            run('normalise', [sys.executable, '-I', product / 'scripts/build_cache.py', 'normalise',
                '--build', build, '--source', source, '--clear-unknown'])
            if cached.exists():
                raise ValueError('Canonical normalisation did not clear the previous CMake cache')
            run('configure', product_build('configure'), extra_env={'CMAKE_EXPORT_COMPILE_COMMANDS': 'ON'})
            cache_text = cached.read_text()
            if not re.search(r'^CMAKE_EXPORT_COMPILE_COMMANDS:[^=]+=ON$', cache_text, re.M):
                raise ValueError('Compile command export was not admitted by actual CMake')
            phase['configuredCacheSha256'] = sha(cached)
            phase['hostCompile'] = admit_compile_database(build, product, control)
            sdk = output / 'original-sdk-metadata'
            sdk.mkdir()
            for name in ['CMakeCache.txt', 'compile_commands.json', 'cmakeconfig.h']:
                shutil.copy2(build / name, sdk / name)
            shutil.copy2(product / 'host/RanvierWebCoreAbi.h', sdk / 'RanvierWebCoreAbi.h')
            phase['sdkMetadata'] = {path.name: sha(path) for path in sdk.iterdir()}
            plan = run('ninja-plan', ['ninja', '-C', build, '-n', 'RanvierWebCoreHost'])
            phase['warmPlan'] = require_warm_plan(plan)
            run('build', product_build('build'), timeout=1800)
            run('package', product_build('package'))
            helper = load_helper(control)
            manifest, native, hashes = helper.admit_stage(stage)
            if manifest['source']['commit'] != PRODUCT_SOURCE or manifest['flavor'] != args.flavor or manifest['version'] != VERSION:
                raise ValueError('Package stage source/flavor/version differs from immutable F')
            packages = [path for path in (work / 'packages').glob('*.nupkg') if helper.package_matches(path, manifest)]
            if len(packages) != 1:
                raise ValueError('Require exactly one unchanged matching product package')
            phase.update(package=str(packages[0]), packageSha256=sha(packages[0]), manifestSha256=sha(stage / 'manifest.json'),
                         native=hashes, productClean=identity(product, PRODUCT_SOURCE) == PRODUCT_SOURCE)
            if os.environ.get('GITHUB_OUTPUT'):
                with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                    stream.write('package=' + str(packages[0]) + '\nmanifest=' + str(stage / 'manifest.json') + '\n')
        else:
            if not receipt['phases'].get('build', {}).get('passed'):
                raise ValueError('A successful admitted product package is required first')
            helper = load_helper(control)
            manifest, native, before = helper.admit_stage(stage)
            if manifest['source']['commit'] != PRODUCT_SOURCE or before != receipt['phases']['build']['native']:
                raise ValueError('The retained product runtime changed')
            if args.phase == 'helpers':
                run('helpers', [sys.executable, '-B', '-I', control / 'tests/controls/build_cocoa_sidecars.py',
                    '--producer-root', product, '--stage', stage, '--build', build, '--webkit-source', source,
                    '--packages', work / 'packages', '--output', output / 'sidecars'], timeout=900,
                    extra_env={'RANVIER_COCOA_OWNED_GROUP': '1'})
            else:
                failures = []
                groups = [('smoke', product_build('smoke')),
                    ('mutation', [sys.executable, '-I', product / 'tests/abi/mutation_observation.py', '--native-directory', native]),
                    ('probes', [sys.executable, '-I', product / 'scripts/probes.py', 'run', '--rid', 'osx-arm64',
                                '--flavor', args.flavor, '--work', work, '--expected-abi', '64'])]
                for name, command in groups:
                    try: run(name, command, timeout=1800)
                    except (RuntimeError, subprocess.TimeoutExpired) as error: failures.append(str(error))
                phase['failures'] = failures
                if failures:
                    raise RuntimeError('Independent product gates failed: ' + '; '.join(failures))
            if helper.snapshot(native) != before:
                raise ValueError('Helper or qualification changed product native payloads')
        phase['passed'] = True
    except Exception as error:
        phase['error'] = repr(error)
        raise
    finally:
        identity_errors = []
        for name, checkout, expected in [('productClean', product, PRODUCT_SOURCE), ('builderClean', control, args.control_source)]:
            try:
                phase[name] = identity(checkout, expected) == expected
            except Exception as error:
                phase[name] = False
                identity_errors.append(str(error))
        phase['identityErrors'] = identity_errors
        receipt['accepted'] = all(receipt['phases'].get(name, {}).get('passed') for name in ['build', 'helpers', 'qualify'])
        if identity_errors:
            phase['passed'] = receipt['accepted'] = False
        receipt_path.write_text(json.dumps(receipt, indent=2))
        if identity_errors:
            raise ValueError('; '.join(identity_errors))


def load_helper(control):
    spec = importlib.util.spec_from_file_location('matching_sidecars', control / 'tests/controls/build_cocoa_sidecars.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


if __name__ == '__main__':
    main()
