"""Private B09 notification candidate: a parent candidate's WebCore objects, with this tree's RanvierNotificationGlue
compiled and linked into WebCore beside the parent's glue objects, and the four host units recompiled and relinked.
usage: build_notification_candidate.py <notification-candidate-N> <parent candidate dir> [repo]
The parent (native46-candidate-6, built at 09732f9) has the binary inputs of batch-1 d247ceb0 apart from this
tree's host changes; its WebCore objects and glue objects are borrowed read-only. C:/wk/src carries patch 0040
(EmptyClients.h), which the parent predates; the recompiled units that include EmptyClients.h pick it up."""
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

repo = Path(sys.argv[3] if len(sys.argv) > 3 else 'C:/wk/native-notifications')
assert sys.argv[1].startswith('notification-candidate-'), 'Build into artifacts/notification-candidate-N'
out = repo / 'artifacts' / sys.argv[1]
parent = Path(sys.argv[2])
build = Path('C:/wk/build-win-slim')
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'

parent_patches = json.loads((parent / 'source-patches.json').read_text())
series = [line for line in (repo / 'patches/series').read_text().splitlines() if line[:4].isdigit() and line[:4] >= '0035']
assert {name[:4] for name in series} <= {name[:4] for name in parent_patches['patches']}, series
# A C:/wk/src patch past this tree's series, reached only through the recompiled units.
empty_clients = 'Source/WebCore/loader/EmptyClients.h'
src_diff = subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--', empty_clients], capture_output=True, text=True, check=True).stdout
extra_patches = {'0040': {'file': empty_clients, 'diffSha256': hashlib.sha256(src_diff.encode()).hexdigest(),
                          'changedLines': [line for line in src_diff.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))],
                          'reachedBy': [name for name in ['RanvierWebCoreAbi.cpp', 'RanvierWebCoreDom.cpp', 'RanvierWebCoreUia.cpp',
                                                          'RanvierWebCoreD3D11.cpp', 'RanvierNotificationGlue.cpp']
                                        if 'EmptyClients.h' in (repo / 'host' / name).read_text(encoding='utf-8')]}}

link = (parent / 'webcore-link.rsp').read_text(encoding='utf-8')
glue_objects = sorted({path for path in re.findall(r'(\S+Ranvier[A-Za-z]+Glue\.cpp\.obj)', link) if 'RanvierDomGlue' not in path})
assert len(glue_objects) == 5 and any('090-RanvierInspectGlue' in path for path in glue_objects), glue_objects

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
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in [*replacements.values(), *glue_objects]}
build_files = {p: p.stat().st_mtime_ns for p in [build / 'CMakeCache.txt', build / 'build.ninja', build / '.ninja_log', build / '.ninja_deps', build / 'bin/WebCore.dll'] if p.exists()}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)

glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
command_map = {}
for command in commands([glue_target]):
    if 'clang-cl.exe' in command:
        output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
        if output:
            command_map[normalize(output.group(1) or output.group(2))] = command
glue_target_new = 'Ranvier/host/RanvierNotificationGlue.cpp.obj'
glue_command, count = re.subn(r'C:[/\\]wk[/\\]ranvier-webcore[/\\]host[/\\]dom[/\\]RanvierDomGlue.cpp',
                              (repo / 'host/RanvierNotificationGlue.cpp').as_posix(), command_map[glue_target])
assert count == 1, count
command_map[glue_target_new] = glue_command
target, glue_obj, code = compile_object(95, glue_target_new)
if code:
    raise SystemExit('RanvierNotificationGlue failed')
(out / 'source-patches.json').write_text(json.dumps({'patches': parent_patches['patches'], 'parent': str(parent), 'parentReceipt': parent_patches,
                                                     'srcPatchesPastSeries': extra_patches, 'hostGlueObjects': glue_objects,
                                                     'recompiledUnits': {glue_target_new: glue_obj}}, indent=2))
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))
extra = [Path(path).as_posix() for path in glue_objects] + [Path(glue_obj).as_posix()]
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
print('NOTIFICATION CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
