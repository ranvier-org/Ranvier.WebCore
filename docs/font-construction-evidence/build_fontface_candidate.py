"""Private T02 font construction candidate (derived from docs/canvas-paths-evidence/build_paths_candidate.py of the R02 lane
and docs/font-readiness-evidence/build_fonts_candidate.py of T01). The parent native46-candidate-6 (built at ed60fd4) with
this tree's RanvierDomGlue, RanvierResourceGlue and RanvierInspectGlue compiled, every unit patch 0048 reaches recompiled
from C:/wk/src, WebCore relinked, and the four host units recompiled and relinked.
usage: build_fontface_candidate.py <fontface-candidate-N> [parent candidate dir]
The other host-glue objects the parent's WebCore link names are borrowed read-only after asserting their sources equal the
parent tree. Root patches 0040-0047, which C:/wk/src carries and this series does not, are checked hunk for hunk; no unit
this build compiles includes a .cpp they change."""
import ast
from concurrent.futures import ThreadPoolExecutor
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

repo = Path('C:/wk/native-fontface')
assert sys.argv[1].startswith('fontface-candidate-'), 'Build into artifacts/fontface-candidate-N'
out = repo / 'artifacts' / sys.argv[1]
parent = Path(sys.argv[2] if len(sys.argv) > 2 else 'C:/wk/native-cascade-shadow/artifacts/native46-candidate-6')
parent_repo, parent_head = Path('C:/wk/native-cascade-shadow'), 'ed60fd4'
src = Path('C:/wk/src')


def same_as_parent(path):
    theirs = subprocess.run(['git', '-C', str(parent_repo), 'show', parent_head + ':' + path], capture_output=True, check=True).stdout
    return (repo / path).read_bytes().replace(b'\r\n', b'\n') == theirs.replace(b'\r\n', b'\n')


def diff_lines(text):
    return [line for line in text.splitlines() if line[:1] in '+-' and not line.startswith(('+++', '---'))]


def hunk_lines(text, target):
    lines = []
    for section in text.split('\ndiff --git ')[0 if text.startswith('diff --git ') else 1:]:
        if re.search(r'a/(\S+) b/', section).group(1) == target:
            lines += diff_lines(section)
    return lines


def patch_targets(text):
    return [re.search(r'a/(\S+) b/', section).group(1) for section in text.split('\ndiff --git ')[0 if text.startswith('diff --git ') else 1:]]


OWN_PATCHES = {'0048-fontface-loaded-rejection.patch'}
LATER_PATCHES = sorted(Path('C:/wk').glob('patch004[0-7]/004[0-7]-*.patch'))
assert [p.name[:4] for p in LATER_PATCHES] == ['0040', '0041', '0042', '0043', '0044', '0045', '0046', '0047'], LATER_PATCHES
for path in sorted((repo / 'patches').iterdir()):
    if path.name in OWN_PATCHES or path.name == 'series':
        continue
    assert same_as_parent('patches/' + path.name), path.name + ' differs from the parent tree'
parent_series = subprocess.run(['git', '-C', str(parent_repo), 'show', parent_head + ':patches/series'], capture_output=True, text=True, check=True).stdout.split()
assert (repo / 'patches/series').read_text().split() == parent_series + sorted(OWN_PATCHES), 'series is the parent series plus the lane patch'
for path in ['config']:
    assert subprocess.run(['git', 'diff', '--quiet', parent_head, '--', path], cwd=repo).returncode == 0, path
build = Path('C:/wk/build-win-slim')
assert not (out / 'runtime-sha256.json').exists(), 'Build into a new versioned directory'

parent_patches = json.loads((parent / 'source-patches.json').read_text())
series = [line for line in (repo / 'patches/series').read_text().splitlines() if line[:4].isdigit() and line[:4] >= '0035']
covered = {name[:4] for name in parent_patches['patches']}
reused = parent_patches.get('reusedOwnerObject')
for item in (reused if isinstance(reused, list) else [reused] if reused else []):
    covered.add(item['patch'][:4])
assert {name[:4] for name in series if name not in OWN_PATCHES} <= covered, ('patches the parent does not cover', series, sorted(covered))
patch_receipt = {}
for name in series:
    text = (repo / 'patches' / name).read_text(encoding='utf-8')
    patch_receipt[name] = {'sha256': hashlib.sha256((repo / 'patches' / name).read_bytes()).hexdigest(), 'files': []}
    for target in patch_targets(text):
        hunk = hunk_lines(text, target)
        current = diff_lines(subprocess.run(['git', '-C', str(src), 'diff', '--', target], capture_output=True, text=True, check=True).stdout)
        index = 0
        for line in current:
            if index < len(hunk) and line == hunk[index]:
                index += 1
        assert index == len(hunk), target + ' does not carry ' + name
        patch_receipt[name]['files'].append(target)

# Every C:/wk/src file changed after the parent's link is this series' hunks plus the later root patches' hunks, exactly.
parent_link = (parent / 'runtime/WebCore.dll').stat().st_mtime_ns
status = subprocess.run(['git', 'status', '--porcelain', '-uall'], cwd=src, capture_output=True, text=True, check=True).stdout.splitlines()
later_texts = {p.name: p.read_text(encoding='utf-8') for p in LATER_PATCHES}
full_series = [line for line in (repo / 'patches/series').read_text().splitlines() if line[:4].isdigit()]
later_files = {}
for line in status:
    path = line[3:]
    if not (src / path).is_file() or os.stat(src / path).st_mtime_ns < parent_link:
        continue
    owners = [name for name, text in later_texts.items() if path in patch_targets(text)]
    if line.startswith('??'):
        assert owners, path + ' is new and no later root patch adds it'
        later_files[path] = {'patches': owners, 'new': True}
        continue
    current = sorted(diff_lines(subprocess.run(['git', '-C', str(src), 'diff', '--', path], capture_output=True, text=True, check=True).stdout))
    expected = [l for name in full_series for l in hunk_lines((repo / 'patches' / name).read_text(encoding='utf-8'), path)]
    expected += [l for name in owners for l in hunk_lines(later_texts[name], path)]
    assert current == sorted(expected), path + ' carries more than the series and the later root patches'
    later_files[path] = {'patches': owners, 'diffLines': len(current)}
later_cpp = {path.split('/')[-1] for path in later_files if path.endswith('.cpp')}

link = (parent / 'webcore-link.rsp').read_text(encoding='utf-8')
glue_objects = sorted({path for path in re.findall(r'(\S+Ranvier[A-Za-z]+Glue\.cpp\.obj)', link) if 'RanvierDomGlue' not in path})
assert len(glue_objects) == 5, glue_objects
RECOMPILED_GLUE = {'RanvierResourceGlue': 91, 'RanvierInspectGlue': 92}
borrowed_glue = []
for glue in glue_objects:
    stem = re.search(r'(Ranvier[A-Za-z]+Glue)\.cpp\.obj', glue).group(1)
    if stem in RECOMPILED_GLUE:
        continue
    for suffix in ['.cpp', '.h']:
        assert same_as_parent('host/' + stem + suffix), stem + suffix + ' changed since the parent: its object is stale'
    borrowed_glue.append(glue)
assert len(borrowed_glue) == 3, borrowed_glue

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
patched_files = sorted({name for item in patch_receipt.values() for name in item['files']})
scan = json.loads(subprocess.run([sys.executable, '-I', 'C:/wk/t06-artifacts/units_for_headers.py', '--json', *patched_files],
                                 capture_output=True, text=True, check=True).stdout)
ninja_text = (build / 'build.ninja').read_text()
own_files = sorted({name for patch in OWN_PATCHES for name in patch_receipt[patch]['files']})
own_units = sorted({unit for name in own_files for unit in scan.get(name, [])})
assert own_units, own_files
unit_check = {}
for name in patched_files:
    if name in own_files:
        continue
    units = list(scan.get(name, []))
    if name.startswith('Source/WebCore/') and name.endswith('.cpp'):
        standalone = 'Source/WebCore/CMakeFiles/WebCore.dir/' + name.removeprefix('Source/WebCore/') + '.obj'
        if ('build ' + standalone.replace('/', chr(92)) + ':') in ninja_text:
            units.append(standalone)
    source_time = os.stat(src / name).st_mtime_ns
    for unit in units:
        obj = replacements.get(unit)
        assert obj and (name in later_files or Path(obj).stat().st_mtime_ns > source_time), unit + ' is not a parent object newer than ' + name
        unit_check[unit] = obj
# A recompiled unified source must hold no .cpp a later root patch changes: those units keep their pre-patch objects.
unified_dir = build / 'WebCore/DerivedSources/unified-sources'
for unit in own_units:
    match = re.search(r'unified-sources/(UnifiedSource[^/]+\.cpp)\.obj', unit)
    if match:
        included = re.findall(r'#include "([^"]+)"', (unified_dir / match.group(1)).read_text(encoding='utf-8'))
        clash = [i for i in included if i.replace(chr(92), '/').split('/')[-1] in later_cpp]
        assert not clash, (unit, clash)
glue_target = 'Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
assert glue_target in replacements
build_files = {p: p.stat().st_mtime_ns for p in [build / 'CMakeCache.txt', build / 'build.ninja', build / '.ninja_log', build / '.ninja_deps', build / 'bin/WebCore.dll'] if p.exists()}
private_headers = out / 'include/WebCore'
private_headers.mkdir(parents=True, exist_ok=True)
for header in ['CSSRule.h', 'CSSFontFaceRule.h', 'PropertySetCSSDescriptors.h']:
    (private_headers / header).write_text('#pragma once\n#include "C:/wk/src/Source/WebCore/css/' + header + '"\n')

command_map = {}
for command in commands([glue_target] + own_units):
    if 'clang-cl.exe' in command:
        output = re.search(r'/Fo(?:"([^"]+)"|(\S+))', command)
        if output:
            command_map[normalize(output.group(1) or output.group(2))] = command
for unit in own_units:
    assert unit in command_map, unit
glue_sources = {}
for stem, index in RECOMPILED_GLUE.items():
    target = 'Ranvier/host/' + stem + '.cpp.obj'
    command, count = re.subn(r"C:[/\\]wk[/\\]ranvier-webcore[/\\]host[/\\]dom[/\\]RanvierDomGlue.cpp",
                             (repo / 'host' / (stem + '.cpp')).as_posix(), command_map[glue_target])
    assert count == 1, count
    command_map[target] = command
    glue_sources[target] = index
# The lane's own glue first, so a glue error stops the build before the long unit compiles.
results = []
for jobs in ([(0, glue_target)] + [(index, target) for target, index in glue_sources.items()],
             [(index, unit) for index, unit in enumerate(own_units, start=1)]):
    with ThreadPoolExecutor(max_workers=int(os.environ.get('FONTFACE_JOBS', '8'))) as pool:
        results += list(pool.map(lambda job: compile_object(*job), jobs))
    failed = [target for target, _, code in results if code]
    if failed:
        raise SystemExit('compile failed: ' + ', '.join(failed))
compiled = {target: obj for target, obj, _ in results}
replacements[glue_target] = compiled[glue_target]
own_objects = {unit: compiled[unit] for unit in own_units}
replacements.update(own_objects)
glue_compiled = [compiled[target] for target in glue_sources]

later_headers = sorted(Path(p).name for p in later_files if not p.endswith('.cpp'))
included_later = {}
for log in sorted(out.glob('[0-9][0-9][0-9]-*.log')):
    text = log.read_text(encoding='utf-8', errors='replace')
    included_later[log.name] = sorted(h for h in later_headers if h in text)
(out / 'source-patches.json').write_text(json.dumps({'patches': patch_receipt, 'parent': str(parent), 'parentHead': parent_head,
                                                     'parentReceipt': parent_patches, 'borrowedHostGlueObjects': borrowed_glue,
                                                     'recompiledGlue': {target: compiled[target] for target in [glue_target, *glue_sources]},
                                                     'ownPatchUnits': own_objects, 'patchUnitsBorrowed': unit_check,
                                                     'laterRootPatches': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in LATER_PATCHES},
                                                     'laterPatchFiles': later_files,
                                                     'laterPatchHeadersSeenInRecompiledLogs': included_later,
                                                     'note': 'later root patches 0040-0047 change no unit this build compiles; their headers are '
                                                             'layout-neutral (inert ENABLE(TOUCH_EVENTS) guards on Windows, static or nested '
                                                             'additions, final -> override)'}, indent=2))
(out / 'replacement-objects.json').write_text(json.dumps(replacements, indent=2))
extra = list(glue_compiled)
for name in borrowed_glue:
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
    'parent': str(parent), 'parentHead': parent_head, 'runtimeSha256': hashes}, indent=2))
print('FONTFACE CANDIDATE READY: ' + str(runtime), {k: hashes[k][:8] for k in ['WebCore.dll', 'RanvierWebCoreHost.dll', 'JavaScriptCore.dll']}, flush=True)
