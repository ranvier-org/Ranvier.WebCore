# Builds the RanvierWebCoreHost library and the libraries it loads from the pinned WebKit commit for one
# runtime identifier, and packages them.
#
#   build.py fetch      clone WebKit at its pin into the work directory; on Windows also vcpkg, and LLVM unless --llvm
#   build.py prepare    apply patches/series to WebKit and install host/ into Tools/TestWebKitAPI
#   build.py configure  run CMake with config/<flavor>.cmake; on Windows vcpkg installs the dependencies here
#   build.py build      build RanvierWebCoreHost; for slim on Windows, also write the filtered ICU data DLL
#   build.py package    stage the libraries RanvierWebCoreHost loads and pack the NuGet package
#   build.py all        every step above, in order
#
# The runtime identifier (--rid) picks the WebKit port: win-* builds PORT=Win with clang-cl and vcpkg,
# linux-* builds PORT=WPE against the distribution's libraries, osx-* builds PORT=Mac. Every path defaults
# to a location under --work, so a fresh machine needs only the tools of docs/CI.md on PATH (or in
# --tool-path) and Python 3.12 or later.
import argparse, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tarfile, urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
pins = json.loads((root / 'pins.json').read_text())
steps = ['fetch', 'prepare', 'configure', 'build', 'package']

parser = argparse.ArgumentParser()
parser.add_argument('step', choices=steps + ['all'])
parser.add_argument('--flavor', choices=['slim', 'gpu', 'lean'], default='slim')
parser.add_argument('--work', default=os.environ.get('RANVIER_WORK'),
                    help='work directory; on Windows keep it short, WebKit paths exceed MAX_PATH under deep roots '
                         '(default C:/rw on Windows, ~/rw elsewhere)')
parser.add_argument('--source', help='WebKit checkout (default <work>/src)')
parser.add_argument('--build-dir', help='build directory (default <work>/build-<flavor>)')
parser.add_argument('--vcpkg', help='vcpkg root (default <work>/vcpkg)')
parser.add_argument('--llvm', help="LLVM's bin directory (default <work>/tools/llvm/bin, which fetch fills)")
parser.add_argument('--webkit-repo', default=pins['webkit']['repository'], help='where fetch clones WebKit from')
parser.add_argument('--tool-path', action='append', default=[], help='a directory put first on PATH (perl, ruby, gperf, python); repeatable')
parser.add_argument('--jobs', type=int, default=os.cpu_count())
parser.add_argument('--rid', default='win-x64', choices=['win-x64', 'win-arm64', 'linux-x64', 'linux-arm64', 'osx-arm64'])
parser.add_argument('--version', default=os.environ.get('RANVIER_PACKAGE_VERSION') or pins['package']['version'],
                    help='package version (default RANVIER_PACKAGE_VERSION, else pins.json)')
args = parser.parse_args()

system, arch = args.rid.split('-')
windows = system == 'win'
work = pathlib.Path(args.work or ('C:/rw' if windows else os.path.expanduser('~/rw')))
source = pathlib.Path(args.source) if args.source else work / 'src'
build = pathlib.Path(args.build_dir) if args.build_dir else work / f'build-{args.flavor}'
vcpkg = pathlib.Path(args.vcpkg) if args.vcpkg else work / 'vcpkg'
llvm = pathlib.Path(args.llvm) if args.llvm else work / 'tools/llvm/bin'
installed = build / 'vcpkg_installed'
triplet = installed / f'{arch}-windows-webkit'
out = work / 'out' / args.flavor
commit = pins['webkit']['commit']
host = {'win': 'RanvierWebCoreHost.dll', 'linux': 'libRanvierWebCoreHost.so', 'osx': 'libRanvierWebCoreHost.dylib'}[system]


def run(command, env=None, cwd=None):
    command = [str(c) for c in command]
    print('>', subprocess.list2cmdline(command), flush=True)
    # CreateProcess looks executables up on this process's PATH, not env's.
    executable = shutil.which(command[0], path=(env or os.environ)['PATH']) or command[0]
    subprocess.run([executable] + command[1:], env=env, cwd=cwd, check=True)


def git(*command, cwd=None):
    run(['git', *command], cwd=cwd)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def download(url, target, expected):
    """Downloads url to target unless target exists, and checks its SHA-256 when expected is not empty."""
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        print('download', url, flush=True)
        partial = target.with_suffix(target.suffix + '.partial')
        with urllib.request.urlopen(url) as response, open(partial, 'wb') as stream:
            shutil.copyfileobj(response, stream)
        partial.replace(target)
    actual = sha256(target)
    print(f'{target.name} sha256 {actual}', flush=True)
    if expected and actual != expected:
        sys.exit(f'{target}: sha256 {actual}, pins.json expects {expected}')


def clone(repository, commit, target, exclude=()):
    """A shallow checkout of one commit: fetching by commit keeps the clone at about 2 GB for WebKit. The
    top-level directories in exclude are left out of the checkout, and their files are not downloaded. A
    checkout already at the commit is left as it is."""
    if (target / '.git').exists():
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=target, capture_output=True, text=True).stdout.strip()
        if head == commit:
            print(target, 'is at', commit, flush=True)
            return
    else:
        target.mkdir(parents=True, exist_ok=True)
        git('init', '-q', cwd=target)
        git('remote', 'add', 'origin', repository, cwd=target)
        if exclude:
            git('sparse-checkout', 'set', '--no-cone', '/*', *(f'!/{name}/' for name in exclude), cwd=target)
    git('fetch', '--depth', '1', *(['--filter=blob:none'] if exclude else []), 'origin', commit, cwd=target)
    git('checkout', '-q', '--detach', commit, cwd=target)


def toolchain_env():
    """On Windows, the vcvars environment of the target architecture with LLVM and --tool-path first on PATH;
    elsewhere this process's environment with --tool-path first, and clang unless CC and CXX say otherwise."""
    if not windows:
        env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1')
        env['PATH'] = os.pathsep.join([*args.tool_path, env['PATH']])
        if system == 'linux':
            env.setdefault('CC', 'clang')
            env.setdefault('CXX', 'clang++')
        return env
    component, vcvars = {'x64': ('x86.x64', 'vcvars64.bat'), 'arm64': ('ARM64', 'vcvarsarm64.bat')}[arch]
    vswhere = pathlib.Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    found = subprocess.run([str(vswhere), '-latest', '-products', '*', '-requires', f'Microsoft.VisualStudio.Component.VC.Tools.{component}',
                            '-find', f'VC/Auxiliary/Build/{vcvars}'], capture_output=True, text=True, check=True).stdout.splitlines()
    if not found:
        sys.exit(f'vswhere found no Visual Studio with the {arch} C++ build tools')
    dump = subprocess.run(f'"{found[-1]}" >nul && set', shell=True, capture_output=True, text=True, check=True).stdout
    env = dict(line.split('=', 1) for line in dump.splitlines() if '=' in line)
    # Windows names are case-insensitive: hosted runners spell it Path, and a dict needs one spelling.
    path = next(env.pop(key) for key in list(env) if key.upper() == 'PATH')
    env['PATH'] = os.pathsep.join([str(llvm), *args.tool_path, path])
    env['VCPKG_ROOT'] = str(vcpkg)
    env['VCPKG_DISABLE_METRICS'] = '1'
    env['DOTNET_CLI_TELEMETRY_OPTOUT'] = '1'
    print('MSVC', env.get('VCToolsVersion', '?'), '- tested:', pins['msvc']['tested'], flush=True)
    return env


def fetch():
    # WebKit's test and website trees are most of its checkout, and the build reads none of them.
    clone(args.webkit_repo, commit, source, exclude=['LayoutTests', 'JSTests', 'PerformanceTests', 'Websites', 'ManualTests'])
    if not windows:
        return
    clone(pins['vcpkg']['repository'], pins['vcpkg']['commit'], vcpkg)
    if not (vcpkg / 'vcpkg.exe').exists():
        run([vcpkg / 'bootstrap-vcpkg.bat', '-disableMetrics'], cwd=vcpkg)
    if not args.llvm and not (llvm / 'clang-cl.exe').exists():
        pin = pins['llvm'][args.rid]
        archive = work / 'downloads' / pin['url'].rsplit('/', 1)[1]
        download(pin['url'], archive, pin['sha256'])
        target = llvm.parent
        print('extract', archive, flush=True)
        with tarfile.open(archive) as tar:
            prefix = tar.getmembers()[0].name.split('/')[0]
            for member in tar.getmembers():
                member.name = member.name[len(prefix) + 1:] if member.name.startswith(prefix + '/') else member.name
                if member.name:
                    tar.extract(member, target, filter='data')


def prepare():
    run([sys.executable, '-I', root / 'scripts/patches.py', 'apply', '--source', source])
    # The host is a new target over WebKit's TestWebCore libraries, so it lives in the API test tree.
    api = source / 'Tools/TestWebKitAPI'
    (api / 'RanvierAbi').mkdir(exist_ok=True)
    for name in ['RanvierWebCoreAbi.h', 'RanvierWebCoreAbi.cpp']:
        shutil.copy2(root / 'host' / name, api / 'RanvierAbi' / name)
    git('checkout', commit, '--', 'Tools/TestWebKitAPI/CMakeLists.txt', cwd=source)
    cmake = api / 'CMakeLists.txt'
    cmake.write_text(cmake.read_text() + (root / 'host/RanvierWebCoreHost.cmake').read_text(), newline='\n')
    print('host installed into', api, flush=True)


def configure(env):
    build.mkdir(parents=True, exist_ok=True)
    # RANVIER_RID comes before -C: config/common.cmake picks the port from it.
    command = ['cmake', '-S', source, '-B', build, '-G', 'Ninja', f'-DRANVIER_RID={args.rid}',
               '-C', root / 'config' / f'{args.flavor}.cmake']
    if windows:
        clang = (llvm / 'clang-cl.exe').as_posix()
        command += [f'-DCMAKE_C_COMPILER={clang}', f'-DCMAKE_CXX_COMPILER={clang}',
                    f'-DCMAKE_TOOLCHAIN_FILE={(vcpkg / "scripts/buildsystems/vcpkg.cmake").as_posix()}',
                    f'-DVCPKG_INSTALLED_DIR={installed.as_posix()}']
    if windows and arch == 'arm64':
        # The ICU port of WebKit's registry bases its DLLs below 4 GB (-base:0x4a800000 and up), which link.exe
        # rejects for ARM64 (LNK1355). link.exe appends _LINK_ after the command line, so this base wins, and
        # VCPKG_KEEP_ENV_VARS passes it to the port builds. ARM64 images are always relocatable: the base is a preference.
        env = dict(env, _LINK_='/BASE:0x180000000', VCPKG_KEEP_ENV_VARS='_LINK_')
    run(command, env=env, cwd=source)


def icu_data(env):
    """ICU's data archive: from vcpkg's download cache, or downloaded when a binary cache hit skipped the download."""
    icu = pins['icu']
    name = icu['url'].rsplit('/', 1)[1]
    cached = pathlib.Path(env.get('VCPKG_DOWNLOADS', vcpkg / 'downloads')) / name
    archive = cached if cached.exists() else work / 'downloads' / name
    download(icu['url'], archive, icu['sha256'])
    data = build / 'icu-source' / pathlib.Path(icu['data']).name
    data.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar, open(data, 'wb') as stream:
        shutil.copyfileobj(tar.extractfile(icu['data']), stream)
    if sha256(data) != icu['data_sha256']:
        sys.exit(f'{data}: sha256 differs from pins.json')
    run([sys.executable, '-I', root / 'scripts/icu_data.py', '--data', data, '--icu-tools', triplet / 'tools/icu',
         '--icu-bin', triplet / 'bin', '--linker', llvm / 'lld-link.exe', '--out', build / 'bin', '--machine', arch.upper()], env=env)


def build_step(env):
    # The gpu flavor is the slim flavor with the GPU code kept (config/gpu.cmake).
    slim = args.flavor in ('slim', 'gpu')
    if windows and slim:
        # lld-link appends _LINK_ after the command line, so it overrides OptionsMSVC.cmake's /OPT:NOICF.
        # Safe ICF folds only functions whose address is not taken. WebCore links dwrite only through
        # PlatformWin.cmake's MediaFoundation target, which ENABLE_VIDEO=OFF removes.
        env = dict(env, _LINK_='/OPT:SAFEICF dwrite.lib')
        # USE_ANGLE_STUB links EGL and GLES statically; ANGLE DLLs from an earlier lean build would hide a dynamic load.
        if args.flavor == 'slim':
            for name in ['libEGL.dll', 'libGLESv2.dll']:
                (build / 'bin' / name).unlink(missing_ok=True)
    run(['cmake', '--build', build, '--target', 'RanvierWebCoreHost', '-j', str(args.jobs)], env=env, cwd=build)
    if windows and slim:
        icu_data(env)


def imports(path):
    """The library names path imports: its DLL imports, ELF NEEDED entries or Mach-O @rpath load commands."""
    if windows:
        text = subprocess.run([str(llvm / 'llvm-readobj.exe'), '--coff-imports', str(path)], capture_output=True, text=True, check=True).stdout
        return re.findall(r'Name: (\S+\.dll)', text, re.I)
    if system == 'linux':
        text = subprocess.run(['readelf', '-d', '--wide', str(path)], capture_output=True, text=True, check=True).stdout
        return re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]', text)
    text = subprocess.run(['otool', '-L', str(path)], capture_output=True, text=True, check=True).stdout
    return re.findall(r'^\s+@rpath/(\S+)', text, re.M)


def closure():
    """(name, path) of each library the host loads, transitively, from the build (and vcpkg on Windows).
    Libraries of the system, and on Linux of the distribution, are not found there and stay out."""
    dirs = [build / 'bin', build / 'lib/ranvier', triplet / 'bin'] if windows else [build / 'lib/ranvier', build / 'lib']
    seen, todo = {}, [host]
    while todo:
        name = todo.pop()
        path = next((d / name for d in dirs if (d / name).exists()), None)
        if name.lower() in seen or path is None:
            continue
        seen[name.lower()] = (name, path)
        todo += imports(path)
    return sorted(seen.values(), key=lambda item: item[0].lower())


def package(env):
    if out.exists():
        shutil.rmtree(out)
    native = out / 'runtimes' / args.rid / 'native'
    symbols = out / 'symbols' / args.rid
    native.mkdir(parents=True)
    symbols.mkdir(parents=True)
    files = []
    for name, path in closure():
        # Under the name the importer asks for: on Linux a versioned symlink's name, holding the file it points to.
        staged = native / name
        shutil.copy2(path, staged)
        if windows:
            pdb = path.with_suffix('.pdb')
            if pdb.exists():
                shutil.copy2(pdb, symbols / pdb.name)
        elif system == 'linux':
            # Debug information goes to symbols/, linked back by name; $ORIGIN finds the sibling libraries.
            debug = symbols / f'{name}.debug'
            run(['objcopy', '--only-keep-debug', staged, debug])
            run(['objcopy', '--strip-debug', '--strip-unneeded', f'--add-gnu-debuglink={debug}', staged])
            run(['patchelf', '--set-rpath', '$ORIGIN', staged])
        files.append(dict(name=name, bytes=staged.stat().st_size, sha256=sha256(staged)))
    # WebCore reads images from WebKit.resources next to WebCore.dll (WebCoreBundleWin.cpp): the icons hold
    # the broken-image and resize-corner images. Media controls (no video) and WebInspectorUI (no
    # inspector) have no reader in the slim flavor. The other ports compile their images in.
    for path in sorted((build / 'bin/WebKit.resources/icons').iterdir()) if windows else []:
        target = native / 'WebKit.resources/icons' / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        files.append(dict(name=f'WebKit.resources/icons/{path.name}', bytes=path.stat().st_size, sha256=sha256(path)))
    (out / 'include').mkdir()
    shutil.copy2(root / 'host/RanvierWebCoreAbi.h', out / 'include')
    abi = re.search(r'rv_abi_version\(void\) \{ return (\d+); \}', (root / 'host/RanvierWebCoreAbi.cpp').read_text())
    manifest = dict(flavor=args.flavor, rid=args.rid, version=args.version, webkit=commit, abi=int(abi.group(1)),
                    total_bytes=sum(f['bytes'] for f in files), files=files)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    targets = (root / 'packaging/buildTransitive.targets').read_text().replace('@RID@', args.rid)
    (out / 'buildTransitive.targets').write_text(targets)
    for f in files:
        print(f"{f['name']:50} {f['bytes']:>12,}")
    print(f"{len(files)} files, {manifest['total_bytes'] / 1e6:.2f} MB", flush=True)
    package_id = pins['package']['id'] + {'slim': '', 'gpu': '.Gpu', 'lean': '.Lean'}[args.flavor] + '.' + args.rid
    run(['dotnet', 'pack', root / 'packaging/Ranvier.WebCore.Native.csproj', '-c', 'Release', '--nologo',
         '-o', work / 'packages', f'-p:PackageId={package_id}', f'-p:PackageVersion={args.version}',
         f'-p:StageDir={out.as_posix()}/', f'-p:RuntimeId={args.rid}', f'-p:WebKitCommit={commit}'], env=env)


selected = steps if args.step == 'all' else [args.step]
env = None
for step in selected:
    print(f'== {step} ({args.flavor})', flush=True)
    if step == 'fetch':
        fetch()
        continue
    if step == 'prepare':
        prepare()
        continue
    env = env or toolchain_env()
    {'configure': configure, 'build': build_step, 'package': package}[step](env)
