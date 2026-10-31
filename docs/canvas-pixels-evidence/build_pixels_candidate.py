"""Private R06 canvas pixels candidate: the parent canvas-candidate-5 (R01, built at native-canvas 3018e23) with this
tree's RanvierDomGlue, the new RanvierCanvasPixelsGlue and RanvierInspectGlue (changed by the batch-1 merge cae4da8)
compiled, WebCore relinked, and the four host units recompiled and relinked. Derived from
docs/canvas-evidence/build_canvas_candidate.py.
usage: build_pixels_candidate.py <pixels-candidate-N> [parent candidate dir]
Every patch of this tree's series must equal the parent tree's: the parent's WebCore objects, its patch units and the
host-glue objects whose sources are unchanged are borrowed read-only."""
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

repo = Path('C:/wk/native-canvas-pixels')
assert sys.argv[1].startswith('pixels-candidate-'), 'Build into artifacts/pixels-candidate-N'
out = repo / 'artifacts' / sys.argv[1]
parent = Path(sys.argv[2] if len(sys.argv) > 2 else 'C:/wk/native-canvas/artifacts/canvas-candidate-5')
parent_repo, parent_head = Path('C:/wk/native-canvas'), '3018e23'
# Glue sources compiled here beside the parent's objects: new files, and files a merge changed since the parent.
NEW_GLUE = ['RanvierCanvasPixelsGlue']
RECOMPILED_GLUE = {'RanvierInspectGlue': 'batch-1 merge cae4da8 qualifies WebCore::Style'}


def parent_text(path):
    return subprocess.run(['git', '-C', str(parent_repo), 'show', parent_head + ':' + path], capture_output=True, check=True).stdout


def same_as_parent(path):
    return (repo / path).read_bytes().replace(b'\r\n', b'\n') == parent_text(path).replace(b'\r\n', b'\n')


for path in sorted((repo / 'patches').iterdir()):
    assert same_as_parent('patches/' + path.name), path.name + ' differs from the parent tree'
build = Path('C:/wk/build-win-slim')
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'
parent_patches = json.loads((parent / 'source-patches.json').read_text())

link = (parent / 'webcore-link.rsp').read_text(encoding='utf-8')
glue_objects = sorted({path for path in re.findall(r'(\S+Ranvier[A-Za-z]+Glue\.cpp\.obj)', link) if 'RanvierDomGlue' not in path})
assert len(glue_objects) == 6, glue_objects
borrowed_glue, glue_receipt = [], {}
for glue in glue_objects:
    stem = re.search(r'(Ranvier[A-Za-z]+Glue)\.cpp\.obj', glue).group(1)
    same = all(same_as_parent('host/' + stem + suffix) for suffix in ['.cpp', '.h'])
    if stem in RECOMPILED_GLUE:
        assert not same, stem + ' equals the parent: borrow it instead'
        glue_receipt[stem] = {'parentObject': glue, 'recompiled': True, 'reason': RECOMPILED_GLUE[stem]}
    else:
        assert same, stem + ' changed since the parent: its object is stale'
        borrowed_glue.append(glue)
        glue_receipt[stem] = {'parentObject': glue, 'recompiled': False}

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
names = {'normalize', 'commands', 'execute', 'compile_object', 'link_command'}
functions = [node for node in helpers.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(functions) == len(names)
exec(compile(ast.Module(body=functions, type_ignores=[]), '<reviewed_private_build_helpers>', 'exec'), globals())
lines = (build / 'build.ninja').read_text().splitlines()

replacements = json.loads((parent / 'replacement-objects.json').read_text())
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in replacements.values()}
glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
assert glue_target in replacements
build_files = {p: p.stat().st_mtime_ns for p in [build / 'CMakeCache.txt', build / 'build.ninja', build / '.ninja_log', build / '.ninja_deps', build / 'bin/WebCore.dll'] if p.exists()}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')

command_map = {}
for command in commands([glue_target]):
    if 'clang-cl.exe' in command:
        output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
        if output:
            command_map[normalize(output.group(1) or output.group(2))] = command
target, obj, code = compile_object(0, glue_target)
if code:
    raise SystemExit('RanvierDomGlue failed')
replacements[glue_target] = obj
extra, recompiled = [], {glue_target: obj}
for index, stem in enumerate(NEW_GLUE + sorted(RECOMPILED_GLUE), start=90):
    unit = 'Ranvier/host/' + stem + '.cpp.obj'
    unit_command, count = re.subn(r'C:[/\\]wk[/\\]ranvier-webcore[/\\]host[/\\]dom[/\\]RanvierDomGlue.cpp',
                                  (repo / 'host' / (stem + '.cpp')).as_posix(), command_map[glue_target])
    assert count == 1, count
    command_map[unit] = unit_command
    target, unit_obj, code = compile_object(index, unit)
    if code:
        raise SystemExit(stem + ' failed')
    extra.append(Path(unit_obj).as_posix())
    recompiled[unit] = unit_obj
for glue in borrowed_glue:
    borrowed[Path(glue)] = Path(glue).stat().st_mtime_ns
    extra.append(Path(glue).as_posix())
(out / 'source-patches.json').write_text(json.dumps({'patches': parent_patches['patches'], 'patchesEqualParentTree': True,
                                                     'parent': str(parent), 'parentRepo': str(parent_repo), 'parentHead': parent_head,
                                                     'parentReceipt': parent_patches, 'hostGlue': glue_receipt,
                                                     'recompiledUnits': recompiled}, indent=2))
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))
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
    host_obj = out / (filename + '.obj')
    command, count = re.subn(r'/Fo(?:"[^"]+"|\S+)', '/Fo' + host_obj.as_posix(), command)
    assert count == 1
    command = re.sub(r'/Fd(?:"[^"]+"|\S+)', '/Fd' + (out / (filename + '.pdb')).as_posix(), command)
    command = command.replace(' -- ', ' ' + flag_arguments + ' -- ')
    if execute(command, filename):
        raise SystemExit(1)
    host_objects.append(host_obj.as_posix())
if execute(link_command('RanvierWebCoreHost', host_objects) + ' Uiautomationcore.lib Ole32.lib OleAut32.lib Comctl32.lib', 'host-link'):
    raise SystemExit(1)

assert borrowed == {path: path.stat().st_mtime_ns for path in borrowed}, 'Borrowed objects changed'
assert build_files == {p: p.stat().st_mtime_ns for p in build_files}, 'build-win-slim changed'
assert parent_hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in parent_files}, 'parent candidate changed'
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.iterdir() if p.is_file()}
assert hashes['JavaScriptCore.dll'].startswith('95149cdc')
(out / 'runtime-sha256.json').write_text(json.dumps(hashes, indent=2))
print('PIXELS CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
