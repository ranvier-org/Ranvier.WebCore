"""Private G14 candidate: a parent candidate's WebCore objects (its replacement-objects.json, RanvierDomGlue included)
with this tree's RanvierViewportGlue compiled into WebCore and the four host units recompiled. Borrows build-win-slim,
the parent's runtime and objects and forms-candidate-4's three other glue objects, all read-only. The parent's tree
must equal this tree in every file its objects compile from, apart from RanvierViewportGlue and the host units."""
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
parser.add_argument('--repo', default='C:/wk/native-coords')
parser.add_argument('--parent', default='C:/wk/native-elinternals/artifacts/ei-candidate-4')
arguments = parser.parse_args()
repo = Path(arguments.repo)
parent = Path(arguments.parent)
glue_parent = Path('C:/wk/native-forms/artifacts/forms-candidate-4')
build = Path('C:/wk/build-win-slim')
assert arguments.name.startswith('coords-candidate-'), 'Build into artifacts/coords-candidate-N'
out = repo / 'artifacts' / arguments.name
assert not out.exists(), 'Build into a new versioned directory'
parent_receipt = json.loads((parent / 'runtime-sha256.json').read_text(encoding='utf-8'))
parent_head = parent_receipt['repoHead']
for unchanged in ['host/RanvierSvgViewGlue.cpp', 'host/RanvierResourceGlue.cpp', 'host/RanvierEventGlue.cpp', 'host/RanvierEventGlue.h']:
    diff = subprocess.run(['git', 'diff', '--quiet', 'b8acc27', '--', unchanged], cwd=repo)
    assert diff.returncode == 0, unchanged + ' changed since b8acc27: the borrowed glue object is stale'
# The parent's RanvierDomGlue object and unit objects stay valid while their inputs equal the parent's tree.
for unchanged in ['host/dom', 'gen', 'patches', 'config']:
    diff = subprocess.run(['git', 'diff', '--quiet', parent_head, '--', unchanged], cwd=repo)
    assert diff.returncode == 0, unchanged + ' changed since the parent ' + parent_head + ': its objects are stale'
parent_patches = json.loads((parent / 'source-patches.json').read_text(encoding='utf-8'))
for name, patch in parent_patches['patches'].items():
    for path in patch['files']:
        current = subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--', path], capture_output=True, text=True, check=True).stdout
        assert current, path + ' no longer carries ' + name
status = subprocess.run(['git', 'status', '--porcelain', '-uall'], cwd='C:/wk/src', capture_output=True, text=True, check=True).stdout.splitlines()
changed_sources = [line[3:] for line in status if (Path('C:/wk/src') / line[3:]).is_file()]
newest_source = max(os.stat(Path('C:/wk/src') / path).st_mtime_ns for path in changed_sources)
assert newest_source < (parent / 'runtime/WebCore.dll').stat().st_mtime_ns, 'C:/wk/src changed after the parent was linked'
runtime = out / 'runtime'
runtime.mkdir(parents=True)
shutil.copytree(parent / 'runtime', runtime, dirs_exist_ok=True)
replacements = json.loads((parent / 'replacement-objects.json').read_text(encoding='utf-8'))
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in replacements.values()}
parent_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in borrowed}
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
build_files = {p: p.stat().st_mtime_ns for p in [build / 'CMakeCache.txt', build / 'build.ninja', build / '.ninja_log', build / '.ninja_deps', build / 'bin/WebCore.dll'] if p.exists()}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')
glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
assert glue_target in replacements
viewport_target = 'Ranvier/host/RanvierViewportGlue.cpp.obj'
command_map = {}
for command in commands([glue_target]):
    if 'clang-cl.exe' in command:
        output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
        if output:
            command_map[normalize(output.group(1) or output.group(2))] = command
command_map[viewport_target] = command_map[glue_target].replace('host/dom/RanvierDomGlue.cpp', 'host/RanvierViewportGlue.cpp').replace(
    'host\\dom\\RanvierDomGlue.cpp', 'host\\RanvierViewportGlue.cpp')
assert command_map[viewport_target] != command_map[glue_target]
command_map[viewport_target] = re.sub(r'C:[/\\]wk[/\\]ranvier-webcore[/\\]host[/\\]RanvierViewportGlue.cpp',
                                      (repo / 'host/RanvierViewportGlue.cpp').as_posix(), command_map[viewport_target])
target, viewport_obj, code = compile_object(90, viewport_target)
if code:
    raise SystemExit('RanvierViewportGlue failed')
extra = []
for name in ['RanvierSvgViewGlue', 'RanvierResourceGlue', 'RanvierEventGlue']:
    glue = glue_parent / (name + '.cpp.obj')
    borrowed[glue] = glue.stat().st_mtime_ns
    extra.append(glue.as_posix())
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
assert parent_hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in map(Path, replacements.values())}, 'parent objects changed'
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.iterdir() if p.is_file()}
assert hashes['JavaScriptCore.dll'].startswith('95149cdc')
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2), encoding='utf-8')
shutil.copyfile(parent / 'source-patches.json', out / 'source-patches.json')
receipt = {'repoHead': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip(),
           'parent': str(parent), 'parentRepoHead': parent_head, 'glueParent': str(glue_parent),
           'recompiled': ['host/RanvierViewportGlue.cpp', 'host/RanvierWebCoreAbi.cpp', 'host/RanvierWebCoreDom.cpp', 'host/RanvierWebCoreUia.cpp', 'host/RanvierWebCoreD3D11.cpp'],
           'borrowedFromParent': 'replacement-objects.json and source-patches.json (unit objects, RanvierDomGlue, patch receipts)',
           'sourceExemption': parent_receipt.get('sourceExemption'),
           'runtimeSha256': hashes}
(out / 'runtime-sha256.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print('COORDINATE CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
