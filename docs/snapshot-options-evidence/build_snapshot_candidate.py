"""Private R12 candidate: a B06 media candidate's WebCore objects (patch 0043's unit included), with this tree's
RanvierResourceGlue compiled and WebCore relinked, and the four host units recompiled and relinked.
usage: build_snapshot_candidate.py <snapshot-candidate-N> --parent DIR --parent-head SHA [--repo DIR]
The parent's objects and host-glue objects are borrowed read-only, and their inputs must equal --parent-head. Every
patch of this tree's series past 0034 must be carried by C:/wk/src and covered by the parent's receipt."""
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
parser.add_argument('--repo', default='C:/wk/native-snapshot-options')
parser.add_argument('--parent', required=True)
parser.add_argument('--parent-head', required=True)
arguments = parser.parse_args()
repo = Path(arguments.repo)
parent = Path(arguments.parent)
build = Path('C:/wk/build-win-slim')
src = Path('C:/wk/src')
assert arguments.name.startswith('snapshot-candidate-'), 'Build into artifacts/snapshot-candidate-N'
out = repo / 'artifacts' / arguments.name
assert not out.exists(), 'Build into a new versioned directory'
parent_head = arguments.parent_head
UNIT = 'Source/WebCore/CMakeFiles/WebCore.dir/__/__/WebCore/DerivedSources/unified-sources/UnifiedSource-Modules-6.cpp.obj'
GLUE = 'RanvierResourceGlue'

# Borrowed inputs equal the parent's tree.
for unchanged in ['host/dom', 'gen', 'config', 'patches']:
    diff = subprocess.run(['git', 'diff', '--quiet', parent_head, '--', unchanged], cwd=repo)
    assert diff.returncode == 0, unchanged + ' changed since the parent ' + parent_head + ': its objects are stale'
link = (parent / 'webcore-link.rsp').read_text(encoding='utf-8')
glue_objects = sorted({path for path in re.findall(r'(\S+Ranvier[A-Za-z]+Glue\.cpp\.obj)', link) if 'RanvierDomGlue' not in path and GLUE not in path})
assert len(glue_objects) == 4, glue_objects
for glue in glue_objects:
    stem = re.search(r'(Ranvier[A-Za-z]+Glue)\.cpp\.obj', glue).group(1)
    diff = subprocess.run(['git', 'diff', '--quiet', parent_head, '--', 'host/' + stem + '.cpp', 'host/' + stem + '.h'], cwd=repo)
    assert diff.returncode == 0, stem + ' changed since the parent: the borrowed glue object is stale'

# Every series patch past 0034 is carried by C:/wk/src; all but 0043 are covered by the parent.
parent_patches = json.loads((parent / 'source-patches.json').read_text(encoding='utf-8'))
series = [line for line in (repo / 'patches/series').read_text(encoding='utf-8').splitlines() if line[:4].isdigit() and line[:4] >= '0035']
assert {name[:4] for name in series} <= {name[:4] for name in parent_patches['patches']}, series
patch_receipt = {}
for name in series:
    text = (repo / 'patches' / name).read_text(encoding='utf-8')
    patch_receipt[name] = {'sha256': hashlib.sha256((repo / 'patches' / name).read_bytes()).hexdigest(), 'files': []}
    for section in text.split('\ndiff --git ')[0 if text.startswith('diff --git ') else 1:]:
        target = re.search(r'a/(\S+) b/', section).group(1)
        hunk = [line for line in section.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))]
        if '\nnew file mode ' in '\n' + section:
            current = (src / target).read_text(encoding='utf-8').splitlines()
            assert ['+' + line for line in current] == hunk, target + ' is not the new file of ' + name
        else:
            current = subprocess.run(['git', '-C', str(src), 'diff', '--', target], capture_output=True, text=True, check=True).stdout
            lines = [line for line in current.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))]
            index = 0
            for line in lines:
                if index < len(hunk) and line == hunk[index]:
                    index += 1
            assert index == len(hunk), target + ' does not carry ' + name
        patch_receipt[name]['files'].append(target)
assert UNIT in json.loads((parent / 'replacement-objects.json').read_text(encoding='utf-8')), 'the parent lacks the patch 0043 unit'

runtime = out / 'runtime'
runtime.mkdir(parents=True)
shutil.copytree(parent / 'runtime', runtime, dirs_exist_ok=True)
parent_files = [p for p in parent.rglob('*') if p.is_file() and p.suffix in ('.obj', '.dll', '.lib', '.json')]
parent_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in parent_files}
cache = (build / 'CMakeCache.txt').read_text()
compiler = Path(re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.+)$', cache, re.M).group(1))
tree = ast.parse((repo / 'scripts/build.py').read_text(encoding='utf-8'))
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'toolchain_env')
scope = dict(os=os, pathlib=__import__('pathlib'), subprocess=subprocess, sys=sys,
             windows=True, arch='x64', system='win', args=types.SimpleNamespace(tool_path=[]),
             llvm=compiler.parent, vcpkg=Path('C:/wk/vcpkg'), pins=json.loads((repo / 'pins.json').read_text(encoding='utf-8')))
exec(compile(ast.Module(body=[function], type_ignores=[]), '<toolchain_env>', 'exec'), scope)
env = scope['toolchain_env']()
ninja = re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$', cache, re.M).group(1)
stop = threading.Event()
helpers = ast.parse(Path('C:/wk/native-cssom-detached-context/artifacts/build_context_candidate.py').read_text(encoding='utf-8'))
names = {'normalize', 'commands', 'execute', 'compile_object', 'link_command'}
functions = [node for node in helpers.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(functions) == len(names)
exec(compile(ast.Module(body=functions, type_ignores=[]), '<reviewed_private_build_helpers>', 'exec'), globals())
lines = (build / 'build.ninja').read_text().splitlines()
replacements = json.loads((parent / 'replacement-objects.json').read_text(encoding='utf-8'))
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in replacements.values()}
build_files = {p: p.stat().st_mtime_ns for p in [build / 'CMakeCache.txt', build / 'build.ninja', build / '.ninja_log', build / '.ninja_deps', build / 'bin/WebCore.dll'] if p.exists()}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')

glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
assert glue_target in replacements
command_map = {}
for command in commands([glue_target]):
    if 'clang-cl.exe' in command:
        output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
        if output:
            command_map[normalize(output.group(1) or output.group(2))] = command
resource_target = 'Ranvier/host/' + GLUE + '.cpp.obj'
resource_command, count = re.subn(r'C:[/\\]wk[/\\]ranvier-webcore[/\\]host[/\\]dom[/\\]RanvierDomGlue.cpp',
                                  (repo / 'host' / (GLUE + '.cpp')).as_posix(), command_map[glue_target])
assert count == 1, count
command_map[resource_target] = resource_command
target, resource_obj, code = compile_object(91, resource_target)
if code:
    raise SystemExit(GLUE + ' failed')
(out / 'source-patches.json').write_text(json.dumps({'patches': patch_receipt, 'parent': str(parent), 'parentReceipt': parent_patches,
                                                     'hostGlueObjects': glue_objects, 'recompiledUnits': {resource_target: resource_obj},
                                                     'patchUnitsBorrowed': {UNIT: replacements[UNIT]}}, indent=2), encoding='utf-8')
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2), encoding='utf-8')
extra = [Path(resource_obj).as_posix()]
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
receipt = {'repoHead': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip(),
           'dirty': subprocess.run(['git', 'status', '--porcelain'], cwd=repo, capture_output=True, text=True).stdout.splitlines(),
           'parent': str(parent), 'parentRepoHead': parent_head, 'hostGlueObjects': glue_objects,
           'recompiled': ['host/' + GLUE + '.cpp', 'host/RanvierWebCoreAbi.cpp', 'host/RanvierWebCoreDom.cpp', 'host/RanvierWebCoreUia.cpp', 'host/RanvierWebCoreD3D11.cpp'],
           'runtimeSha256': hashes}
(out / 'runtime-sha256.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print('SNAPSHOT CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
