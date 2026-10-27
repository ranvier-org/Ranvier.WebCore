# Releases packages built on this machine. Each --rid is built by build.py from a clean commit that is on the
# remote, the packed package is checked and loaded by smoke.py, and the GitHub release v<version> is created
# with the packages attached. Creating the release pushes its tag; the tag's CI run builds the runtimes not
# attached, checks the attached ones again on its own runners, and pushes every package to nuget.org.
#
#   release.py --rid win-x64 [--rid ...] [--flavor slim] [--work DIR] [--dry-run] [build.py options]
#
# Options release.py does not know go to build.py (--source, --vcpkg, --llvm, --tool-path, --jobs). The
# version is pins.json's package.version. gh creates the release as its signed-in account, and CI uses an
# attached package only when that account owns the repository (docs/CI.md).
import argparse, json, os, pathlib, subprocess, sys

root = pathlib.Path(__file__).resolve().parents[1]
pins = json.loads((root / 'pins.json').read_text())

parser = argparse.ArgumentParser()
parser.add_argument('--rid', action='append', required=True)
parser.add_argument('--flavor', choices=['slim', 'lean'], default='slim')
parser.add_argument('--work', default=os.environ.get('RANVIER_WORK'))
parser.add_argument('--dry-run', action='store_true', help='build and check, but create no release')
args, build_args = parser.parse_known_args()

version = pins['package']['version']
tag = f'v{version}'


def output(*command):
    return subprocess.run(command, cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def run(*command):
    command = [str(c) for c in command]
    print('>', subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=root, check=True)


if output('git', 'status', '--porcelain'):
    sys.exit('the working tree has changes: commit them and push first')
head = output('git', 'rev-parse', 'HEAD')
run('git', 'fetch', '-q', 'origin')
if not output('git', 'branch', '-r', '--contains', head):
    sys.exit(f'{head} is on no remote branch: push it first')
if output('git', 'ls-remote', '--tags', 'origin', f'refs/tags/{tag}'):
    sys.exit(f'{tag} exists on the remote: change package.version in pins.json')

packages = []
for rid in args.rid:
    work = pathlib.Path(args.work or ('C:/rw' if rid.startswith('win') else os.path.expanduser('~/rw')))
    common = ['--rid', rid, '--flavor', args.flavor, '--work', work, '--version', version, *build_args]
    for step in ['fetch', 'prepare', 'configure', 'build', 'package']:
        run(sys.executable, '-I', root / 'scripts/build.py', step, *common, *(['--strict'] if step == 'prepare' else []))
    package_id = pins['package']['id'] + ('' if args.flavor == 'slim' else '.Lean') + '.' + rid
    package = work / 'packages' / f'{package_id}.{version}.nupkg'
    # The packed files, not the staged ones: what nuget.org would serve.
    run(sys.executable, '-I', root / 'scripts/smoke.py', '--package', package, '--expect-commit', head,
        '--expect-version', version, '--expect-flavor', args.flavor, *(['--no-load'] if rid.startswith('linux') else []))
    packages.append(package)

if args.dry_run:
    print('dry run: would create', tag, 'at', head, 'with', *(p.name for p in packages))
    sys.exit()
notes = (f'Built from {head}. The packages of {", ".join(args.rid)} were built locally by scripts/release.py; '
         'CI builds the other runtimes.')
run('gh', 'release', 'create', tag, '--target', head, '--title', tag, '--notes', notes,
    *(['--prerelease'] if '-' in version else []), *packages)
print(f'{tag} created: its CI run checks these packages and publishes them with the rest', flush=True)
