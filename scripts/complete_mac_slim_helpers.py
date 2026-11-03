"""Complete two AppKit helpers against the retained immutable Slim producer evidence."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import signal
import stat
import subprocess
import sys
import urllib.request
import urllib.parse
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / 'scripts/mac_slim_helper_completion_inputs.json'
REPO = 'ranvier-org/Ranvier.WebCore'


class DownloadRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        redirected = super().redirect_request(request, response, code, message, headers, url)
        if redirected is not None and urllib.parse.urlparse(url).hostname != 'api.github.com':
            redirected.remove_header('Authorization')
        return redirected


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def child_environment():
    return {key: value for key, value in os.environ.items() if key not in {'GH_TOKEN', 'GITHUB_TOKEN'}}


def members(archive):
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError('Duplicate archive members')
    for row in archive.infolist():
        name = PurePosixPath(row.filename)
        if (name.is_absolute() or '..' in name.parts or '\\' in row.filename
                or stat.S_ISLNK(row.external_attr >> 16)):
            raise ValueError('Unsafe archive member')
    return {name: hashlib.sha256(archive.read(name)).hexdigest() for name in names if not name.endswith('/')}


def verify_archive(path, digest, expected=None):
    if sha(path) != digest:
        raise ValueError('Archive digest mismatch')
    with zipfile.ZipFile(path) as archive:
        actual = members(archive)
    if expected is not None and actual != expected:
        raise ValueError('Archive member mismatch')
    return actual


def api(route, target=None):
    request = urllib.request.Request('https://api.github.com/repos/' + REPO + '/' + route,
                                    headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                                             'Accept': 'application/vnd.github+json'})
    with urllib.request.build_opener(DownloadRedirect()).open(request, timeout=60) as response:
        if target is None:
            return json.load(response)
        with target.open('xb') as stream:
            while data := response.read(1024 * 1024):
                stream.write(data)


def admit_original(contract, proof, package):
    prefix = contract['proofPrefix']
    verify_archive(proof, contract['artifacts']['proof']['sha256'], contract['proofMembers'])
    verify_archive(package, contract['artifacts']['package']['sha256'],
                   {'Ranvier.WebCore.Native.osx-arm64.0.1.1-preview.12.nupkg': contract['packageSha256']})
    with zipfile.ZipFile(proof) as archive:
        recovery = json.loads(archive.read(prefix + 'recovery-receipt.json'))
        sidecars = json.loads(archive.read(prefix + 'sidecars/producer-sidecars.json'))
        if (recovery['productSource'] != contract['productSource']
                or recovery['controlSource'] != contract['originalControllerSource']
                or recovery['workflowRun'] != str(contract['originalRun'])
                or recovery['flavor'] != 'slim' or recovery['accepted'] is not False
                or {key: row['passed'] for key, row in recovery['phases'].items()}
                != {'build': True, 'helpers': False, 'qualify': True}
                or sidecars['nativeSource'] != contract['productSource']
                or sidecars['nativeUnchanged'] is not True
                or sidecars['sourcesUnchanged'] is not True):
            raise ValueError('Original run boundary changed')
        for name in ['timer', 'page']:
            receipt = json.loads(archive.read(prefix + 'sidecars/' + name + '/build-receipt.json'))
            if (receipt['status'] != 'compiled' or receipt['inputsUnchanged'] is not True
                    or receipt['runtimeUnchanged'] is not True):
                raise ValueError('Retained helper was not successfully compiled')
            helper = sidecars['helpers'][name]
            if hashlib.sha256(archive.read(prefix + 'sidecars/' + helper['path'])).hexdigest() != helper['sha256']:
                raise ValueError('Retained helper bytes changed')
    return recovery, sidecars


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64' or platform.mac_ver()[0].split('.')[0] != '26':
        raise ValueError('Require actual macOS26 ARM64')
    spec = importlib.util.spec_from_file_location('completion_sidecars', ROOT / 'tests/controls/build_cocoa_sidecars.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    product = args.producer_root.resolve(strict=True)
    head, product_head = builder.clean_source(ROOT), builder.clean_source(product)
    helper_blob = subprocess.check_output(['git', 'rev-parse', 'HEAD:tests/controls/build_cocoa_sidecars.py'],
                                          cwd=ROOT, text=True, timeout=30).strip()
    if helper_blob != 'f626b86e23f8e78e5b08adcf17b58c7ec1efbf67':
        raise ValueError('Require the separately reviewed clang++ invocation fix')
    contract = json.loads(INPUTS.read_text())
    if product_head != contract['productSource']:
        raise ValueError('Require exact clean immutable product F')
    output = args.output.resolve()
    if output.exists() or any(output.is_relative_to(root) or root.is_relative_to(output) for root in [ROOT, product]):
        raise ValueError('Require fresh separate completion output')
    output.mkdir(parents=True)
    receipt = dict(schemaVersion=1, boundary='immutable-d31-slim-stitched-helper-completion-v1',
                   productSource=product_head, helperControlSource=head,
                   completionRun=os.environ['GITHUB_RUN_ID'], originalRun=contract['originalRun'],
                   originalControllerSource=contract['originalControllerSource'],
                   helperBuilderGitBlob=helper_blob,
                   helperBuilderSha256=sha(ROOT / 'tests/controls/build_cocoa_sidecars.py'),
                   inputsContractSha256=sha(INPUTS), originalProofPrefix=contract['proofPrefix'],
                   productBuildRepeated=False, nativeGatesRepeated=False, engineCompilation=False,
                   timerPageRecompiled=False, publication=False, accepted=False, commands=[], helpers={})

    def run(name, command, expected=0):
        row = dict(name=name, argv=[str(value) for value in command])
        receipt['commands'].append(row)
        with (output / (name + '.log')).open('wb') as stream:
            child = subprocess.Popen(row['argv'], stdout=stream, stderr=subprocess.STDOUT, start_new_session=True,
                                     env=child_environment())
            row['pid'] = child.pid
            try:
                row['exit'] = child.wait(timeout=180)
            finally:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=10)
                row.update(groupKillRequested=True, directChildReaped=True)
        row['logSha256'] = sha(output / (name + '.log'))
        if row['exit'] != expected:
            raise RuntimeError(name + ' failed')

    native = None
    try:
        original_run = api('actions/runs/' + str(contract['originalRun']))
        (output / 'original-run.json').write_text(json.dumps(original_run, indent=2) + '\n')
        if (original_run['head_sha'] != contract['originalControllerSource']
                or original_run['event'] != 'workflow_dispatch' or original_run['head_branch'] != 'main'
                or original_run['path'] != '.github/workflows/macos-preview12-recovery.yml'
                or original_run['status'] != 'completed' or original_run['conclusion'] != 'failure'
                or original_run['run_attempt'] != 1):
            raise ValueError('Original workflow run mismatch')
        for name, pin in contract['artifacts'].items():
            metadata = api('actions/artifacts/' + str(pin['id']))
            (output / (name + '-artifact.json')).write_text(json.dumps(metadata, indent=2) + '\n')
            if (metadata['expired'] or metadata['workflow_run']['id'] != contract['originalRun']
                    or metadata['workflow_run']['head_sha'] != contract['originalControllerSource']
                    or metadata['digest'] != 'sha256:' + pin['sha256']):
                raise ValueError('Original artifact metadata mismatch')
            api('actions/artifacts/' + str(pin['id']) + '/zip', output / (name + '.zip'))
        for key in ['GH_TOKEN', 'GITHUB_TOKEN']:
            os.environ.pop(key, None)
        receipt['acquisitionCredentialsRemoved'] = True
        recovery, prior = admit_original(contract, output / 'proof.zip', output / 'package.zip')
        header = product / 'host/RanvierWebCoreAbi.h'
        declarations = re.findall(rb'RV_EXPORT\s+[^;]*?\b(rv_\w+)\s*\([^;]*?\)\s*;', header.read_bytes(), re.S)
        if (sha(header) != prior['headerSha256'] or len(declarations) != 349 or len(set(declarations)) != 349):
            raise ValueError('Require the retained canonical 349-declaration product header')
        receipt.update(headerSha256=sha(header), declarations=349, abi=64)
        receipt['originalPhases'] = {name: row['passed'] for name, row in recovery['phases'].items()}
        receipt['originalFailedHelper'] = prior['error']
        with zipfile.ZipFile(output / 'package.zip') as archive:
            archive.extractall(output / 'package')
        package, = (output / 'package').glob('*.nupkg')
        with zipfile.ZipFile(package) as archive:
            members(archive)
            manifest = json.loads(archive.read('manifest.json'))
            archive.extractall(output / 'stage')
        admitted_manifest, native, before = builder.admit_stage(output / 'stage')
        if (admitted_manifest != manifest or not builder.package_matches(package, manifest)
                or before != recovery['phases']['build']['native'] or manifest['source']['commit'] != product_head):
            raise ValueError('Exact package and native manifest mismatch')
        receipt.update(packageSha256=sha(package), nativeBefore=before)
        with zipfile.ZipFile(output / 'proof.zip') as archive:
            prefix = contract['proofPrefix']
            for name, digest in contract['proofMembers'].items():
                if name.startswith(prefix + 'sidecars/'):
                    destination = output / 'retained-sidecars' / name.removeprefix(prefix + 'sidecars/')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(archive.read(name))
            for name in ['timer', 'page']:
                retained = prior['helpers'][name]
                receipt['helpers'][name] = dict(path='retained-sidecars/' + retained['path'],
                                               sha256=retained['sha256'], reusedFromRun=contract['originalRun'],
                                               receipt='retained-sidecars/' + name + '/build-receipt.json',
                                               capsule='retained-sidecars/' + name + '/consumed-inputs.zip')
        compiler, binary, compiler_sha = builder.cxx_compiler(subprocess.check_output(
            ['xcrun', '--find', 'clang++'], text=True, timeout=30).strip())
        sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True, timeout=30).strip()
        if compiler_sha != prior['appkitCompilerSha256'] or sdk != prior['appkitSdk']:
            raise ValueError('Require the actual original compiler binary and SDK')
        original_inputs = {}
        with zipfile.ZipFile(output / 'retained-sidecars/motion-consumed-inputs.zip') as archive:
            members(archive)
            for name in archive.namelist():
                path = Path('/' + name.removeprefix('inputs/'))
                if not name.startswith('inputs/') or not path.is_file() or sha(path) != hashlib.sha256(archive.read(name)).hexdigest():
                    raise ValueError('Original consumed SDK/source input unavailable or changed')
                original_inputs[str(path)] = sha(path)
        receipt.update(compilerInvocation=str(compiler), compilerResolvedPath=str(binary), compilerSha256=compiler_sha,
                       sdk=sdk, originalConsumedInputsVerified=True, originalConsumedInputs=original_inputs)
        run('driver-control', [sys.executable, '-B', '-I', ROOT / 'tests/controls/cocoa_cxx_driver_diagnostic.py',
                               '--output', output / 'driver-control'])
        control = json.loads((output / 'driver-control/driver-diagnostic.json').read_text())
        if control['result'] != 'PASS' or control['compilerSha256'] != compiler_sha:
            raise ValueError('Actual strict driver comparison failed')
        for name, filename in [('motion', 'cocoa_progress_motion.mm'), ('contrast', 'cocoa_contrast_scoped_override.mm')]:
            probe = product / 'tests/controls' / filename
            helper = output / ('libRanvierCocoa' + name.title() + '.dylib')
            common = [compiler, '-std=c++20', '-fobjc-arc', '-arch', 'arm64', '-isysroot', sdk,
                      '-mmacosx-version-min=26.0', '-framework', 'AppKit', '-framework', 'Foundation', probe]
            dependencies = output / (name + '.d')
            run(name + '-dependencies', [*common, '-M', '-MF', dependencies, '-MT', 'helper'])
            text = dependencies.read_text().replace('\\\n', ' ')
            paths = {Path(word.replace('\\ ', ' ')).resolve(strict=True)
                     for word in re.split(r'(?<!\\)\s+', text.split(':', 1)[1].strip())}
            hashes = {str(path): sha(path) for path in sorted(paths)}
            capsule = output / (name + '-consumed-inputs.zip')
            with zipfile.ZipFile(capsule, 'x', zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(paths):
                    if sha(path) != hashes[str(path)]:
                        raise ValueError('Input changed before compile capture')
                    archive.writestr('inputs/' + str(path).lstrip('/'), path.read_bytes())
            run(name + '-compile', [*common, '-dynamiclib', '-Wl,-undefined,error',
                                   '-Wl,-install_name,@rpath/' + helper.name, '-o', helper])
            run(name + '-sign', ['codesign', '--force', '--sign', '-', helper])
            run(name + '-verify', ['codesign', '--verify', '--strict', helper])
            if hashes != {path: sha(path) for path in hashes}:
                raise ValueError('AppKit consumed inputs changed')
            receipt['helpers'][name] = dict(path=helper.name, sha256=sha(helper), compiledInRun=receipt['completionRun'],
                                           capsule=capsule.name, capsuleSha256=sha(capsule), inputs=hashes)
        receipt.update(status='compiled', accepted=True, runtimeConsumerQualification=False)
    except BaseException as error:
        receipt.update(status='failed', error=repr(error))
        raise
    finally:
        receipt['nativeAfter'] = builder.snapshot(native) if native is not None else None
        receipt['nativeUnchanged'] = native is not None and receipt['nativeAfter'] == receipt['nativeBefore']
        receipt['sourcesUnchanged'] = builder.clean_source(ROOT) == head and builder.clean_source(product) == product_head
        receipt['compilerUnchanged'] = 'compilerSha256' in receipt and sha(receipt['compilerResolvedPath']) == receipt['compilerSha256']
        receipt['originalConsumedInputsUnchanged'] = ('originalConsumedInputs' in receipt
                and receipt['originalConsumedInputs'] == {path: sha(path) for path in receipt['originalConsumedInputs']})
        receipt['archivesUnchanged'] = all(sha(output / (name + '.zip')) == pin['sha256']
                                           for name, pin in contract['artifacts'].items()
                                           if (output / (name + '.zip')).exists())
        receipt['packageUnchanged'] = ('packageSha256' in receipt and sha(package) == receipt['packageSha256'])
        receipt['accepted'] = receipt['accepted'] and all(receipt[key] for key in [
            'nativeUnchanged', 'sourcesUnchanged', 'archivesUnchanged', 'packageUnchanged',
            'compilerUnchanged', 'originalConsumedInputsUnchanged'])
        receipt['members'] = {path.relative_to(output).as_posix(): sha(path) for path in sorted(output.rglob('*')) if path.is_file()}
        (output / 'helper-completion.json').write_text(json.dumps(receipt, indent=2) + '\n')
        if not receipt['accepted']:
            raise RuntimeError('Helper completion failed; original proof remains unchanged')


if __name__ == '__main__':
    main()
