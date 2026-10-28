"""Isolated shared-texture feasibility proof using installed SDL and a read-only GPU stage."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--run-only', action='store_true')
parser.add_argument('--native', type=Path, default=Path('C:/wk/out/gpu/runtimes/win-x64/native'))
parser.add_argument('--build', type=Path, default=Path('C:/wk/build-win-gpu'))
parser.add_argument('--sdl', type=Path, default=Path('C:/Users/shaya/.nuget/packages/ppy.sdl3-cs/2026.1002.1/runtimes/win-x64/native/SDL3.dll'))
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
out = root / 'artifacts/gpu-spike'
out.mkdir(parents=True, exist_ok=True)
exe = out / 'SharedTextureSpike.exe'
if args.run_only:
    subprocess.run([str(exe)], cwd=out, check=True, timeout=30)
else:
    for name in ['libEGL.dll', 'libGLESv2.dll', 'zlib1.dll']:
        shutil.copy2(args.native / name, out / name)
    shutil.copy2(args.sdl, out / 'SDL3.dll')
    env = dict(os.environ)
    vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    installation = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
    script = out / 'compiler-environment.cmd'
    script.write_text(f'@call "{installation}/VC/Auxiliary/Build/vcvars64.bat" >nul\n@set PATH\n@set INCLUDE\n@set LIB\n', newline='\r\n')
    for line in subprocess.check_output(['cmd', '/d', '/c', str(script)], text=True).splitlines():
        if '=' in line and not line.startswith('='):
            key, value = line.split('=', 1)
            env[key.upper()] = value
    compiler = shutil.which('cl', path=env['PATH'])
    subprocess.run([compiler, '/nologo', '/std:c++20', '/EHsc', '/W4', f'/I{args.build}/ANGLE/Headers', str(root / 'tests/gpu/SharedTextureSpike.cpp'), f'/Fe:{exe}', f'/Fo:{out}/', '/link', str(args.build / 'lib/libEGL.lib'), str(args.build / 'lib/libGLESv2.lib'), 'd3d11.lib', 'dxgi.lib', 'user32.lib'], cwd=out, env=env, check=True)
