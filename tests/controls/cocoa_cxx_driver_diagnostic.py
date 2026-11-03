"""Compare the old resolved C-driver invocation with the preserved C++ driver; no engine inputs."""
import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64' or platform.mac_ver()[0].split('.')[0] != '26':
        raise ValueError('Require actual macOS26 ARM64')
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT):
        raise ValueError('Require a fresh owned output outside the source')
    output.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location('sidecars', ROOT / 'tests/controls/build_cocoa_sidecars.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    head = builder.clean_source(ROOT)
    value = subprocess.check_output(['xcrun', '--find', 'clang++'], text=True).strip()
    invocation, binary, binary_sha = builder.cxx_compiler(value)
    sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
    sdk_version = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-version'], text=True).strip()
    if int(sdk_version.split('.')[0]) < 26 or binary.name != 'clang' or invocation == binary:
        raise ValueError('This exact driver-alias negative control is unavailable on the actual SDK')
    source = Path(__file__).with_name('cocoa_cxx_driver_probe.mm')
    receipt = dict(source=head, platform=platform.platform(), sdk=sdk, sdkVersion=sdk_version,
                   compilerInvocation=str(invocation), compilerResolvedPath=str(binary), compilerSha256=binary_sha,
                   probeSha256=builder.sha(source), helperSourceSha256=builder.sha(ROOT / 'tests/controls/build_cocoa_sidecars.py'),
                   commands=[], result='FAIL', engineBuild=False, nativePackageLoaded=False)

    def run(name, command):
        row = dict(name=name, argv=[str(value) for value in command])
        receipt['commands'].append(row)
        with (output / (name + '.log')).open('wb') as stream:
            process = subprocess.Popen(row['argv'], stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            row['pid'] = process.pid
            try:
                row['exit'] = process.wait(timeout=60)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
                row.update(groupKillRequested=True, directChildReaped=True)
        row['logSha256'] = builder.sha(output / (name + '.log'))
        return row['exit']

    try:
        common = ['-std=c++20', '-fobjc-arc', '-arch', 'arm64', '-isysroot', sdk, '-mmacosx-version-min=26.0',
                  '-dynamiclib', '-framework', 'AppKit', '-framework', 'Foundation', '-Wl,-undefined,error', source]
        old = run('old-resolved-clang', [binary, *common, '-o', output / 'old.dylib'])
        if old == 0 or 'gxx_personality' not in (output / 'old-resolved-clang.log').read_text(errors='replace'):
            raise ValueError('The actual old driver did not reproduce the strict C++ personality link failure')
        library = output / 'new.dylib'
        if run('new-preserved-clang++', [invocation, *common, '-o', library]) != 0:
            raise ValueError('The preserved C++ driver failed the same strict link')
        if run('sign', ['codesign', '--force', '--sign', '-', library]) or run('verify', ['codesign', '--verify', '--strict', library]):
            raise ValueError('Test helper signature failed')
        helper = ctypes.CDLL(str(library))
        helper.ranvier_cxx_driver_probe.restype = ctypes.c_int
        if helper.ranvier_cxx_driver_probe() != 0:
            raise ValueError('Actual Objective-C++ exception/ARC control failed')
        receipt.update(result='PASS', oldStrictLinkFailed=True, newStrictLinkPassed=True, actualProbe=0,
                       helperSha256=builder.sha(library))
    finally:
        receipt['sourceUnchanged'] = builder.clean_source(ROOT) == head
        receipt['compilerUnchanged'] = builder.sha(binary) == binary_sha
        receipt['probeUnchanged'] = builder.sha(source) == receipt['probeSha256']
        (output / 'driver-diagnostic.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        if not all(receipt[key] for key in ['sourceUnchanged', 'compilerUnchanged', 'probeUnchanged']):
            raise ValueError('Diagnostic inputs changed')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
