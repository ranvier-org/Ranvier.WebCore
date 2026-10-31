"""Private T01 font-readiness candidate: a parent candidate's WebCore objects with this tree's RanvierResourceGlue
compiled and WebCore relinked, and the four host units recompiled and relinked.
usage: build_fonts_candidate.py <fonts-candidate-N> [parent candidate dir] [parent head] [repo]
The parent (default native46-candidate-6, built from ed60fd4) must equal this tree in every file its borrowed objects
compile from: host/dom, gen, patches, config and the other host-glue sources. Its WebCore objects, RanvierDomGlue and the
host-glue objects its WebCore link names besides RanvierResourceGlue are borrowed read-only."""
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

repo = Path(sys.argv[4] if len(sys.argv) > 4 else 'C:/wk/native-fonts')
assert sys.argv[1].startswith('fonts-candidate-'), 'Build into artifacts/fonts-candidate-N'
out = repo / 'artifacts' / sys.argv[1]
parent = Path(sys.argv[2] if len(sys.argv) > 2 else 'C:/wk/native-cascade-shadow/artifacts/native46-candidate-6')
parent_head = sys.argv[3] if len(sys.argv) > 3 else 'ed60fd4'
build = Path('C:/wk/build-win-slim')
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'
link = (parent / 'webcore-link.rsp').read_text(encoding='utf-8')
glue_objects = sorted({path for path in re.findall(r'(\S+Ranvier[A-Za-z]+Glue\.cpp\.obj)', link)
                       if 'RanvierDomGlue' not in path and 'RanvierResourceGlue' not in path})
assert len(glue_objects) == 4, glue_objects
unchanged = ['host/dom', 'gen', 'patches', 'config']
for glue in glue_objects:
    stem = re.search(r'(Ranvier[A-Za-z]+Glue)\.cpp\.obj', glue).group(1)
    unchanged += ['host/' + stem + '.cpp', 'host/' + stem + '.h']
for path in unchanged:
    diff = subprocess.run(['git', 'diff', '--quiet', parent_head, '--', path], cwd=repo)
    assert diff.returncode == 0, path + ' changed since the parent ' + parent_head + ': its objects are stale'
status = subprocess.run(['git', 'status', '--porcelain', '-uall'], cwd='C:/wk/src', capture_output=True, text=True, check=True).stdout.splitlines()
changed_sources = [line[3:] for line in status if (Path('C:/wk/src') / line[3:]).is_file()]
# A source newer than the parent's link is exempt when it is a .cpp this build compiles no unit from, or a header whose
# working-tree diff is exactly carried by this tree's patch series (a re-applied, unchanged patch).
parent_link = (parent / 'runtime/WebCore.dll').stat().st_mtime_ns
series_lines = set()
for name in (repo / 'patches/series').read_text().splitlines():
    if name[:4].isdigit():
        series_lines.update(line for line in (repo / 'patches' / name).read_text(encoding='utf-8').splitlines()
                            if line[:1] in '+-' and not line.startswith(('+++', '---')))
source_exemptions = {}
for path in changed_sources:
    if os.stat(Path('C:/wk/src') / path).st_mtime_ns < parent_link:
        continue
    if path.endswith('.cpp'):
        source_exemptions[path] = 'implementation file; no unit of this build compiles it'
        continue
    current = subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--', path], capture_output=True, text=True, check=True).stdout
    lines = [line for line in current.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))]
    extra = [line for line in lines if line not in series_lines]
    # A virtual's final changed to override keeps every class layout and vtable slot.
    flips = {'+' + line[1:].replace(' final ', ' override ') for line in extra if line.startswith('-')}
    assert lines and all(line.startswith('-') or line in flips for line in extra), path + ' changed after the parent was linked beyond the series'
    source_exemptions[path] = 'header diff carried by the patch series plus %d final-to-override lines' % (len(extra) // 2)
print('SOURCE_EXEMPTIONS=' + json.dumps(source_exemptions), flush=True)
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
resource_target = 'Ranvier/host/RanvierResourceGlue.cpp.obj'
resource_command, count = re.subn(r"C:[/\\]wk[/\\]ranvier-webcore[/\\]host[/\\]dom[/\\]RanvierDomGlue.cpp",
                                  (repo / 'host/RanvierResourceGlue.cpp').as_posix(), command_map[glue_target])
assert count == 1, count
command_map[resource_target] = resource_command
target, resource_obj, code = compile_object(91, resource_target)
if code:
    raise SystemExit('RanvierResourceGlue failed')
shutil.copyfile(parent / 'source-patches.json', out / 'source-patches.json')
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))
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
(out / 'runtime-sha256.json').write_text(json.dumps({'repoHead': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip(),
    'dirty': subprocess.run(['git', 'status', '--porcelain'], cwd=repo, capture_output=True, text=True).stdout.splitlines(),
    'parent': str(parent), 'parentHead': parent_head, 'sourceExemptions': source_exemptions, 'hostGlueObjects': glue_objects, 'recompiled': ['host/RanvierResourceGlue.cpp', 'host/RanvierWebCoreAbi.cpp', 'host/RanvierWebCoreDom.cpp', 'host/RanvierWebCoreUia.cpp', 'host/RanvierWebCoreD3D11.cpp'],
    'runtimeSha256': hashes}, indent=2))
print('FONTS CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
