"""Private batch-4 candidate (I03+I04+I06, A01, T02, B06+R12) on the full flag-enabled build C:/wk/pointer-build
(ENABLE_TOUCH_EVENTS and ENABLE_POINTER_LOCK on), whose objects are borrowed read-only. Every host glue unit of this
tree is compiled (config/common.cmake WebCore_EMBEDDER_SOURCES), every unit that the series patches 0040-0043 and 0048
reach is recompiled from C:/wk/src, WebCore is relinked, and the five host units are recompiled and relinked. The other
runtime libraries are pointer-candidate-4's, whose WebCore.dll equals the build's.
usage: build_batch4_candidate.py <batch4-candidate-N> [repo]
Every borrowed object must be newer than each recorded dependency, except dependencies that only the later patches
(LATER_PATCHES, applied in C:/wk/src but outside this batch) touched: those objects predate the later patch, which this
batch leaves out. A recompiled unit that a later patch reaches is recorded; one that compiles a later patch's .cpp is
borrowed instead. A recompiled unit outside every later patch must disassemble identically to the build's object."""
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

repo = Path(sys.argv[2] if len(sys.argv) > 2 else 'C:/wk/native-batch-4')
assert sys.argv[1].startswith('batch4-candidate-'), 'Build into artifacts/batch4-candidate-N'
RECOMPILED_PATCHES = ['0040', '0041', '0042', '0043', '0048']
POINTER_PATCHES = ['0044', '0045', '0046', '0047']
LATER_PATCHES = ['C:/wk/patch0049/0049-image-bitmap-crop-completion-handler.patch',
                 'C:/wk/patch0050/0050-image-bitmap-unaccelerated-buffers.patch',
                 'C:/wk/patch0051/0051-web-animation-promise-observer.patch']
out = repo / 'artifacts' / sys.argv[1]
build = Path('C:/wk/pointer-build')
pointer_parent = Path('C:/wk/pointer-artifacts/pointer-candidate-4')
slim = Path('C:/wk/build-win-slim')
src = Path('C:/wk/src')
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


# The series: 0040-0048 here; C:/wk/src carries each one, and the later patches too.
series = [line for line in (repo / 'patches/series').read_text().splitlines() if line[:4].isdigit() and line[:4] >= '0040']
assert [name[:4] for name in series] == ['0040', '0041', '0042', '0043', '0044', '0045', '0046', '0047', '0048'], series
patch_receipt = {}
for name in series:
    path = repo / 'patches' / name
    patch_receipt[name] = {'sha256': sha(path), 'files': patch_files(path)}
    for target in patch_receipt[name]['files']:
        assert carries(path, target), target + ' does not carry ' + name
later_files = {}
for patch in LATER_PATCHES:
    later_files[patch] = [name for name in patch_files(patch) if (src / name).exists()]
    for name in later_files[patch]:
        assert carries(patch, name), name + ' does not carry ' + patch
later_sources = {os.path.normcase(os.path.normpath(str(src / name))) for names in later_files.values() for name in names}

cache = (build / 'CMakeCache.txt').read_text()
for flag in ['ENABLE_TOUCH_EVENTS', 'ENABLE_POINTER_LOCK']:
    assert re.search('^' + flag + r':BOOL=ON$', cache, re.M), flag
compiler = Path(re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.+)$', cache, re.M).group(1))
ninja = re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$', cache, re.M).group(1)
guarded = [build / name for name in ['CMakeCache.txt', 'build.ninja', '.ninja_log', '.ninja_deps', 'bin/WebCore.dll', 'bin/JavaScriptCore.dll', 'lib/WebCore.lib']]
guarded_times = {p: p.stat().st_mtime_ns for p in guarded}
slim_time = (slim / 'build.ninja').stat().st_mtime_ns
assert sha(build / 'bin/WebCore.dll') == sha(pointer_parent / 'runtime/WebCore.dll'), 'pointer-build is not pointer-candidate-4'

# Freshness of every borrowed object: newer than each recorded dependency, or older only than later-patch files.
deps_text = subprocess.run([ninja, '-C', str(build), '-t', 'deps'], capture_output=True, text=True, check=True).stdout
assert guarded_times == {p: p.stat().st_mtime_ns for p in guarded}
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
stale_later, stale_other = {}, {}
for target, items in deps.items():
    own = mtime(os.path.normcase(os.path.normpath(str(build / target))))
    if own is None:
        continue
    newer = []
    for item in items:
        real = os.path.normcase(os.path.realpath(item))
        stamp = mtime(real)
        if stamp is None or stamp > own:
            newer.append(real)
    if newer:
        bucket = stale_later if all(item in later_sources for item in newer) else stale_other
        bucket[target] = sorted(set(newer))
assert not stale_other, ('borrowed objects older than a batch source', dict(list(stale_other.items())[:5]))


def units_of(files):
    keys = {os.path.normcase(os.path.normpath(str(src / name))): name for name in files}
    hits = {name: set() for name in files}
    for target, items in deps.items():
        for item in items:
            real = os.path.normcase(os.path.realpath(item))
            if real in keys:
                hits[keys[real]].add(target)
    return {name: sorted(targets) for name, targets in hits.items()}


recompile_files = sorted({name for key, item in patch_receipt.items() if key[:4] in RECOMPILED_PATCHES for name in item['files']})
reach = units_of(recompile_files)
units = sorted({unit for targets in reach.values() for unit in targets if unit.startswith('Source/WebCore/CMakeFiles/WebCore.dir/')
                and 'Ranvier' not in unit})
later_reach = {}
for unit in units:
    hits = sorted({item for item in deps[unit] if os.path.normcase(os.path.realpath(item)) in later_sources})
    if hits:
        later_reach[unit] = [os.path.realpath(item).replace(chr(92), '/') for item in hits]
later_cpp = {unit for unit, hits in later_reach.items() if any(hit.endswith('.cpp') for hit in hits)}
borrowed_instead = sorted(later_cpp)
units = [unit for unit in units if unit not in later_cpp]
if os.environ.get('BATCH4_PLAN_ONLY'):
    print(json.dumps({'units': units, 'laterReach': later_reach, 'borrowedInstead': borrowed_instead, 'staleLater': len(stale_later)}, indent=1))
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
assert glue_sources[0] == 'host/dom/RanvierDomGlue.cpp' and len(glue_sources) == 11, glue_sources
pointer_glue = {Path(m).name: m.replace(chr(92), '/') for m in re.findall(r'^build (Source\\WebCore\\CMakeFiles\\WebCore\.dir\\C_\\wk\\native-pointer\\host\\\S+?\.cpp\.obj):', '\n'.join(lines), re.M)}
dom_target = pointer_glue['RanvierDomGlue.cpp.obj']
command_map = {}
for command in commands([dom_target, *units]):
    output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
    if 'clang-cl.exe' in command and output:
        command_map[normalize(output.group(1) or output.group(2))] = command
assert set([dom_target, *units]) <= set(command_map), sorted(set([dom_target, *units]) - set(command_map))
replacements, extra_glue, jobs = {}, [], []
for index, source in enumerate(glue_sources):
    glue_command, count = re.subn(r'C:[/\\]wk[/\\]native-pointer[/\\]host[/\\]dom[/\\]RanvierDomGlue\.cpp', (repo / source).as_posix(), command_map[dom_target])
    assert count == 1, (source, count)
    jobs.append((index, 'glue/' + Path(source).name + '.obj', glue_command, pointer_glue.get(Path(source).name + '.obj')))
for index, unit in enumerate(units, start=100):
    jobs.append((index, unit, command_map[unit], unit))


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


with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
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
    item = {'object': obj, 'buildObject': (build / target).as_posix(), 'laterPatchFilesReaching': later_reach.get(target, []),
            'patchFilesReaching': sorted(name for name, us in reach.items() if target in us)}
    item['disassemblySha256'], item['buildDisassemblySha256'] = disassembly(obj), disassembly(build / target)
    item['disassemblyEqual'] = item['disassemblySha256'] == item['buildDisassemblySha256']
    assert item['disassemblyEqual'] or item['laterPatchFilesReaching'], (target, 'recompiled code differs from the build object')
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

# JavaScriptCore and every other library: the build's and pointer-candidate-4's.
shutil.copy2(build / 'bin/JavaScriptCore.dll', runtime / 'JavaScriptCore.dll')
shutil.copy2(build / 'bin/JavaScriptCore.pdb', runtime / 'JavaScriptCore.pdb')
reused = {}
for item in sorted((pointer_parent / 'runtime').iterdir()):
    if item.name.startswith(('RanvierWebCoreHost', 'WebCore', 'JavaScriptCore')):
        continue
    if item.is_dir():
        shutil.copytree(item, runtime / item.name, dirs_exist_ok=True)
    else:
        shutil.copy2(item, runtime / item.name)
        reused[item.name] = sha(item)
assert guarded_times == {p: p.stat().st_mtime_ns for p in guarded}, 'pointer-build changed'
assert (slim / 'build.ninja').stat().st_mtime_ns == slim_time, 'build-win-slim changed'
hashes = {str(p.relative_to(runtime)).replace(chr(92), '/'): sha(p) for p in sorted(runtime.rglob('*')) if p.is_file()}
assert hashes['JavaScriptCore.dll'] == sha(pointer_parent / 'runtime/JavaScriptCore.dll')
(out / 'runtime-sha256.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2) + '\n', encoding='utf-8')
(out / 'source-patches.json').write_text(json.dumps({
    'build': str(build), 'flags': {'ENABLE_TOUCH_EVENTS': 'ON', 'ENABLE_POINTER_LOCK': 'ON'},
    'hostCapabilityFlags': 'RV_CAP_* from the build CMakeCache (pointer-candidate-4 compiled its host from a flags-off template)',
    'patches': patch_receipt, 'recompiledPatches': RECOMPILED_PATCHES, 'pointerPatchesFromBuild': POINTER_PATCHES,
    'laterPatches': later_files, 'laterPatchNote': 'Applied in C:/wk/src after the build, outside batch 4. Borrowed objects that '
    'depend on their files predate them; recompiled units that reach them carry them (0049: an unused exported static function).',
    'borrowedObjectsOlderOnlyThanLaterPatchFiles': stale_later, 'recompiledUnits': unit_receipt,
    'unitsBorrowedBecauseTheyCompileALaterPatchCpp': borrowed_instead,
    'glueObjects': glue_objects, 'glueReplacingBuildObjects': {k: v for k, v in replacements.items() if 'native-pointer' in k},
    'glueAppended': extra_glue, 'inspectGlue': {'undefinedSymbols': len(undefined), 'inspectorSymbols': inspector_symbols},
    'reusedFromPointerCandidate4': reused}, indent=2) + '\n', encoding='utf-8')
print('BATCH4 CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']},
      'units', len(unit_receipt), 'equal', sum(item['disassemblyEqual'] for item in unit_receipt.values()),
      'laterReach', len([u for u in unit_receipt.values() if u['laterPatchFilesReaching']]), 'borrowedInstead', len(borrowed_instead), flush=True)
