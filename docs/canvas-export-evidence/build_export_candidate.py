"""Private R07 canvas export candidate: the parent pixels-candidate-3 (R06, built at native-canvas-pixels 265caf2) with
the B06 media-capabilities unit borrowed from its owner's media-candidate-2 (patch 0043), the units patches 0049 and 0050 reach
compiled from C:/wk/src, this tree's RanvierDomGlue, RanvierResourceGlue and the new RanvierCanvasExportGlue compiled,
WebCore relinked, and the five host units (RanvierImageEncoding.cpp included) recompiled and relinked. Derived from
docs/canvas-pixels-evidence/build_pixels_candidate.py.
usage: build_export_candidate.py <export-candidate-N> [parent candidate dir]
Without patch 0049 in patches/series the build stops at the first unit that needs it: that log is the patch's RED."""
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

repo = Path('C:/wk/native-canvas-pixels')
assert sys.argv[1].startswith('export-candidate-'), 'Build into artifacts/export-candidate-N'
out = repo / 'artifacts' / sys.argv[1]
parent = Path(sys.argv[2] if len(sys.argv) > 2 else 'C:/wk/native-canvas-pixels/artifacts/pixels-candidate-3')
parent_head = '265caf2'
# The patch owner's object for 0043: med1's media-candidate-2, compiled after the patched MediaCapabilities.cpp.
MEDIA_PARENT = Path('C:/wk/native-media-caps/artifacts/media-candidate-2')
MEDIA_PATCH = '0043-media-capabilities-native-query.patch'
OWN_PATCHES = ['0049-image-bitmap-crop-completion-handler.patch', '0050-image-bitmap-unaccelerated-buffers.patch']
NEW_GLUE = ['RanvierCanvasExportGlue', 'RanvierResourceGlue']


def parent_text(path):
    return subprocess.run(['git', '-C', str(repo), 'show', parent_head + ':' + path], capture_output=True, check=True).stdout


def same_as_parent(path):
    return (repo / path).read_bytes().replace(b'\r\n', b'\n') == parent_text(path).replace(b'\r\n', b'\n')


series = (repo / 'patches/series').read_text().split()
parent_series = parent_text('patches/series').decode().split()
own = [name for name in series if name in OWN_PATCHES]
assert series == parent_series + [MEDIA_PATCH] + own, ('series is the parent series plus 0043, 0049 and 0050', series)
for name in parent_series:
    if name.endswith('.patch'):
        assert same_as_parent('patches/' + name), name + ' differs from the parent tree'


def carried(name):
    """The files patch name changes, after asserting C:/wk/src carries each hunk."""
    text = (repo / 'patches' / name).read_text(encoding='utf-8')
    files = []
    for section in text.split('\ndiff --git ')[0 if text.startswith('diff --git ') else 1:]:
        target = re.search(r'a/(\S+) b/', section).group(1)
        hunk = [line for line in section.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))]
        if '\n--- /dev/null' in section:
            # A file the patch creates is untracked in C:/wk/src: its lines are the hunk's.
            created = (Path('C:/wk/src') / target).read_text(encoding='utf-8').replace('\r\n', '\n').splitlines()
            assert ['+' + line for line in created] == hunk, target + ' does not carry ' + name
            files.append(target)
            continue
        current =subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--', target], capture_output=True, text=True, check=True).stdout
        lines = [line for line in current.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))]
        index = 0
        for line in lines:
            if index < len(hunk) and line == hunk[index]:
                index += 1
        assert index == len(hunk), target + ' does not carry ' + name
        files.append(target)
    return files


patch_receipt = {name: {'sha256': hashlib.sha256((repo / 'patches' / name).read_bytes()).hexdigest(), 'files': carried(name)}
                 for name in [MEDIA_PATCH] + own}
build = Path('C:/wk/build-win-slim')
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'
parent_patches = json.loads((parent / 'source-patches.json').read_text())
media_receipt = json.loads((MEDIA_PARENT / 'source-patches.json').read_text())
media_replacements = json.loads((MEDIA_PARENT / 'replacement-objects.json').read_text())

link = (parent / 'webcore-link.rsp').read_text(encoding='utf-8')
glue_objects = sorted({path for path in re.findall(r'(\S+Ranvier[A-Za-z]+Glue\.cpp\.obj)', link) if 'RanvierDomGlue' not in path})
borrowed_glue, glue_receipt = [], {}
for glue in glue_objects:
    stem = re.search(r'(Ranvier[A-Za-z]+Glue)\.cpp\.obj', glue).group(1)
    if stem in NEW_GLUE:
        glue_receipt[stem] = {'parentObject': glue, 'recompiled': True}
        continue
    assert all(same_as_parent('host/' + stem + suffix) for suffix in ['.cpp', '.h']), stem + ' changed since the parent'
    borrowed_glue.append(glue)
    glue_receipt[stem] = {'parentObject': glue, 'recompiled': False}

runtime = out / 'runtime'
runtime.mkdir(parents=True, exist_ok=True)
shutil.copytree(parent / 'runtime', runtime, dirs_exist_ok=True)
watched = [p for p in list(parent.rglob('*')) + list(MEDIA_PARENT.glob('*')) if p.is_file() and p.suffix in ('.obj', '.dll', '.lib', '.json')]
watched_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
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
# 0043's unit: the owner's object, newer than every file the patch changes.
media_unit = media_receipt['ownPatchUnits'][0]
media_object = media_replacements[media_unit]
for name in patch_receipt[MEDIA_PATCH]['files']:
    assert Path(media_object).stat().st_mtime_ns > os.stat(Path('C:/wk/src') / name).st_mtime_ns, media_unit + ' predates ' + name
replacements[media_unit] = media_object
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in replacements.values()}
glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
build_files = {p: p.stat().st_mtime_ns for p in [build / 'CMakeCache.txt', build / 'build.ninja', build / '.ninja_log', build / '.ninja_deps', build / 'bin/WebCore.dll'] if p.exists()}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')

# The units 0049 reaches compile from C:/wk/src, which carries the patch.
own_units = []
if own:
    own_files = sorted({name for patch in own for name in patch_receipt[patch]['files']})
    scan = json.loads(subprocess.run([sys.executable, '-I', 'C:/wk/t06-artifacts/units_for_headers.py', '--json', *own_files],
                                     capture_output=True, text=True, check=True).stdout)
    own_units = sorted(scan['all'])
command_map = {}
for command in commands([glue_target] + own_units):
    if 'clang-cl.exe' in command:
        output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
        if output:
            command_map[normalize(output.group(1) or output.group(2))] = command
target, obj, code = compile_object(0, glue_target)
if code:
    raise SystemExit('RanvierDomGlue failed')
replacements[glue_target] = obj
recompiled = {glue_target: obj}
for index, unit in enumerate(own_units, start=1):
    assert unit in command_map, unit
    target, unit_obj, code = compile_object(index, unit)
    if code:
        raise SystemExit(unit + ' failed')
    replacements[unit] = unit_obj
    recompiled[unit] = unit_obj
# PRIVATE_IMAGE_BITMAP_SOURCE names a patched ImageBitmap.cpp proven before root applies its patch: html-16, which holds
# ImageBitmap.cpp, compiles from a private unified copy and links in place of the C:/wk/src unit. Such a candidate is
# evidence for the patch only.
private_bitmap = os.environ.get('PRIVATE_IMAGE_BITMAP_SOURCE')
private_unit = None
if private_bitmap:
    unit_target = 'Source/WebCore/CMakeFiles/WebCore.dir/__/__/WebCore/DerivedSources/unified-sources/UnifiedSource-html-16.cpp.obj'
    unified = build / 'WebCore/DerivedSources/unified-sources/UnifiedSource-html-16.cpp'
    text = unified.read_text(encoding='utf-8')
    assert text.count('#include "html\\ImageBitmap.cpp"') == 1, 'html-16 no longer holds ImageBitmap.cpp'
    private_unified = out / 'UnifiedSource-html-16-private.cpp'
    private_unified.write_text(text.replace('#include "html\\ImageBitmap.cpp"', '#include "' + Path(private_bitmap).resolve().as_posix() + '"'), encoding='utf-8')
    if unit_target not in command_map:
        for command in commands([unit_target]):
            if 'clang-cl.exe' in command:
                command_map[unit_target] = command
    private_target = unit_target.replace('UnifiedSource-html-16.cpp.obj', 'UnifiedSource-html-16-private.cpp.obj')
    command_map[private_target] = re.sub(r'\S*UnifiedSource-html-16\.cpp(?=\s|$)', private_unified.as_posix(), command_map[unit_target])
    target, private_obj, code = compile_object(80, private_target)
    if code:
        raise SystemExit('private html-16 failed')
    replacements[unit_target] = private_obj
    recompiled[unit_target] = private_obj
    private_unit = {'unit': unit_target, 'privateSource': Path(private_bitmap).resolve().as_posix(),
                    'privateSourceSha256': hashlib.sha256(Path(private_bitmap).read_bytes()).hexdigest(), 'object': private_obj}
extra = []
for index, stem in enumerate(NEW_GLUE, start=90):
    unit = 'Ranvier/host/' + stem + '.cpp.obj'
    unit_command, count = re.subn(r'C:[/\\]wk[/\\]ranvier-webcore[/\\]host[/\\]dom[/\\]RanvierDomGlue.cpp',
                                  (repo / 'host' / (stem + '.cpp')).as_posix(), command_map[glue_target])
    assert count == 1, count
    command_map[unit] = unit_command
    target, unit_obj, code = compile_object(index, unit)
    if code:
        raise SystemExit(stem + ' failed')
    extra.append(Path(unit_obj).as_posix())
    recompiled[unit] = unit_obj
for glue in borrowed_glue:
    borrowed[Path(glue)] = Path(glue).stat().st_mtime_ns
    extra.append(Path(glue).as_posix())
(out / 'source-patches.json').write_text(json.dumps({'patches': {**{name: None for name in parent_patches['patches']}, **patch_receipt},
                                                     'parent': str(parent), 'parentHead': parent_head, 'parentReceipt': parent_patches,
                                                     'patch0043Owner': {'candidate': str(MEDIA_PARENT), 'unit': media_unit, 'object': media_object},
                                                     'ownPatchUnits': own_units, 'privateImageBitmapSource': private_unit, 'hostGlue': glue_receipt, 'recompiledUnits': recompiled,
                                                     'srcDiffSha256': hashlib.sha256(subprocess.run(['git', '-C', 'C:/wk/src', 'diff'], capture_output=True, check=True).stdout).hexdigest()},
                                                    indent=2))
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))
if execute(link_command('WebCore') + ' ' + ' '.join(extra) + ' Dwrite.lib', 'webcore-link'):
    raise SystemExit(1)

host_target = r'Tools\TestWebKitAPI\CMakeFiles\RanvierWebCoreHost.dir\RanvierAbi\RanvierWebCoreAbi.cpp.obj'
host_command = next(c for c in commands([host_target]) if 'clang-cl.exe' in c and 'RanvierWebCoreAbi.cpp' in c)
flags = re.findall(r'^((?:USE|ENABLE)_[A-Z0-9_]+):BOOL=(ON|OFF|1|0|TRUE|FALSE)$', cache, re.M)
flag_arguments = ' '.join('/DRV_CAP_' + name + '=' + ('1' if value in ['ON', '1', 'TRUE'] else '0') for name, value in flags)
host_objects = []
for filename in ['RanvierWebCoreAbi.cpp', 'RanvierWebCoreDom.cpp', 'RanvierWebCoreUia.cpp', 'RanvierWebCoreD3D11.cpp', 'RanvierImageEncoding.cpp']:
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
assert watched_hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}, 'parent candidates changed'
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.iterdir() if p.is_file()}
assert hashes['JavaScriptCore.dll'].startswith('95149cdc')
(out / 'runtime-sha256.json').write_text(json.dumps(hashes, indent=2))
print('EXPORT CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
