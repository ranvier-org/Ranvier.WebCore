"""Private vm2 candidate: batch6-candidate-diag1 (batch 6 without patch 0052) with UnifiedSource-dom-10 compiled from a
private unified source whose EventLoop.cpp is an overlay file, and WebCore relinked from diag1's link response with that
one object replaced. Every other runtime library, RanvierWebCoreHost.dll included, is diag1's, unless VM2_HOST=1: then the
five host units of this tree are recompiled with diag1's host commands and the host is relinked.
The compile command is the pointer-build command batch6-candidate-1 used for the unit (build_batch6_candidate.py).
usage: build_vm2_overlay.py <vm2-name> <overlay EventLoop.cpp> [repo]
Prints the disassembly SHA-256 of the compiled unit; an overlay equal to C:/wk/src's EventLoop.cpp reproduces
batch5-candidate-1's dom-10 disassembly (c10de946...)."""
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

name, overlay_source = sys.argv[1], Path(sys.argv[2])
repo = Path(sys.argv[3] if len(sys.argv) > 3 else 'C:/wk/native-vm2')
assert name.startswith('vm2-'), 'Build into artifacts/vm2-<name>'
parent = Path('C:/wk/native-batch-6/artifacts/batch6-candidate-diag1')
out = repo / 'artifacts' / name
build = Path('C:/wk/pointer-build')
slim = Path('C:/wk/build-win-slim')
src = Path('C:/wk/src')
UNIT = 'Source/WebCore/CMakeFiles/WebCore.dir/__/__/WebCore/DerivedSources/unified-sources/UnifiedSource-dom-10.cpp.obj'
MEMBER = 'Source/WebCore/dom/EventLoop.cpp'
PARENT_UNIT_OBJECT = 'C:/wk/native-batch-5/artifacts/batch5-candidate-1/150-UnifiedSource-dom-10.cpp.obj'
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'
out.mkdir(parents=True, exist_ok=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


assert not subprocess.run(['git', '-C', str(src), 'diff', '--', MEMBER], capture_output=True, text=True, check=True).stdout, \
    'C:/wk/src changes ' + MEMBER
overlay_file = out / 'overlay' / MEMBER
overlay_file.parent.mkdir(parents=True, exist_ok=True)
overlay_bytes = overlay_source.read_bytes()
assert b'\r\n' not in overlay_bytes
overlay_file.write_bytes(overlay_bytes)

cache = (build / 'CMakeCache.txt').read_text()
compiler = Path(re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.+)$', cache, re.M).group(1))
ninja = re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$', cache, re.M).group(1)
guarded = [build / n for n in ['CMakeCache.txt', 'build.ninja', '.ninja_log', '.ninja_deps', 'bin/WebCore.dll', 'bin/JavaScriptCore.dll', 'lib/WebCore.lib']]
guarded_times = {p: p.stat().st_mtime_ns for p in guarded}
slim_time = (slim / 'build.ninja').stat().st_mtime_ns
parent_files = [p for p in parent.rglob('*') if p.is_file() and p.suffix in ('.obj', '.dll', '.lib', '.json', '.rsp')]
parent_times = {str(p): p.stat().st_mtime_ns for p in parent_files}
parent_unit_time = Path(PARENT_UNIT_OBJECT).stat().st_mtime_ns

tree = ast.parse((repo / 'scripts/build.py').read_text())
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'toolchain_env')
scope = dict(os=os, pathlib=__import__('pathlib'), subprocess=subprocess, sys=sys, windows=True, arch='x64', system='win',
             args=types.SimpleNamespace(tool_path=[]), llvm=compiler.parent, vcpkg=Path('C:/wk/vcpkg'),
             pins=json.loads((repo / 'pins.json').read_text()))
exec(compile(ast.Module(body=[function], type_ignores=[]), '<toolchain_env>', 'exec'), scope)
env = scope['toolchain_env']()
stop = threading.Event()
helpers = ast.parse(Path('C:/wk/native-cssom-detached-context/artifacts/build_context_candidate.py').read_text())
names = {'normalize', 'commands', 'execute'}
functions = [node for node in helpers.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(functions) == len(names)
exec(compile(ast.Module(body=functions, type_ignores=[]), '<reviewed_private_build_helpers>', 'exec'), globals())
runtime = out / 'runtime'
runtime.mkdir(parents=True, exist_ok=True)
for item in sorted((parent / 'runtime').iterdir()):
    if item.name.startswith('WebCore.'):
        continue
    if item.is_dir():
        shutil.copytree(item, runtime / item.name, dirs_exist_ok=True)
    else:
        shutil.copy2(item, runtime / item.name)
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')

command = next(c for c in commands([UNIT]) if 'clang-cl.exe' in c and 'UnifiedSource-dom-10.cpp' in c.replace(chr(92), '/'))
unified = build / 'WebCore/DerivedSources/unified-sources' / Path(UNIT).name.removesuffix('.obj')
unified_lines = unified.read_text().splitlines()
original = '#include "' + MEMBER.removeprefix('Source/WebCore/').replace('/', chr(92)) + '"'
assert unified_lines.count(original) == 1, original
unified_lines[unified_lines.index(original)] = '#include "' + overlay_file.as_posix() + '"'
private_unified = out / ('overlay-' + unified.name)
private_unified.write_text(chr(10).join(unified_lines) + chr(10))
pattern = ('[/' + chr(92) * 2 + ']').join(re.escape(part) for part in unified.as_posix().split('/'))
command, count = re.subn(pattern, lambda _: private_unified.as_posix(), command)
assert count == 1, count
assert '/Yc' not in command and '/sourceDependencies' not in command
stem = '200-UnifiedSource-dom-10.cpp.obj'
obj = out / stem
command, count = re.subn(r'/Fo(?:"[^"]+"|\S+)', '/Fo' + obj.as_posix(), command)
assert count == 1
command = re.sub(r'/Fd(?:"[^"]+"|\S+)', '/Fd' + (out / (stem + '.pdb')).as_posix(), command)
parts = re.match(r'^(?:"([^"]+)"|(\S+))\s+(.*)$', command)
command = '"' + (parts.group(1) or parts.group(2)) + '" /I' + private_headers.parent.as_posix() + ' /I' + private_headers.as_posix() + ' ' + parts.group(3)
(out / (stem + '.command-sha256')).write_text(hashlib.sha256(command.encode()).hexdigest())
if execute(command, stem):
    raise SystemExit(1)


def disassembly(path):
    listing = subprocess.run([str(compiler.parent / 'llvm-objdump.exe'), '-d', '--no-show-raw-insn', str(path)], capture_output=True, text=True, check=True).stdout
    return hashlib.sha256(chr(10).join(listing.splitlines()[2:]).encode()).hexdigest()


unit_disassembly = disassembly(obj)
print('dom-10 disassembly', unit_disassembly, 'parent', disassembly(PARENT_UNIT_OBJECT)[:8], flush=True)

link = (parent / 'webcore-link.rsp').read_text(encoding='utf-8')
assert link.count(PARENT_UNIT_OBJECT) == 1
link = link.replace(PARENT_UNIT_OBJECT, obj.as_posix())
parent_runtime = (parent / 'runtime').as_posix()
assert link.count(parent_runtime + '/WebCore.') == 3, link.count(parent_runtime)
link = link.replace(parent_runtime + '/WebCore.', runtime.as_posix() + '/WebCore.')
assert parent.as_posix() + '/runtime' not in link
if execute('"' + (compiler.parent / 'lld-link.exe').as_posix() + '" ' + link, 'webcore-link'):
    raise SystemExit(1)

host = {}
if os.environ.get('VM2_HOST') == '1':
    host_link = (parent / 'host-link.rsp').read_text(encoding='utf-8')
    for filename in ['RanvierWebCoreAbi.cpp', 'RanvierWebCoreDom.cpp', 'RanvierWebCoreUia.cpp', 'RanvierWebCoreD3D11.cpp', 'RanvierImageEncoding.cpp']:
        rsp = (parent / (filename + '.rsp')).read_text(encoding='utf-8')
        old_source = 'C:/wk/native-batch-6/host/' + filename
        assert rsp.count(old_source) == 1, (filename, rsp.count(old_source))
        rsp = rsp.replace(old_source, (repo / 'host' / filename).as_posix())
        rsp = rsp.replace(parent.as_posix() + '/', out.as_posix() + '/')
        if execute('"' + (compiler.parent / 'clang-cl.exe').as_posix() + '" ' + rsp, filename):
            raise SystemExit(1)
        host[filename] = sha(repo / 'host' / filename)
    host_link = host_link.replace(parent.as_posix() + '/', out.as_posix() + '/')
    assert parent.as_posix() not in host_link
    if execute('"' + (compiler.parent / 'lld-link.exe').as_posix() + '" ' + host_link, 'host-link'):
        raise SystemExit(1)

assert guarded_times == {p: p.stat().st_mtime_ns for p in guarded}, 'pointer-build changed'
assert (slim / 'build.ninja').stat().st_mtime_ns == slim_time, 'build-win-slim changed'
assert parent_times == {str(p): p.stat().st_mtime_ns for p in parent_files}, 'diag1 changed'
assert Path(PARENT_UNIT_OBJECT).stat().st_mtime_ns == parent_unit_time
hashes = {str(p.relative_to(runtime)).replace(chr(92), '/'): sha(p) for p in sorted(runtime.rglob('*')) if p.is_file()}
assert hashes['JavaScriptCore.dll'] == sha(parent / 'runtime/JavaScriptCore.dll')
(out / 'runtime-sha256.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')
(out / 'source-patches.json').write_text(json.dumps({
    'parent': str(parent), 'build': str(build), 'unit': UNIT, 'replacedObject': PARENT_UNIT_OBJECT,
    'overlay': {'member': MEMBER, 'source': str(overlay_source), 'file': overlay_file.as_posix(), 'sha256': sha(overlay_file),
                'unifiedSource': private_unified.as_posix()},
    'object': obj.as_posix(), 'disassemblySha256': unit_disassembly, 'hostSources': host}, indent=2) + '\n', encoding='utf-8')
print('VM2 CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
