import ast, json, os, re, subprocess, sys, types
from pathlib import Path
repo = Path('C:/wk/native-svg-paint'); build = Path('C:/wk/build-win-slim')
cache = (build / 'CMakeCache.txt').read_text()
compiler = Path(re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.+)$', cache, re.M).group(1))
tree = ast.parse((repo / 'scripts/build.py').read_text())
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'toolchain_env')
scope = dict(os=os, pathlib=__import__('pathlib'), subprocess=subprocess, sys=sys, windows=True, arch='x64', system='win',
             args=types.SimpleNamespace(tool_path=[]), llvm=compiler.parent, vcpkg=Path('C:/wk/vcpkg'), pins=json.loads((repo / 'pins.json').read_text()))
exec(compile(ast.Module(body=[function], type_ignores=[]), '<t>', 'exec'), scope)
env = scope['toolchain_env']()
watch = ['ImageLoader.h', 'HTMLImageElement.h', 'SVGImageElement.h']
for rsp in sys.argv[1:]:
    text = Path(rsp).read_text(encoding='utf-8')
    text = re.sub(r'/Fo(?:"[^"]+"|\S+)', '', text)
    text = re.sub(r'/Fd(?:"[^"]+"|\S+)', '', text)
    text = text.replace(' -c ', ' /E /showIncludes ')
    tmp = Path(rsp + '.scan'); tmp.write_text(text, encoding='utf-8')
    r = subprocess.run([str(compiler), '@' + str(tmp)], cwd=build, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors='replace')
    hits = sorted({line.split('file:', 1)[1].strip() for line in r.stderr.splitlines() if 'including file' in line and any(line.rstrip().endswith(w) for w in watch)})
    print(Path(rsp).name, r.returncode, hits, flush=True)
