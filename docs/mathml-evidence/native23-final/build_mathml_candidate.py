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
producer = Path('C:/wk/native-svg-paint/artifacts/native21-candidate-0032')
build = Path('C:/wk/build-win-slim')
out = repo / 'artifacts' / (sys.argv[1] if len(sys.argv) > 1 else 'native21-candidate')
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'
runtime = out / 'runtime'
runtime.mkdir(parents=True, exist_ok=True)
shutil.copytree(producer / 'runtime', runtime, dirs_exist_ok=True)
parent_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (producer / 'runtime').glob('*') if p.is_file()}
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
tree = ast.parse(Path('C:/wk/native-cssom-detached-context/artifacts/build_context_candidate.py').read_text())
names = {'normalize', 'commands', 'execute', 'compile_object', 'link_command'}
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(functions) == len(names)
exec(compile(ast.Module(body=functions, type_ignores=[]), '<reviewed_private_build_helpers>', 'exec'), globals())
lines = (build / 'build.ninja').read_text().splitlines()

replacements = json.loads((producer / 'replacement-objects.json').read_text())
assert len(replacements) == 56
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in replacements.values()}
glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
unified = 'Source/WebCore/CMakeFiles/WebCore.dir/__/__/WebCore/DerivedSources/unified-sources/'
engine_targets = []
cached = {build / target: (build / target).stat().st_mtime_ns for target in [glue_target, *engine_targets]}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')
# Shadow the headers that the next producer's H05 patch changes in the shared source, so these objects keep the
# class layouts of the borrowed objects and of this series.
h05_overlay = {'ImageLoader.h': 'Source/WebCore/loader/ImageLoader.h', 'HTMLImageElement.h': 'Source/WebCore/html/HTMLImageElement.h',
               'SVGImageElement.h': 'Source/WebCore/svg/SVGImageElement.h'}
for header, source in h05_overlay.items():
    pristine = subprocess.run(['git', '-C', 'C:/wk/src', 'show', 'HEAD:' + source], capture_output=True, check=True).stdout
    (private_headers.parent / header).write_bytes(pristine)
command_map = {}
for command in commands([glue_target, *engine_targets]):
    if 'clang-cl.exe' in command:
        output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
        if output:
            command_map[normalize(output.group(1) or output.group(2))] = command
for index, target in enumerate([glue_target, *engine_targets]):
    target, obj, code = compile_object(index, target)
    if code:
        raise SystemExit('Native21 candidate compilation failed: ' + target)
    replacements[target] = obj
assert len(replacements) == 56
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))

glue_command = next(c for c in commands([glue_target]) if 'clang-cl.exe' in c and 'RanvierDomGlue.cpp' in c)
helper_object = out / 'RanvierSvgViewGlue.cpp.obj'
helper_command = re.sub(r' -c -- .*$', ' -c -- ' + (repo / 'host/RanvierSvgViewGlue.cpp').as_posix(), glue_command)
helper_command = re.sub(r'/Fo(?:"[^"]+"|\S+)', '/Fo' + helper_object.as_posix(), helper_command)
helper_command = re.sub(r'/Fd(?:"[^"]+"|\S+)', '/Fd' + (out / 'RanvierSvgViewGlue.cpp.pdb').as_posix(), helper_command)
if execute(helper_command, 'svg-view-helper'):
    raise SystemExit(1)
if execute(link_command('WebCore') + ' ' + helper_object.as_posix() + ' Dwrite.lib', 'webcore-link'):
    raise SystemExit(1)

host_target = r'Tools\TestWebKitAPI\CMakeFiles\RanvierWebCoreHost.dir\RanvierAbi\RanvierWebCoreAbi.cpp.obj'
cached[build / host_target] = (build / host_target).stat().st_mtime_ns
host_command = next(c for c in commands([host_target]) if 'clang-cl.exe' in c and 'RanvierWebCoreAbi.cpp' in c)
flags = re.findall(r'^((?:USE|ENABLE)_[A-Z0-9_]+):BOOL=(ON|OFF|1|0|TRUE|FALSE)$', cache, re.M)
flag_arguments = ' '.join('/DRV_CAP_' + name + '=' + ('1' if value in ['ON', '1', 'TRUE'] else '0') for name, value in flags)
(out / 'configured-flags.json').write_text(json.dumps(dict(flags), indent=2))
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

assert borrowed == {path: path.stat().st_mtime_ns for path in borrowed}, 'Borrowed Native19 objects changed'
assert cached == {path: path.stat().st_mtime_ns for path in cached}, 'Cached build outputs changed'
assert parent_hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (producer / 'runtime').glob('*') if p.is_file()}, 'Frozen parent runtime changed'
hashes = {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest() for name in ['RanvierWebCoreHost.dll', 'WebCore.dll', 'JavaScriptCore.dll']}
assert hashes['JavaScriptCore.dll'].startswith('95149cdc')
(out / 'runtime-sha256.json').write_text(json.dumps(hashes, indent=2))
print('MATHML PRIVATE CANDIDATE READY: ' + str(runtime), flush=True)
