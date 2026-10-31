"""Private batch-6 candidate (Web Animations A02-A10 on batch 5) on the flag-enabled build C:/wk/pointer-build, whose
objects are borrowed read-only. It starts from batch5-candidate-1: every WebCore unit links batch5-candidate-1's object
(its recompiled 0040-0050 units, or the build's own object), except the units that patch 0051 reaches, which are
recompiled from C:/wk/src, and UnifiedSource-dom-10, which is compiled from a private unified source whose EventLoop.cpp
is an overlay copy of C:/wk/src's with patch 0052 applied (0052 is not yet in C:/wk/src). Every host glue unit of this
tree is compiled (config/common.cmake WebCore_EMBEDDER_SOURCES), WebCore is relinked, and the five host units are
recompiled and relinked. The other runtime libraries are batch5-candidate-1's.
The overlay mechanism is the one of C:/wk/waapi-fx-artifacts/a11/build_fx_candidate-overlay.py (FX_OVERLAY), applied to
the pointer-build commands that batch5-candidate-1 used.
usage: build_batch6_candidate.py <batch6-candidate-N> [repo]
Every linked object must be newer than each recorded dependency, or be recompiled here."""
import ast
import concurrent.futures
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

repo = Path(sys.argv[2] if len(sys.argv) > 2 else 'C:/wk/native-batch-6')
assert sys.argv[1].startswith('batch6-candidate-'), 'Build into artifacts/batch6-candidate-N'
parent5 = Path('C:/wk/native-batch-5/artifacts/batch5-candidate-1')
out = repo / 'artifacts' / sys.argv[1]
build = Path('C:/wk/pointer-build')
slim = Path('C:/wk/build-win-slim')
src = Path('C:/wk/src')
OVERLAY_PATCH = '0052'
OVERLAY_UNIT = 'Source/WebCore/CMakeFiles/WebCore.dir/__/__/WebCore/DerivedSources/unified-sources/UnifiedSource-dom-10.cpp.obj'
OVERLAY_MEMBER = 'Source/WebCore/dom/EventLoop.cpp'
RECOMPILED_PATCHES = ['0051']
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'
out.mkdir(parents=True, exist_ok=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
    tracked = subprocess.run(['git', '-C', str(src), 'ls-files', '--', name], capture_output=True, text=True, check=True).stdout.strip()
    if not tracked:
        return ['+' + line for line in (src / name).read_text(encoding='utf-8').splitlines()]
    return diff_lines(subprocess.run(['git', '-C', str(src), 'diff', '--', name], capture_output=True, text=True, check=True).stdout)


def carries(patch, name):
    hunk, index = hunk_lines(patch, name), 0
    for line in src_diff(name):
        if index < len(hunk) and line == hunk[index]:
            index += 1
    return index == len(hunk)


# The series: 0040-0052. C:/wk/src carries 0040-0051; 0052 is applied to the overlay copy only.
series = [line for line in (repo / 'patches/series').read_text().splitlines() if line[:4].isdigit() and line[:4] >= '0040']
assert [name[:4] for name in series] == [f'{n:04d}' for n in range(40, 53)], series
patch_receipt = {}
for name in series:
    path = repo / 'patches' / name
    patch_receipt[name] = {'sha256': sha(path), 'files': patch_files(path)}
    if name[:4] == OVERLAY_PATCH:
        assert patch_receipt[name]['files'] == [OVERLAY_MEMBER], patch_receipt[name]
        assert not src_diff(OVERLAY_MEMBER), 'C:/wk/src already changes ' + OVERLAY_MEMBER
        continue
    for target in patch_receipt[name]['files']:
        assert carries(path, target), target + ' does not carry ' + name
overlay_patch = repo / 'patches' / next(name for name in series if name[:4] == OVERLAY_PATCH)
overlay_root = out / 'overlay'
overlay_file = overlay_root / OVERLAY_MEMBER
overlay_file.parent.mkdir(parents=True, exist_ok=True)


def apply_hunks(patch, name, text):
    """The text with each hunk of the patch for the file replaced, old block by new block; each old block is unique."""
    body = Path(patch).read_text(encoding='utf-8')
    for hunk in re.split(r'(?m)^@@ [^\n]*@@[^\n]*\n', body.split('diff --git a/' + name, 1)[1])[1:]:
        hunk = hunk.split('\ndiff --git ', 1)[0]
        old = [line[1:] for line in hunk.splitlines() if line[:1] in (' ', '-')]
        new = [line[1:] for line in hunk.splitlines() if line[:1] in (' ', '+')]
        old_text, new_text = '\n'.join(old) + '\n', '\n'.join(new) + '\n'
        assert text.count(old_text) == 1, ('hunk context not unique', name)
        text = text.replace(old_text, new_text)
    return text


source_text = (src / OVERLAY_MEMBER).read_bytes().decode('utf-8')
assert '\r\n' not in source_text
overlay_file.write_bytes(apply_hunks(overlay_patch, OVERLAY_MEMBER, source_text).encode('utf-8'))
overlay_diff = subprocess.run(['git', 'diff', '--no-index', '--', (src / OVERLAY_MEMBER).as_posix(), overlay_file.as_posix()],
                              capture_output=True, text=True).stdout
assert diff_lines(overlay_diff) == hunk_lines(overlay_patch, OVERLAY_MEMBER), 'overlay differs from the patch'

cache = (build / 'CMakeCache.txt').read_text()
for flag in ['ENABLE_TOUCH_EVENTS', 'ENABLE_POINTER_LOCK']:
    assert re.search('^' + flag + r':BOOL=ON$', cache, re.M), flag
compiler = Path(re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.+)$', cache, re.M).group(1))
ninja = re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$', cache, re.M).group(1)
guarded = [build / name for name in ['CMakeCache.txt', 'build.ninja', '.ninja_log', '.ninja_deps', 'bin/WebCore.dll', 'bin/JavaScriptCore.dll', 'lib/WebCore.lib']]
guarded_times = {p: p.stat().st_mtime_ns for p in guarded}
slim_time = (slim / 'build.ninja').stat().st_mtime_ns
parent_files = [p for p in parent5.rglob('*') if p.is_file() and p.suffix in ('.obj', '.dll', '.lib', '.json')]
parent_times = {str(p): p.stat().st_mtime_ns for p in parent_files}
parent_objects = json.loads((parent5 / 'replacement-objects.json').read_text(encoding='utf-8'))
parent_receipt = json.loads((parent5 / 'source-patches.json').read_text(encoding='utf-8'))

deps_text = subprocess.run([ninja, '-C', str(build), '-t', 'deps'], capture_output=True, text=True, check=True).stdout
mtimes, deps, target = {}, {}, None


def mtime(path):
    if path not in mtimes:
        try:
            mtimes[path] = os.stat(path).st_mtime_ns
        except FileNotFoundError:
            mtimes[path] = None
    return mtimes[path]


for line in deps_text.splitlines():
    if line and not line.startswith(' '):
        target = line.split(':', 1)[0].strip().replace(chr(92), '/')
        deps[target] = []
        continue
    if line.strip() and target:
        path = Path(line.strip())
        deps[target].append(os.path.normcase(os.path.normpath(str(path if path.is_absolute() else build / path))))


def units_of(files):
    keys = {os.path.normcase(os.path.normpath(str(src / name))): name for name in files}
    hits = {name: set() for name in files}
    for unit, items in deps.items():
        for item in items:
            real = os.path.normcase(os.path.realpath(item))
            if real in keys:
                hits[keys[real]].add(unit)
    return {name: sorted(targets) for name, targets in hits.items()}


recompile_files = sorted({name for key, item in patch_receipt.items() if key[:4] in RECOMPILED_PATCHES for name in item['files']
                          if (src / name).suffix in ('.cpp', '.h')})
reach = units_of(recompile_files)
units = sorted({unit for targets in reach.values() for unit in targets if unit.startswith('Source/WebCore/CMakeFiles/WebCore.dir/')
                and 'Ranvier' not in unit})
assert OVERLAY_UNIT not in units, 'the overlay unit is reached by 0051'
# Freshness of every linked object that is not recompiled here: the parent's object (or the build's) is newer than each
# dependency recorded for its unit.
stale = {}
for unit, items in deps.items():
    if not unit.startswith('Source/WebCore/CMakeFiles/WebCore.dir/') or 'Ranvier' in unit or unit in units or unit == OVERLAY_UNIT:
        continue
    linked = parent_objects.get(unit, (build / unit).as_posix())
    own = mtime(os.path.normcase(os.path.normpath(linked)))
    if own is None:
        continue
    newer = sorted({os.path.realpath(item).replace(chr(92), '/') for item in items
                    if (mtime(os.path.normcase(os.path.realpath(item))) or 0) > own})
    if newer:
        stale[unit] = newer
assert not stale, ('linked objects older than a source', dict(list(stale.items())[:5]))
if os.environ.get('BATCH6_PLAN_ONLY'):
    print(json.dumps({'recompile': units, 'reach': reach, 'overlay': OVERLAY_UNIT, 'parentObjects': len(parent_objects)}, indent=1))
    raise SystemExit(0)

tree = ast.parse((repo / 'scripts/build.py').read_text())
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'toolchain_env')
scope = dict(os=os, pathlib=__import__('pathlib'), subprocess=subprocess, sys=sys, windows=True, arch='x64', system='win',
             args=types.SimpleNamespace(tool_path=[]), llvm=compiler.parent, vcpkg=Path('C:/wk/vcpkg'),
             pins=json.loads((repo / 'pins.json').read_text()))
exec(compile(ast.Module(body=[function], type_ignores=[]), '<toolchain_env>', 'exec'), scope)
env = scope['toolchain_env']()
stop = threading.Event()
helpers = ast.parse(Path('C:/wk/native-cssom-detached-context/artifacts/build_context_candidate.py').read_text())
names = {'normalize', 'commands', 'execute', 'link_command'}
functions = [node for node in helpers.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(functions) == len(names)
exec(compile(ast.Module(body=functions, type_ignores=[]), '<reviewed_private_build_helpers>', 'exec'), globals())
lines = (build / 'build.ninja').read_text().splitlines()
runtime = out / 'runtime'
runtime.mkdir(parents=True, exist_ok=True)
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')

# Glue: each source of config/common.cmake compiles with the build's DOM glue command, retargeted to this tree.
cmake = (repo / 'config/common.cmake').read_text(encoding='utf-8')
embedder = re.search(r'set\(WebCore_EMBEDDER_SOURCES "([^"]+)"', cmake).group(1).split(';')
glue_sources = [item.replace('${_ranvier_root}/', '') for item in embedder]
assert glue_sources[0] == 'host/dom/RanvierDomGlue.cpp' and len(glue_sources) == 13, glue_sources
pointer_glue = {Path(m).name: m.replace(chr(92), '/') for m in re.findall(r'^build (Source\\WebCore\\CMakeFiles\\WebCore\.dir\\C_\\wk\\native-pointer\\host\\\S+?\.cpp\.obj):', '\n'.join(lines), re.M)}
dom_target = pointer_glue['RanvierDomGlue.cpp.obj']
command_map = {}
for command in commands([dom_target, *units, OVERLAY_UNIT]):
    output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
    if 'clang-cl.exe' in command and output:
        command_map[normalize(output.group(1) or output.group(2))] = command
assert set([dom_target, *units, OVERLAY_UNIT]) <= set(command_map), sorted(set([dom_target, *units, OVERLAY_UNIT]) - set(command_map))
# The overlay unit: a private unified source that includes the overlay EventLoop.cpp in place of the member.
unified = build / 'WebCore/DerivedSources/unified-sources' / Path(OVERLAY_UNIT).name.removesuffix('.obj')
unified_lines = unified.read_text().splitlines()
original = '#include "' + OVERLAY_MEMBER.removeprefix('Source/WebCore/').replace('/', chr(92)) + '"'
assert unified_lines.count(original) == 1, original
unified_lines[unified_lines.index(original)] = '#include "' + overlay_file.as_posix() + '"'
private_unified = out / ('overlay-' + unified.name)
private_unified.write_text(chr(10).join(unified_lines) + chr(10))
pattern = ('[/' + chr(92) * 2 + ']').join(re.escape(part) for part in unified.as_posix().split('/'))
overlay_command, count = re.subn(pattern, lambda _: private_unified.as_posix(), command_map[OVERLAY_UNIT])
assert count == 1, count

# Every glue object of the parent is replaced; the WebCore link takes the parent's other objects.
replacements = {k: v for k, v in parent_objects.items() if 'Ranvier' not in k}
extra_glue, jobs = [], []
for index, source in enumerate(glue_sources):
    glue_command, count = re.subn(r'C:[/\\]wk[/\\]native-pointer[/\\]host[/\\]dom[/\\]RanvierDomGlue\.cpp', (repo / source).as_posix(), command_map[dom_target])
    assert count == 1, (source, count)
    jobs.append((index, 'glue/' + Path(source).name + '.obj', glue_command, pointer_glue.get(Path(source).name + '.obj')))
for index, unit in enumerate(units, start=100):
    jobs.append((index, unit, command_map[unit], unit))
jobs.append((200, OVERLAY_UNIT, overlay_command, OVERLAY_UNIT))


def compile_job(job):
    index, name, command, target = job
    if stop.is_set():
        return job, None, 1
    assert '/Yc' not in command and '/sourceDependencies' not in command, name
    stem = f'{index:03d}-' + Path(name).name
    obj = out / stem
    command, count = re.subn(r'/Fo(?:"[^"]+"|\S+)', '/Fo' + obj.as_posix(), command)
    assert count == 1
    command = re.sub(r'/Fd(?:"[^"]+"|\S+)', '/Fd' + (out / (stem + '.pdb')).as_posix(), command)
    parts = re.match(r'^(?:"([^"]+)"|(\S+))\s+(.*)$', command)
    command = '"' + (parts.group(1) or parts.group(2)) + '" /I' + private_headers.parent.as_posix() + ' /I' + private_headers.as_posix() + ' ' + parts.group(3)
    (out / (stem + '.command-sha256')).write_text(hashlib.sha256(command.encode()).hexdigest())
    return job, obj.as_posix(), execute(command, stem)


with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    results = list(pool.map(compile_job, jobs))
failed = [job[1] for job, obj, code in results if code]
assert not failed, failed
glue_objects, unit_receipt = {}, {}


def disassembly(path):
    listing = subprocess.run([str(compiler.parent / 'llvm-objdump.exe'), '-d', '--no-show-raw-insn', path], capture_output=True, text=True, check=True).stdout
    return hashlib.sha256(chr(10).join(listing.splitlines()[2:]).encode()).hexdigest()


for (index, name, command, target), obj, code in results:
    if name.startswith('glue/'):
        glue_objects[name[5:]] = obj
        if target:
            replacements[target] = obj
        else:
            extra_glue.append(obj)
        continue
    replacements[target] = obj
    item = {'object': obj, 'buildObject': (build / target).as_posix(), 'parentObject': parent_objects.get(target),
            'patchFilesReaching': sorted(name for name, us in reach.items() if target in us)}
    if target == OVERLAY_UNIT:
        item['overlay'] = {'member': OVERLAY_MEMBER, 'file': overlay_file.as_posix(), 'sha256': sha(overlay_file),
                           'patch': overlay_patch.name, 'unifiedSource': private_unified.as_posix()}
    item['disassemblySha256'], item['buildDisassemblySha256'] = disassembly(obj), disassembly(build / target)
    item['disassemblyEqualToBuild'] = item['disassemblySha256'] == item['buildDisassemblySha256']
    unit_receipt[target] = item
assert set(pointer_glue.values()) <= set(replacements), 'a glue object of the build is not replaced'
undefined = subprocess.run([str(compiler.parent / 'llvm-nm.exe'), '--undefined-only', '--demangle', glue_objects['RanvierInspectGlue.cpp.obj']],
                           capture_output=True, text=True, check=True).stdout.splitlines()
inspector_symbols = [line for line in undefined if re.search(r'Inspector(Controller|Instrumentation|Frontend|Agent)|InspectorOverlay', line)]
assert not inspector_symbols, inspector_symbols

link = link_command('WebCore') + ' ' + ' '.join(Path(item).as_posix() for item in extra_glue) + ' Dwrite.lib'
if execute(link, 'webcore-link'):
    raise SystemExit(1)

host_target = r'Tools\TestWebKitAPI\CMakeFiles\RanvierWebCoreHost.dir\RanvierAbi\RanvierWebCoreAbi.cpp.obj'
host_command = next(c for c in commands([host_target]) if 'clang-cl.exe' in c and 'RanvierWebCoreAbi.cpp' in c)
flags = re.findall(r'^((?:USE|ENABLE)_[A-Z0-9_]+):BOOL=(ON|OFF|1|0|TRUE|FALSE)$', cache, re.M)
flag_arguments = ' '.join('/DRV_CAP_' + name + '=' + ('1' if value in ['ON', '1', 'TRUE'] else '0') for name, value in flags)
assert '/DRV_CAP_ENABLE_TOUCH_EVENTS=1' in flag_arguments and '/DRV_CAP_ENABLE_POINTER_LOCK=1' in flag_arguments
host_objects = []
for filename in ['RanvierWebCoreAbi.cpp', 'RanvierWebCoreDom.cpp', 'RanvierWebCoreUia.cpp', 'RanvierWebCoreD3D11.cpp', 'RanvierImageEncoding.cpp']:
    command, count = re.subn(r'C:[/\\]wk[/\\]src[/\\]Tools[/\\]TestWebKitAPI[/\\]RanvierAbi[/\\]RanvierWebCoreAbi\.cpp', (repo / 'host' / filename).as_posix(), host_command)
    assert count == 1, (filename, count)
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

# JavaScriptCore and every other library: batch5-candidate-1's.
reused = {}
for item in sorted((parent5 / 'runtime').iterdir()):
    if item.name.startswith(('RanvierWebCoreHost', 'WebCore')):
        continue
    if item.is_dir():
        shutil.copytree(item, runtime / item.name, dirs_exist_ok=True)
    else:
        shutil.copy2(item, runtime / item.name)
        reused[item.name] = sha(item)
assert guarded_times == {p: p.stat().st_mtime_ns for p in guarded}, 'pointer-build changed'
assert (slim / 'build.ninja').stat().st_mtime_ns == slim_time, 'build-win-slim changed'
assert parent_times == {str(p): p.stat().st_mtime_ns for p in parent_files}, 'batch5-candidate-1 changed'
hashes = {str(p.relative_to(runtime)).replace(chr(92), '/'): sha(p) for p in sorted(runtime.rglob('*')) if p.is_file()}
assert hashes['JavaScriptCore.dll'] == sha(parent5 / 'runtime/JavaScriptCore.dll')
(out / 'runtime-sha256.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2) + '\n', encoding='utf-8')
(out / 'source-patches.json').write_text(json.dumps({
    'build': str(build), 'flags': {'ENABLE_TOUCH_EVENTS': 'ON', 'ENABLE_POINTER_LOCK': 'ON'}, 'parent': str(parent5),
    'parentReceipt': parent_receipt, 'patches': patch_receipt, 'recompiledPatches': RECOMPILED_PATCHES,
    'overlayPatch': {'patch': overlay_patch.name, 'unit': OVERLAY_UNIT, 'note': 'not yet in C:/wk/src; compiled from an overlay copy'},
    'recompiledUnits': unit_receipt, 'glueObjects': glue_objects, 'glueAppended': extra_glue,
    'inspectGlue': {'undefinedSymbols': len(undefined), 'inspectorSymbols': inspector_symbols},
    'reusedFromBatch5Candidate1': reused}, indent=2) + '\n', encoding='utf-8')
print('BATCH6 CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']},
      'units', len(unit_receipt), flush=True)
