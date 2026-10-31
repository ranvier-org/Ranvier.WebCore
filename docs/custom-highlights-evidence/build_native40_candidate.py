"""Private Native40 T03 (custom highlights) candidate: B22's native36-candidate-4 (Source 0000-0035 and 0037; its
replacement map holds G09's UnifiedSource-dom-7 for 0035 and B22's compiles of every unit 0037 reaches) with this tree's
regenerated RanvierDomGlue compiled into WebCore and the four host units recompiled. Borrows build-win-slim,
native36-candidate-4's runtime and its 130 replacement objects, and forms-candidate-4's four other glue objects, all
read-only. Each borrowed patch-unit object postdates the files of its patch; every other borrowed object postdates the
newest change to the remaining WebKit source."""
import argparse
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

parser = argparse.ArgumentParser()
parser.add_argument('name')
parser.add_argument('--repo', default='C:/wk/native-highlight')
parser.add_argument('--parent', default='C:/wk/native-crypto/artifacts/native36-candidate-4')
arguments = parser.parse_args()
repo = Path(arguments.repo)
parent = Path(arguments.parent)
glue_parent = Path('C:/wk/native-forms/artifacts/forms-candidate-4')
build = Path('C:/wk/build-win-slim')
assert arguments.name.startswith('native40-candidate-'), 'Build into artifacts/native40-candidate-N'
out = repo / 'artifacts' / arguments.name
assert not out.exists(), 'Build into a new versioned directory'
# The viewport glue changed after b8acc27 (G04) is compiled here; the other glue objects are borrowed.
viewport_changed = subprocess.run(['git', 'diff', '--quiet', 'b8acc27', '--', 'host/RanvierViewportGlue.cpp', 'host/RanvierViewportGlue.h'],
                                  cwd=repo).returncode != 0
for unchanged in ['host/RanvierSvgViewGlue.cpp', 'host/RanvierResourceGlue.cpp', 'host/RanvierEventGlue.cpp', 'host/RanvierEventGlue.h'] + (
        [] if viewport_changed else ['host/RanvierViewportGlue.cpp', 'host/RanvierViewportGlue.h']):
    diff = subprocess.run(['git', 'diff', '--quiet', 'b8acc27', '--', unchanged], cwd=repo)
    assert diff.returncode == 0, unchanged + ' changed since b8acc27: the borrowed glue object is stale'
# The borrowed objects postdate the newest change to the patched WebKit source, except Document.cpp (patch 0035),
# whose unified source is the patch owner's (G09) compile, made after the patch.
status = subprocess.run(['git', 'status', '--porcelain', '-uall'], cwd='C:/wk/src', capture_output=True, text=True, check=True).stdout.splitlines()
caret_source = 'Source/WebCore/dom/Document.cpp'
changed_sources = [line[3:] for line in status if (Path('C:/wk/src') / line[3:]).is_file()]
caret_mtime = os.stat(Path('C:/wk/src') / caret_source).st_mtime_ns
# Patch 0037 (D14): every unit whose recorded dependencies include a file it changes is the parent's (B22's) compile,
# checked below to postdate the patched files, after checking that C:/wk/src carries the patch's lines.
patch_0037 = repo / 'patches/0037-frame-loader-client-form-submission-hook.patch'
if not patch_0037.exists():
    patch_0037 = Path('C:/wk/native-formsubmit/patches/0037-frame-loader-client-form-submission-hook.patch')
# Patch 0038 (G04): its unified source and PlatformScreenWin.cpp are compiled here from C:/wk/src.
patch_0038 = repo / 'patches/0038-platform-screen-win-embedder-screen-data.patch'
if not patch_0038.exists():
    patch_0038 = Path('C:/wk/native-screen/patches/0038-platform-screen-win-embedder-screen-data.patch')
patches = sorted(p.name for p in (repo / 'patches').glob('*.patch')) + [patch_0037.name, patch_0038.name]
assert sorted(set(patches))[-1].startswith('0038-'), 'a source patch after 0038 needs its owner objects: ' + sorted(set(patches))[-1]
def hunk_lines(text):
    return [line for line in text.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))]
def contains(lines, part):
    index = 0
    for line in lines:
        if index < len(part) and line == part[index]:
            index += 1
    return index == len(part)
patch_receipt = {}
def patch_files(patch):
    files = set()
    text = patch.read_text(encoding='utf-8')
    for section in text.split('\ndiff --git ')[0 if text.startswith('diff --git ') else 1:]:
        name = re.search(r'a/(\S+) b/', section).group(1)
        current = subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--', name], capture_output=True, text=True, check=True).stdout
        assert contains(hunk_lines(current), hunk_lines(section)), name + ' does not carry ' + patch.name
        files.add(name)
        patch_receipt.setdefault(patch.name, {'sha256': hashlib.sha256(patch.read_bytes()).hexdigest(), 'files': {}})['files'][name] = hunk_lines(section)
    return files
recompiled_sources = patch_files(patch_0037)
screen_sources = patch_files(patch_0038)
screen_scan = subprocess.run([sys.executable, '-I', 'C:/wk/t06-artifacts/units_for_headers.py', '--json', *sorted(screen_sources)],
                             capture_output=True, text=True, check=True)
screen_units = json.loads(screen_scan.stdout)['all'] + ['Source/WebCore/CMakeFiles/WebCore.dir/platform/win/PlatformScreenWin.cpp.obj']
scan = subprocess.run([sys.executable, '-I', 'C:/wk/t06-artifacts/units_for_headers.py', '--json', *sorted(recompiled_sources)],
                      capture_output=True, text=True, check=True)
patched_units = json.loads(scan.stdout)['all']
newest_source = max(os.stat(Path('C:/wk/src') / path).st_mtime_ns for path in changed_sources
                    if path != caret_source and path not in recompiled_sources | screen_sources)
runtime = out / 'runtime'
runtime.mkdir(parents=True)
shutil.copytree(parent / 'runtime', runtime, dirs_exist_ok=True)
parent_files = [p for p in list(parent.rglob('*')) + list(glue_parent.glob('*.cpp.obj')) if p.is_file() and p.suffix in ('.obj', '.dll', '.lib', '.json')]
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
assert len(replacements) == 130
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in replacements.values()}
dom_target = next(key for key in replacements if key.endswith('/UnifiedSource-dom-7.cpp.obj'))
assert Path(replacements[dom_target]).stat().st_mtime_ns > caret_mtime, 'the borrowed dom-7 object predates patch 0035'
patch_mtime = max(os.stat(Path('C:/wk/src') / name).st_mtime_ns for name in recompiled_sources)
parent_patches = json.loads((parent / 'source-patches.json').read_text())
assert dom_target not in patched_units
for unit in patched_units:
    assert replacements.get(unit) == parent_patches['recompiledUnits'][unit], unit + ': not the parent patch compile'
    assert Path(replacements[unit]).stat().st_mtime_ns > patch_mtime, unit + ': the borrowed object predates patch 0037'
patch_objects = {Path(replacements[unit]) for unit in patched_units} | {Path(replacements[dom_target])}
# As in the parent builds: the objects compiled for the stack after the source patches through 0034 postdate every
# source change other than the patched files; the older shared replacement objects are the reviewed borrow recipe.
recent = ('forms-candidate-4', 'native32', 'native-crypto')
stale = [str(path) for path in borrowed
         if any(part in str(path) for part in recent) and path not in patch_objects and path.stat().st_mtime_ns <= newest_source]
assert not stale, 'WebKit source changed after the borrowed objects: ' + ', '.join(stale[:5])
glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
assert glue_target in replacements
build_files = {p: p.stat().st_mtime_ns for p in [build / 'CMakeCache.txt', build / 'build.ninja', build / '.ninja_log', build / '.ninja_deps', build / 'bin/WebCore.dll'] if p.exists()}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')
command_map = {}
assert not set(screen_units) & set(patched_units)
for command in commands([glue_target, *screen_units]):
    if 'clang-cl.exe' in command:
        output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
        if output:
            command_map[normalize(output.group(1) or output.group(2))] = command
target, obj, code = compile_object(0, glue_target)
if code:
    raise SystemExit('RanvierDomGlue failed')
replacements[glue_target] = obj
viewport_obj = None
if viewport_changed:
    viewport_target = 'Ranvier/host/RanvierViewportGlue.cpp.obj'
    command_map[viewport_target] = command_map[glue_target].replace('host/dom/RanvierDomGlue.cpp', 'host/RanvierViewportGlue.cpp').replace(
        'host\\dom\\RanvierDomGlue.cpp', 'host\\RanvierViewportGlue.cpp')
    assert command_map[viewport_target] != command_map[glue_target]
    command_map[viewport_target] = re.sub(r'C:[/\\]wk[/\\]ranvier-webcore[/\\]host[/\\]RanvierViewportGlue.cpp',
                                          (repo / 'host/RanvierViewportGlue.cpp').as_posix(), command_map[viewport_target])
    target, viewport_obj, code = compile_object(90, viewport_target)
    if code:
        raise SystemExit('RanvierViewportGlue failed')
objects = {unit: replacements[unit] for unit in patched_units}
screen_objects = {}
for index, unit in enumerate(screen_units, start=1):
    target, obj, code = compile_object(index, unit)
    if code:
        raise SystemExit(unit + ' failed')
    replacements[unit] = obj
    screen_objects[unit] = obj
(out / 'source-patches.json').write_text(json.dumps({'patches': patch_receipt, 'reusedPatchUnits': objects, 'recompiledUnits': screen_objects,
                                                      'reusedOwnerObject': {'patch': '0035', 'unit': dom_target, 'object': replacements[dom_target]}}, indent=2))
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))

extra = []
for name in ['RanvierSvgViewGlue', 'RanvierResourceGlue', 'RanvierEventGlue'] + ([] if viewport_obj else ['RanvierViewportGlue']):
    glue = glue_parent / (name + '.cpp.obj')
    borrowed[glue] = glue.stat().st_mtime_ns
    extra.append(glue.as_posix())
if viewport_obj:
    extra.append(Path(viewport_obj).as_posix())
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
assert parent_hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in parent_files}, 'parent candidates changed'
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.iterdir() if p.is_file()}
assert hashes['JavaScriptCore.dll'].startswith('95149cdc')
receipt = {'repoHead': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip(),
           'parent': str(parent), 'glueParent': str(glue_parent), 'recompiled': ['RanvierDomGlue.cpp'] + (['host/RanvierViewportGlue.cpp'] if viewport_obj else []) + [
               'host/RanvierWebCoreAbi.cpp', 'host/RanvierWebCoreDom.cpp', 'host/RanvierWebCoreUia.cpp', 'host/RanvierWebCoreD3D11.cpp'],
           'patchUnits': 'every unit patch 0037 reaches is the parent (B22) compile, newer than the patched files; the units of patch 0038 are compiled here',
           'sourceExemption': {'file': caret_source, 'reason': 'patch 0035 owner G09 object (native32-candidate-3 dom-7) reused',
                               'objectMtimeNs': Path(replacements[dom_target]).stat().st_mtime_ns, 'sourceMtimeNs': caret_mtime},
           'runtimeSha256': hashes}
(out / 'runtime-sha256.json').write_text(json.dumps(receipt, indent=2))
print('NATIVE40 HIGHLIGHT CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
