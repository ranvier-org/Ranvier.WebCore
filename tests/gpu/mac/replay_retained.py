"""Link retained Host objects against retained engines and capture a private runtime trace."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys


def verify_files(root, expected):
    for name, digest in expected.items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Retained input mismatch: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sdl', type=Path, required=True)
    args = parser.parse_args()
    assert sys.platform == 'darwin' and platform.machine() == 'arm64'
    root = Path(__file__).resolve().parents[3]
    expected = json.loads((root / 'tests/fixtures/mac220-retained-inputs.json').read_text())
    output = args.output.resolve()
    assert not output.exists() and not root.is_relative_to(output) and not output.is_relative_to(root)
    output.mkdir(parents=True)
    record = {'scope': expected['scope'], 'status': 'STARTING', 'commands': []}
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    full = args.inputs / 'full'
    sdk = args.inputs / 'sdk'

    def save():
        (output / 'replay.json').write_text(json.dumps(record, indent=2))

    def run(name, argv, allow_failure=False):
        command = [str(x) for x in argv]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=120, text=True, errors='replace')
        log = output / (name + '.log')
        log.write_text(result.stdout)
        record['commands'].append({'name': name, 'argv': command, 'exit': result.returncode, 'logSha256': sha(log)})
        save()
        if not allow_failure and result.returncode:
            raise RuntimeError(name + ' failed; retained log: ' + str(log))
        return result.stdout

    try:
        verify_files(full, expected['fullFiles'])
        verify_files(sdk, expected['sdkFiles'])
        original = json.loads((full / 'ranvier-mac220/spike-evidence/receipt.json').read_text())
        objects = json.loads((sdk / 'receipt.json').read_text())
        assert original['sourceCommit'] == expected['fullSource'] and objects['sourceCommit'] == expected['sdkSource']
        assert objects['passed'] and len(objects['objects']) == 7
        assert (sdk / 'cmakeconfig.h').read_bytes() == (full / 'ranvier-mac220/build-mac-gpu-spike/cmakeconfig.h').read_bytes()
        assert run('sdk-version', ['xcrun', '--show-sdk-version']).strip() == (full / 'ranvier-mac220/spike-evidence/environment.log').read_text().strip()
        assert run('xcode-version', ['xcodebuild', '-version']).strip() == (full / 'ranvier-mac220/spike-evidence/xcode.log').read_text().strip()
        external = {name: digest for name, digest in objects['dependencyHashes'].items()
                    if not name.startswith('/Users/runner/work/_temp/')}
        for name, digest in external.items():
            assert Path(name).is_file() and sha(Path(name)) == digest, 'External SDK input changed: ' + name
        record['externalSdkHeadersVerified'] = len(external)
        record['inputsValidated'] = True
        record['originalProofExit'] = next(row['exit'] for row in original['steps'] if row['name'] == 'proof')
        native = output / 'native'
        native.mkdir()
        source = full / 'ranvier-mac220/build-mac-gpu-spike'
        libraries = {'libEGL.dylib': source / 'libEGL.dylib', 'libGLESv2.dylib': source / 'libGLESv2.dylib'}
        for name in ['WebCore', 'JavaScriptCore', 'WebGPU']:
            libraries['lib' + name + '.dylib'] = source / (name + '.framework/Versions/A/' + name)
        for name, path in libraries.items():
            staged = native / name
            shutil.copy2(path, staged)
            imported = run('imports-' + name, ['xcrun', 'otool', '-L', staged])
            command = ['xcrun', 'install_name_tool', '-id', '@rpath/' + name]
            for line in imported.splitlines()[1:]:
                dependency = line.strip().split(' (', 1)[0]
                match = re.search(r'(WebCore|JavaScriptCore|WebGPU)\.framework/(?:Versions/A/)?\1$', dependency)
                if match:
                    command += ['-change', dependency, '@rpath/lib' + match[1] + '.dylib']
            commands = run('loads-' + name, ['xcrun', 'otool', '-l', staged])
            for entry in re.findall(r'cmd LC_RPATH\n\s+cmdsize \d+\n\s+path (.+?) \(offset', commands):
                command += ['-delete_rpath', entry]
            run('flatten-' + name, [*command, staged])
            run('rpath-' + name, ['xcrun', 'install_name_tool', '-add_rpath', '@loader_path', staged])
            run('sign-' + name, ['codesign', '--force', '--sign', '-', staged])
        host = native / 'libRanvierWebCoreHost.dylib'
        retained_objects = [sdk / Path(row['path']).name for row in objects['objects']]
        run('strict-host-link', ['xcrun', 'clang++', '-dynamiclib', '-arch', 'arm64', '-mmacosx-version-min=26.0',
            '-Wl,-install_name,@rpath/libTestWebCore.dylib', '-Wl,-undefined,error', '-Wl,-rpath,@loader_path',
            '-o', host, *retained_objects, *[native / name for name in libraries], '-licucore',
            '-framework', 'AppKit', '-framework', 'Foundation', '-framework', 'CoreFoundation',
            '-framework', 'CoreGraphics', '-framework', 'ImageIO', '-framework', 'IOSurface', '-framework', 'Metal'])
        run('host-id', ['xcrun', 'install_name_tool', '-id', '@rpath/libRanvierWebCoreHost.dylib', host])
        run('host-sign', ['codesign', '--force', '--sign', '-', host])
        record['derivativeNative'] = {p.name: sha(p) for p in native.iterdir()}
        program = output / 'mac-gpu-spike'
        shutil.copy2(full / 'ranvier-mac220/spike-evidence/mac-gpu-spike', program)
        program.chmod(program.stat().st_mode | 0o111)
        record['fixtureSha256'] = sha(program)
        run('fixture-imports', ['xcrun', 'otool', '-L', program])
        run('fixture-rpaths', ['xcrun', 'otool', '-l', program])
        (output / 'proof').mkdir()
        environment = 'DYLD_LIBRARY_PATH=' + str(native) + ':' + str(args.sdl / 'lib')
        run('lldb', ['xcrun', 'lldb', '--batch', '-o', 'settings set target.disable-aslr false',
            '-o', 'settings set target.env-vars ' + environment,
            '-o', 'run --output ' + str(output / 'proof'),
            '-k', 'thread backtrace all', '-k', 'image list -o -f', '--', program], allow_failure=True)
        record['nativeUnchangedByDebugging'] = record['derivativeNative'] == {p.name: sha(p) for p in native.iterdir()}
        assert record['nativeUnchangedByDebugging']
        record['status'] = 'CAPTURED'
    except BaseException as error:
        record['status'] = 'FAIL'
        record['error'] = repr(error)
        raise
    finally:
        try:
            verify_files(full, expected['fullFiles'])
            verify_files(sdk, expected['sdkFiles'])
            record['retainedInputsUnchanged'] = True
        finally:
            save()


if __name__ == '__main__':
    main()
