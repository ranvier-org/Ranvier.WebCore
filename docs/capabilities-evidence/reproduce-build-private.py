from pathlib import Path
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import types

repo = Path('C:/wk/native-capabilities')
parent = Path('C:/wk/native-svg-surfaces/artifacts/svg-surfaces-candidate')
build = Path('C:/wk/build-win-slim')
out = repo/'artifacts/h07/candidate'
runtime = out/'runtime'
runtime.mkdir(parents=True, exist_ok=True)
shutil.copytree(parent/'runtime',runtime,dirs_exist_ok=True)
parent_hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (parent/'runtime').glob('*') if p.is_file()}
cache = (build/'CMakeCache.txt').read_text()
ninja = re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$',cache,re.M).group(1)
compiler = Path(re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.+)$',cache,re.M).group(1))
tree = ast.parse((repo/'scripts/build.py').read_text())
function = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='toolchain_env')
scope = dict(os=os,pathlib=__import__('pathlib'),subprocess=subprocess,sys=sys,windows=True,arch='x64',system='win',args=types.SimpleNamespace(tool_path=[]),llvm=compiler.parent,vcpkg=Path('C:/wk/vcpkg'),pins=json.loads((repo/'pins.json').read_text()))
exec(compile(ast.Module(body=[function],type_ignores=[]),'<existing-toolchain>','exec'),scope)
env=scope['toolchain_env']()
tree=ast.parse(Path('C:/wk/native-cssom-detached-context/artifacts/build_context_candidate.py').read_text())
names={'commands','execute','link_command'}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'<existing-private-build-helpers>','exec'),globals())
stop=threading.Event()
lines=(build/'build.ninja').read_text().splitlines()
target=r'Tools\TestWebKitAPI\CMakeFiles\RanvierWebCoreHost.dir\RanvierAbi\RanvierWebCoreAbi.cpp.obj'
command=next(c for c in commands([target]) if 'clang-cl.exe' in c and 'RanvierWebCoreAbi.cpp' in c)
cached=build/target
cache_stat=cached.stat().st_mtime_ns
flags=re.findall(r'^((?:USE|ENABLE)_[A-Z0-9_]+):BOOL=(ON|OFF|1|0|TRUE|FALSE)$',cache,re.M)
flag_arguments=' '.join('/DRV_CAP_'+name+'='+('1' if value in ['ON','1','TRUE'] else '0') for name,value in flags)
(out/'configured-flags.json').write_text(json.dumps(dict(flags),indent=2))
objects=[]
glue_target='Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
glue_command=next(c for c in commands([glue_target]) if 'clang-cl.exe' in c and 'RanvierDomGlue.cpp' in c)
helper=repo/'host/RanvierSvgViewGlue.cpp'
helper_object=out/'RanvierSvgViewGlue.cpp.obj'
helper_command=re.sub(r' -c -- .*$', ' -c -- '+helper.as_posix(),glue_command)
helper_command=re.sub(r'/Fo(?:"[^"]+"|\S+)','/Fo'+helper_object.as_posix(),helper_command)
helper_command=re.sub(r'/Fd(?:"[^"]+"|\S+)','/Fd'+(out/'RanvierSvgViewGlue.cpp.pdb').as_posix(),helper_command)
if execute(helper_command,'svg-view-helper'): raise SystemExit(1)
replacements=json.loads((parent/'replacement-objects.json').read_text())
svg_target='Source/WebCore/CMakeFiles/WebCore.dir/__/__/WebCore/DerivedSources/unified-sources/UnifiedSource-svg-13.cpp.obj'
svg_cached=build/svg_target
svg_cached_mtime=svg_cached.stat().st_mtime_ns
svg_command=next(c for c in commands([svg_target]) if 'clang-cl.exe' in c and 'UnifiedSource-svg-13.cpp' in c)
svg_object=out/'svg-view-reset-UnifiedSource-svg-13.cpp.obj'
svg_command=re.sub(r'/Fo(?:"[^"]+"|\S+)','/Fo'+svg_object.as_posix(),svg_command)
svg_command=re.sub(r'/Fd(?:"[^"]+"|\S+)','/Fd'+(out/'svg-view-reset.pdb').as_posix(),svg_command)
if execute(svg_command,'svg-view-reset-engine'): raise SystemExit(1)
replacements[svg_target]=svg_object.as_posix()
if execute(link_command('WebCore')+' '+helper_object.as_posix()+' Dwrite.lib','webcore-link-svg-view-helper'): raise SystemExit(1)
assert svg_cached_mtime==svg_cached.stat().st_mtime_ns,'Read-only SVG cache changed'
for filename in ['RanvierWebCoreAbi.cpp','RanvierWebCoreDom.cpp','RanvierWebCoreUia.cpp','RanvierWebCoreD3D11.cpp']:
    current=re.sub(r'C:[/\\]wk[/\\]src[/\\]Tools[/\\]TestWebKitAPI[/\\]RanvierAbi[/\\]RanvierWebCoreAbi.cpp',(repo/'host'/filename).as_posix(),command)
    obj=out/(filename+'.obj')
    current,count=re.subn(r'/Fo(?:"[^"]+"|\S+)','/Fo'+obj.as_posix(),current)
    assert count==1
    current=re.sub(r'/Fd(?:"[^"]+"|\S+)','/Fd'+(out/(filename+'.pdb')).as_posix(),current)
    current=current.replace(' -- ', ' '+flag_arguments+' -- ')
    if execute(current,filename): raise SystemExit(1)
    objects.append(obj.as_posix())
if execute(link_command('RanvierWebCoreHost',objects)+' Uiautomationcore.lib Ole32.lib OleAut32.lib Comctl32.lib','host-link'): raise SystemExit(1)
assert cache_stat==cached.stat().st_mtime_ns,'Read-only cache changed'
assert parent_hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (parent/'runtime').glob('*') if p.is_file()},'Frozen parent changed'
hashes={str(p.relative_to(runtime)):hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.rglob('*') if p.is_file()}
(out/'runtime-sha256.json').write_text(json.dumps(hashes,indent=2))
print('H07_PRIVATE_RUNTIME='+str(runtime),flush=True)
