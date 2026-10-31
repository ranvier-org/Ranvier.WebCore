"""Private Native31 H11 candidate: D13's forms-candidate-4 (Native28, Source 0000-0034) with this tree's regenerated
RanvierDomGlue compiled into WebCore and the four host units recompiled. Borrows build-win-slim, forms-candidate-4's
runtime, its 111 replacement objects (two of them its own compiles) and its four glue objects read-only."""
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
parent = Path('C:/wk/native-forms/artifacts/forms-candidate-4')
build = Path('C:/wk/build-win-slim')
assert sys.argv[1].startswith('native31-candidate-'), 'Build into artifacts/native31-candidate-N'
out = repo / 'artifacts' / sys.argv[1]
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'
for unchanged in ['host/RanvierSvgViewGlue.cpp', 'host/RanvierResourceGlue.cpp', 'host/RanvierEventGlue.cpp', 'host/RanvierEventGlue.h',
                  'host/RanvierViewportGlue.cpp', 'host/RanvierViewportGlue.h']:
    diff = subprocess.run(['git', 'diff', '--quiet', 'b8acc27', '--', unchanged], cwd=repo)
    assert diff.returncode == 0, unchanged + ' changed since b8acc27: the borrowed glue object is stale'
# Every borrowed object postdates the newest change to the patched WebKit source.
status = subprocess.run(['git', 'status', '--porcelain', '-uall'], cwd='C:/wk/src', capture_output=True, text=True, check=True).stdout.splitlines()
# Root exemption (2026-10-31): G09's Source patch 0035 changes only Document::caretPositionFromPoint after the borrowed
# objects were compiled. Native31 excludes 0035: it borrows the pre-0035 objects and recompiles no unified source.
EXEMPT = 'Source/WebCore/dom/Document.cpp'
PATCH_0035 = Path('C:/wk/native-caret/patches/0035-caret-position-text-control-shadow-roots.patch')
CRLF, LF = bytes([13, 10]), bytes([10])
document_diff = subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--', EXEMPT], capture_output=True, check=True).stdout.replace(CRLF, LF)
expected_hunk = PATCH_0035.read_bytes().replace(CRLF, LF)
assert document_diff[document_diff.index(LF + b'@@'):] == expected_hunk[expected_hunk.index(LF + b'@@'):], 'Document.cpp differs from patch 0035'
assert not any(EXEMPT in patch.read_text(encoding='utf-8', errors='replace') for patch in (repo / 'patches').glob('*.patch')), 'an earlier patch touches Document.cpp'
exemption = {'file': EXEMPT, 'patch': str(PATCH_0035), 'patchSha256': hashlib.sha256(PATCH_0035.read_bytes()).hexdigest(),
             'sourceDiffSha256': hashlib.sha256(document_diff).hexdigest(), 'assertion': 'git diff of the file equals the patch hunk byte for byte',
             'mtimeNs': os.stat(Path('C:/wk/src') / EXEMPT).st_mtime_ns}
newest_source = max(os.stat(Path('C:/wk/src') / line[3:]).st_mtime_ns for line in status
                    if (Path('C:/wk/src') / line[3:]).is_file() and line[3:] != EXEMPT)
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
assert len(replacements) == 111
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in replacements.values()}
document_unit = 'Source/WebCore/CMakeFiles/WebCore.dir/__/__/WebCore/DerivedSources/unified-sources/UnifiedSource-dom-7.cpp.obj'
assert r'#include "dom\Document.cpp"' in (build / 'WebCore/DerivedSources/unified-sources/UnifiedSource-dom-7.cpp').read_text()
assert Path(replacements[document_unit]).stat().st_mtime_ns < exemption['mtimeNs'], 'the Document.cpp unit postdates patch 0035'
exemption['borrowedDocumentUnit'] = replacements[document_unit]
assert all(path.stat().st_mtime_ns > newest_source for path in borrowed if 'forms-candidate-4' in str(path)), 'WebKit source changed after forms-candidate-4'
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
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))

extra = []
for name in ['RanvierSvgViewGlue', 'RanvierResourceGlue', 'RanvierEventGlue', 'RanvierViewportGlue']:
    glue = parent / (name + '.cpp.obj')
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
assert parent_hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in parent_files}, 'forms-candidate-4 changed'
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.iterdir() if p.is_file()}
assert hashes['JavaScriptCore.dll'].startswith('95149cdc')
(out / 'runtime-sha256.json').write_text(json.dumps(hashes, indent=2))
(out / 'source-exemption.json').write_text(json.dumps(exemption, indent=2))
assert not any('UnifiedSource' in str(target) for target in [glue_target]), 'Native31 recompiles no unified source'
print('NATIVE31 BINARY CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
