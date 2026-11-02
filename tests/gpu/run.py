"""Build/run actual WebCore-to-SDL D3D11 presentation and lifetime acceptance on Windows."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--native', type=Path, required=True, help='GPU runtime directory containing native DLLs and WebKit.resources.')
parser.add_argument('--sdl', type=Path, required=True, help='SDL3.dll from the application dependency.')
parser.add_argument('--runtime-overlay', type=Path, help='Private updated DLLs to stage over the read-only runtime.')
parser.add_argument('--build-only', action='store_true')
parser.add_argument('--run-only', action='store_true')
parser.add_argument('--compiler-environment', type=Path)
parser.add_argument('--teardown', choices=['explicit', 'host', 'renderer', 'window', 'all'], default='all')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
out = root / 'artifacts/gpu-acceptance'
out.mkdir(parents=True, exist_ok=True)
for source in args.native.resolve().iterdir():
    if source.is_dir():
        shutil.copytree(source, out / source.name, dirs_exist_ok=True)
    elif source.suffix.lower() == '.dll':
        shutil.copy2(source, out / source.name)
shutil.copy2(args.sdl.resolve(), out / 'SDL3.dll')
if args.runtime_overlay:
    for source in args.runtime_overlay.resolve().glob('*.dll'):
        shutil.copy2(source, out / source.name)
exe = out / 'NativeFrameAcceptance.exe'
env = dict(os.environ)
if not args.run_only:
    if args.compiler_environment or not shutil.which('cl'):
        compiler_environment = args.compiler_environment
        if not compiler_environment:
            vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
            installation = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
            if not installation:
                parser.error('No installed Visual Studio C++ compiler found; pass --compiler-environment.')
            compiler_environment = Path(installation) / 'VC/Auxiliary/Build/vcvars64.bat'
        script = out / 'compiler-environment.cmd'
        script.write_text(f'@call "{compiler_environment}" >nul\n@set PATH\n@set INCLUDE\n@set LIB\n', newline='\r\n')
        for line in subprocess.check_output(['cmd', '/d', '/c', str(script)], text=True).splitlines():
            if '=' in line and not line.startswith('='):
                key, value = line.split('=', 1)
                env[key.upper()] = value
    compiler = shutil.which('cl', path=env.get('PATH'))
    if not compiler:
        parser.error('Selected compiler environment did not provide cl.exe.')
    subprocess.run([compiler, '/nologo', '/std:c++20', '/EHsc', '/W4', str(root / 'tests/gpu/NativeFrameAcceptance.cpp'), f'/Fe:{exe}', f'/Fo:{out}/', '/link', 'd3d11.lib', 'dxgi.lib', 'user32.lib', 'd3d12.lib'], cwd=out, env=env, check=True)
if not args.build_only:
    for mode in ['explicit', 'host', 'renderer', 'window'] if args.teardown == 'all' else [args.teardown]:
        subprocess.run([str(exe), mode], cwd=out, env=env, check=True, timeout=45)
