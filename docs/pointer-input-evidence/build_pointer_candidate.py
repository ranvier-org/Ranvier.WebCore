"""Pointer-input candidate runtime from the full private build C:/wk/pointer-build (build_pointer_full.py): its WebCore.dll and
JavaScriptCore.dll, which embed this tree's glue (config/common.cmake's WebCore_EMBEDDER_SOURCES), and the four host units of
this tree compiled and linked as native46-candidate-6 compiles and links them, with the build directory, the tree and the
output directory replaced. The other runtime libraries are candidate-6's, built from the same vcpkg installation.
usage: build_pointer_candidate.py <pointer-candidate-N>
Every object is compiled with ENABLE_TOUCH_EVENTS and ENABLE_POINTER_LOCK on: no object of a build without them is borrowed."""
import ast, hashlib, json, os, pathlib, re, shutil, subprocess, sys, types
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
name = sys.argv[1]
assert name.startswith('pointer-candidate-'), 'Build into C:/wk/pointer-artifacts/pointer-candidate-N'
out = Path('C:/wk/pointer-artifacts') / name
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'
build, slim = Path('C:/wk/pointer-build'), Path('C:/wk/build-win-slim')
parent = Path('C:/wk/native-cascade-shadow/artifacts/native46-candidate-6')
cache = (build / 'CMakeCache.txt').read_text()
for flag in ['ENABLE_TOUCH_EVENTS', 'ENABLE_POINTER_LOCK']:
    assert re.search('^' + flag + r':BOOL=ON$', cache, re.M), flag
compiler = Path(re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.+)$', cache, re.M).group(1))
ninja = re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$', cache, re.M).group(1)
tree = ast.parse((repo / 'scripts/build.py').read_text())
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'toolchain_env')
scope = dict(os=os, pathlib=pathlib, subprocess=subprocess, sys=sys, windows=True, arch='x64', system='win',
             args=types.SimpleNamespace(tool_path=[]), llvm=compiler.parent, vcpkg=Path('C:/wk/vcpkg'),
             pins=json.loads((repo / 'pins.json').read_text()))
exec(compile(ast.Module(body=[function], type_ignores=[]), '<toolchain_env>', 'exec'), scope)
env = scope['toolchain_env']()
env['_LINK_'] = '/OPT:SAFEICF dwrite.lib'
slim_mtime = (slim / 'build.ninja').stat().st_mtime_ns

# WebCore and its dependencies, with this tree's glue.
subprocess.run([ninja, '-C', str(build), '-j', '16', 'WebCore'], env=env, check=True)
runtime = out / 'runtime'
runtime.mkdir(parents=True, exist_ok=True)


def retarget(text):
    for old in ['C:\\wk\\build-win-slim', 'C:/wk/build-win-slim']:
        text = text.replace(old, str(build) if '\\' in old else build.as_posix())
    text = text.replace('C:/wk/native-cascade-shadow/artifacts/native46-candidate-6', out.as_posix())
    text = text.replace('C:/wk/native-cascade-shadow/host', (repo / 'host').as_posix())
    assert 'native-cascade' not in text and 'build-win-slim' not in text, 'unreplaced parent path'
    return text


logs = {}
for unit in ['RanvierWebCoreAbi', 'RanvierWebCoreDom', 'RanvierWebCoreUia', 'RanvierWebCoreD3D11']:
    rsp = out / (unit + '.cpp.rsp')
    rsp.write_text(retarget((parent / (unit + '.cpp.rsp')).read_text(encoding='utf-8')), encoding='utf-8')
    done = subprocess.run([str(compiler), '@' + str(rsp)], env=env, cwd=build, capture_output=True, text=True)
    (out / (unit + '.cpp.log')).write_text(done.stdout + done.stderr, encoding='utf-8')
    assert done.returncode == 0, unit + ' failed:\n' + (done.stdout + done.stderr)[-4000:]
# WebCore.dll and its import library come from the private build.
for item in ['WebCore.dll', 'WebCore.pdb', 'JavaScriptCore.dll', 'JavaScriptCore.pdb']:
    shutil.copy2(build / 'bin' / item, runtime / item)
shutil.copy2(build / 'lib' / 'WebCore.lib', runtime / 'WebCore.lib')
link = retarget((parent / 'host-link.rsp').read_text(encoding='utf-8'))
(out / 'host-link.rsp').write_text(link, encoding='utf-8')
linker = compiler.parent / 'lld-link.exe'
done = subprocess.run([str(linker), '@' + str(out / 'host-link.rsp')], env=env, cwd=build, capture_output=True, text=True)
(out / 'host-link.log').write_text(done.stdout + done.stderr, encoding='utf-8')
assert done.returncode == 0, 'host link failed:\n' + (done.stdout + done.stderr)[-4000:]
# The libraries the private build does not rebuild: candidate-6's, from the same vcpkg installation.
reused = {}
for item in sorted((parent / 'runtime').iterdir()):
    if item.name.startswith(('RanvierWebCoreHost', 'WebCore', 'JavaScriptCore')):
        continue
    target = runtime / item.name
    if item.is_dir():
        shutil.copytree(item, target, dirs_exist_ok=True)
    else:
        shutil.copy2(item, target)
        reused[item.name] = hashlib.sha256(item.read_bytes()).hexdigest()
assert (slim / 'build.ninja').stat().st_mtime_ns == slim_mtime, 'build-win-slim changed'
hashes = {str(p.relative_to(runtime)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(runtime.rglob('*')) if p.is_file()}
(out / 'runtime-sha256.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')
src = subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--stat'], capture_output=True, text=True, check=True).stdout
receipt = {
    'build': str(build), 'flags': {'ENABLE_TOUCH_EVENTS': 'ON', 'ENABLE_POINTER_LOCK': 'ON'},
    'fullRebuild': 'Every WebCore and JavaScriptCore object compiled in C:/wk/pointer-build; none borrowed. Once this config '
                   'lands, every later candidate needs a full rebuild: both flags are in cmakeconfig.h.',
    'patches': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((repo / 'patches').glob('004[4-7]-*.patch'))},
    'srcDiffStatLines': len(src.splitlines()),
    'reusedFromNative46Candidate6': reused,
    'hostUnits': ['RanvierWebCoreAbi', 'RanvierWebCoreDom', 'RanvierWebCoreUia', 'RanvierWebCoreD3D11'],
}
(out / 'source-patches.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print('candidate', out, 'host', hashes['RanvierWebCoreHost.dll'][:16], 'webcore', hashes['WebCore.dll'][:16])
