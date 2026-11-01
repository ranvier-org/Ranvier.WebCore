"""Compiles C:/wk/native-batch-6/host/dom/RanvierDomGlue.cpp with the batch-6 candidate's flags (no PCH) and the
overlay cmakeconfig.h in macsim/include (Mac-off features forced to 0), every error reported. usage: compile.py <log>"""
import ast, json, os, re, subprocess, sys, types
from pathlib import Path
repo = Path('C:/wk/native-batch-6'); here = Path('C:/wk/int7-tools/macsim')
compiler = Path('C:/wk/tools/clang+llvm-23.1.4-x86_64-pc-windows-msvc/bin/clang-cl.exe')
tree = ast.parse((repo / 'scripts/build.py').read_text())
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'toolchain_env')
scope = dict(os=os, pathlib=__import__('pathlib'), subprocess=subprocess, sys=sys, windows=True, arch='x64', system='win',
             args=types.SimpleNamespace(tool_path=[]), llvm=compiler.parent, vcpkg=Path('C:/wk/vcpkg'),
             pins=json.loads((repo / 'pins.json').read_text()))
exec(compile(ast.Module(body=[function], type_ignores=[]), '<toolchain_env>', 'exec'), scope)
env = scope['toolchain_env']()
rsp = (repo / 'artifacts/batch6-candidate-2/000-RanvierDomGlue.cpp.obj.rsp').read_text().split()
drop = re.compile(r'^(/Yu|/Fp|/FI|/showIncludes|/Fo|/Fd|-c$|--$)')
flags = [f for f in rsp if not drop.match(f) and not f.endswith('RanvierDomGlue.cpp')]
(here / 'flags.rsp').write_text(' '.join(flags))
command = [str(compiler), '-I' + str(here / 'include'), '@' + str(here / 'flags.rsp'), '/clang:-ferror-limit=0',
           '/Fo' + str(here / 'glue.obj'), '-c', '--', str(repo / (sys.argv[2] if len(sys.argv) > 2 else 'host/dom/RanvierDomGlue.cpp'))]
result = subprocess.run(command, env=env, capture_output=True, text=True)
Path(sys.argv[1]).write_text(result.stdout + result.stderr + f'\nEXIT={result.returncode}\n', encoding='utf-8')
print('EXIT', result.returncode)
