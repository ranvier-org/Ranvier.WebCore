# Builds libpas alone from a WebKit checkout with clang-cl and links commit_test.c against it, so patch
# 0084 can be checked in minutes without a WebKit build. Windows only.
#
#   python -I tests/libpas_commit/build.py --source <webkit> --out <dir> [--lazy] [--llvm <bin dir>]
#   <dir>/commit_test.exe first | workload | stress [regions]
#
# --source needs only Source/bmalloc, with patches/series applied. --lazy defines PAS_WINDOWS_LAZY_COMMIT=1,
# which is what USE_LIBPAS_LAZY_COMMIT does in the WebKit build; without it the build is WebKit's own, and
# `first` and `workload` fail. docs/PATCHES.md, "0084-libpas-windows-lazy-commit", has the figures.
import argparse, concurrent.futures, os, pathlib, subprocess, sys

parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True, help='WebKit checkout')
parser.add_argument('--out', required=True, help='build directory')
parser.add_argument('--lazy', action='store_true', help='build with PAS_WINDOWS_LAZY_COMMIT=1')
parser.add_argument('--llvm', default=os.path.join(os.environ.get('RANVIER_WORK', 'C:/rw'), 'tools/llvm/bin'),
                    help="LLVM's bin directory (default <work>/tools/llvm/bin, as scripts/build.py)")
args = parser.parse_args()
bmalloc, out, llvm = pathlib.Path(args.source).resolve() / 'Source/bmalloc', pathlib.Path(args.out).resolve(), pathlib.Path(args.llvm)
here = pathlib.Path(__file__).resolve().parent
(out / 'obj').mkdir(parents=True, exist_ok=True)

vswhere = pathlib.Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
install = subprocess.run([str(vswhere), '-latest', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
                          '-property', 'installationPath'], capture_output=True, text=True, check=True).stdout.strip()
vcvars = pathlib.Path(install) / 'VC/Auxiliary/Build/vcvars64.bat'
dump = subprocess.run(f'cmd /c ""{vcvars}" >nul && set"', capture_output=True, text=True, shell=True, check=True).stdout
env = dict(line.split('=', 1) for line in dump.splitlines() if '=' in line)

# PAS_BMALLOC and _GNU_SOURCE are Source/bmalloc/CMakeLists.txt's definitions. STATICALLY_LINKED_WITH_bmalloc
# makes the system-heap hooks plain symbols, which commit_test.c defines in place of bmalloc's C++.
flags = ['/nologo', '/c', '/O2', '/MD', '/clang:-std=gnu2x', '-mcx16', '-w', '/DPAS_BMALLOC=1', '/D_GNU_SOURCE',
         '/D_CRT_SECURE_NO_WARNINGS', '/DSTATICALLY_LINKED_WITH_bmalloc', f'/I{bmalloc}', f'/I{bmalloc / "bmalloc"}',
         f'/I{bmalloc / "libpas/src/libpas"}'] + (['/DPAS_WINDOWS_LAZY_COMMIT=1'] if args.lazy else [])


def compile_one(source):
    obj, mark = out / 'obj' / (source.stem + '.obj'), out / 'obj' / (source.stem + '.stamp')
    stamp = repr((source.stat().st_mtime_ns, flags))
    if obj.exists() and mark.exists() and mark.read_text() == stamp:
        return obj, ''
    done = subprocess.run([str(llvm / 'clang-cl.exe'), *flags, f'/Fo{obj}', str(source)], capture_output=True, text=True, env=env)
    if done.returncode:
        return None, f'{source.name}:\n{done.stdout}{done.stderr}'
    mark.write_text(stamp)
    return obj, ''


sources = sorted((bmalloc / 'libpas/src/libpas').glob('*.c')) + [here / 'commit_test.c']
with concurrent.futures.ThreadPoolExecutor(os.cpu_count()) as pool:
    results = list(pool.map(compile_one, sources))
failures = [text for obj, text in results if obj is None]
if failures:
    sys.exit(f'{len(failures)} of {len(sources)} sources failed\n' + '\n'.join(failures)[:6000])
exe = out / 'commit_test.exe'
link = subprocess.run([str(llvm / 'lld-link.exe'), '/nologo', f'/out:{exe}', '/subsystem:console', '/ignore:4217',
                       *[str(obj) for obj, _ in results], 'psapi.lib', 'synchronization.lib'], capture_output=True, text=True, env=env)
if link.returncode:
    sys.exit('link failed\n' + (link.stdout + link.stderr)[:6000])
print(exe)
