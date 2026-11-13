# Checks a staged or packed runtime: the manifest names the files that are there, with their sizes and
# SHA-256, and states what is expected of it; on Linux, verifies that no staged shared object dynamically
# links ICU or harfbuzz-icu or exports their internal symbols; then the host loads from the staged files
# alone and paints a page.
#
#   smoke.py --stage DIR          a directory that build.py package staged (<work>/out/<flavor>)
#   smoke.py --package FILE       a .nupkg, extracted to a temporary directory first
#
# The --expect-* options compare the manifest with the build a release names. --build-dir, on macOS, fails a
# library whose load commands name the build tree. Python's main thread is the process's main thread, which
# WebCore on Cocoa requires, so this runs as its own process.
import argparse, ctypes, hashlib, json, os, pathlib, struct, subprocess, sys, tempfile, zipfile

FORBIDDEN_LINUX_NEEDED_PREFIXES = ('libicu', 'libharfbuzz-icu')
FORBIDDEN_LINUX_EXPORT_PREFIXES = ('hb_icu_', 'icudt')


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def _cstr(buf, offset):
    if offset < 0 or offset >= len(buf):
        return ''
    end = buf.find(b'\0', offset)
    return buf[offset:end if end != -1 else len(buf)].decode('utf-8', 'replace')


def elf_linkage(path):
    """Returns (needed, exported) from an ELF64 little-endian shared object's .dynamic and .dynsym sections."""
    data = pathlib.Path(path).read_bytes()
    if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01':
        return [], []
    e_shoff = struct.unpack_from('<Q', data, 40)[0]
    e_shentsize, e_shnum = struct.unpack_from('<HH', data, 58)
    if not e_shoff or not e_shnum or e_shentsize < 64 or e_shoff + e_shnum * e_shentsize > len(data):
        return [], []
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, e_shoff + i * e_shentsize) for i in range(e_shnum)]
    needed = []
    exported = []
    for _, sh_type, _, _, sh_offset, sh_size, sh_link, _, _, sh_entsize in sections:
        if sh_offset + sh_size > len(data) or not (0 <= sh_link < len(sections)):
            continue
        str_off, str_size = sections[sh_link][4], sections[sh_link][5]
        if str_off + str_size > len(data):
            continue
        strtab = data[str_off:str_off + str_size]
        if sh_type == 6:  # SHT_DYNAMIC
            step = sh_entsize or 16
            for off in range(sh_offset, sh_offset + sh_size - (step - 1), step):
                d_tag, d_val = struct.unpack_from('<qQ', data, off)
                if d_tag == 0:
                    break
                if d_tag == 1:  # DT_NEEDED
                    needed.append(_cstr(strtab, d_val))
        elif sh_type == 11:  # SHT_DYNSYM
            step = sh_entsize or 24
            for off in range(sh_offset, sh_offset + sh_size - (step - 1), step):
                st_name, st_info, _, st_shndx, _, _ = struct.unpack_from('<IBBHQQ', data, off)
                if st_shndx != 0 and (st_info >> 4) != 0 and st_name:
                    exported.append(_cstr(strtab, st_name))
    return needed, exported


def linux_icu_problems(native):
    problems = []
    for path in sorted(p for p in pathlib.Path(native).iterdir() if p.is_file() and (p.suffix == '.so' or '.so.' in p.name)):
        needed, exported = elf_linkage(path)
        for lib in needed:
            if lib.startswith(FORBIDDEN_LINUX_NEEDED_PREFIXES):
                problems.append(f'{path.name}: dynamically links {lib}; ICU and harfbuzz-icu must be linked statically')
        for sym in exported:
            if sym.startswith(FORBIDDEN_LINUX_EXPORT_PREFIXES):
                problems.append(f'{path.name}: exports internal ICU symbol {sym}')
    return problems


def check(stage, args):
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
    if rid.startswith('linux-') and native.exists():
        problems += linux_icu_problems(native)
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


def main():
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

    if args.stage:
        check(pathlib.Path(args.stage), args)
    else:
        # The loaded libraries stay mapped until the process exits, and Windows cannot delete a mapped file.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            with zipfile.ZipFile(args.package) as package:
                package.extractall(temp)
            check(pathlib.Path(temp), args)


if __name__ == '__main__':
    main()
