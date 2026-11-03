"""Build a test-only genuine WTF timer helper against a coherent Mac producer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import shlex
import subprocess
import sys
import zipfile


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'webkit-source', 'runtime', 'runtime-hashes', 'probe-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--public-sidecar', action='store_true')
    parser.add_argument('--link-webcore', action='store_true')
    args = parser.parse_args()
    assert sys.platform == 'darwin' and platform.machine() == 'arm64'
    assert platform.mac_ver()[0].split('.')[0] == '26'
    build, source, runtime = (path.resolve(strict=True) for path in (args.build, args.webkit_source, args.runtime))
    output = args.output.resolve()
    output.mkdir(exist_ok=False)
    expected = json.loads(args.runtime_hashes.read_text())
    assert {'libJavaScriptCore.dylib', 'libRanvierWebCoreHost.dylib'} <= expected.keys()
    assert all(Path(name).name == name and name.endswith('.dylib') for name in expected)
    before = {path.name: sha(path) for path in runtime.glob('*.dylib')}
    assert before == expected
    result = {'scope': 'Test-only real WTF timers linked to the coherent producer Host/JSC. No engine methods overridden; all dispatch uses public rv_run_loop_cycle.',
              'runtimeBefore': before, 'commands': [], 'steps': [], 'probeSha256': sha(args.probe_source)}

    def run(name, command, cwd):
        result['commands'].append(command)
        owns_group = os.environ.get('RANVIER_COCOA_OWNED_GROUP') != '1'
        with (output / (name + '.log')).open('wb') as stream:
            child = subprocess.Popen(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, start_new_session=owns_group)
            try:
                code = child.wait(timeout=240)
            finally:
                if owns_group:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif child.poll() is None:
                    child.kill()
                child.wait(timeout=10)
        result['steps'].append({'name': name, 'exit': code})
        assert code == 0, name + ': ' + (output / (name + '.log')).read_text(errors='replace')[-4000:]

    try:
        entries = json.loads((build / 'compile_commands.json').read_text())
        entry, = [entry for entry in entries if Path(entry['file']).name == 'RanvierWebCoreAbi.cpp']
        cwd = Path(entry['directory']).resolve(strict=True)
        command = list(entry.get('arguments') or shlex.split(entry['command']))
        assert not any(argument.startswith('@') for argument in command)
        if args.public_sidecar:
            assert not any(argument.startswith(('-save-temps', '-fprofile', '-fmodules', '-MJ',
                                                '-serialize-diagnostics', '-fdiagnostics-serialize')) for argument in command), 'Unqualified implicit compiler output/cache option'
        result['producerCommand'] = command[:]
        source_count = output_count = 0
        for index, argument in enumerate(command):
            if argument == '-o':
                command[index + 1] = str(output / 'cocoa-timer-contract.o')
                output_count += 1
            elif argument == '-MF':
                command[index + 1] = str(output / 'cocoa-timer-contract.d')
            elif not argument.startswith('-') and (cwd / argument).resolve() == (cwd / entry['file']).resolve():
                command[index] = str(args.probe_source.resolve())
                source_count += 1
        assert source_count == output_count == 1
        command.extend(['-I' + str(source / 'Source/WTF'), '-I' + str(source / 'Source/bmalloc'), '-I' + str(source / 'Source/WebCore/PAL')])
        dependency = command[:] + ['-M', '-MF', str(output / 'inputs.d'), '-MT', 'probe']
        run('dependencies', dependency, cwd)
        text = (output / 'inputs.d').read_text().replace('\\\n', ' ')
        inputs = {str(args.runtime_hashes.resolve()), str(build / 'compile_commands.json'), str(Path(command[0]).resolve(strict=True))}
        for word in re.split(r'(?<!\\)\s+', text.split(':', 1)[1].strip()):
            path = Path(word.replace('\\ ', ' '))
            if not path.is_absolute():
                path = cwd / path
            inputs.add(str(path.resolve(strict=True)))
        inputs.update(str(runtime / name) for name in expected)
        if args.public_sidecar:
            for argument in command:
                value = argument.split('=', 1)[-1]
                for prefix in ['-iframework', '-isystem', '-I', '-F']:
                    if value.startswith(prefix) and len(value) > len(prefix):
                        value = value[len(prefix):]
                        break
                candidate = Path(value)
                if not candidate.is_absolute():
                    candidate = cwd / candidate
                if candidate.is_file():
                    inputs.add(str(candidate.resolve()))
        result['inputsBefore'] = {name: sha(Path(name)) for name in sorted(inputs)}
        run('compile', command, cwd)
        sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True, timeout=30).strip()
        helper = output / ('libRanvierCocoaPageControls.dylib' if args.link_webcore else 'libRanvierCocoaTimerContract.dylib')
        link = [command[0], '-dynamiclib', '-arch', 'arm64', '-isysroot', sdk, str(output / 'cocoa-timer-contract.o'),
                str(runtime / 'libJavaScriptCore.dylib'), str(runtime / 'libRanvierWebCoreHost.dylib'),
                '-framework', 'CoreFoundation', '-framework', 'Foundation', '-Wl,-rpath,' + str(runtime), '-o', str(helper)]
        if args.link_webcore:
            assert args.public_sidecar and 'libWebCore.dylib' in expected
            link.append(str(runtime / 'libWebCore.dylib'))
        if args.public_sidecar:
            link.extend(['-Wl,-undefined,error', '-Wl,-install_name,@rpath/libTestWebCore.dylib'])
        run('link', link, cwd)
        if args.public_sidecar:
            run('final-install-name', ['install_name_tool', '-id', '@rpath/' + helper.name, str(helper)], cwd)
            run('sign-helper', ['codesign', '--force', '--sign', '-', str(helper)], cwd)
            run('verify-helper-signature', ['codesign', '--verify', '--strict', str(helper)], cwd)
            run('helper-dependencies', ['otool', '-L', str(helper)], cwd)
            capsule = output / 'consumed-inputs.zip'
            with zipfile.ZipFile(capsule, 'x', zipfile.ZIP_DEFLATED) as archive:
                for name in sorted(inputs):
                    path = Path(name)
                    if path.resolve().is_relative_to(runtime) or path.resolve() == Path(command[0]).resolve():
                        continue
                    data = path.read_bytes()
                    assert hashlib.sha256(data).hexdigest() == result['inputsBefore'][name], 'Compiler input changed before capture'
                    archive.writestr('inputs/' + str(path).lstrip('/'), data)
            result['consumedInputsArchiveSha256'] = sha(capsule)
            result['compilerSha256'] = sha(Path(command[0]).resolve())
            result['compileCommandsSha256'] = sha(build / 'compile_commands.json')
            result['producerConfigurationSha256'] = sha(build / 'cmakeconfig.h')
            result['hostReplaced'] = result['headerReconstruction'] = result['engineCompilation'] = False
        result.update(status='compiled', helperPath=str(helper), helperSha256=sha(helper), sdk=sdk)
    except Exception as error:
        result.update(status='failed', error=repr(error))
        raise
    finally:
        if 'inputsBefore' in result:
            result['inputsAfter'] = {name: sha(Path(name)) for name in result['inputsBefore']}
            result['inputsUnchanged'] = result['inputsBefore'] == result['inputsAfter']
        result['runtimeAfter'] = {path.name: sha(path) for path in runtime.glob('*.dylib')}
        result['runtimeUnchanged'] = result['runtimeAfter'] == before
        (output / 'build-receipt.json').write_text(json.dumps(result, indent=2))
        assert result.get('inputsUnchanged', True) and result['runtimeUnchanged']


if __name__ == '__main__':
    main()
