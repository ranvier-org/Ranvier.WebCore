"""Verify first-caller ownership survives native Windows owner-thread termination."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


MODES = ('main-none', 'worker-none', 'main-sta', 'worker-sta', 'main-mta', 'worker-mta')


def runtime_hashes(directory):
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.rglob('*')) if path.is_file()}


def compiler_environment(work, selected):
    env = dict(os.environ)
    if selected or not shutil.which('cl'):
        if not selected:
            vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
            installation = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-requires',
                'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True, timeout=15).strip()
            if not installation:
                raise RuntimeError('No installed Visual Studio C++ compiler; pass --compiler-environment.')
            selected = Path(installation) / 'VC/Auxiliary/Build/vcvars64.bat'
        script = work / 'environment.cmd'
        script.write_text(f'@call "{selected}" >nul\n@if errorlevel 1 exit /b %errorlevel%\n@set PATH\n@set INCLUDE\n@set LIB\n', newline='\r\n')
        for line in subprocess.check_output(['cmd', '/d', '/c', str(script)], text=True, timeout=30).splitlines():
            if '=' in line and not line.startswith('='):
                key, value = line.split('=', 1)
                env[key.upper()] = value
    compiler = shutil.which('cl', path=env.get('PATH'))
    if not compiler:
        raise RuntimeError('Selected environment has no cl.exe.')
    return compiler, env


def run_control(exe, host, mode, env):
    try:
        completed = subprocess.run([str(exe), str(host), mode], env=env, capture_output=True, text=True, timeout=20)
        output = completed.stdout + completed.stderr
        required = ['AFTER_NATIVE_HOST_DESTROY', 'AFTER_COM_UNINITIALIZE',
                    'OWNER_FUNCTION_RETURNING', 'PROCESS_MAIN_RETURNING result=0']
        if mode.startswith('worker-'):
            required.append('OWNER_THREAD_JOINED')
        return {'mode': mode, 'exit': completed.returncode, 'hexExit': hex(completed.returncode & 0xffffffff),
                'output': output, 'passed': completed.returncode == 0 and all(marker in output for marker in required)}
    except subprocess.TimeoutExpired as error:
        def decode(value):
            return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
        return {'mode': mode, 'timeout': True, 'passed': False, 'output': decode(error.stdout) + decode(error.stderr)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-directory', type=Path, required=True)
    parser.add_argument('--compiler-environment', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('This control qualifies the Windows x64 native owner-thread contract.')
    native = args.native_directory.resolve()
    host = native / 'RanvierWebCoreHost.dll'
    if not host.is_file():
        parser.error(f'Missing {host}')
    if args.report and args.report.resolve().is_relative_to(native):
        parser.error('Report must be outside the immutable runtime directory.')
    before = runtime_hashes(native)
    source = Path(__file__).with_suffix('.cpp')
    report = {'nativeDirectory': str(native), 'before': before,
              'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'cases': []}
    try:
        with tempfile.TemporaryDirectory(prefix='ranvier-owner-thread-') as temporary:
            work = Path(temporary)
            compiler, env = compiler_environment(work, args.compiler_environment)
            exe = work / 'owner-thread-exit.exe'
            command = [compiler, '/nologo', '/std:c++20', '/EHsc', '/MD', '/W4', str(source),
                       f'/Fe:{exe}', f'/Fo:{work}/', '/link', 'ole32.lib']
            compiled = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True, timeout=90)
            report['compile'] = {'command': command, 'exit': compiled.returncode, 'output': compiled.stdout + compiled.stderr}
            if compiled.returncode:
                raise RuntimeError(report['compile']['output'])
            report['controlSha256'] = hashlib.sha256(exe.read_bytes()).hexdigest()
            for mode in MODES:
                row = run_control(exe, host, mode, env)
                report['cases'].append(row)
                print(mode, 'PASS' if row['passed'] else 'FAIL', row.get('hexExit', 'timeout'), flush=True)
            report['passed'] = all(row['passed'] for row in report['cases'])
    except Exception as error:
        report['error'] = str(error)
        report['passed'] = False
    finally:
        report['after'] = runtime_hashes(native)
        report['runtimeUnchanged'] = report['before'] == report['after']
        report['passed'] = report.get('passed', False) and report['runtimeUnchanged']
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2), encoding='utf8')
    if not report['passed']:
        print(json.dumps(report, indent=2))
        return 1
    print('PASS six native owner-thread exit modes; runtime unchanged')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
