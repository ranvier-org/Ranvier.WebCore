"""Private Native27 G02/G12 runtime on I12: native25-candidate-3 (Source 0000-0034) with I12's RanvierEventGlue object, RanvierViewportGlue
compiled into WebCore and the four host units recompiled from this tree. Borrows build-win-slim, native25-candidate-3's
runtime, its 111 replacement objects and its three glue objects read-only; RanvierDomGlue is unchanged since e58aa24f."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import types

repo = Path(__file__).resolve().parents[1]
parent = Path('C:/wk/native-traversal/artifacts/native25-candidate-3')
build = Path('C:/wk/build-win-slim')
out = repo / 'artifacts' / sys.argv[1]
assert sys.argv[1].startswith('native27-candidate-'), 'Build into artifacts/native27-candidate-N'
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'
i12 = Path('C:/wk/native-focus-input/artifacts/native26-candidate-3')
for unchanged, base in [('host/dom/RanvierDomGlue.cpp', 'e58aa24f'), ('host/dom/RanvierDomGlue.h', 'e58aa24f'), ('host/RanvierResourceGlue.cpp', 'e58aa24f'),
                        ('host/RanvierSvgViewGlue.cpp', 'e58aa24f'), ('host/RanvierEventGlue.cpp', '4ef65aa'), ('host/RanvierEventGlue.h', '4ef65aa')]:
    diff = subprocess.run(['git', 'diff', '--quiet', base, '--', unchanged], cwd=repo)
    assert diff.returncode == 0, unchanged + ' changed since ' + base + ': the borrowed glue object is stale'
runtime = out / 'runtime'
runtime.mkdir(parents=True, exist_ok=True)
shutil.copytree(parent / 'runtime', runtime, dirs_exist_ok=True)
parent_files = [p for p in parent.rglob('*') if p.is_file() and p.suffix in ('.obj', '.dll', '.lib', '.json')]
parent_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in parent_files}
cache = (build / 'CMakeCache.txt').read_text()
compiler = Path(re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.+)$', cache, re.M).group(1))
tree = ast.parse((repo / 'scripts/build.py').read_text())
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'toolchain_env')
scope = dict(os=os, pathlib=__import__('pathlib'), subprocess=subprocess, sys=sys,
             windows=True, arch='x64', system='win', args=types.SimpleNamespace(tool_path=[]),
             llvm=compiler.parent, vcpkg=Path('C:/wk/vcpkg'), pins=json.loads((repo / 'pins.json').read_text()))
exec(compile(ast.Module(body=[function], type_ignores=[]), '<toolchain_env>', 'exec'), scope)
env = scope['toolchain_env']()
ninja = re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$', cache, re.M).group(1)
stop = threading.Event()
helpers = ast.parse(Path('C:/wk/native-cssom-detached-context/artifacts/build_context_candidate.py').read_text())
names = {'normalize', 'commands', 'execute', 'link_command'}
functions = [node for node in helpers.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(functions) == len(names)
exec(compile(ast.Module(body=functions, type_ignores=[]), '<reviewed_private_build_helpers>', 'exec'), globals())
lines = (build / 'build.ninja').read_text().splitlines()

replacements = json.loads((parent / 'replacement-objects.json').read_text())
assert len(replacements) == 111
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in replacements.values() if Path(path).is_file()}
glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
build_files = {p: p.stat().st_mtime_ns for p in [build / 'CMakeCache.txt', build / 'build.ninja', build / '.ninja_log', build / '.ninja_deps', build / 'bin/WebCore.dll'] if p.exists()}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)

# Five native22-final replacement objects were deleted; their rebuilt copies come from the v2 map read-only.
v2 = json.loads(Path('C:/wk/h05-private/native22-final/replacement-objects-v2.json').read_text())
missing = [target for target, obj in replacements.items() if not Path(obj).is_file()]
assert len(missing) == 5 and all(v2[target].startswith('C:/wk/shared-objects/native22-replacements-v2/') for target in missing), missing
for target in missing:
    replacements[target] = v2[target]
    borrowed[Path(v2[target])] = Path(v2[target]).stat().st_mtime_ns

glue_command = next(c for c in commands([glue_target]) if 'clang-cl.exe' in c and 'RanvierDomGlue.cpp' in c)
extra = []
for name in ['RanvierSvgViewGlue', 'RanvierResourceGlue', 'RanvierEventGlue']:
    obj = (i12 if name == 'RanvierEventGlue' else parent) / (name + '.cpp.obj')
    borrowed[obj] = obj.stat().st_mtime_ns
    extra.append(obj.as_posix())
obj = out / 'RanvierViewportGlue.cpp.obj'
command = re.sub(r' -c -- .*$', ' -c -- ' + (repo / 'host/RanvierViewportGlue.cpp').as_posix(), glue_command)
command = re.sub(r'/Fo(?:"[^"]+"|\S+)', '/Fo' + obj.as_posix(), command)
command = re.sub(r'/Fd(?:"[^"]+"|\S+)', '/Fd' + (out / 'RanvierViewportGlue.cpp.pdb').as_posix(), command)
if execute(command, 'RanvierViewportGlue'):
    raise SystemExit(1)
extra.append(obj.as_posix())
if execute(link_command('WebCore') + ' ' + ' '.join(extra) + ' Dwrite.lib', 'webcore-link'):
    raise SystemExit(1)

host_target = r'Tools\TestWebKitAPI\CMakeFiles\RanvierWebCoreHost.dir\RanvierAbi\RanvierWebCoreAbi.cpp.obj'
host_command = next(c for c in commands([host_target]) if 'clang-cl.exe' in c and 'RanvierWebCoreAbi.cpp' in c)
flags = re.findall(r'^((?:USE|ENABLE)_[A-Z0-9_]+):BOOL=(ON|OFF|1|0|TRUE|FALSE)$', cache, re.M)
flag_arguments = ' '.join('/DRV_CAP_' + name + '=' + ('1' if value in ['ON', '1', 'TRUE'] else '0') for name, value in flags)
host_objects = []
for filename in ['RanvierWebCoreAbi.cpp', 'RanvierWebCoreDom.cpp', 'RanvierWebCoreUia.cpp', 'RanvierWebCoreD3D11.cpp']:
    command = re.sub(r'C:[/\\]wk[/\\]src[/\\]Tools[/\\]TestWebKitAPI[/\\]RanvierAbi[/\\]RanvierWebCoreAbi.cpp',
                     (repo / 'host' / filename).as_posix(), host_command)
    obj = out / (filename + '.obj')
    command, count = re.subn(r'/Fo(?:"[^"]+"|\S+)', '/Fo' + obj.as_posix(), command)
    assert count == 1
    command = re.sub(r'/Fd(?:"[^"]+"|\S+)', '/Fd' + (out / (filename + '.pdb')).as_posix(), command)
    command = command.replace(' -- ', ' ' + flag_arguments + ' -- ')
    if execute(command, filename):
        raise SystemExit(1)
    host_objects.append(obj.as_posix())
if execute(link_command('RanvierWebCoreHost', host_objects) + ' Uiautomationcore.lib Ole32.lib OleAut32.lib Comctl32.lib', 'host-link'):
    raise SystemExit(1)

assert borrowed == {path: path.stat().st_mtime_ns for path in borrowed}, 'Borrowed objects changed'
assert build_files == {p: p.stat().st_mtime_ns for p in build_files}, 'build-win-slim changed'
assert parent_hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in parent_files}, 'native25-candidate-3 changed'
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.iterdir() if p.is_file()}
assert hashes['JavaScriptCore.dll'].startswith('95149cdc')
(out / 'runtime-sha256.json').write_text(json.dumps(hashes, indent=2))
print('NATIVE27 VIEWPORT CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
