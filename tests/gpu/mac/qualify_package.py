"""Exercise public IOSurface output and native texture input from an extracted GPU package."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def hashes(directory):
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.rglob('*')) if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-directory', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        parser.error('the IOSurface package gate requires macOS arm64')
    native, output = args.native_directory.resolve(), args.output.resolve()
    if not native.is_dir() or output.is_relative_to(native) or native.is_relative_to(output):
        parser.error('native and output must be separate directories')
    output.mkdir(parents=True, exist_ok=False)
    before = hashes(native)
    receipt = {'scope': 'Extracted package public IOSurface output/input qualification',
               'nativeBefore': before, 'steps': [], 'passed': False}
    environment = dict(os.environ)

    def run(name, command, timeout=180, expected_failure=None):
        log = output / (name + '.log')
        row = {'name': name, 'command': [str(value) for value in command]}
        receipt['steps'].append(row)
        with log.open('wb') as stream:
            child = subprocess.Popen(row['command'], cwd=ROOT, env=environment,
                                     stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            row['pid'] = child.pid
            try:
                row['exit'] = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                row['timedOut'] = True
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                raise
        row['logSha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
        text = log.read_text(errors='replace')
        if expected_failure is not None:
            row['expectedFailure'] = expected_failure
            if row['exit'] != 1 or expected_failure not in text:
                raise RuntimeError('The explicit base-repaint negative control was not rejected')
        elif row['exit']:
            raise subprocess.CalledProcessError(row['exit'], row['command'])
        return text

    try:
        sdk = output / 'presenter-sdk'
        run('presenter-sdk', [sys.executable, '-I', Path(__file__).with_name('prepare_sdk.py'),
                              '--directory', sdk], timeout=300)
        environment['PKG_CONFIG_PATH'] = str(sdk / 'lib/pkgconfig')
        environment['DYLD_LIBRARY_PATH'] = os.pathsep.join([str(native), str(sdk / 'lib')])
        flags = shlex.split(run('presenter-flags', ['pkg-config', '--cflags', '--libs', 'sdl3']).strip())
        for name in ('spike', 'texture_input'):
            binary = output / name
            run('compile-' + name, ['xcrun', 'clang++', '-std=c++20', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                '-DRANVIER_MAC_PUBLIC_TRANSPORT=1', '-mmacosx-version-min=26.0', '-I' + str(ROOT / 'host'),
                Path(__file__).with_name(name + '.mm'), '-o', binary,
                '-L' + str(native), '-lRanvierWebCoreHost', '-Wl,-rpath,' + str(native),
                '-framework', 'Metal', '-framework', 'IOSurface', '-framework', 'Foundation', *flags])
            run('public-' + name, [binary, '--output', output])
        run('reject-software', [output / 'spike', '--reject-software'])
        run('reject-steady-base-repaint', [output / 'spike', '--force-steady-repaint'],
            expected_failure='MAC_GPU_SPIKE FAIL transform and opacity animation reuse base backing')
        receipt['nativeAfter'] = hashes(native)
        if receipt['nativeAfter'] != before:
            raise RuntimeError('The extracted native payload changed')
        receipt['passed'] = True
    finally:
        receipt['nativeAfter'] = hashes(native)
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps({'passed': True, 'receipt': str(output / 'receipt.json')}))


if __name__ == '__main__':
    main()
