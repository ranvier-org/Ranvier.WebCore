"""Build the optional application DLL with the installed Windows SDK and MSVC."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def build(output):
    if os.name != 'nt':
        raise RuntimeError('The optional Media Foundation adapter requires Windows')
    source = Path(__file__).resolve().parent
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='media-sdk-', dir=output))
    inputs = ['WindowsPlayback.h', 'WindowsMediaControls.h', 'WindowsPlaybackBridge.h', 'WindowsPlaybackBridge.cpp']
    hashes = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in inputs}
    environment = dict(os.environ)
    environment['OS'], environment['PROCESSOR_ARCHITECTURE'] = 'Windows_NT', 'AMD64'
    try:
        if not shutil.which('cl'):
            locator = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
            installation = subprocess.check_output([str(locator), '-latest', '-products', '*', '-requires',
                'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
            if not installation:
                raise RuntimeError('Install Visual Studio C++ tools and the Windows SDK to build this optional adapter')
            setup = Path(installation) / 'VC/Auxiliary/Build/vcvars64.bat'
            script = work / 'environment.cmd'
            script.write_text(f'@call "{setup}" >nul\n@set PATH\n@set INCLUDE\n@set LIB\n', encoding='utf-8', newline='\r\n')
            for line in subprocess.check_output(['cmd', '/d', '/c', str(script)], text=True).splitlines():
                if '=' in line and not line.startswith('='):
                    key, value = line.split('=', 1)
                    environment[key.upper()] = value
        compiler = shutil.which('cl', path=environment.get('PATH'))
        if not compiler:
            raise RuntimeError('Selected compiler environment did not provide cl.exe')
        library = output / 'RanvierNativeMedia.dll'
        command = [compiler, '/nologo', '/std:c++20', '/EHsc', '/W4', '/WX', '/MT', '/utf-8', '/LD',
                   '/DWIN32_LEAN_AND_MEAN', '/DNOMINMAX', '/D_WIN32_WINNT=0x0A00',
                   str(source / 'WindowsPlaybackBridge.cpp'), f'/Fo:{work}/', f'/Fe:{library}',
                   '/link', f'/IMPLIB:{work}/RanvierNativeMedia.lib', 'ole32.lib', 'oleaut32.lib', 'uuid.lib',
                   'mfplat.lib', 'mf.lib', 'mfreadwrite.lib', 'mfuuid.lib', 'd3d11.lib', 'dxgi.lib',
                   'runtimeobject.lib', 'windowsapp.lib', 'shell32.lib', 'user32.lib']
        with (output / 'compile.log').open('wb') as stream:
            result = subprocess.run(command, cwd=work, env=environment, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
        record = {'argv': command, 'compiler': compiler, 'inputs': hashes, 'compileExit': result.returncode,
                  'provider': 'Optional app-owned Media Foundation/MediaEngine/SMTC, Windows SDK only',
                  'rendererInputs': 'none', 'sourceUnchanged': hashes == {
                      name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in inputs}}
        if result.returncode == 0:
            record['dllSha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
        temporary = output / 'build.tmp'
        temporary.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        temporary.replace(output / 'build.json')
        assert record['sourceUnchanged']
        if result.returncode:
            raise RuntimeError((output / 'compile.log').read_text(encoding='utf-8', errors='replace'))
        print(json.dumps(record))
    finally:
        assert work.parent == output
        shutil.rmtree(work)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
