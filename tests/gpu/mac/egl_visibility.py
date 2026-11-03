"""Check actual ANGLE EGL-wrapper exports under Cocoa visibility flags."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        parser.error('requires actual macOS arm64 SDK')
    assert platform.mac_ver()[0].split('.')[0] == '26', platform.mac_ver()
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    angle = source / 'Source/ThirdParty/ANGLE'
    unit = angle / 'src/libEGL/libEGL_autogen.cpp'
    assert '-fvisibility=hidden' in (source / 'Source/cmake/OptionsCocoa.cmake').read_text()
    assert 'EGLAPI=' in (angle / 'CMakeLists.txt').read_text()
    receipt = {'scope': 'Actual Cocoa SDK compilation of pinned ANGLE export wrapper only; no rebuilt WebCore or GPU runtime qualification.',
               'platform': platform.platform(), 'sourceCommit': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
               'cases': [], 'sourceSha256': hashlib.sha256(unit.read_bytes()).hexdigest()}
    assert receipt['sourceCommit'] == 'b95c91b1c0ee43cc86d25ff7af73038f67a88e04'
    common = ['xcrun', 'clang++', '-std=c++20', '-arch', 'arm64', '-fPIC', '-DEGLAPI=',
              '-DGL_GLES_PROTOTYPES=0', '-DEGL_EGL_PROTOTYPES=0', '-I' + str(angle / 'include'),
              '-I' + str(angle / 'src'), '-I' + str(angle / 'src/common/base'),
              '-fvisibility=hidden', '-fvisibility-inlines-hidden']
    try:
        for name, extra in [('hidden', []), ('default', ['-fvisibility=default'])]:
            obj = output / (name + '.o')
            command = common + extra + ['-c', str(unit), '-o', str(obj)]
            child = subprocess.run(command, capture_output=True, text=True, timeout=180)
            (output / (name + '.log')).write_text(child.stdout + child.stderr)
            case = {'name': name, 'command': command, 'exit': child.returncode}
            receipt['cases'].append(case)
            assert child.returncode == 0, child.stderr
            symbols = subprocess.check_output(['xcrun', 'nm', '-m', str(obj)], text=True)
            (output / (name + '-symbols.txt')).write_text(symbols)
            exports = [line for line in symbols.splitlines() if line.split() and line.split()[-1].startswith('_egl') and '(undefined)' not in line]
            assert len(exports) >= 100, exports
            assert all(('private external' in line) == (name == 'hidden') for line in exports), exports
            assert all('external' in line for line in exports), exports
            case.update(eglSymbols=exports, objectSha256=hashlib.sha256(obj.read_bytes()).hexdigest())
        assert [line.split()[-1] for line in receipt['cases'][0]['eglSymbols']] == [line.split()[-1] for line in receipt['cases'][1]['eglSymbols']]
        receipt['passed'] = True
    finally:
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
