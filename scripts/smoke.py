# Checks a staged or packed runtime: the manifest names the files that are there, with their sizes and
# SHA-256, and states what is expected of it; then the host loads from the staged files alone and paints a page.
#
#   smoke.py --stage DIR          a directory that build.py package staged (<work>/out/<flavor>)
#   smoke.py --package FILE       a .nupkg, extracted to a temporary directory first
#
# The --expect-* options compare the manifest with the build a release names. --build-dir, on macOS, fails a
# library whose load commands name the build tree. Python's main thread is the process's main thread, which
# WebCore on Cocoa requires, so this runs as its own process.
import argparse, ctypes, hashlib, json, os, pathlib, subprocess, sys, tempfile, zipfile

parser = argparse.ArgumentParser()
where = parser.add_mutually_exclusive_group(required=True)
where.add_argument('--stage')
where.add_argument('--package')
parser.add_argument('--build-dir')
parser.add_argument('--expect-commit', help='the ranvier-webcore commit the build must come from, from a clean tree')
parser.add_argument('--expect-version')
parser.add_argument('--expect-flavor')
parser.add_argument('--no-load', action='store_true', help='check the manifest only')
args = parser.parse_args()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def check(stage):
    manifest = json.loads((stage / 'manifest.json').read_text())
    rid = manifest['rid']
    native = stage / 'runtimes' / rid / 'native'
    problems = []
    for f in manifest['files']:
        path = native / f['name']
        if not path.exists():
            problems.append(f"{f['name']}: missing")
        elif (path.stat().st_size, sha256(path)) != (f['bytes'], f['sha256']):
            problems.append(f"{f['name']}: size or sha256 differs from the manifest")
    source = manifest.get('source', {})
    expected = {'flavor': args.expect_flavor, 'version': args.expect_version}
    problems += [f'manifest {key} is {manifest[key]!r}, expected {value!r}' for key, value in expected.items()
                 if value and manifest[key] != value]
    if args.expect_commit and (source.get('commit'), source.get('dirty')) != (args.expect_commit, False):
        problems.append(f"built from {source.get('commit')} (dirty: {source.get('dirty')}), expected {args.expect_commit}, clean")
    print(f"{rid} {manifest['flavor']} {manifest['version']}: {len(manifest['files'])} files, built by "
          f"{source.get('builder', '?')} from {source.get('commit', '?')}", flush=True)
    if args.build_dir and sys.platform == 'darwin':
        for path in sorted(native.glob('*.dylib')):
            commands = subprocess.run(['otool', '-l', str(path)], capture_output=True, text=True, check=True).stdout
            if args.build_dir in commands:
                problems.append(f'{path.name} names the build tree')
    if problems:
        sys.exit('\n'.join(problems))
    if not args.no_load:
        paint(native, manifest)


def paint(native, manifest):
    system = manifest['rid'].split('-')[0]
    host = native / {'win': 'RanvierWebCoreHost.dll', 'linux': 'libRanvierWebCoreHost.so', 'osx': 'libRanvierWebCoreHost.dylib'}[system]
    if system == 'win':
        # Also for the libraries the host loads later, as LoadLibrary, which the load directory does not cover.
        os.add_dll_directory(str(native))
    lib = ctypes.CDLL(str(host))
    lib.rv_host_create.restype = ctypes.c_void_p
    lib.rv_host_create.argtypes = [ctypes.c_int32, ctypes.c_int32]
    # The markup is UTF-8 bytes and their byte count.
    lib.rv_host_load_html.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32]
    lib.rv_host_paint_rgba.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32]
    lib.rv_host_destroy.argtypes = [ctypes.c_void_p]
    abi = lib.rv_abi_version()
    print('rv_abi_version', abi, '- manifest', manifest['abi'], flush=True)
    assert abi == manifest['abi']
    host = lib.rv_host_create(32, 32)
    assert host
    markup = b'<body style="margin:0;background:#f00"><div style="width:8px;height:8px;background:#00f"></div>'
    assert lib.rv_host_load_html(host, markup, len(markup)) == 0
    rgba = ctypes.create_string_buffer(32 * 32 * 4)
    assert lib.rv_host_paint_rgba(host, rgba, len(rgba)) == 0
    pixel = lambda x, y: tuple(rgba.raw[(y * 32 + x) * 4:(y * 32 + x) * 4 + 4])
    print('pixel (2, 2)', pixel(2, 2), 'pixel (20, 20)', pixel(20, 20), flush=True)
    near = lambda actual, expected: all(abs(a - e) <= 2 for a, e in zip(actual, expected))
    assert near(pixel(2, 2), (0, 0, 255, 255)) and near(pixel(20, 20), (255, 0, 0, 255))
    lib.rv_host_destroy(host)
    print('painted', flush=True)


if args.stage:
    check(pathlib.Path(args.stage))
else:
    # The loaded libraries stay mapped until the process exits, and Windows cannot delete a mapped file.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        with zipfile.ZipFile(args.package) as package:
            package.extractall(temp)
        check(pathlib.Path(temp))
