"""Build and run an independent OS UIA client against the bridge in a staged native host DLL.

No WebCore source/build cache is modified. Build and test can be invoked separately for lease ownership.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser()
runtime = parser.add_mutually_exclusive_group(required=True)
runtime.add_argument('--native', type=Path, help='Directory containing staged native DLLs.')
runtime.add_argument('--stage', type=Path, help='Native package stage with manifest.json and runtimes/.')
parser.add_argument('--host-lib', type=Path)
parser.add_argument('--build-dir', type=Path, help='WebCore CMake build; its lib/RanvierWebCoreHost.lib is used for linking.')
parser.add_argument('--build-only', action='store_true')
parser.add_argument('--run-only', action='store_true')
parser.add_argument('--integrated', action='store_true', help='Accepted for compatibility; tests always use the bridge exported by the host DLL.')
parser.add_argument('--host-dll', type=Path, help='Override only the host DLL while retaining staged runtime dependencies.')
parser.add_argument('--teardown', choices=['explicit', 'host', 'window', 'sync', 'overflow', 'cache'], default='explicit')
parser.add_argument('--cache-probe', action='store_true', help='Compile the white-box cache fixture with the real provider source; normal acceptance always uses the DLL bridge.')
parser.add_argument('--compiler-environment', type=Path, help='Optional vcvars64.bat; otherwise use ambient cl or discover installed Visual Studio.')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
out = root / 'artifacts/uia'
out.mkdir(parents=True, exist_ok=True)
env = dict(os.environ)
if not args.run_only and (args.compiler_environment or not shutil.which('cl')):
    compiler_environment = args.compiler_environment
    if compiler_environment is None:
        vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
        installation = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
        if not installation:
            parser.error('No installed Visual Studio C++ toolchain found; pass --compiler-environment.')
        compiler_environment = Path(installation) / 'VC/Auxiliary/Build/vcvars64.bat'
    environment_script = out / 'compiler-environment.cmd'
    environment_script.write_text(f'@call "{compiler_environment}" >nul\n@set PATH\n@set INCLUDE\n@set LIB\n', newline='\r\n')
    environment = subprocess.check_output(['cmd', '/d', '/c', str(environment_script)], text=True)
    for line in environment.splitlines():
        if '=' in line and not line.startswith('='):
            key, value = line.split('=', 1)
            env[key.upper()] = value
env['OS'] = 'Windows_NT'
native = args.native
if args.stage:
    manifest = json.loads((args.stage / 'manifest.json').read_text())
    if manifest['rid'] != 'win-x64':
        parser.error('The UIA acceptance client currently builds and runs as Windows x64.')
    native = args.stage / 'runtimes' / manifest['rid'] / 'native'
for source in native.resolve().iterdir():
    destination = out / source.name
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        shutil.copy2(source, destination)
if args.host_dll:
    shutil.copy2(args.host_dll.resolve(), out / 'RanvierWebCoreHost.dll')
host_lib = args.host_lib or (args.build_dir / 'lib/RanvierWebCoreHost.lib' if args.build_dir else None)
if not args.run_only and host_lib is None:
    parser.error('Pass --host-lib or --build-dir to link the fixture against the native host.')
compiler = shutil.which('cl', path=env.get('PATH')) if not args.run_only else 'cl'
if not compiler:
    parser.error('The selected compiler environment did not provide cl.exe.')
executable = out / ('RanvierUiaCacheAcceptance.exe' if args.cache_probe else 'RanvierUiaAcceptance.exe')
source = root / 'tests/uia' / ('CacheAcceptance.cpp' if args.cache_probe else 'Acceptance.cpp')
command = [compiler, '/nologo', '/std:c++20', '/EHsc', '/W4', '/DRV_EXPORT=', str(source),
           f'/Fe:{executable}', f'/Fo:{out}/',
           '/link', str(host_lib.resolve()) if host_lib else '', 'Uiautomationcore.lib', 'Ole32.lib', 'OleAut32.lib', 'Comctl32.lib', 'User32.lib', 'Uuid.lib']
if not args.run_only:
    subprocess.run(command, cwd=out, env=env, check=True)
if not args.build_only:
    subprocess.run([str(executable), args.teardown], cwd=out, env=env, check=True, timeout=135 if args.teardown == 'cache' else 45)
