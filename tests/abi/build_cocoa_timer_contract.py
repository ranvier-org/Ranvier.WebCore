"""Build a test-only genuine WTF timer helper against a coherent Mac producer."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'webkit-source', 'runtime', 'runtime-hashes', 'probe-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
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
        child = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=240)
        (output / (name + '.log')).write_text(child.stdout + child.stderr)
        result['steps'].append({'name': name, 'exit': child.returncode})
        assert child.returncode == 0, name + ': ' + (child.stdout + child.stderr)[-4000:]

    try:
        entries = json.loads((build / 'compile_commands.json').read_text())
        entry, = [entry for entry in entries if Path(entry['file']).name == 'RanvierWebCoreAbi.cpp']
        cwd = Path(entry['directory']).resolve(strict=True)
        command = list(entry.get('arguments') or shlex.split(entry['command']))
        assert not any(argument.startswith('@') for argument in command)
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
        result['inputsBefore'] = {name: sha(Path(name)) for name in sorted(inputs)}
        run('compile', command, cwd)
        sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True, timeout=30).strip()
        helper = output / 'libRanvierCocoaTimerContract.dylib'
        link = [command[0], '-dynamiclib', '-arch', 'arm64', '-isysroot', sdk, str(output / 'cocoa-timer-contract.o'),
                str(runtime / 'libJavaScriptCore.dylib'), str(runtime / 'libRanvierWebCoreHost.dylib'),
                '-framework', 'CoreFoundation', '-framework', 'Foundation', '-Wl,-rpath,' + str(runtime), '-o', str(helper)]
        run('link', link, cwd)
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
