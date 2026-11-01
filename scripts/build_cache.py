# Support for the build-tree cache of .github/workflows/build.yml (docs/CI.md, "Build tree").
#
#   build_cache.py keys       --rid RID --flavor FLAVOR    print the cache keys as name=value lines (GITHUB_OUTPUT)
#   build_cache.py normalise  --build DIR --source DIR     give unchanged sources the times of the cached build
#   build_cache.py explain    --build DIR                  print the edges ninja would run and its first reasons
#   build_cache.py record     --build DIR --source DIR     write the manifest of the sources as they are, for a tree
#                                                          built from them without the cache (a workstation's)
#
# A restored build tree holds the objects of an earlier build, but checkout and the WebKit fetch give every
# source file a fresh modification time, which ninja reads as a change to all of them. The tree carries a
# manifest of the sources it was built from: for each file, its git blob id and its modification time.
# normalise sets every file whose blob id matches the manifest back to the recorded time, leaves changed and
# new files at their checkout time, then writes the manifest of the current sources for the next save. Blob ids
# come from git's index, which the checkout has just written, so only the files git reports as changed are read.
# Restoring the recorded time rather than an arbitrary old one also keeps clang's precompiled headers valid:
# a PCH records each input's modification time and is rejected when one differs.
#
# normalise also deletes the restored CMakeCache.txt: the config files set options with set(... CACHE), which
# never replace a value already in a cache, so only a configure without a cache gives a clean configure's options.
import argparse, hashlib, json, os, pathlib, re, stat, subprocess, sys, time

root = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = 'ranvier-sources.json'
FORMAT = 1


def long_path(path):
    """path in the form Windows accepts beyond MAX_PATH; other systems take it as it is."""
    if os.name != 'nt':
        return str(path)
    text = os.path.abspath(path).replace('/', '\\')
    return text if text.startswith('\\\\') else '\\\\?\\' + text


def git(cwd, *command):
    return subprocess.run(['git', '-C', str(cwd), '--no-optional-locks', *command], capture_output=True, check=True).stdout


def blob_ids(tree):
    """{path: blob id} of the files in a git working tree: the index's id for each file git reports clean, the hashed
    content for each changed or untracked one (ignored files are left out). Paths use '/'."""
    ids = {}
    for record in git(tree, 'ls-files', '-z', '-s', '-t').split(b'\0'):
        if not record:
            continue
        info, path = record.split(b'\t', 1)
        tag, mode, oid, _ = info.split(b' ')
        # S: outside the sparse checkout. 160000: a submodule. 120000: a symbolic link, whose target has its own entry.
        if tag == b'S' or mode in (b'160000', b'120000'):
            continue
        ids[path.decode()] = oid.decode()
    changed = []
    records = git(tree, 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--no-renames').split(b'\0')
    for record in records:
        if not record:
            continue
        code, path = record[:2], record[3:].decode()
        if b'D' in code:
            ids.pop(path, None)
        else:
            changed.append(path)
    if changed:
        hashed = subprocess.run(['git', '-C', str(tree), 'hash-object', '--stdin-paths'], input='\n'.join(changed).encode(),
                                capture_output=True, check=True).stdout.decode().split()
        ids.update(zip(changed, hashed))
    return ids, len(changed)


def normalise(args):
    start = time.monotonic()
    build = pathlib.Path(args.build)
    trees = {'webkit': pathlib.Path(args.source), 'repository': pathlib.Path(args.repository)}
    manifest_path = build / MANIFEST
    try:
        cached = json.loads(manifest_path.read_text())
        if cached.get('format') != FORMAT:
            cached = None
    except (OSError, ValueError):
        cached = None
    if args.command == 'record':
        cached = None
    elif cached is None and (build / 'build.ninja').exists():
        # A tree without a manifest: its sources' times are unknown, so any of them may be older than its objects.
        if not args.clear_unknown:
            sys.exit(f'build_cache: {build} has no {MANIFEST}; build_cache.py record writes one for a tree built from these sources')
        print('build_cache: the build tree has no source manifest, so it is cleared', flush=True)
        clear(build)
    written = {'format': FORMAT, 'trees': {}}
    for name, tree in trees.items():
        ids, hashed = blob_ids(tree)
        old = (cached or {}).get('trees', {}).get(name, {})
        entries = {}
        kept = changed = added = 0
        for path, oid in ids.items():
            full = long_path(tree / path)
            try:
                info = os.lstat(full)
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            seconds = int(info.st_mtime)
            previous = old.get(path)
            if previous is None:
                added += 1
            elif previous[0] != oid:
                changed += 1
            else:
                kept += 1
                if previous[1] != seconds:
                    os.utime(full, ns=(previous[1] * 10**9, previous[1] * 10**9))
                    seconds = previous[1]
            entries[path] = [oid, seconds]
        # A directory is an input of some edges (WebKit's header links name source directories), and checkout gives
        # it a fresh time too. One whose listing of tracked entries is unchanged gets its recorded time back.
        listings = {}
        for path in entries:
            parts = path.split('/')
            for depth in range(1, len(parts)):
                listings.setdefault('/'.join(parts[:depth]), set()).add(parts[depth])
        old_dirs = (cached or {}).get('directories', {}).get(name, {})
        dirs = {}
        for path, names in listings.items():
            listing = hashlib.sha1('\0'.join(sorted(names)).encode()).hexdigest()
            full = long_path(tree / path)
            try:
                seconds = int(os.stat(full).st_mtime)
            except FileNotFoundError:
                continue
            previous = old_dirs.get(path)
            if previous and previous[0] == listing and previous[1] != seconds:
                os.utime(full, ns=(previous[1] * 10**9, previous[1] * 10**9))
                seconds = previous[1]
            dirs[path] = [listing, seconds]
        written.setdefault('directories', {})[name] = dirs
        written['trees'][name] = entries
        print(f'build_cache: {name}: {kept} unchanged, {changed} changed, {added} new, '
              f'{len(set(old) - set(entries))} gone ({hashed} hashed)', flush=True)
    build.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(written, separators=(',', ':')))
    # CMake appends each configure to its log, which would otherwise grow with every run the tree is reused for.
    for stale in [build / 'CMakeCache.txt', build / 'CMakeFiles/CMakeConfigureLog.yaml']:
        if args.command == 'normalise' and stale.exists():
            stale.unlink()
            print('build_cache: deleted', stale, flush=True)
    print(f'build_cache: normalised in {time.monotonic() - start:.1f} s', flush=True)


def clear(build):
    """Empties the build directory, keeping nothing an incremental build could trust."""
    import shutil
    for child in build.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(long_path(child))
        else:
            child.unlink()


def digest(*parts):
    text = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def files_digest(*patterns):
    """Hash of the tracked files under the repository paths, by path and blob id."""
    listing = git(root, 'ls-files', '-s', '--', *patterns).decode()
    return hashlib.sha256(listing.encode()).hexdigest()[:16]


def output(command):
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()


def config_chain(flavor):
    """The config files config/<flavor>.cmake loads, in the order CMake reads them."""
    seen = []

    def visit(path):
        if path in seen or not path.exists():
            return
        seen.append(path)
        for name in re.findall(r'include\("\$\{CMAKE_CURRENT_LIST_DIR\}/([\w.-]+)"\)', path.read_text()):
            visit(path.parent / name)

    visit(root / 'config' / f'{flavor}.cmake')
    return seen


def vcpkg_features(flavor):
    return [value for path in config_chain(flavor)
            for value in re.findall(r'set\(VCPKG_MANIFEST_FEATURES\s+"([^"]*)"', path.read_text())]


def vcpkg_patches():
    """The patches that write a vcpkg input of the WebKit checkout: its manifest, its configuration or its triplets."""
    inputs = re.compile(r'^diff --git a/(vcpkg\.json|vcpkg-configuration\.json|WebKitLibraries/triplets/\S+) ', re.M)
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((root / 'patches').glob('*.patch')) if inputs.search(path.read_text(encoding='utf-8'))}


def tree_digest(*directories):
    """Hash of the relative path and size of every file under the directories."""
    entries = []
    for directory in directories:
        for folder, _, names in os.walk(directory):
            for name in names:
                path = os.path.join(folder, name)
                entries.append(f'{os.path.relpath(path, directory)}:{os.path.getsize(path)}')
    return hashlib.sha256('|'.join(sorted(entries)).encode()).hexdigest()[:16]


def msvc(arch):
    """The identity of the toolset that build.py's vcvars call selects (the default toolset of the newest Visual
    Studio with the architecture's C++ tools, and the newest Windows 10/11 SDK): their versions, the hash of
    cl.exe, which vcpkg's compiler hash also covers, and the paths and sizes of their headers. Runner images can
    ship the same versions with other binaries and headers; ninja tracks neither."""
    component = {'x64': 'x86.x64', 'arm64': 'ARM64'}[arch]
    vswhere = pathlib.Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    installs = output([str(vswhere), '-latest', '-products', '*', '-requires',
                       f'Microsoft.VisualStudio.Component.VC.Tools.{component}', '-property', 'installationPath']).splitlines()
    if not installs:
        sys.exit(f'vswhere found no Visual Studio with the {arch} C++ build tools')
    version = (pathlib.Path(installs[-1]) / 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt').read_text().strip()
    tools = pathlib.Path(installs[-1]) / 'VC/Tools/MSVC' / version
    cl = hashlib.sha256((tools / f'bin/Host{arch}/{arch}/cl.exe').read_bytes()).hexdigest()[:16]
    kits = pathlib.Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Windows Kits/10/Include'
    sdks = sorted((p.name for p in kits.glob('10.*') if (p / 'um').exists()), key=lambda v: [int(x) for x in v.split('.')])
    sdk = sdks[-1] if sdks else 'none'
    return [version, sdk, cl, tree_digest(tools / 'include', *([kits / sdk] if sdks else []))]


def toolchain(rid):
    """The compilers' identity, which ninja does not track: a build tree is reused only under the same one."""
    system, arch = rid.split('-')
    if system == 'win':
        return msvc(arch)
    if system == 'linux':
        return [output(['clang', '--version']).splitlines()[0], os.environ.get('ImageOS', '')]
    return [output(['xcodebuild', '-version']).replace('\n', ' '), output(['xcrun', '--show-sdk-version'])]


def keys(args):
    pins = json.loads((root / 'pins.json').read_text())
    rid, flavor = args.rid, args.flavor
    system, arch = rid.split('-')
    webkit = pins['webkit']['commit']
    llvm = pins['llvm'].get(rid, {}).get('sha256', 'none')
    lines = {'llvm': f'llvm-{rid}-{llvm}'}
    tools = toolchain(rid)
    if system == 'win':
        # The inputs of vcpkg's ABI hashes: the vcpkg tool and its ports, WebKit's manifest, registries and overlay
        # triplets (at the WebKit pin, with any patch that writes them), the flavor's manifest features, and the
        # compiler the triplets use (cl.exe of the selected toolset).
        vcpkg = digest(pins['vcpkg'], webkit, vcpkg_patches(), vcpkg_features(flavor), tools)
        lines['vcpkg'] = f'vcpkg-{rid}-{flavor}-{vcpkg}'
        lines['vcpkg-prefix'] = f'vcpkg-{rid}-{flavor}-'
        # Source archives and tools vcpkg downloads: named by their hashes, and the same for every flavor.
        downloads = digest(pins['vcpkg'], webkit, pins['icu'])
        lines['downloads'] = f'vcpkg-downloads-{rid}-{downloads}'
        lines['downloads-prefix'] = f'vcpkg-downloads-{rid}-'
        # The tree holds vcpkg_installed, whose headers precompiled headers record.
        tools = [tools, llvm, vcpkg]
    tool = digest(tools)
    # Everything the native build reads from this repository, by blob id.
    core = files_digest('patches', 'config', 'scripts/build.py', 'scripts/patches.py')
    host = files_digest('host')
    base = f'tree-{rid}-{flavor}-{webkit[:12]}-{tool}-'
    lines['tree'] = f'{base}{core}-{host}'
    lines['tree-restore'] = f'{base}{core}-\n{base}'
    lines['toolchain'] = json.dumps(tools)
    text = ''.join(f'{name}<<EOF\n{value}\nEOF\n' if '\n' in value else f'{name}={value}\n' for name, value in lines.items())
    print(text, end='')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as out:
            out.write(text)


def explain(args):
    """Prints how many edges ninja would run for the target and the first reasons it gives, without building."""
    result = subprocess.run(['cmake', '--build', args.build, '--target', args.target, '--', '-n', '-d', 'explain'],
                            capture_output=True, text=True, errors='replace')
    lines = (result.stdout + result.stderr).splitlines()
    reasons = [line for line in lines if line.startswith('ninja explain:')]
    edges = [line for line in lines if re.match(r'\[\d+/\d+\] ', line)]
    print(f'build_cache: ninja would run {len(edges)} edges for {args.target}', flush=True)
    for line in reasons[:args.lines]:
        print(line)


parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest='command', required=True)
for command in ['normalise', 'record']:
    n = sub.add_parser(command)
    n.add_argument('--build', required=True, help='the build directory, which holds the manifest')
    n.add_argument('--source', required=True, help='the WebKit checkout')
    n.add_argument('--repository', default=str(root), help="this repository's checkout (default: the one holding this script)")
    n.add_argument('--clear-unknown', action='store_true', help='empty a build directory that has no manifest instead of failing')
e = sub.add_parser('explain')
e.add_argument('--build', required=True)
e.add_argument('--target', default='RanvierWebCoreHost')
e.add_argument('--lines', type=int, default=20)
k = sub.add_parser('keys')
k.add_argument('--rid', required=True)
k.add_argument('--flavor', required=True)
args = parser.parse_args()
{'normalise': normalise, 'record': normalise, 'keys': keys, 'explain': explain}[args.command](args)
