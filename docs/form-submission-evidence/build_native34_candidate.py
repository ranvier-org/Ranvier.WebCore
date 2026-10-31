"""Private Native34 D14 candidate: D13's forms-candidate-4 (Native28, Source 0000-0034) with this tree's regenerated
RanvierDomGlue and every unified source whose recorded dependencies include a file changed by source patches 0035, 0036
or 0037 compiled into WebCore, and the four host units recompiled. Until root applies 0037 to C:/wk/src, a clang VFS
overlay substitutes the patched copies in artifacts/src0037/b. Borrows build-win-slim, forms-candidate-4's runtime, its
111 replacement objects and its four glue objects read-only."""
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
assert sys.argv[1].startswith('native34-candidate-'), 'Build into artifacts/native34-candidate-N'
out = repo / 'artifacts' / sys.argv[1]
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'
for unchanged in ['host/RanvierSvgViewGlue.cpp', 'host/RanvierResourceGlue.cpp', 'host/RanvierEventGlue.cpp', 'host/RanvierEventGlue.h',
                  'host/RanvierViewportGlue.cpp', 'host/RanvierViewportGlue.h']:
    diff = subprocess.run(['git', 'diff', '--quiet', 'b8acc27', '--', unchanged], cwd=repo)
    assert diff.returncode == 0, unchanged + ' changed since b8acc27: the borrowed glue object is stale'
# Every borrowed object postdates the newest change to the patched WebKit source.
status = subprocess.run(['git', 'status', '--porcelain', '-uall'], cwd='C:/wk/src', capture_output=True, text=True, check=True).stdout.splitlines()
# The source patches applied after forms-candidate-4's objects. Each file they change must carry the patch's lines in
# C:/wk/src, and this build recompiles every unit whose recorded dependencies include one of those files.
committed_0037 = sorted((repo / 'patches').glob('0037-*.patch'))
proposed_0037 = repo / 'artifacts/src0037/0037-proposed.diff'
source_patches = [repo / 'patches/0035-caret-position-text-control-shadow-roots.patch',
                  committed_0037[0] if committed_0037 else proposed_0037]
assert [line for line in (repo / 'patches/series').read_text().splitlines() if line[:4].isdigit() and line[:4] >= '0035'] == [p.name for p in source_patches], 'series differs'
# The dropped 0036 (number unused): EmptyFrameLoaderClient.h is stock again, so its units that 0037 leaves alone keep
# their borrowed objects.
assert not list((repo / 'patches').glob('0036-*.patch'))
assert subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--quiet', '--', 'Source/WebCore/loader/EmptyFrameLoaderClient.h']).returncode == 0
dropped_0036_units = json.loads(subprocess.run([sys.executable, '-I', 'C:/wk/t06-artifacts/units_for_headers.py', '--json',
                                                'Source/WebCore/loader/EmptyFrameLoaderClient.h', 'Source/WebCore/loader/EmptyClients.h'],
                                               capture_output=True, text=True, check=True).stdout)['all']
overlay_files = {}
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
for patch_path in source_patches:
    text = patch_path.read_text(encoding='utf-8')
    for section in text.split('\ndiff --git ')[0 if text.startswith('diff --git ') else 1:]:
        name = re.search(r'a/(\S+) b/', section).group(1)
        current = subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--', name], capture_output=True, text=True, check=True).stdout
        if patch_path == proposed_0037 and not hunk_lines(current):
            # Not yet applied: the overlay substitutes the private copy, whose pre-patch original must match C:/wk/src.
            leaf = Path(name).name
            assert (repo / 'artifacts/src0037/a' / leaf).read_bytes() == (Path('C:/wk/src') / name).read_bytes(), name + ' changed in C:/wk/src'
            overlay_files[name] = repo / 'artifacts/src0037/b' / leaf
        else:
            assert contains(hunk_lines(current), hunk_lines(section)), name + ' does not carry ' + patch_path.name
        recompiled_sources.add(name)
        patch_receipt.setdefault(patch_path.name, {})[name] = hunk_lines(section)
scan = subprocess.run([sys.executable, '-I', 'C:/wk/t06-artifacts/units_for_headers.py', '--json', *sorted(recompiled_sources)],
                      capture_output=True, text=True, check=True)
patched_units = json.loads(scan.stdout)['all']
overlay_arguments = ''
if overlay_files:
    roots = {}
    for name, private in overlay_files.items():
        roots.setdefault(str((Path('C:/wk/src') / name).parent), []).append({'type': 'file', 'name': Path(name).name, 'external-contents': str(private)})
        if name.endswith('.h'):
            roots.setdefault(str(build / 'WebCore/PrivateHeaders/WebCore'), []).append({'type': 'file', 'name': Path(name).name, 'external-contents': str(private)})
    out.mkdir(parents=True, exist_ok=True)
    overlay = out / 'patch-0037-overlay.json'
    overlay.write_text(json.dumps({'version': 0, 'case-sensitive': 'false', 'roots': [
        {'type': 'directory', 'name': directory, 'contents': contents} for directory, contents in roots.items()]}, indent=2))
    overlay_arguments = '-vfsoverlay ' + overlay.as_posix() + ' '
def with_overlay(command):
    return re.sub(r'^("[^"]+"|\S+)\s', lambda match: match.group(0) + overlay_arguments, command, count=1)
newest_source = max(os.stat(Path('C:/wk/src') / line[3:]).st_mtime_ns for line in status
                    if (Path('C:/wk/src') / line[3:]).is_file() and line[3:] not in recompiled_sources)
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
assert all(path.stat().st_mtime_ns > newest_source for path in borrowed if 'forms-candidate-4' in str(path)), 'WebKit source changed after forms-candidate-4'
glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
assert glue_target in replacements
build_files = {p: p.stat().st_mtime_ns for p in [build / 'CMakeCache.txt', build / 'build.ninja', build / '.ninja_log', build / '.ninja_deps', build / 'bin/WebCore.dll'] if p.exists()}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')
# With a second argument, WebCore comes from that earlier candidate of the same source state and only the host recompiles.
webcore_from = repo / 'artifacts' / sys.argv[2] if len(sys.argv) > 2 else None
if webcore_from:
    earlier = json.loads((webcore_from / 'source-patches.json').read_text())
    assert earlier['patches'] == patch_receipt and earlier['overlay'] == {k: str(v) for k, v in overlay_files.items()}, 'source state differs'
    for name in ['WebCore.dll', 'WebCore.lib', 'WebCore.pdb']:
        borrowed[webcore_from / 'runtime' / name] = (webcore_from / 'runtime' / name).stat().st_mtime_ns
        shutil.copy2(webcore_from / 'runtime' / name, runtime / name)
    (out / 'source-patches.json').write_text(json.dumps({**earlier, 'webcoreFrom': webcore_from.name}, indent=2))
else:
    command_map = {}
    for unit in patched_units:
        assert unit in replacements or (build / unit).exists(), unit
    for command in commands([glue_target, *patched_units]):
        if 'clang-cl.exe' in command:
            output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
            if output:
                command_map[normalize(output.group(1) or output.group(2))] = with_overlay(command)
    target, obj, code = compile_object(0, glue_target)
    if code:
        raise SystemExit('RanvierDomGlue failed')
    replacements[glue_target] = obj
    objects = {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda item: compile_object(*item), enumerate(patched_units, start=1)))
    for target, obj, code in results:
        if code:
            raise SystemExit(target + ' failed')
        replacements[target] = obj
        objects[target] = obj
    (out / 'source-patches.json').write_text(json.dumps({'patches': patch_receipt, 'overlay': {k: str(v) for k, v in overlay_files.items()},
                                                         'recompiledUnits': objects,
                                                         'dropped0036UnitsBorrowed': [u for u in dropped_0036_units if u not in patched_units]}, indent=2))
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
    command = with_overlay(command.replace(' -- ', ' ' + flag_arguments + ' -- '))
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
print('NATIVE34 FORM SUBMISSION CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
