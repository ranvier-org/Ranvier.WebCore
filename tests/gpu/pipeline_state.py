"""Compile and run the platform-independent transport ledger tests."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
out = root / 'artifacts/gpu-pipeline-state'
out.mkdir(parents=True, exist_ok=True)
source = root / 'tests/gpu/FramePipelineStateTests.cpp'
env = dict(os.environ)
if sys.platform == 'win32':
    vswhere = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    vcvars = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-requires',
        'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-find', 'VC/Auxiliary/Build/vcvars64.bat'], text=True).strip()
    bootstrap = {k: v for k, v in env.items() if k.upper() not in ('PATH', 'INCLUDE', 'LIB', 'LIBPATH')}
    bootstrap['PATH'] = os.environ['SystemRoot'] + '/System32;' + os.environ['SystemRoot']
    dump = subprocess.check_output(f'cmd.exe /d /s /c ""{vcvars}" >nul && set"', env=bootstrap, text=True)
    env = dict(line.split('=', 1) for line in dump.splitlines() if '=' in line)
    compiler = shutil.which('cl.exe', path=next(v for k, v in env.items() if k.upper() == 'PATH'))
    exe = out / 'FramePipelineStateTests.exe'
    command = [compiler, '/nologo', '/std:c++20', '/EHsc', str(source), '/Fe:' + str(exe), '/Fo:' + str(out) + '/']
else:
    exe = out / 'FramePipelineStateTests'
    command = [env.get('CXX', 'c++'), '-std=c++20', str(source), '-o', str(exe)]
subprocess.run(command, cwd=out, env=env, check=True)
subprocess.run([str(exe)], cwd=out, env=env, check=True)
print('GPU_PIPELINE_STATE=PASS')
if '--helper' in sys.argv and sys.platform == 'win32':
    library = out / 'D3DFrameReadback.dll'
    subprocess.run([compiler, '/nologo', '/std:c++20', '/EHsc', '/W4', '/WX', '/LD', '/MT',
        str(root / 'tests/gpu/D3DTextureInputTests.cpp'), '/Fe:' + str(library), '/Fo:' + str(out) + '/',
        '/link', 'd3d11.lib', 'dxgi.lib', 'd3d12.lib'], cwd=out, env=env, check=True)
    print('GPU_PIPELINE_HELPER=' + str(library))
