"""Plan or execute one private osx-arm64 GPU spike; never dispatches CI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def run_step(name, command, producer, evidence, receipt, timeout=None):
    try:
        result = subprocess.run(command, cwd=producer, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired as error:
        partial = error.stdout or ''
        if isinstance(partial, bytes):
            partial = partial.decode('utf-8', errors='replace')
        (evidence / (name + '.log')).write_text(partial, encoding='utf-8')
        receipt['steps'].append({'name': name, 'command': command, 'exit': None, 'timedOut': True})
        raise RuntimeError(name + ' exceeded its ' + str(timeout) + ' second native-process limit') from error
    (evidence / (name + '.log')).write_text(result.stdout, encoding='utf-8')
    receipt['steps'].append({'name': name, 'command': command, 'exit': result.returncode})
    print(result.stdout, end='', flush=True)
    result.check_returncode()
    return result.stdout


def commands(rid, opt_in, work, jobs):
    if rid != 'osx-arm64':
        raise ValueError('the Mac spike accepts only osx-arm64')
    if not opt_in:
        raise ValueError('explicit --mac-gpu-spike opt-in is required')
    if not 1 <= jobs <= 4:
        raise ValueError('jobs must be between 1 and 4')
    common = ['--rid', rid, '--flavor', 'gpu', '--mac-gpu-spike',
              '--work', work.as_posix(), '--source', (work / 'src').as_posix(),
              '--build-dir', (work / 'build-mac-gpu-spike').as_posix(), '--jobs', str(jobs),
              '--strict', '--version', '0.0.0-project2-mac220.1']
    return [{'name': step, 'command': [sys.executable, str(ROOT / 'scripts/build.py'), step, *common]}
            for step in ['fetch', 'prepare', 'configure', 'build', 'package']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rid', default='osx-arm64')
    parser.add_argument('--mac-gpu-spike', action='store_true')
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--execute', action='store_true', help='run locally on macOS arm64; default prints commands')
    parser.add_argument('--texture-input', action='store_true', help='also compile/run the private native Metal IOSurface input fixture')
    args = parser.parse_args()
    work = args.work.expanduser().resolve()
    plan = commands(args.rid, args.mac_gpu_spike, work, args.jobs)
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        parser.error('--execute requires a macOS arm64 machine')
    if ROOT.is_relative_to(work) or work.is_relative_to(ROOT):
        parser.error('--work must be separate from the producer checkout')
    evidence = work / 'spike-evidence'
    evidence.mkdir(parents=True, exist_ok=False)
    receipt = {'label': 'unqualified macOS GPU spike', 'steps': [], 'passed': False,
               'system': platform.platform(), 'machine': platform.machine(), 'producer': str(ROOT)}

    def run(name, command):
        return run_step(name, command, ROOT, evidence, receipt,
                        timeout=180 if name in ('proof', 'unsupported-renderer') else None)

    try:
        receipt['sourceCommit'] = run('producer-commit', ['git', 'rev-parse', 'HEAD']).strip()
        receipt['sourceStatus'] = run('producer-status', ['git', 'status', '--porcelain'])
        if receipt['sourceStatus'].strip():
            raise RuntimeError('the private Mac experiment requires a clean immutable producer checkout')
        receipt['sourceTree'] = run('producer-tree', ['git', 'rev-parse', 'HEAD^{tree}']).strip()
        receipt['webkitPin'] = json.loads((ROOT / 'pins.json').read_text())['webkit']['commit']
        run('environment', ['xcrun', '--show-sdk-version'])
        run('xcode', ['xcodebuild', '-version'])
        for step in plan:
            run(step['name'], step['command'])
            if step['name'] == 'configure':
                configuration = work / 'build-mac-gpu-spike' / 'cmakeconfig.h'
                configured = configuration.read_text()
                for name in ('RANVIER_MAC_GPU_SPIKE', 'USE_TEXTURE_MAPPER', 'USE_GRAPHICS_LAYER_TEXTURE_MAPPER'):
                    if not re.search(r'^#define\s+' + name + r'\s+1\s*$', configured, re.M):
                        raise RuntimeError('actual configuration did not enable ' + name)
                receipt['cmakeconfigSHA256'] = hashlib.sha256(configuration.read_bytes()).hexdigest()
                build = work / 'build-mac-gpu-spike'
                run('egl-build', ['cmake', '--build', str(build), '--target', 'EGL', '--parallel', str(args.jobs)])
                symbols = run('egl-exports', ['xcrun', 'nm', '-gU', str(build / 'libEGL.dylib')])
                required = ('eglBindAPI', 'eglChooseConfig', 'eglCreateContext', 'eglCreatePbufferSurface',
                            'eglCreateWindowSurface', 'eglDestroyContext', 'eglDestroySurface',
                            'eglGetConfigAttrib', 'eglGetCurrentContext', 'eglGetCurrentDisplay',
                            'eglGetCurrentSurface', 'eglGetError', 'eglGetProcAddress', 'eglInitialize',
                            'eglMakeCurrent', 'eglQueryString', 'eglSwapBuffers', 'eglTerminate')
                exported = {line.split()[-1] for line in symbols.splitlines() if line.split()}
                missing = sorted(set('_' + name for name in required) - exported)
                if missing:
                    raise RuntimeError('EGL shared-library export preflight failed: ' + ', '.join(missing))
                receipt['eglExportPreflight'] = {'required': list(required), 'missing': missing,
                    'librarySHA256': hashlib.sha256((build / 'libEGL.dylib').read_bytes()).hexdigest()}
        stage = work / 'out/gpu/runtimes/osx-arm64/native'
        run('stage-manifest', [sys.executable, str(ROOT / 'scripts/smoke.py'), '--stage', str(work / 'out/gpu'),
                               '--build-dir', str(work / 'build-mac-gpu-spike'), '--expect-flavor', 'gpu', '--no-load'])
        run('exports', [sys.executable, str(Path(__file__).with_name('check_exports.py')), str(stage),
                        *(['--texture-input'] if args.texture_input else [])])
        sdl = shlex.split(run('sdl-flags', ['pkg-config', '--cflags', '--libs', 'sdl3']).strip())
        receipt['sdlVersion'] = run('sdl-version', ['pkg-config', '--modversion', 'sdl3']).strip()
        executable = evidence / 'mac-gpu-spike'
        run('proof-compile', ['xcrun', 'clang++', '-std=c++20', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                              '-mmacosx-version-min=26.0', '-I' + str(ROOT / 'host'),
                              str(Path(__file__).with_name('spike.mm')), '-o', str(executable),
                              '-L' + str(stage), '-lRanvierWebCoreHost', '-Wl,-rpath,' + str(stage),
                              '-framework', 'Metal', '-framework', 'IOSurface', '-framework', 'Foundation', *sdl])
        run('proof', [str(executable), '--output', str(evidence)])
        run('unsupported-renderer', [str(executable), '--reject-software'])
        if args.texture_input:
            input_executable = evidence / 'mac-texture-input'
            run('input-compile', ['xcrun', 'clang++', '-std=c++20', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                                  '-mmacosx-version-min=26.0', '-I' + str(ROOT / 'host'),
                                  str(Path(__file__).with_name('texture_input.mm')), '-o', str(input_executable),
                                  '-L' + str(stage), '-lRanvierWebCoreHost', '-Wl,-rpath,' + str(stage),
                                  '-framework', 'Metal', '-framework', 'IOSurface', '-framework', 'Foundation', *sdl])
            run_step('input-proof', [str(input_executable), '--output', str(evidence)], ROOT, evidence, receipt, timeout=180)
        receipt['files'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in stage.iterdir() if p.is_file()}
        receipt['passed'] = True
    finally:
        (evidence / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
