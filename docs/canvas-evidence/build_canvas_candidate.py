"""Private R01 canvas candidate on native codex/batch-1: the parent native46-candidate-6 (built at ed60fd4, equal to
batch-1 d247ceb in host, config, gen and patches) with this tree's RanvierDomGlue and the new RanvierCanvasGlue compiled,
WebCore relinked, and the four host units recompiled and relinked. Derived from docs/cascade-evidence/build_native46_candidate.py.
usage: build_canvas_candidate.py <canvas-candidate-N> [parent candidate dir]
The parent's objects must cover every patch of this tree's series past 0034, which C:/wk/src must carry; its WebCore
objects and the five host-glue objects its WebCore link names (RanvierInspectGlue included) are borrowed read-only,
after asserting their sources and the patch series equal the parent tree."""
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

repo = Path('C:/wk/native-canvas')
assert sys.argv[1].startswith('canvas-candidate-'), 'Build into artifacts/canvas-candidate-N'
out = repo / 'artifacts' / sys.argv[1]
parent = Path(sys.argv[2] if len(sys.argv) > 2 else 'C:/wk/native-cascade-shadow/artifacts/native46-candidate-6')
parent_repo, parent_head = Path('C:/wk/native-cascade-shadow'), 'ed60fd4'


def same_as_parent(path):
    theirs = subprocess.run(['git', '-C', str(parent_repo), 'show', parent_head + ':' + path], capture_output=True, check=True).stdout
    return (repo / path).read_bytes().replace(b'\r\n', b'\n') == theirs.replace(b'\r\n', b'\n')


# This lane's own source patch, which the parent's objects predate: every unit it reaches is recompiled here.
OWN_PATCHES = {'0042-canvas-renders-embedder-context.patch'}
for path in sorted((repo / 'patches').iterdir()):
    if path.name in OWN_PATCHES or path.name == 'series':
        continue
    assert same_as_parent('patches/' + path.name), path.name + ' differs from the parent tree'
parent_series = subprocess.run(['git', '-C', str(parent_repo), 'show', parent_head + ':patches/series'], capture_output=True, text=True, check=True).stdout.split()
assert (repo / 'patches/series').read_text().split() == parent_series + sorted(OWN_PATCHES), 'series is the parent series plus the lane patches'
build = Path('C:/wk/build-win-slim')
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'

# Every source patch of this tree's series past 0034 is carried by C:/wk/src and covered by the parent's objects, either in
# its receipt's patches or as a reused owner object.
parent_patches = json.loads((parent / 'source-patches.json').read_text())
series = [line for line in (repo / 'patches/series').read_text().splitlines() if line[:4].isdigit() and line[:4] >= '0035']
covered = {name[:4] for name in parent_patches['patches']}
reused = parent_patches.get('reusedOwnerObject')
for item in (reused if isinstance(reused, list) else [reused] if reused else []):
    covered.add(item['patch'][:4])
assert {name[:4] for name in series if name not in OWN_PATCHES} <= covered, ('patches the parent does not cover', series, sorted(covered))
patch_receipt = {}
for name in series:
    text = (repo / 'patches' / name).read_text(encoding='utf-8')
    patch_receipt[name] = {'sha256': hashlib.sha256((repo / 'patches' / name).read_bytes()).hexdigest(), 'files': []}
    for section in text.split('\ndiff --git ')[0 if text.startswith('diff --git ') else 1:]:
        target = re.search(r'a/(\S+) b/', section).group(1)
        hunk = [line for line in section.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))]
        current = subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--', target], capture_output=True, text=True, check=True).stdout
        lines = [line for line in current.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))]
        index = 0
        for line in lines:
            if index < len(hunk) and line == hunk[index]:
                index += 1
        assert index == len(hunk), target + ' does not carry ' + name
        patch_receipt[name]['files'].append(target)
# The host-glue objects WebCore links besides RanvierDomGlue are the parent's.
link = (parent / 'webcore-link.rsp').read_text(encoding='utf-8')
glue_objects = sorted({path for path in re.findall(r'(\S+Ranvier[A-Za-z]+Glue\.cpp\.obj)', link) if 'RanvierDomGlue' not in path})
assert len(glue_objects) == 5, glue_objects
for glue in glue_objects:
    stem = re.search(r'(Ranvier[A-Za-z]+Glue)\.cpp\.obj', glue).group(1)
    for suffix in ['.cpp', '.h']:
        assert same_as_parent('host/' + stem + suffix), stem + suffix + ' changed since the parent: its object is stale'

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
# Every unit a series patch reaches, unified or standalone, is a parent object compiled after the patched source.
patched_files = sorted({name for item in patch_receipt.values() for name in item['files']})
scan = json.loads(subprocess.run([sys.executable, '-I', 'C:/wk/t06-artifacts/units_for_headers.py', '--json', *patched_files],
                                 capture_output=True, text=True, check=True).stdout)
ninja_text = (build / 'build.ninja').read_text()
unit_check = {}
own_files = sorted({name for patch in OWN_PATCHES for name in patch_receipt[patch]['files']})
own_units = sorted({unit for name in own_files for unit in scan.get(name, [])})
assert own_units, own_files
for name in patched_files:
    if name in own_files:
        continue
    units = list(scan.get(name, []))
    if name.startswith('Source/WebCore/') and name.endswith('.cpp'):
        standalone = 'Source/WebCore/CMakeFiles/WebCore.dir/' + name.removeprefix('Source/WebCore/') + '.obj'
        if ('build ' + standalone.replace('/', chr(92)) + ':') in ninja_text:
            units.append(standalone)
    source_time = os.stat(Path('C:/wk/src') / name).st_mtime_ns
    for unit in units:
        obj = replacements.get(unit)
        assert obj and Path(obj).stat().st_mtime_ns > source_time, unit + ' is not a parent object newer than ' + name
        unit_check[unit] = obj
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
# Every unit the lane's own patch reaches compiles from C:/wk/src, which must carry the patch.
own_objects = {}
for command in commands(own_units):
    if 'clang-cl.exe' in command:
        output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
        if output:
            command_map[normalize(output.group(1) or output.group(2))] = command
for index, unit in enumerate(own_units, start=1):
    assert unit in command_map and unit in replacements, unit
    target, unit_obj, code = compile_object(index, unit)
    if code:
        raise SystemExit(unit + ' failed')
    replacements[unit] = unit_obj
    own_objects[unit] = unit_obj
# PRIVATE_CANVAS_SOURCE names the patched copy the patch was first proven with: its unit compiles beside the C:/wk/src one,
# unlinked, and the two disassemblies are compared.
private_canvas = os.environ.get('PRIVATE_CANVAS_SOURCE')
private_unit = None
if private_canvas:
    unit_target = 'Source/WebCore/CMakeFiles/WebCore.dir/__/__/WebCore/DerivedSources/unified-sources/UnifiedSource-html-6.cpp.obj'
    assert unit_target in own_objects
    unified = build / 'WebCore/DerivedSources/unified-sources/UnifiedSource-html-6.cpp'
    text = unified.read_text(encoding='utf-8')
    assert text.count('#include "html\\HTMLCanvasElement.cpp"') == 1, 'html-6 no longer holds HTMLCanvasElement.cpp'
    private_unified = out / 'UnifiedSource-html-6-private.cpp'
    private_unified.write_text(text.replace('#include "html\\HTMLCanvasElement.cpp"', '#include "' + Path(private_canvas).resolve().as_posix() + '"'), encoding='utf-8')
    private_target = unit_target.replace('UnifiedSource-html-6.cpp.obj', 'UnifiedSource-html-6-private.cpp.obj')
    command_map[private_target] = re.sub(r'\S*UnifiedSource-html-6\.cpp(?=\s|$)', private_unified.as_posix(), command_map[unit_target])
    target, private_obj, code = compile_object(80, private_target)
    if code:
        raise SystemExit('private html-6 failed')

    def disassembly(path):
        listing = subprocess.run([str(compiler.parent / 'llvm-objdump.exe'), '-d', '--no-show-raw-insn', path], capture_output=True, text=True, check=True).stdout
        return hashlib.sha256(chr(10).join(listing.splitlines()[2:]).encode()).hexdigest()

    private_unit = {'unit': unit_target, 'privateSource': Path(private_canvas).resolve().as_posix(),
                    'privateSourceSha256': hashlib.sha256(Path(private_canvas).read_bytes()).hexdigest(),
                    'privateObject': private_obj, 'srcObject': own_objects[unit_target],
                    'privateDisassemblySha256': disassembly(private_obj), 'srcDisassemblySha256': disassembly(own_objects[unit_target])}
    private_unit['disassemblyEqual'] = private_unit['privateDisassemblySha256'] == private_unit['srcDisassemblySha256']
canvas_target = 'Ranvier/host/RanvierCanvasGlue.cpp.obj'
canvas_command, count = re.subn(r'C:[/\\]wk[/\\]ranvier-webcore[/\\]host[/\\]dom[/\\]RanvierDomGlue.cpp',
                                (repo / 'host/RanvierCanvasGlue.cpp').as_posix(), command_map[glue_target])
assert count == 1, count
command_map[canvas_target] = canvas_command
target, canvas_obj, code = compile_object(90, canvas_target)
if code:
    raise SystemExit('RanvierCanvasGlue failed')
# Patch 0040 (EmptyClients.h: final -> override, vtable unchanged) is in C:/wk/src and postdates the parent's objects.
empty_clients = subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--', 'Source/WebCore/loader/EmptyClients.h'],
                               capture_output=True, text=True, check=True).stdout
included = {}
for log in sorted(out.glob('0[09][0-9]-*.log')):
    included[log.name] = 'EmptyClients.h' in log.read_text(encoding='utf-8', errors='replace')
(out / 'source-patches.json').write_text(json.dumps({'patches': patch_receipt, 'parent': str(parent), 'parentHead': parent_head,
                                                     'parentReceipt': parent_patches, 'hostGlueObjects': glue_objects,
                                                     'recompiledUnits': {glue_target: obj, canvas_target: canvas_obj}, 'patchUnitsBorrowed': unit_check, 'privateCanvasSource': private_unit, 'ownPatchUnits': own_objects,
                                                     'patch0040': {'emptyClientsDiffSha256': hashlib.sha256(empty_clients.encode()).hexdigest(),
                                                                   'emptyClientsDiffLines': len(empty_clients.splitlines()),
                                                                   'recompiledUnitIncludes': included,
                                                                   'note': 'final -> override, vtable unchanged; postdates the parent objects'}}, indent=2))
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))
extra = [Path(canvas_obj).as_posix()]
for name in glue_objects:
    glue = Path(name)
    borrowed[glue] = glue.stat().st_mtime_ns
    extra.append(glue.as_posix())
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
print('CANVAS CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
