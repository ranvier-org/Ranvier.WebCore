"""Private crypto (B22) candidate: G09's native32-candidate-3 (Source 0000-0035, its own UnifiedSource-dom-7 and glue
compiles over D13's forms-candidate-4) with this tree's regenerated RanvierDomGlue and every unit patch 0037 reaches
compiled into WebCore and the four host units recompiled. Borrows build-win-slim, native32-candidate-3's runtime and its 111 replacement objects (dom-7 is
the 0035 patch owner's object) and forms-candidate-4's four other glue objects, all read-only."""
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
parser.add_argument('--repo', default='C:/wk/native-crypto')
parser.add_argument('--parent', default='C:/wk/native-caret/artifacts/native32-candidate-3')
arguments = parser.parse_args()
repo = Path(arguments.repo)
parent = Path(arguments.parent)
glue_parent = Path('C:/wk/native-forms/artifacts/forms-candidate-4')
build = Path('C:/wk/build-win-slim')
assert arguments.name.startswith('native36-candidate-'), 'Build into artifacts/native36-candidate-N'
out = repo / 'artifacts' / arguments.name
assert not out.exists(), 'Build into a new versioned directory'
for unchanged in ['host/RanvierSvgViewGlue.cpp', 'host/RanvierResourceGlue.cpp', 'host/RanvierEventGlue.cpp', 'host/RanvierEventGlue.h',
                  'host/RanvierViewportGlue.cpp', 'host/RanvierViewportGlue.h']:
    diff = subprocess.run(['git', 'diff', '--quiet', 'b8acc27', '--', unchanged], cwd=repo)
    assert diff.returncode == 0, unchanged + ' changed since b8acc27: the borrowed glue object is stale'
# The borrowed objects postdate the newest change to the patched WebKit source, except Document.cpp (patch 0035),
# whose unified source is the patch owner's (G09) compile, made after the patch.
status = subprocess.run(['git', 'status', '--porcelain', '-uall'], cwd='C:/wk/src', capture_output=True, text=True, check=True).stdout.splitlines()
caret_source = 'Source/WebCore/dom/Document.cpp'
changed_sources = [line[3:] for line in status if (Path('C:/wk/src') / line[3:]).is_file()]
caret_mtime = os.stat(Path('C:/wk/src') / caret_source).st_mtime_ns
# Patch 0037 (D14) postdates the parent's objects: every unit whose recorded dependencies include a file it changes
# is recompiled here, after checking that C:/wk/src carries the patch's lines.
patch_0037 = repo / 'patches/0037-frame-loader-client-form-submission-hook.patch'
if not patch_0037.exists():
    patch_0037 = Path('C:/wk/native-formsubmit/patches/0037-frame-loader-client-form-submission-hook.patch')
patches = sorted(p.name for p in (repo / 'patches').glob('*.patch')) + [patch_0037.name]
assert sorted(set(patches))[-1].startswith('0037-'), 'a source patch after 0037 needs its owner objects: ' + patches[-1]
def hunk_lines(text):
    return [line for line in text.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))]
def contains(lines, part):
    index = 0
    for line in lines:
        if index < len(part) and line == part[index]:
            index += 1
    return index == len(part)
patch_receipt = {}
recompiled_sources = set()
text = patch_0037.read_text(encoding='utf-8')
for section in text.split('\ndiff --git ')[0 if text.startswith('diff --git ') else 1:]:
    name = re.search(r'a/(\S+) b/', section).group(1)
    current = subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--', name], capture_output=True, text=True, check=True).stdout
    assert contains(hunk_lines(current), hunk_lines(section)), name + ' does not carry ' + patch_0037.name
    recompiled_sources.add(name)
    patch_receipt.setdefault(patch_0037.name, {'sha256': hashlib.sha256(patch_0037.read_bytes()).hexdigest(), 'files': {}})['files'][name] = hunk_lines(section)
scan = subprocess.run([sys.executable, '-I', 'C:/wk/t06-artifacts/units_for_headers.py', '--json', *sorted(recompiled_sources)],
                      capture_output=True, text=True, check=True)
patched_units = json.loads(scan.stdout)['all']
newest_source = max(os.stat(Path('C:/wk/src') / path).st_mtime_ns for path in changed_sources
                    if path != caret_source and path not in recompiled_sources)
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
assert len(replacements) == 111
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in replacements.values()}
dom_target = next(key for key in replacements if key.endswith('/UnifiedSource-dom-7.cpp.obj'))
assert Path(replacements[dom_target]).stat().st_mtime_ns > caret_mtime, 'the borrowed dom-7 object predates patch 0035'
assert all(path.stat().st_mtime_ns > newest_source for path in borrowed if 'forms-candidate-4' in str(path) or 'native32' in str(path)), \
    'WebKit source changed after the borrowed objects'
glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
assert glue_target in replacements
build_files = {p: p.stat().st_mtime_ns for p in [build / 'CMakeCache.txt', build / 'build.ninja', build / '.ninja_log', build / '.ninja_deps', build / 'bin/WebCore.dll'] if p.exists()}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')
command_map = {}
for unit in patched_units:
    assert unit in replacements or (build / unit).exists(), unit
assert dom_target not in patched_units
for command in commands([glue_target, *patched_units]):
    if 'clang-cl.exe' in command:
        output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
        if output:
            command_map[normalize(output.group(1) or output.group(2))] = command
target, obj, code = compile_object(0, glue_target)
if code:
    raise SystemExit('RanvierDomGlue failed')
replacements[glue_target] = obj
from concurrent.futures import ThreadPoolExecutor
objects = {}
with ThreadPoolExecutor(max_workers=6) as pool:
    for target, obj, code in pool.map(lambda item: compile_object(item[0], item[1]), enumerate(patched_units, start=1)):
        if code:
            stop.set()
            raise SystemExit(target + ' failed')
        replacements[target] = obj
        objects[target] = obj
(out / 'source-patches.json').write_text(json.dumps({'patches': patch_receipt, 'recompiledUnits': objects,
                                                      'reusedOwnerObject': {'patch': '0035', 'unit': dom_target, 'object': replacements[dom_target]}}, indent=2))
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))

extra = []
for name in ['RanvierSvgViewGlue', 'RanvierResourceGlue', 'RanvierEventGlue', 'RanvierViewportGlue']:
    glue = glue_parent / (name + '.cpp.obj')
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
assert parent_hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in parent_files}, 'parent candidates changed'
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.iterdir() if p.is_file()}
assert hashes['JavaScriptCore.dll'].startswith('95149cdc')
receipt = {'repoHead': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip(),
           'parent': str(parent), 'glueParent': str(glue_parent), 'recompiled': ['RanvierDomGlue.cpp'] + [
               'host/RanvierWebCoreAbi.cpp', 'host/RanvierWebCoreDom.cpp', 'host/RanvierWebCoreUia.cpp', 'host/RanvierWebCoreD3D11.cpp'],
           'sourceExemption': {'file': caret_source, 'reason': 'patch 0035 owner G09 object (native32-candidate-3 dom-7) reused',
                               'objectMtimeNs': Path(replacements[dom_target]).stat().st_mtime_ns, 'sourceMtimeNs': caret_mtime},
           'runtimeSha256': hashes}
(out / 'runtime-sha256.json').write_text(json.dumps(receipt, indent=2))
print('NATIVE36 CRYPTO CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
