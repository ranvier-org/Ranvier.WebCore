# Writes a filtered ICU data DLL (icudt77.dll) from ICU's data archive (icudt77l.dat).
# Kept: break iterators and their dictionaries, normalisation, IDNA and stringprep data, emoji and
# layout properties, converter aliases, supplemental data, and the root and English locale data
# of every tree. Removed: converters (.cnv), character names, transliteration, and every other
# locale's data.
#
#   icu_data.py --data DAT --icu-tools DIR --icu-bin DIR --linker LLD-LINK --out DIR [--machine X64|ARM64]
#
# --icu-tools holds icupkg.exe and genccode.exe (vcpkg's tools/icu/bin), --icu-bin the ICU DLLs they load.
import argparse, os, pathlib, re, subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--data', required=True)
parser.add_argument('--icu-tools', required=True)
parser.add_argument('--icu-bin', required=True)
parser.add_argument('--linker', required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--machine', default='X64', help="lld-link's /MACHINE: the target architecture")
args = parser.parse_args()
source, tools, out = pathlib.Path(args.data), pathlib.Path(args.icu_tools), pathlib.Path(args.out)
env = dict(os.environ, PATH=args.icu_bin + os.pathsep + os.environ['PATH'])
locale = re.compile(r'[a-z]{2,3}(_[A-Za-z0-9]+)*')
english = {'root', 'en', 'en_US', 'en_US_POSIX', 'res_index', 'pool'}

def keep(item):
    tree, _, name = item.rpartition('/')
    stem, extension = os.path.splitext(name)
    if extension == '.cnv' or item == 'unames.icu' or tree == 'translit':
        return False
    if tree == 'brkitr':
        return True
    if tree == 'coll':
        return extension == '.icu' or stem in english
    if extension == '.res' and locale.fullmatch(stem):
        return stem in english
    return True

work = out / 'icu-slim'
work.mkdir(parents=True, exist_ok=True)
items = subprocess.run([str(tools / 'icupkg.exe'), '-l', str(source)], capture_output=True, text=True, check=True, env=env).stdout.split()
removed = [i for i in items if not keep(i)]
(work / 'removed.txt').write_text('\n'.join(removed) + '\n')
data = work / 'icudt77l.dat'
data.unlink(missing_ok=True)
subprocess.run([str(tools / 'icupkg.exe'), '-r', str(work / 'removed.txt'), str(source), str(data)], check=True, env=env)
subprocess.run([str(tools / 'genccode.exe'), '-o', '-e', 'icudt77', '-d', str(work), str(data)], check=True, env=env)
obj = next(work.glob('icudt77l_dat.obj'))
subprocess.run([args.linker, '/DLL', '/NOENTRY', f'/MACHINE:{args.machine}', '/OPT:REF', '/EXPORT:icudt77_dat,DATA', f'/OUT:{out / "icudt77.dll"}', str(obj)], check=True, env=env)
print(f'icu: {source} ({source.stat().st_size} bytes), {len(items)} items; kept {len(items) - len(removed)}, '
      f'removed {len(removed)} (listed in {work / "removed.txt"}); icudt77.dll {(out / "icudt77.dll").stat().st_size} bytes')
