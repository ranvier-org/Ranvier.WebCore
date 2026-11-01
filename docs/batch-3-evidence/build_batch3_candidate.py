"""Private batch-3 candidate (R01, D17, T01+R09, B10, B09, I07+T09+T04) on the batch-2 candidate: its WebCore objects,
with every host glue unit of this tree compiled (config/common.cmake WebCore_EMBEDDER_SOURCES), every unit of source
patches 0041 and 0042 (OWN_PATCHES) recompiled from C:/wk/src, WebCore relinked, and the four host units recompiled and
relinked.
usage: build_batch3_candidate.py <batch3-candidate-N> <parent candidate dir> [repo]
The parent's objects must cover every other patch of this tree's series past 0034, which C:/wk/src must carry; its
WebCore objects are borrowed read-only. C:/wk/src also carries patches later in the stack (LATER_PATCHES). A borrowed
unit older than a source a later patch touched must have a diff equal to this series' hunks plus the later patches'.
A recompiled unit a later patch reaches must disassemble identically to its patch owner's object (OWNER_OBJECTS), which
predates the later patch. The inspect glue object's undefined symbols must name no inspector controller,
instrumentation or frontend."""
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

repo = Path(sys.argv[3] if len(sys.argv) > 3 else 'C:/wk/native-batch-3')
assert sys.argv[1].startswith('batch3-candidate-'), 'Build into artifacts/batch3-candidate-N'
OWN_PATCHES = ['0041-data-transfer-in-memory-file-access.patch', '0042-canvas-renders-embedder-context.patch']
LATER_PATCHES = ['C:/wk/native-media-caps/patches/0043-media-capabilities-native-query.patch',
                 'C:/wk/native-pointer/patches/0044-pointer-event-pen-geometry.patch',
                 'C:/wk/native-pointer/patches/0045-touch-pointer-events-win.patch',
                 'C:/wk/native-pointer/patches/0046-pointer-capture-pen-mouse-path.patch',
                 'C:/wk/native-pointer/patches/0047-navigator-embedder-max-touch-points.patch',
                 'C:/wk/native-fontface/patches/0048-fontface-loaded-rejection.patch']
UNIFIED = 'Source/WebCore/CMakeFiles/WebCore.dir/__/__/WebCore/DerivedSources/unified-sources/'
OWNER_OBJECTS = {UNIFIED + 'UnifiedSource-dom-6.cpp.obj': 'C:/wk/native-dnd/artifacts/dnd-candidate-9/100-UnifiedSource-dom-6.cpp.obj',
                 UNIFIED + 'UnifiedSource-html-6.cpp.obj': 'C:/wk/native-canvas/artifacts/canvas-candidate-5/001-UnifiedSource-html-6.cpp.obj'}
out = repo / 'artifacts' / sys.argv[1]
parent = Path(sys.argv[2])
build = Path('C:/wk/build-win-slim')
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'


def diff_lines(text):
    return [line for line in text.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))]


def hunk_lines(patch, target):
    text = Path(patch).read_text(encoding='utf-8')
    lines = []
    for section in text.split('\ndiff --git ')[0 if text.startswith('diff --git ') else 1:]:
        if re.search(r'a/(\S+) b/', section).group(1) == target:
            lines += diff_lines(section)
    return lines


def patch_files(patch):
    return sorted(set(re.findall(r'^diff --git a/(\S+) b/', Path(patch).read_text(encoding='utf-8'), re.M)))


def src_diff(name):
    """The +/- lines of C:/wk/src's diff of name; an untracked file is all added lines."""
    tracked = subprocess.run(['git', '-C', 'C:/wk/src', 'ls-files', '--', name], capture_output=True, text=True, check=True).stdout.strip()
    if not tracked:
        return ['+' + line for line in (Path('C:/wk/src') / name).read_text(encoding='utf-8').splitlines()]
    return diff_lines(subprocess.run(['git', '-C', 'C:/wk/src', 'diff', '--', name], capture_output=True, text=True, check=True).stdout)


parent_patches = json.loads((parent / 'source-patches.json').read_text())
series = [line for line in (repo / 'patches/series').read_text().splitlines() if line[:4].isdigit() and line[:4] >= '0035']
covered = {name[:4] for name in parent_patches['patches']}
assert {name[:4] for name in series if name not in OWN_PATCHES} <= covered, ('patches the parent does not cover', series, sorted(covered))
assert set(OWN_PATCHES) <= set(series)
patch_receipt = {}
for name in series:
    patch_receipt[name] = {'sha256': hashlib.sha256((repo / 'patches' / name).read_bytes()).hexdigest(), 'files': patch_files(repo / 'patches' / name)}
    for target in patch_receipt[name]['files']:
        hunk, index = hunk_lines(repo / 'patches' / name, target), 0
        for line in src_diff(target):
            if index < len(hunk) and line == hunk[index]:
                index += 1
        assert index == len(hunk), target + ' does not carry ' + name
later_files = {patch: [name for name in patch_files(patch) if (Path('C:/wk/src') / name).exists()] for patch in LATER_PATCHES}
for patch, names in later_files.items():
    for name in names:
        hunk, index = hunk_lines(patch, name), 0
        for line in src_diff(name):
            if index < len(hunk) and line == hunk[index]:
                index += 1
        assert index == len(hunk), name + ' does not carry ' + patch

# Every host glue source of config/common.cmake compiles here; WebCore links none of the parent's glue objects.
cmake = (repo / 'config/common.cmake').read_text(encoding='utf-8')
embedder = re.search(r'set\(WebCore_EMBEDDER_SOURCES "([^"]+)"', cmake).group(1).split(';')
glue_sources = [item.replace('${_ranvier_root}/', '') for item in embedder]
assert glue_sources[0] == 'host/dom/RanvierDomGlue.cpp' and len(glue_sources) == 10, glue_sources
link = (parent / 'webcore-link.rsp').read_text(encoding='utf-8')
parent_glue = sorted({Path(path).name.split('-', 1)[-1] for path in re.findall(r'(\S+Ranvier[A-Za-z]+Glue\.cpp\.obj)', link)})
assert set(parent_glue) <= {Path(name).name + '.obj' for name in glue_sources}, parent_glue

runtime = out / 'runtime'
runtime.mkdir(parents=True, exist_ok=True)
shutil.copytree(parent / 'runtime', runtime, dirs_exist_ok=True)
parent_files = [p for p in parent.rglob('*') if p.is_file() and p.suffix in ('.obj', '.dll', '.lib', '.json')]
parent_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in parent_files}
owner_hashes = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in OWNER_OBJECTS.values()}
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
ninja_text = (build / 'build.ninja').read_text()

replacements = json.loads((parent / 'replacement-objects.json').read_text())
borrowed = {Path(path): Path(path).stat().st_mtime_ns for path in replacements.values()}


def units_of(files):
    return json.loads(subprocess.run([sys.executable, '-I', 'C:/wk/t06-artifacts/units_for_headers.py', '--json', *files],
                                     capture_output=True, text=True, check=True).stdout)


# Borrowed units of the other series patches: parent objects compiled after the patched source, or exempt when the
# source's whole diff is this series' hunks plus later patches' hunks.
patched_files = sorted({name for key, item in patch_receipt.items() if key not in OWN_PATCHES for name in item['files']})
own_files = sorted({name for key in OWN_PATCHES for name in patch_receipt[key]['files']})
scan = units_of(patched_files)
later_exemptions, unit_check = {}, {}
for name in patched_files:
    units = list(scan.get(name, []))
    if name.startswith('Source/WebCore/') and name.endswith('.cpp'):
        standalone = 'Source/WebCore/CMakeFiles/WebCore.dir/' + name.removeprefix('Source/WebCore/') + '.obj'
        if ('build ' + standalone.replace('/', chr(92)) + ':') in ninja_text:
            units.append(standalone)
    source_time = os.stat(Path('C:/wk/src') / name).st_mtime_ns
    for unit in units:
        if unit in OWNER_OBJECTS:
            continue
        obj = replacements.get(unit)
        assert obj, unit + ' has no parent object'
        if Path(obj).stat().st_mtime_ns <= source_time:
            ours = [line for key in patch_receipt if key not in OWN_PATCHES for line in hunk_lines(repo / 'patches' / key, name)]
            theirs = {patch: hunk_lines(patch, name) for patch in LATER_PATCHES}
            assert any(theirs.values()) and sorted(src_diff(name)) == sorted(ours + [line for lines in theirs.values() for line in lines]), \
                unit + ' is not a parent object newer than ' + name
            later_exemptions[name] = {'unit': unit, 'laterPatches': [patch for patch, lines in theirs.items() if lines],
                                      'seriesLines': len(ours), 'laterLines': sum(len(lines) for lines in theirs.values())}
        unit_check[unit] = obj
own_scan = units_of(own_files)
own_units = sorted(set(own_scan['all']))
assert sorted(own_units) == sorted(OWNER_OBJECTS), own_units
later_scan = units_of([name for names in later_files.values() for name in names])
later_reach = {unit: sorted(name for name, us in later_scan.items() if name != 'all' and unit in us) for unit in own_units}

glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
assert glue_target in replacements
build_files = {p: p.stat().st_mtime_ns for p in [build / 'CMakeCache.txt', build / 'build.ninja', build / '.ninja_log', build / '.ninja_deps', build / 'bin/WebCore.dll'] if p.exists()}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')

command_map = {}
for command in commands([glue_target, *own_units]):
    output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
    if 'clang-cl.exe' in command and output:
        command_map[normalize(output.group(1) or output.group(2))] = command
target, obj, code = compile_object(0, glue_target)
if code:
    raise SystemExit('RanvierDomGlue failed')
replacements[glue_target] = obj
recompiled = {glue_target: obj}


def disassembly(path):
    listing = subprocess.run([str(compiler.parent / 'llvm-objdump.exe'), '-d', '--no-show-raw-insn', path], capture_output=True, text=True, check=True).stdout
    return hashlib.sha256(chr(10).join(listing.splitlines()[2:]).encode()).hexdigest()


own_unit_receipt = {}
for index, unit in enumerate(own_units, start=1):
    assert unit in command_map and unit in replacements, unit
    target, unit_obj, code = compile_object(100 + index, unit)
    if code:
        raise SystemExit(unit + ' failed')
    replacements[unit] = unit_obj
    recompiled[unit] = unit_obj
    own_unit_receipt[unit] = {'object': unit_obj, 'ownerObject': OWNER_OBJECTS[unit], 'laterPatchFilesReaching': later_reach[unit],
                              'disassemblySha256': disassembly(unit_obj), 'ownerDisassemblySha256': disassembly(OWNER_OBJECTS[unit])}
    own_unit_receipt[unit]['disassemblyEqual'] = own_unit_receipt[unit]['disassemblySha256'] == own_unit_receipt[unit]['ownerDisassemblySha256']
    assert own_unit_receipt[unit]['disassemblyEqual'] or not later_reach[unit], (unit, 'a later patch reaches it and its code differs from the owner object')

own_glue = {}
inspect_obj, undefined, inspector_symbols = None, [], []
for index, source in enumerate(glue_sources[1:], start=90):
    stem = Path(source).stem
    glue_command, count = re.subn(r'C:[/\\]wk[/\\]ranvier-webcore[/\\]host[/\\]dom[/\\]RanvierDomGlue.cpp', (repo / source).as_posix(), command_map[glue_target])
    assert count == 1, count
    command_map['Ranvier/host/' + stem + '.cpp.obj'] = glue_command
    target, glue_obj, code = compile_object(index, 'Ranvier/host/' + stem + '.cpp.obj')
    if code:
        raise SystemExit(stem + ' failed')
    own_glue[stem] = glue_obj
    if stem == 'RanvierInspectGlue':
        inspect_obj = glue_obj
        undefined = subprocess.run([str(compiler.parent / 'llvm-nm.exe'), '--undefined-only', '--demangle', glue_obj],
                                   capture_output=True, text=True, check=True).stdout.splitlines()
        inspector_symbols = [line for line in undefined if re.search(r'Inspector(Controller|Instrumentation|Frontend|Agent)|InspectorOverlay', line)]
        assert not inspector_symbols, inspector_symbols
assert inspect_obj
(out / 'source-patches.json').write_text(json.dumps({'patches': patch_receipt, 'parent': str(parent), 'parentReceipt': parent_patches,
                                                     'recompiledUnits': recompiled, 'ownPatches': OWN_PATCHES, 'ownPatchUnits': own_unit_receipt,
                                                     'ownPatchFiles': {name: hashlib.sha256((Path('C:/wk/src') / name).read_bytes()).hexdigest() for name in own_files},
                                                     'patchUnitsBorrowed': unit_check, 'laterPatches': later_files, 'laterPatchExemptions': later_exemptions,
                                                     'inspectGlue': {'object': inspect_obj, 'undefinedSymbols': len(undefined), 'inspectorSymbols': inspector_symbols},
                                                     'ownGlue': own_glue, 'parentGlueObjects': parent_glue}, indent=2))
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))
extra = [Path(item).as_posix() for item in own_glue.values()]
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
assert owner_hashes == {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in OWNER_OBJECTS.values()}, 'owner objects changed'
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.iterdir() if p.is_file()}
assert hashes['JavaScriptCore.dll'].startswith('95149cdc')
(out / 'runtime-sha256.json').write_text(json.dumps(hashes, indent=2))
print('BATCH3 CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']},
      {unit.rsplit('/', 1)[-1]: item['disassemblyEqual'] for unit, item in own_unit_receipt.items()}, flush=True)
