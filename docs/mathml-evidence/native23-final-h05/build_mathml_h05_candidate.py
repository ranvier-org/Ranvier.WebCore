"""Private Native23 MathML runtime on H05: native22-final (Source 0001-0033) with the merged tree's RanvierDomGlue and
UnifiedSource-svg-14 (Source 0034) recompiled against C:/wk/src, no header overlay. Borrows build-win-slim and native22-final
read-only."""
import ast
import concurrent.futures
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
parent = Path('C:/wk/h05-private/native22-final')
build = Path('C:/wk/build-win-slim')
out = repo / 'artifacts' / (sys.argv[1] if len(sys.argv) > 1 else 'mathml-candidate-h05')
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'
runtime = out / 'runtime'
runtime.mkdir(parents=True, exist_ok=True)
shutil.copytree(parent / 'runtime', runtime, dirs_exist_ok=True)
parent_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (parent / 'runtime').glob('*') if p.is_file()}
cache = (build / 'CMakeCache.txt').read_text()
ninja = re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$', cache, re.M).group(1)
compiler = Path(re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.+)$', cache, re.M).group(1))
tree = ast.parse((repo / 'scripts/build.py').read_text())
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'toolchain_env')
scope = dict(os=os, pathlib=__import__('pathlib'), subprocess=subprocess, sys=sys,
             windows=True, arch='x64', system='win', args=types.SimpleNamespace(tool_path=[]),
             llvm=compiler.parent, vcpkg=Path('C:/wk/vcpkg'), pins=json.loads((repo / 'pins.json').read_text()))
exec(compile(ast.Module(body=[function], type_ignores=[]), '<toolchain_env>', 'exec'), scope)
env = scope['toolchain_env']()
stop = threading.Event()
helpers = ast.parse(Path('C:/wk/native-cssom-detached-context/artifacts/build_context_candidate.py').read_text())
names = {'normalize', 'commands', 'execute', 'compile_object', 'link_command'}
functions = [node for node in helpers.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(functions) == len(names)
exec(compile(ast.Module(body=functions, type_ignores=[]), '<reviewed_private_build_helpers>', 'exec'), globals())
lines = (build / 'build.ninja').read_text().splitlines()

replacements = json.loads((parent / 'replacement-objects.json').read_text())
assert len(replacements) == 111
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in replacements.values()}
# Every object that includes ImageLoader.h, HTMLImageElement.h or SVGImageElement.h, the candidate's own included.
glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
# The MathML glue includes HTMLImageElement.h; UnifiedSource-svg-14 holds Source 0034's SVGStringList.cpp. The other
# H05 and Native21 objects predate 0034 and contain none of its code, so they are borrowed from native22-final.
targets = [glue_target, 'Source/WebCore/CMakeFiles/WebCore.dir/__/__/WebCore/DerivedSources/unified-sources/UnifiedSource-svg-14.cpp.obj']
cached = {build / target: (build / target).stat().st_mtime_ns for target in targets}
build_files = {p: p.stat().st_mtime_ns for p in [build / 'CMakeCache.txt', build / 'build.ninja', build / '.ninja_log', build / '.ninja_deps', build / 'bin/WebCore.dll'] if p.exists()}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')
command_map = {}
for command in commands(targets):
    if 'clang-cl.exe' in command:
        output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
        if output:
            command_map[normalize(output.group(1) or output.group(2))] = command
missing = [t for t in targets if t not in command_map]
assert not missing, missing
reused = out / 'replacement-objects.json'
if False:
    # The 0032 engine objects depend only on C:/wk/src, which this run asserts unchanged since they were compiled.
    previous = json.loads(reused.read_text())
    results = [(target, previous[target], 0) for target in targets]
    assert all(Path(obj).is_file() for _, obj, _ in results)
else:
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda pair: compile_object(*pair), enumerate(targets)))
failed = [target for target, obj, code in results if code]
if failed:
    raise SystemExit('ImageLoader dependents failed: ' + ', '.join(failed))
for target, obj, code in results:
    replacements[target] = obj
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))

glue_command = next(c for c in commands([glue_target]) if 'clang-cl.exe' in c and 'RanvierDomGlue.cpp' in c)
extra = []
for name in ['RanvierSvgViewGlue', 'RanvierResourceGlue']:
    obj = out / (name + '.cpp.obj')
    command = re.sub(r' -c -- .*$', ' -c -- ' + (repo / 'host' / (name + '.cpp')).as_posix(), glue_command)
    command = re.sub(r'/Fo(?:"[^"]+"|\S+)', '/Fo' + obj.as_posix(), command)
    command = re.sub(r'/Fd(?:"[^"]+"|\S+)', '/Fd' + (out / (name + '.cpp.pdb')).as_posix(), command)
    if execute(command, name):
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
assert cached == {path: path.stat().st_mtime_ns for path in cached}, 'Cached build outputs changed'
assert build_files == {p: p.stat().st_mtime_ns for p in build_files}, 'build-win-slim changed'
assert parent_hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (parent / 'runtime').glob('*') if p.is_file()}, 'native22-final parent changed'
resolved = {}
for log in out.glob('*.log'):
    for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
        match = re.search(r'Note: including file:\s*(.*(?:ImageLoader|HTMLImageElement|SVGImageElement)\.h)\s*$', line)
        if match and not Path(match.group(1)).name.startswith('JS'):
            resolved.setdefault(match.group(1).replace('\\', '/'), set()).add(log.name)
foreign = [path for path in resolved if not path.lower().startswith('c:/wk/src/source/webcore/')]
assert not foreign, ('Headers resolved outside the 0032 source', foreign)
assert 'C:/wk/src/Source/WebCore/html/HTMLImageElement.h' in resolved
(out / 'header-resolution.json').write_text(json.dumps({k: sorted(v) for k, v in sorted(resolved.items())}, indent=2))
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.iterdir() if p.is_file()}
assert hashes['JavaScriptCore.dll'].startswith('95149cdc')
(out / 'runtime-sha256.json').write_text(json.dumps(hashes, indent=2))
print('MATHML H05 CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
