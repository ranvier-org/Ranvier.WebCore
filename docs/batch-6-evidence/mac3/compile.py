"""Compiles one host translation unit of C:/wk/native-batch-6 with the batch-6 candidate's flags (no PCH, every error
reported), optionally force-including carbon-globals.h, the stand-in for the macOS SDK's global Carbon type names.

usage: compile.py <log> <source relative to the repo> <rsp in artifacts/batch6-candidate-2> [--carbon] [--overlay <dir>]

--overlay puts <dir> first on the include path: int7's macsim/include holds a cmakeconfig.h with the macOS-off
features forced to 0."""
import ast, json, os, re, subprocess, sys, types
from pathlib import Path
repo = Path('C:/wk/native-batch-6'); here = Path(__file__).resolve().parent
work = Path('C:/wk/mac3/obj'); work.mkdir(parents=True, exist_ok=True)
compiler = Path('C:/wk/tools/clang+llvm-23.1.4-x86_64-pc-windows-msvc/bin/clang-cl.exe')
tree = ast.parse((repo / 'scripts/build.py').read_text())
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'toolchain_env')
scope = dict(os=os, pathlib=__import__('pathlib'), subprocess=subprocess, sys=sys, windows=True, arch='x64', system='win',
             args=types.SimpleNamespace(tool_path=[]), llvm=compiler.parent, vcpkg=Path('C:/wk/vcpkg'),
             pins=json.loads((repo / 'pins.json').read_text()))
exec(compile(ast.Module(body=[function], type_ignores=[]), '<toolchain_env>', 'exec'), scope)
env = scope['toolchain_env']()
log, source, rsp_name = sys.argv[1], sys.argv[2], sys.argv[3]
carbon = '--carbon' in sys.argv[4:]
overlay = sys.argv[sys.argv.index('--overlay') + 1] if '--overlay' in sys.argv else None
rsp = (repo / 'artifacts/batch6-candidate-2' / rsp_name).read_text().split()
drop = re.compile(r'^(/Yu|/Yc|/Fp|/FI|/showIncludes|/Fo|/Fd|-c$|--$)')
stem = Path(source).stem
flags = [f for f in rsp if not drop.match(f) and not f.endswith('.cpp')]
flags_file = work / f'{stem}.rsp'
flags_file.write_text(' '.join(flags))
command = [str(compiler)] + (['-I' + overlay] if overlay else []) + ['@' + str(flags_file), '/clang:-ferror-limit=0', '/Fo' + str(work / f'{stem}.obj')]
if carbon:
    command.append('/FI' + str(here / 'carbon-globals.h'))
command += ['-c', '--', str(repo / source)]
result = subprocess.run(command, env=env, capture_output=True, text=True)
errors = len(re.findall(r': error:', result.stdout + result.stderr))
Path(log).write_text(result.stdout + result.stderr + f'\nERRORS={errors}\nEXIT={result.returncode}\n', encoding='utf-8')
print(source, 'carbon' if carbon else 'plain', 'overlay' if overlay else '', 'ERRORS', errors, 'EXIT', result.returncode)
