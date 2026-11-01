"""Full private WebKit build for the pointer-input groups (I03/I04/I06): ENABLE_TOUCH_EVENTS and ENABLE_POINTER_LOCK are
in cmakeconfig.h, so no WebCore object of a build without them can be borrowed. Configures C:/wk/pointer-build from
C:/wk/src (read-only: CMake writes only into the build directory) with this tree's config, a private copy of
build-win-slim's vcpkg_installed (manifest install off), and builds RanvierWebCoreHost with ninja -j16.
usage: build_pointer_full.py configure|build"""
import ast, json, os, pathlib, re, shutil, subprocess, sys, types
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
source, build, slim = Path('C:/wk/src'), Path('C:/wk/pointer-build'), Path('C:/wk/build-win-slim')
cache = (slim / 'CMakeCache.txt').read_text()
compiler = Path(re.search(r'^CMAKE_CXX_COMPILER:[^=]+=(.+)$', cache, re.M).group(1))
ninja = re.search(r'^CMAKE_MAKE_PROGRAM:[^=]+=(.+)$', cache, re.M).group(1)
cmake = re.search(r'^CMAKE_COMMAND:[^=]+=(.+)$', cache, re.M).group(1)
# The tools build-win-slim was configured with.
tools = {key: re.search('^' + key + r':[^=]+=(.+)$', cache, re.M).group(1) for key in ['GPERF_EXECUTABLE', 'PERL_EXECUTABLE', 'PYTHON_EXECUTABLE', 'Ruby_EXECUTABLE']}
tree = ast.parse((repo / 'scripts/build.py').read_text())
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'toolchain_env')
scope = dict(os=os, pathlib=pathlib, subprocess=subprocess, sys=sys, windows=True, arch='x64', system='win',
             args=types.SimpleNamespace(tool_path=[str(Path(tools[k]).parent) for k in ['PERL_EXECUTABLE', 'GPERF_EXECUTABLE', 'Ruby_EXECUTABLE']]), llvm=compiler.parent, vcpkg=Path('C:/wk/vcpkg'),
             pins=json.loads((repo / 'pins.json').read_text()))
exec(compile(ast.Module(body=[function], type_ignores=[]), '<toolchain_env>', 'exec'), scope)
env = scope['toolchain_env']()
# As scripts/build.py build_step does for the slim flavor.
env['_LINK_'] = '/OPT:SAFEICF dwrite.lib'

if sys.argv[1] == 'configure':
    assert not (build / 'build.ninja').exists(), 'configure into a new build directory'
    build.mkdir(parents=True, exist_ok=True)
    shutil.copytree(slim / 'vcpkg_installed', build / 'vcpkg_installed', dirs_exist_ok=True)
    clang = compiler.as_posix()
    command = [cmake, '-S', str(source), '-B', str(build), '-G', 'Ninja', f'-DCMAKE_MAKE_PROGRAM={ninja}', '-DRANVIER_RID=win-x64',
               '-C', str(repo / 'config/slim.cmake'), f'-DCMAKE_C_COMPILER={clang}', f'-DCMAKE_CXX_COMPILER={clang}',
               '-DCMAKE_TOOLCHAIN_FILE=C:/wk/vcpkg/scripts/buildsystems/vcpkg.cmake',
               f'-DVCPKG_INSTALLED_DIR={(build / "vcpkg_installed").as_posix()}', '-DVCPKG_MANIFEST_INSTALL=OFF'] + [f'-D{k}={v}' for k, v in tools.items()]
    subprocess.run(command, env=env, cwd=build, check=True)
    new = (build / 'CMakeCache.txt').read_text()
    for flag in ['ENABLE_TOUCH_EVENTS', 'ENABLE_POINTER_LOCK']:
        assert re.search('^' + flag + r':BOOL=ON$', new, re.M), flag
    print('configured', build)
else:
    for name in ['libEGL.dll', 'libGLESv2.dll']:
        (build / 'bin' / name).unlink(missing_ok=True)
    subprocess.run([ninja, '-C', str(build), '-j', '16', '-k', '0', 'RanvierWebCoreHost'], env=env, check=True)
