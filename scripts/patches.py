# The WebKit source patch series: one concern per patch, applied in the order of `series` over the
# pinned WebKit commit. Each patch gates its change behind a CMake option that defaults to WebKit's
# behaviour, so builds that leave the options unset compile WebKit's own sources. The exception is
# 0000-skia-strike-ref.patch, which adds the source file the pinned Skia list omits, for every build.
#
# The pin is pins.json's webkit.commit. --source is a WebKit checkout that has the pin's objects.
#
#   patches.py apply  --source DIR                   reset the series' files to the pin, then apply the series
#   patches.py check  COMMIT --source DIR            dry-run the series against another WebKit commit
#   patches.py export NAME PATH... --source DIR      write NAME.patch from PATHs' changes against the pin with the
#                                                    patches before NAME in series applied (all of them for a new NAME)
import argparse, json, pathlib, re, subprocess, sys, tempfile

here = pathlib.Path(__file__).resolve().parents[1] / 'patches'
pin = json.loads((here.parent / 'pins.json').read_text())['webkit']['commit']
parser = argparse.ArgumentParser()
parser.add_argument('command', choices=['apply', 'check', 'export'])
parser.add_argument('args', nargs='*')
parser.add_argument('--source', required=True)
args = parser.parse_args()
source = pathlib.Path(args.source)

def git(*command, cwd=source, check=True, **kw):
    return subprocess.run(['git', *command], cwd=cwd, capture_output=True, text=True, encoding='utf-8', check=check, **kw)

def series():
    return [here / line.strip() for line in (here / 'series').read_text().splitlines() if line.strip() and not line.startswith('#')]

def touched(patch):
    """The paths a patch writes, and whether the patch creates each one."""
    text = patch.read_text(encoding='utf-8')
    paths = re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)
    created = set(re.findall(r'^diff --git a/(\S+) b/\S+\nnew file mode', text, re.M))
    return {p: p in created for p in paths}

if args.command == 'apply':
    patches = series()
    for patch in patches:
        for path, created in touched(patch).items():
            if created:
                (source / path).unlink(missing_ok=True)
            else:
                git('checkout', pin, '--', path)
    for patch in patches:
        result = git('apply', '--whitespace=nowarn', str(patch), check=False)
        print(patch.name, 'applied' if not result.returncode else 'FAILED\n' + result.stderr)
        if result.returncode:
            sys.exit(1)
elif args.command == 'check':
    commit, = args.args
    failed = 0
    with tempfile.TemporaryDirectory() as temp:
        root = pathlib.Path(temp)
        for patch in series():
            for path, created in touched(patch).items():
                shown = git('show', f'{commit}:{path}', check=False)
                if shown.returncode == 0 and not (root / path).exists():
                    (root / path).parent.mkdir(parents=True, exist_ok=True)
                    (root / path).write_text(shown.stdout, encoding='utf-8', newline='\n')
            result = git('apply', '--check', '--whitespace=nowarn', str(patch), cwd=root, check=False)
            print(patch.name, 'applies' if not result.returncode else 'FAILS\n' + result.stderr)
            failed += bool(result.returncode)
            if not result.returncode:
                git('apply', '--whitespace=nowarn', str(patch), cwd=root)
    sys.exit(1 if failed else 0)
else:
    name, *paths = args.args
    patches = series()
    names = [patch.stem for patch in patches]
    earlier = patches[:names.index(name)] if name in names else patches
    with tempfile.TemporaryDirectory() as temp:
        root = pathlib.Path(temp)
        git('init', '-q', cwd=root)
        base = set(paths)
        for patch in earlier:
            base |= {path for path, created in touched(patch).items() if not created}
        for path in base:
            shown = git('show', f'{pin}:{path}', check=False)
            if shown.returncode == 0:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(shown.stdout, encoding='utf-8', newline=chr(10))
        for patch in earlier:
            git('apply', '--whitespace=nowarn', str(patch), cwd=root)
        git('add', '-A', cwd=root)
        git('-c', 'user.name=patches', '-c', 'user.email=patches@localhost', 'commit', '-q', '--allow-empty', '-m', 'base', cwd=root)
        for path in paths:
            target = root / path
            if (source / path).exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((source / path).read_bytes())
            else:
                target.unlink(missing_ok=True)
        git('add', '-A', '--', *paths, cwd=root)
        diff = git('-c', 'core.autocrlf=false', 'diff', '--cached', '--no-color', '--no-ext-diff', '--', *paths, cwd=root).stdout
    (here / f'{name}.patch').write_text(diff, encoding='utf-8', newline=chr(10))
    print(f'{name}.patch: {len(touched(here / f"{name}.patch"))} files')
