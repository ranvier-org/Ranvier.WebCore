"""Qualify an optional OS spelling provider and its native suggestion action."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiler-environment', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    consumer = Path(tempfile.mkdtemp(prefix='sdk-', dir=output)).resolve()
    root = Path(__file__).resolve().parents[2]
    record = {}
    try:
        environment = dict(os.environ)
        environment['OS'] = 'Windows_NT'
        environment['PROCESSOR_ARCHITECTURE'] = 'AMD64'
        setup = args.compiler_environment
        if setup or not shutil.which('cl'):
            if not setup:
                vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
                installation = subprocess.check_output([
                    str(vswhere), '-latest', '-products', '*', '-requires',
                    'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
                if not installation:
                    raise RuntimeError('Visual Studio C++ tools are required for the spelling consumer')
                setup = Path(installation) / 'VC/Auxiliary/Build/vcvars64.bat'
            script = consumer / 'compiler-environment.cmd'
            script.write_text(f'@call "{setup}" >nul\n@set PATH\n@set INCLUDE\n@set LIB\n', encoding='utf-8', newline='\r\n')
            for line in subprocess.check_output(['cmd', '/d', '/c', str(script)], text=True).splitlines():
                if '=' in line and not line.startswith('='):
                    key, value = line.split('=', 1)
                    environment[key.upper()] = value
        compiler = shutil.which('cl', path=environment.get('PATH'))
        if not compiler:
            raise RuntimeError('Selected compiler environment did not provide cl.exe')
        test = consumer / 'provider.exe'
        source = root / 'tests/spelling/windows_provider.cpp'
        command = [compiler, '/nologo', '/std:c++20', '/EHsc', '/W4', '/WX', '/MT', '/utf-8',
                   '/DWIN32_LEAN_AND_MEAN', '/DNOMINMAX', '/D_WIN32_WINNT=0x0A00',
                   str(source), f'/Fe:{test}', f'/Fo:{consumer}/', '/link', 'ole32.lib', 'uuid.lib']
        record['compileCommand'] = command
        record['sourceSha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        subprocess.run(command, cwd=consumer, env=environment, check=True, timeout=60)
        provider = subprocess.run([str(test), str(output / 'provider.json')], cwd=consumer, env=environment, timeout=60)
        record['providerExit'] = provider.returncode
        if provider.returncode == 77:
            record['availability'] = 'OS en-US spelling provider unavailable; replacement regression runs separately'
        else:
            provider.check_returncode()
            record['availability'] = 'available'
            command = [sys.executable, '-I', '-X', 'utf8', str(root / 'tests/abi/spelling_suggestion.py'),
                       '--native-directory', str(args.native_directory.resolve()), '--provider-result', str(output / 'provider.json'),
                       '--report', str(output / 'suggestion.json')]
            record['suggestionCommand'] = command
            result = subprocess.run(command, cwd=root, timeout=120)
            record['suggestionExit'] = result.returncode
            result.check_returncode()
    finally:
        target = output / 'receipt.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        temporary.replace(target)
        assert consumer.parent == output
        shutil.rmtree(consumer)


if __name__ == '__main__':
    main()
