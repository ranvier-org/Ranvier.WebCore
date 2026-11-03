"""Capture test helpers while the matching macOS producer headers are available."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(native):
    return {path.relative_to(native).as_posix(): sha(path)
            for path in sorted(native.rglob('*')) if path.is_file()}


def clean_source(root):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=root, text=True)
    if not re.fullmatch('[a-f0-9]{40}', head) or dirty:
        raise ValueError('Require a clean tracked source checkout')
    return head


def admit_stage(stage):
    stage = stage.resolve(strict=True)
    manifest = json.loads((stage / 'manifest.json').read_text())
    if (manifest.get('rid') != 'osx-arm64' or manifest.get('abi') != 64
            or manifest.get('flavor') not in {'slim', 'gpu'}
            or manifest.get('source', {}).get('dirty') is not False
            or not re.fullmatch('[a-f0-9]{40}', manifest['source'].get('commit', ''))):
        raise ValueError('Require a clean matching ABI64 macOS producer')
    native = stage / 'runtimes/osx-arm64/native'
    expected = {item['name']: item['sha256'] for item in manifest['files']}
    required = {'libRanvierWebCoreHost.dylib', 'libWebCore.dylib', 'libJavaScriptCore.dylib', 'libWebGPU.dylib'}
    if manifest['flavor'] == 'gpu':
        required |= {'libEGL.dylib', 'libGLESv2.dylib'}
    if (len(expected) != len(manifest['files']) or not required <= expected.keys()
            or snapshot(native) != expected):
        raise ValueError('The complete staged native payload must match its manifest')
    return manifest, native, expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['stage', 'build', 'webkit-source', 'packages', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--producer-root', type=Path, default=ROOT)
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64' or platform.mac_ver()[0].split('.')[0] != '26':
        raise ValueError('Require the actual macOS26 ARM64 producer')
    manifest, native, before = admit_stage(args.stage)
    producer_root = args.producer_root.resolve(strict=True)
    head = clean_source(producer_root)
    controller_head = clean_source(ROOT)
    if head != manifest['source']['commit']:
        raise ValueError('Helper sources must match the clean producer commit')
    header = (producer_root / 'host/RanvierWebCoreAbi.h').read_bytes()
    declarations = re.findall(rb'RV_EXPORT\s+[^;]*?\b(rv_\w+)\s*\([^;]*?\)\s*;', header, re.S)
    if len(declarations) != 349 or len(set(declarations)) != 349:
        raise ValueError('Require the complete canonical 349-declaration header')
    build = args.build.resolve(strict=True)
    source = args.webkit_source.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or any(output.is_relative_to(path) for path in [ROOT, producer_root, build, source, args.stage.resolve()]):
        raise ValueError('Require a fresh separate helper output directory')
    package, = [path for path in args.packages.glob('*.nupkg')
                if zipfile.is_zipfile(path) and package_matches(path, manifest)]
    output.mkdir(parents=True)
    runtime_hashes = output / 'runtime-dylib-hashes.json'
    runtime_hashes.write_text(json.dumps({name: digest for name, digest in before.items() if name.endswith('.dylib')}, indent=2))
    receipt = dict(schemaVersion=1, boundary='producer-Host-unchanged-sidecars-v1', abi=64, declarations=349,
                   nativeSource=manifest['source']['commit'], unsignedPackageSha256=sha(package),
                   producerRoot=str(producer_root), controllerRoot=str(ROOT),
                   controllerSource=controller_head, controllerTrackedDirty=False,
                   controllerSha256=sha(Path(__file__)), helperBuilderSha256=sha(ROOT / 'tests/abi/build_cocoa_timer_contract.py'),
                   headerSha256=hashlib.sha256(header).hexdigest(),
                   nativeBefore=before, commands=[], helpers={}, accepted=False,
                   hostReplaced=False, headerReconstruction=False, engineCompilation=False)

    def run(name, command):
        owns_group = os.environ.get('RANVIER_COCOA_OWNED_GROUP') != '1'
        row = dict(name=name, argv=[str(value) for value in command], ownsProcessGroup=owns_group)
        receipt['commands'].append(row)
        with (output / (name + '.log')).open('wb') as stream:
            child = subprocess.Popen(row['argv'], stdout=stream, stderr=subprocess.STDOUT, start_new_session=owns_group,
                                     env=dict(os.environ, RANVIER_COCOA_OWNED_GROUP='1'))
            try:
                row['exit'] = child.wait(timeout=300)
            finally:
                if owns_group:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif child.poll() is None:
                    child.kill()
                child.wait(timeout=10)
                row['childReaped'] = True
                if owns_group:
                    row['processGroupReaped'] = True
        if row['exit']:
            raise RuntimeError('Matching producer helper failed: ' + name)

    try:
        for name, probe in [('timer', 'tests/abi/cocoa_timer_contract.cpp'), ('page', 'tests/controls/cocoa_page_sidecar.cpp')]:
            command = [sys.executable, '-B', '-I', ROOT / 'tests/abi/build_cocoa_timer_contract.py',
                       '--build', build, '--webkit-source', source, '--runtime', native,
                       '--runtime-hashes', runtime_hashes, '--probe-source', producer_root / probe,
                       '--output', output / name, '--public-sidecar']
            if name == 'page':
                command.append('--link-webcore')
            run(name, command)
            proof = json.loads((output / name / 'build-receipt.json').read_text())
            if proof.get('status') != 'compiled' or not proof.get('inputsUnchanged') or not proof.get('runtimeUnchanged'):
                raise ValueError('Helper compilation failed its unchanged-input contract')
            helper = Path(proof['helperPath'])
            receipt['helpers'][name] = dict(path=helper.relative_to(output).as_posix(), sha256=sha(helper))
        compiler = Path(subprocess.check_output(['xcrun', '--find', 'clang++'], text=True, timeout=30).strip()).resolve(strict=True)
        sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True, timeout=30).strip()
        receipt.update(appkitCompilerSha256=sha(compiler), appkitSdk=sdk)
        run('appkit-toolchain', [compiler, '--version'])
        appkit_inputs = set()
        appkit_before = {}
        for name, filename in [('motion', 'cocoa_progress_motion.mm'), ('contrast', 'cocoa_contrast_scoped_override.mm')]:
            probe = producer_root / 'tests/controls' / filename
            helper = output / ('libRanvierCocoa' + name.title() + '.dylib')
            common = [compiler, '-std=c++20', '-fobjc-arc', '-arch', 'arm64', '-isysroot', sdk,
                      '-mmacosx-version-min=26.0', '-framework', 'AppKit', '-framework', 'Foundation', probe]
            dependencies = output / (name + '.d')
            run(name + '-dependencies', [*common, '-M', '-MF', dependencies, '-MT', 'helper'])
            text = dependencies.read_text().replace('\\\n', ' ')
            for word in re.split(r'(?<!\\)\s+', text.split(':', 1)[1].strip()):
                appkit_inputs.add(Path(word.replace('\\ ', ' ')).resolve(strict=True))
            input_before = {str(path): sha(path) for path in sorted(appkit_inputs)}
            for path, digest in input_before.items():
                if path in appkit_before and appkit_before[path] != digest:
                    raise ValueError('Earlier AppKit inputs changed')
            appkit_before.update(input_before)
            capsule = output / (name + '-consumed-inputs.zip')
            with zipfile.ZipFile(capsule, 'x', zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(appkit_inputs):
                    data = path.read_bytes()
                    if hashlib.sha256(data).hexdigest() != input_before[str(path)]:
                        raise ValueError('AppKit input changed before compile capture')
                    archive.writestr('inputs/' + str(path).lstrip('/'), data)
            receipt.setdefault('appkitConsumedInputs', {})[name] = dict(path=capsule.name, sha256=sha(capsule))
            run(name + '-compile', [*common, '-dynamiclib', '-Wl,-undefined,error',
                                   '-Wl,-install_name,@rpath/' + helper.name, '-o', helper])
            run(name + '-sign', ['codesign', '--force', '--sign', '-', helper])
            run(name + '-verify', ['codesign', '--verify', '--strict', helper])
            if input_before != {path: sha(path) for path in input_before}:
                raise ValueError('AppKit helper inputs changed')
            receipt['helpers'][name] = dict(path=helper.name, sha256=sha(helper))
        with zipfile.ZipFile(output / 'appkit-consumed-inputs.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(appkit_inputs):
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != appkit_before[str(path)]:
                    raise ValueError('AppKit input changed before capture')
                archive.writestr('inputs/' + str(path).lstrip('/'), data)
        if appkit_before != {path: sha(path) for path in appkit_before}:
            raise ValueError('AppKit inputs changed during capture')
        receipt['appkitInputs'] = appkit_before
        receipt.update(status='compiled', publicConsumerSealRequired=True)
    except Exception as error:
        receipt.update(status='failed', error=repr(error))
        raise
    finally:
        try:
            receipt['producerSourceAfter'] = clean_source(producer_root)
            receipt['controllerSourceAfter'] = clean_source(ROOT)
            receipt['sourcesUnchanged'] = receipt['producerSourceAfter'] == head and receipt['controllerSourceAfter'] == controller_head
        except Exception as error:
            receipt.update(sourcesUnchanged=False, sourceRecheckError=repr(error))
        receipt['nativeAfter'] = snapshot(native)
        receipt['nativeUnchanged'] = receipt['nativeAfter'] == before
        receipt['artifacts'] = {path.relative_to(output).as_posix(): sha(path)
                                for path in sorted(output.rglob('*')) if path.is_file()}
        (output / 'producer-sidecars.json').write_text(json.dumps(receipt, indent=2) + '\n')
        if not receipt['nativeUnchanged']:
            raise ValueError('The producer native payload changed during helper compilation')
        if not receipt['sourcesUnchanged']:
            raise ValueError('The producer or controller source changed during helper compilation')


def package_matches(path, manifest):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or 'manifest.json' not in names or json.loads(archive.read('manifest.json')) != manifest:
            return False
        prefix = 'runtimes/osx-arm64/native/'
        expected = {prefix + item['name']: item['sha256'] for item in manifest['files']}
        actual = {name for name in names if name.startswith(prefix) and not name.endswith('/')}
        return actual == expected.keys() and all(hashlib.sha256(archive.read(name)).hexdigest() == digest
                                                for name, digest in expected.items())


if __name__ == '__main__':
    main()
