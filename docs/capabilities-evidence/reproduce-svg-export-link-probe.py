from pathlib import Path
import ast,json,os,re,shutil,subprocess,sys,threading,types
repo=Path('C:/wk/native-capabilities')
build=Path('C:/wk/build-win-slim')
out=repo/'artifacts/h07/svg-export-link-probe'
runtime=out/'runtime'
runtime.mkdir(parents=True,exist_ok=True)
shutil.copyfile(repo/'artifacts/h07/candidate/runtime/WebCore.lib',runtime/'WebCore.lib')
cache=(build/'CMakeCache.txt').read_text()
ninja=re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$',cache,re.M).group(1)
compiler=Path(re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.+)$',cache,re.M).group(1))
tree=ast.parse((repo/'scripts/build.py').read_text())
function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='toolchain_env')
scope=dict(os=os,pathlib=__import__('pathlib'),subprocess=subprocess,sys=sys,windows=True,arch='x64',system='win',args=types.SimpleNamespace(tool_path=[]),llvm=compiler.parent,vcpkg=Path('C:/wk/vcpkg'),pins=json.loads((repo/'pins.json').read_text()))
exec(compile(ast.Module(body=[function],type_ignores=[]),'<existing-toolchain>','exec'),scope)
env=scope['toolchain_env']()
tree=ast.parse(Path('C:/wk/native-cssom-detached-context/artifacts/build_context_candidate.py').read_text())
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'commands','execute','link_command'}],type_ignores=[]),'<private-link-helpers>','exec'),globals())
stop=threading.Event()
lines=(build/'build.ninja').read_text().splitlines()
target='Source/WebCore/CMakeFiles/WebCore.dir/C_/wk/ranvier-webcore/host/dom/RanvierDomGlue.cpp.obj'
command=next(c for c in commands([target]) if 'clang-cl.exe' in c and 'RanvierDomGlue.cpp' in c)
source=out/'svg-export-probe.cpp'
source.write_text('#include "config.h"\n#include "C:/wk/src/Source/WebCore/svg/SVGSVGElement.h"\nextern "C" __declspec(dllexport) int rv_link_probe(WebCore::SVGSVGElement* root) { root->resetScrollAnchor(); return root->scrollToFragment(WTF::StringView { }); }\n')
command=re.sub(r' -c -- .*$', ' -c -- '+source.as_posix(), command)
obj=out/'svg-export-probe.obj'
command=re.sub(r'/Fo(?:"[^"]+"|\S+)','/Fo'+obj.as_posix(),command)
command=re.sub(r'/Fd(?:"[^"]+"|\S+)','/Fd'+(out/'svg-export-probe.pdb').as_posix(),command)
if execute(command,'compile'): raise SystemExit('Probe compilation failed before linker evidence')
status=execute(link_command('RanvierWebCoreHost',[obj.as_posix()])+' Uiautomationcore.lib Ole32.lib OleAut32.lib Comctl32.lib','link')
log=(out/'link.log').read_text(errors='replace')
assert status != 0 and 'scrollToFragment' in log and 'resetScrollAnchor' in log,'Expected actual missing-method linker evidence'
print('SVG_EXISTING_METHOD_EXPORT_LINK_RED='+str(status),flush=True)
