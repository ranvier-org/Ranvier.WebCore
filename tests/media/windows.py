"""Build and qualify the optional application-side Windows media consumer."""
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
    parser.add_argument('--native-directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--compiler-environment',type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    consumer = Path(tempfile.mkdtemp(prefix='sdk-',dir=output)).resolve()
    sha = lambda p: hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
    inputs = [*sorted((root/'examples/NativeMedia').glob('*.h')),*sorted((root/'tests/media').glob('*.cpp')),
              root/'examples/NativeMedia/WindowsPlaybackBridge.cpp', root/'tests/media/bridge_lifetime.py',
              root/'tests/media/windows_composition.py',root/'tests/fixtures/native-media-colors-tone.mp4',root/'tests/fixtures/native-media-colors-tone.json']
    before = {str(p.relative_to(root)):sha(p) for p in inputs}
    native_before = {p.relative_to(args.native_directory).as_posix():sha(p) for p in args.native_directory.rglob('*') if p.is_file()}
    report = {'sourceBefore':before,'nativeBefore':native_before,'groups':[]}
    failures = []
    try:
        fixture = root/'tests/fixtures/native-media-colors-tone.mp4'
        manifest = json.loads(fixture.with_suffix('.json').read_text())
        assert sha(fixture) == manifest['sha256'], 'Original media fixture identity'
        environment = dict(os.environ)
        environment['OS'],environment['PROCESSOR_ARCHITECTURE'] = 'Windows_NT','AMD64'
        setup = args.compiler_environment
        if setup or not shutil.which('cl'):
            if not setup:
                locator = Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
                installation = subprocess.check_output([str(locator),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
                if not installation:
                    raise RuntimeError('Windows SDK and Visual Studio C++ tools are required for this optional consumer')
                setup = Path(installation)/'VC/Auxiliary/Build/vcvars64.bat'
            script = consumer/'compiler-environment.cmd'
            script.write_text(f'@call "{setup}" >nul\n@set PATH\n@set INCLUDE\n@set LIB\n',encoding='utf-8',newline='\r\n')
            for line in subprocess.check_output(['cmd','/d','/c',str(script)],text=True).splitlines():
                if '=' in line and not line.startswith('='):
                    key,value = line.split('=',1)
                    environment[key.upper()] = value
        compiler = shutil.which('cl',path=environment.get('PATH'))
        if not compiler:
            raise RuntimeError('Selected compiler environment did not provide cl.exe')
        libraries = ['ole32.lib','oleaut32.lib','uuid.lib','mfplat.lib','mf.lib','mfreadwrite.lib','mfuuid.lib','d3d11.lib','dxgi.lib']
        provider_absent = False
        for stem in ['windows_provider','windows_video','windows_audio','windows_controls','WindowsPlaybackProbe','WindowsPlaybackBridge']:
            if provider_absent:
                report['groups'].append({'name':stem,'availability':'not run: optional OS playback provider unavailable'})
                continue
            bridge = stem == 'WindowsPlaybackBridge'
            module = stem == 'WindowsPlaybackProbe' or bridge
            source = root/('examples/NativeMedia' if bridge else 'tests/media')/(stem+'.cpp')
            executable = consumer/(stem+('.dll' if module else '.exe'))
            command = [compiler,'/nologo','/std:c++20','/EHsc','/W4','/WX','/MT','/utf-8','/DWIN32_LEAN_AND_MEAN','/DNOMINMAX','/D_WIN32_WINNT=0x0A00',
                       *(['/LD'] if module else []),str(source),f'/Fe:{executable}',f'/Fo:{consumer}/',
                       '/link',*libraries,*(['runtimeobject.lib','windowsapp.lib','shell32.lib','user32.lib'] if stem=='windows_controls' or bridge else [])]
            group = {'name':stem,'compileCommand':command}
            with (output/(stem+'-compile.log')).open('wb') as log:
                result = subprocess.run(command,cwd=consumer,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=90)
            group['compileExit'] = result.returncode
            if result.returncode:
                failures.append(stem+' compile')
            else:
                group['executableSha256'] = sha(executable)
                if bridge:
                    command = [sys.executable,'-I','-B','-X','utf8',str(root/'tests/media/bridge_lifetime.py'),
                               '--bridge',str(executable),'--fixture',str(fixture),'--report',str(output/'bridge.json')]
                elif module:
                    command = [sys.executable,'-I','-B','-X','utf8',str(root/'tests/media/windows_composition.py'),
                               '--native-directory',str(args.native_directory.resolve()),'--helper',str(executable),'--fixture',str(fixture),
                               '--report',str(output/'composition.json')]
                else:
                    command = [str(executable),str(fixture)]
                group['runtimeCommand'] = command
                with (output/(stem+'-runtime.log')).open('wb') as log:
                    result = subprocess.run(command,cwd=consumer,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=120)
                group['runtimeExit'] = result.returncode
                if result.returncode == 77:
                    group['availability'] = 'explicit optional OS provider/endpoint unavailable'
                    if stem == 'windows_provider':
                        provider_absent = True
                elif result.returncode:
                    failures.append(stem+' runtime')
                print(stem,result.returncode,(output/(stem+'-runtime.log')).read_text(errors='replace')[-1800:],flush=True)
            report['groups'].append(group)
        report['failed'] = failures
        assert not failures, failures
    finally:
        report['sourceAfter'] = {str(p.relative_to(root)):sha(p) for p in inputs}
        report['nativeAfter'] = {p.relative_to(args.native_directory).as_posix():sha(p) for p in args.native_directory.rglob('*') if p.is_file()}
        report['inputsUnchanged'] = before == report['sourceAfter'] and native_before == report['nativeAfter']
        target = output/'receipt.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        temporary.replace(target)
        assert consumer.parent == output
        shutil.rmtree(consumer)
        assert report['inputsUnchanged']


if __name__ == '__main__':
    main()
