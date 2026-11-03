"""Compile the private Cocoa GPU Host without building engine objects."""
import argparse
import hashlib
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
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    assert sys.platform == 'darwin' and platform.machine() == 'arm64'
    assert platform.mac_ver()[0].split('.')[0] == '26'
    root = Path(__file__).resolve().parents[3]
    work = args.work.resolve()
    assert not root.is_relative_to(work) and not work.is_relative_to(root)
    assert not work.exists()
    output = work / 'host-preflight'
    output.mkdir(parents=True)
    source, build = work / 'src', work / 'build-mac-gpu-spike'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    receipt = {'scope': 'Private Cocoa GPU Host object/header qualification only; no engine compilation, link, compositor runtime or publication.',
               'platform': platform.platform(), 'commands': [], 'passed': False}

    def save():
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2))

    def run(name, argv, directory=root, timeout=600):
        row = {'name': name, 'argv': [str(x) for x in argv], 'cwd': str(directory)}
        receipt['commands'].append(row)
        save()
        log = output / (name + '.log')
        with log.open('wb') as stream:
            child = subprocess.Popen(row['argv'], cwd=directory, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            started = time.monotonic()
            row['pid'] = child.pid
            try:
                while child.poll() is None:
                    census = subprocess.check_output(['ps', '-axo', 'pgid=,rss='], text=True)
                    rss = sum(int(fields[1]) * 1024 for line in census.splitlines()
                              if len(fields := line.split()) == 2 and int(fields[0]) == child.pid)
                    assert rss <= 8 * 1024 ** 3, 'Owned command exceeded 8GiB RSS'
                    assert time.monotonic() - started <= timeout, 'Bounded command timed out'
                    time.sleep(.5)
                row['exit'] = child.returncode
            finally:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=5)
                row['logSha256'] = sha(log)
                row['elapsedSeconds'] = time.monotonic() - started
                save()
        assert row['exit'] == 0, name + ' failed; log retained'
        return log.read_text(errors='replace')

    try:
        receipt['sourceCommit'] = run('source-commit', ['git', 'rev-parse', 'HEAD']).strip()
        assert not run('source-status', ['git', 'status', '--porcelain']).strip()
        common = ['--rid', 'osx-arm64', '--flavor', 'gpu', '--mac-gpu-spike', '--strict', '--jobs', '1',
                  '--work', str(work), '--source', str(source), '--build-dir', str(build)]
        for step in ['fetch', 'prepare', 'configure']:
            run(step, [sys.executable, '-I', root / 'scripts/build.py', step, *common])
        run('compdb', ['cmake', '-S', source, '-B', build, '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'])
        configured = (build / 'cmakeconfig.h').read_text()
        for key in ['RANVIER_MAC_GPU_SPIKE', 'USE_TEXTURE_MAPPER', 'USE_GRAPHICS_LAYER_TEXTURE_MAPPER']:
            assert re.search(r'^#define\s+' + key + r'\s+1\s*$', configured, re.M), key
        targets = ['ANGLEHeaders', 'GLSLANGHeaders', 'ANGLE-webgl-headers', 'bmalloc_CopyHeaders', 'bmalloc_CopyPrivateHeaders', 'WTF_CopyHeaders', 'WTF_CopyPreferences',
                   'JavaScriptCore_CopyHeaders', 'JavaScriptCore_CopyPrivateHeaders', 'PAL_CopyHeaders',
                   'WebCore_CopyPrivateHeaders', 'WebCoreGeneratedSources']
        plan = run('header-plan', ['ninja', '-n', '-v', *targets], build)
        assert not re.search(r'(^|\s)(?:\S*/)?(?:clang\+\+|clang|swiftc)(?:\s|$)', plan), 'Header plan includes compiler work'
        run('headers', ['ninja', '-j1', *targets], build)
        entries = json.loads((build / 'compile_commands.json').read_text())
        hosts = [row for row in entries if 'CMakeFiles/RanvierWebCoreHost.dir/' in row.get('command', '')]
        assert len(hosts) == len({row['file'] for row in hosts}) == 7
        assert {Path(row['file']).name for row in hosts} == {'RanvierWebCoreAbi.cpp', 'RanvierWebCoreDom.cpp',
            'RanvierWebCoreUia.cpp', 'RanvierWebCoreD3D11.cpp', 'RanvierWebCoreEGL.cpp', 'RanvierImageEncoding.cpp', 'RanvierMacGpuSpike.mm'}
        receipt['objects'] = []
        dependencies = set()
        for number, entry in enumerate(hosts):
            argv = shlex.split(entry['command'])
            assert not any(x.startswith('@') for x in argv), 'Unproven compile response-file shape'
            assert '-DRANVIER_COMPOSITING=1' in argv
            assert '-I' + str(source / 'Source/WebCore/platform/graphics') in argv
            obj = output / (Path(entry['file']).name + '.o')
            dep = obj.with_suffix('.d')
            argv[argv.index('-o') + 1] = str(obj)
            if '-MF' in argv:
                argv[argv.index('-MF') + 1] = str(dep)
            else:
                argv += ['-MD', '-MF', str(dep)]
            run('host-' + str(number), argv, Path(entry['directory']))
            undefined = run('undefined-' + str(number), ['xcrun', 'nm', '-u', str(obj)])
            assert not re.search(r'(?m)^\s*(?:U\s+)?_gl[A-Z]\w*\s*$', undefined), 'Host still references system OpenGL entry points'
            if Path(entry['file']).name == 'RanvierWebCoreAbi.cpp':
                assert '_GL_BindFramebuffer' in undefined, 'Host did not bind ANGLE framebuffer entry point'
            if Path(entry['file']).name == 'RanvierMacGpuSpike.mm':
                assert '_GL_GetString' in undefined, 'Spike did not bind ANGLE renderer query'
            receipt['objects'].append({'source': entry['file'], 'path': str(obj), 'sha256': sha(obj)})
            text = dep.read_text().replace('\\\n', ' ')
            dependencies.update((Path(entry['directory']) / name).resolve() for name in shlex.split(text.split(':', 1)[1]))
        receipt['dependencyHashes'] = {str(path): sha(path) for path in sorted(dependencies)}
        receipt['passed'] = True
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        for name in ['cmakeconfig.h', 'CMakeCache.txt', 'compile_commands.json', 'availability-overlay.yaml']:
            if (build / name).exists():
                shutil.copy2(build / name, output / name)
        save()


if __name__ == '__main__':
    main()
