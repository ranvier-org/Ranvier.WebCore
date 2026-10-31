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
parent = Path('C:/wk/native-cssom-detached-context')
producer = Path('C:/wk/native-svg-geometry')
build = Path('C:/wk/build-win-slim')
coordinate_probe = '--coordinate-probe' in sys.argv
before_owner = '--before-owner' in sys.argv
out = repo / ('artifacts/svg-coordinate-probe-before' if before_owner else 'artifacts/svg-coordinate-probe' if coordinate_probe else 'artifacts/svg-surfaces-candidate')
runtime = out / 'runtime'
runtime.mkdir(parents=True, exist_ok=True)
shutil.copytree(producer / 'artifacts/svg-geometry-candidate/runtime', runtime, dirs_exist_ok=True)
cache = (build / 'CMakeCache.txt').read_text()
ninja = re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$', cache, re.M).group(1)
compiler = Path(re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.+)$', cache, re.M).group(1))
glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
replacements = json.loads((producer / 'artifacts/svg-geometry-candidate/replacement-objects.json').read_text())
assert len(replacements) == 49 and glue_target in replacements
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in replacements.values()}
cached = {build / target: (build / target).stat().st_mtime_ns for target in replacements}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')
tree = ast.parse((repo / 'scripts/build.py').read_text())
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'toolchain_env')
scope = dict(os=os, pathlib=__import__('pathlib'), subprocess=subprocess, sys=sys,
             windows=True, arch='x64', system='win', args=types.SimpleNamespace(tool_path=[]),
             llvm=compiler.parent, vcpkg=Path('C:/wk/vcpkg'), pins=json.loads((repo / 'pins.json').read_text()))
exec(compile(ast.Module(body=[function], type_ignores=[]), '<toolchain_env>', 'exec'), scope)
env = scope['toolchain_env']()
stop = threading.Event()
tree = ast.parse((parent / 'artifacts/build_context_candidate.py').read_text())
names = {'normalize', 'commands', 'execute', 'compile_object', 'link_command'}
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(functions) == len(names)
exec(compile(ast.Module(body=functions, type_ignores=[]), '<reviewed_private_build_helpers>', 'exec'), globals())
if coordinate_probe:
    private_host = out / 'probe/host'
    (private_host / 'dom').mkdir(parents=True, exist_ok=True)
    for name in ['RanvierWebCoreAbi.h', 'RanvierWebCoreDom.h', 'dom/RanvierDomGlue.h']:
        shutil.copyfile(repo / 'host' / name, private_host / name)
    source = (repo / 'host/dom/RanvierDomGlue.cpp').read_text()
    source += '''
extern "C" __declspec(dllexport) int ranvier_svg_probe_window_metrics(RvNode* target, double* values)
{
    if (!target || !values)
        return -1;
    auto* window = nodeOf(target)->document().window();
    if (!window)
        return -1;
    values[0] = window->innerWidth();
    values[1] = window->innerHeight();
    values[2] = window->devicePixelRatio();
    return 0;
}
'''
    (private_host / 'dom/RanvierDomGlue.cpp').write_text(source)
    compile_source = ast.get_source_segment((parent / 'artifacts/build_context_candidate.py').read_text(), next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'compile_object'))
    compile_source = compile_source.replace("(repo / 'host/dom/RanvierDomGlue.cpp').as_posix()", "(private_host / 'dom/RanvierDomGlue.cpp').as_posix()")
    exec(compile(compile_source, '<private_coordinate_probe_compile>', 'exec'), globals())
lines = (build / 'build.ninja').read_text().splitlines()
engine_targets = [] if before_owner else ['Source/WebCore/CMakeFiles/WebCore.dir/__/__/WebCore/DerivedSources/unified-sources/UnifiedSource-svg-13.cpp.obj', 'Source/WebCore/CMakeFiles/WebCore.dir/__/__/WebCore/DerivedSources/unified-sources/UnifiedSource-rendering-30.cpp.obj']
for target in engine_targets:
    cached[build / target] = (build / target).stat().st_mtime_ns
command_map = {}
for command in commands([glue_target, *engine_targets]):
    if 'clang-cl.exe' in command:
        output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
        if output:
            command_map[normalize(output.group(1) or output.group(2))] = command
for index, target in enumerate([glue_target, *engine_targets]):
    target, obj, code = compile_object(index, target)
    if code:
        raise SystemExit('SVG candidate compilation failed')
    replacements[target] = obj
assert len(replacements) == 49 + len(engine_targets)
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))
lines = (build / 'build.ninja').read_text().splitlines()
if execute(link_command('WebCore') + ' Dwrite.lib', 'webcore-link'):
    raise SystemExit(1)
host_target = r'Tools\TestWebKitAPI\CMakeFiles\RanvierWebCoreHost.dir\RanvierAbi\RanvierWebCoreAbi.cpp.obj'
host_commands = [command for command in commands([host_target]) if 'clang-cl.exe' in command and 'RanvierWebCoreAbi.cpp' in command]
assert len(host_commands) == 1
host_objects = []
for filename in ['RanvierWebCoreAbi.cpp', 'RanvierWebCoreDom.cpp', 'RanvierWebCoreUia.cpp', 'RanvierWebCoreD3D11.cpp']:
    if filename not in ['RanvierWebCoreDom.cpp', 'RanvierWebCoreAbi.cpp']:
        previous = ((producer / 'artifacts/svg-geometry-candidate') if filename == 'RanvierWebCoreAbi.cpp'
                    else Path('C:/wk/native-typed-style-maps/artifacts/typed-map-entries')) / (filename + '.obj')
        assert previous.is_file()
        host_objects.append(previous.as_posix())
        continue
    command = re.sub(r'C:[/\\]wk[/\\]src[/\\]Tools[/\\]TestWebKitAPI[/\\]RanvierAbi[/\\]RanvierWebCoreAbi.cpp',
                     (repo / 'host' / filename).as_posix(), host_commands[0])
    obj = out / (filename + '.obj')
    command, count = re.subn(r'/Fo(?:"[^"]+"|\S+)', '/Fo' + obj.as_posix(), command)
    assert count == 1
    command = re.sub(r'/Fd(?:"[^"]+"|\S+)', '/Fd' + (out / (filename + '.pdb')).as_posix(), command)
    if execute(command, filename):
        raise SystemExit(1)
    host_objects.append(obj.as_posix())
if execute(link_command('RanvierWebCoreHost', host_objects) + ' Uiautomationcore.lib Ole32.lib OleAut32.lib Comctl32.lib', 'host-link'):
    raise SystemExit(1)
assert borrowed == {path: path.stat().st_mtime_ns for path in borrowed}, 'Parent outputs changed'
assert cached == {path: path.stat().st_mtime_ns for path in cached}, 'Cached outputs changed'
hashes = {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest() for name in ['RanvierWebCoreHost.dll', 'WebCore.dll', 'JavaScriptCore.dll']}
(out / 'runtime-sha256.json').write_text(json.dumps(hashes, indent=2))
print('PRIVATE SVG SURFACES CANDIDATE READY: ' + str(runtime), flush=True)
