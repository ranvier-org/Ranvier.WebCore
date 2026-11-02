import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from d3d11_diagnostic_process import bounded

parser = argparse.ArgumentParser()
parser.add_argument('--package', type=Path, required=True)
parser.add_argument('--manifest', type=Path, required=True)
parser.add_argument('--sdl', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
out = args.output.resolve()
assert out.is_relative_to(root / 'artifacts'), 'Diagnostic output must stay in the owned artifact directory'
out.mkdir(parents=True, exist_ok=True)
assert not any(out.iterdir()), 'Diagnostic output must be fresh'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
expected = '9a4015a5eaf3581fa9481146ded5b6dbee8d6e63cf1e5b13ed5e24522a8ad243'
assert sha(args.package) == expected, 'Wrong official package'
manifest = json.loads(args.manifest.read_text())
assert manifest['source'] == {'commit': '05ba023551aaf58946cbc0ca7099ca65d9860e14', 'dirty': False, 'builder': 'ci'}
assert manifest['abi'] == 60 and manifest['rid'] == 'win-x64' and manifest['flavor'] == 'gpu'
with zipfile.ZipFile(args.package) as package:
    for name in package.namelist():
        prefix = 'runtimes/win-x64/native/'
        if name.startswith(prefix) and not name.endswith('/'):
            target = out / name[len(prefix):]
            assert target.resolve().is_relative_to(out)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.read(name))
payloads = {p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()}
assert len(payloads) == 26, 'Unexpected official payload count'
assert payloads == {item['name']: item['sha256'] for item in manifest['files']}, 'Official manifest payload hashes differ'
shutil.copy2(args.sdl, out / 'SDL3.dll')
env = dict(os.environ)
if not shutil.which('cl'):
    vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    installation = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True, timeout=30).strip()
    assert installation, 'No Visual Studio C++ compiler'
    script = out / 'compiler-environment.cmd'
    script.write_text(f'@call "{installation}/VC/Auxiliary/Build/vcvars64.bat" >nul\n@set PATH\n@set INCLUDE\n@set LIB\n', newline='\r\n')
    for line in subprocess.check_output(['cmd', '/d', '/c', str(script)], text=True, timeout=60).splitlines():
        if '=' in line and not line.startswith('='):
            key, value = line.split('=', 1)
            env[key.upper()] = value
compiler = shutil.which('cl', path=env.get('PATH'))
assert compiler
source = root / 'tests/gpu/NativeFrameDiagnostic.cpp'
header = root / 'host/RanvierWebCoreAbi.h'
canonical_header = hashlib.sha256(header.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
assert canonical_header == '1a667caafb5781a9c7683b7671c25de4ac940f3a216318cdd41ee877e3f8f48e', '05ba public header differs'
exe = out / 'NativeFrameDiagnostic.exe'
command = [compiler, '/nologo', '/std:c++20', '/EHsc', '/W4', '/I' + str(root / 'host'), str(source),
           '/Fe:' + str(exe), '/Fo:' + str(out / 'NativeFrameDiagnostic.obj'), '/Fd:' + str(out / 'NativeFrameDiagnostic.compile.pdb'),
           '/link', '/PDB:' + str(out / 'NativeFrameDiagnostic.pdb'), 'd3d11.lib', 'dxgi.lib', 'user32.lib']
receipt = {'officialSource': '05ba023551aaf58946cbc0ca7099ca65d9860e14', 'packageSha256': expected,
           'manifest': manifest, 'sourceSha256': sha(source), 'publicHeaderSha256': sha(header), 'publicHeaderCanonicalSha256': canonical_header, 'sdlSha256': sha(args.sdl),
           'compileCommand': command, 'payloadsBefore': payloads, 'originalExpectationPreserved': True,
           'setupTimeoutsSeconds': {'vswhere': 30, 'vcvars': 60}, 'runtimeTimeoutSeconds': 45, 'maximumCleanupGraceSeconds': 9,
           'nativeProductBuildInvoked': False, 'publishInvoked': False}
result_code = 1
try:
    compiled = bounded(command, cwd=out, env=env, timeout=120, events=receipt.setdefault('ownedProcesses', []))
    receipt['compileExit'] = compiled.returncode
    (out / 'diagnostic-compile.log').write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    run = bounded([str(exe), 'diagnostic'], cwd=out, env=env, timeout=45, events=receipt['ownedProcesses'])
    receipt['runtimeExit'] = run.returncode
    (out / 'diagnostic-runtime.log').write_text(run.stdout + run.stderr)
    print(run.stdout + run.stderr, flush=True)
    result_code = run.returncode
finally:
    receipt['payloadsAfter'] = {name: sha(out / name) for name in payloads}
    assert receipt['payloadsAfter'] == payloads
    assert sha(args.package) == expected
    receipt['all26PayloadsAndPackageUnchanged'] = True
    (out / 'diagnostic-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
raise SystemExit(result_code)
