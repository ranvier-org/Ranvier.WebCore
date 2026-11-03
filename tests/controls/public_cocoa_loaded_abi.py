"""Check the actual loaded public Host, handwritten exports and native image identities."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import sys

MAC_BASE_LIBRARIES = {'libRanvierWebCoreHost.dylib', 'libWebCore.dylib', 'libJavaScriptCore.dylib', 'libWebGPU.dylib'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-directory', type=Path, required=True)
    parser.add_argument('--header', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise ValueError('Actual macOS loader required')
    native = args.native_directory.resolve(strict=True)
    host = C.CDLL(str(native / 'libRanvierWebCoreHost.dylib'))
    host.rv_abi_version.argtypes, host.rv_abi_version.restype = [], C.c_int32
    abi = host.rv_abi_version()
    if abi != 64:
        raise ValueError('The actual loaded Host must report ABI64')
    names = re.findall(rb'RV_EXPORT\s+[^;]*?\b(rv_\w+)\s*\([^;]*?\)\s*;', args.header.read_bytes(), re.S)
    if len(names) != 349 or len(set(names)) != 349:
        raise ValueError('Require all349 canonical declarations')
    for name in names:
        getattr(host, name.decode('ascii'))
    process = C.CDLL(None)
    process._dyld_image_count.argtypes, process._dyld_image_count.restype = [], C.c_uint32
    process._dyld_get_image_name.argtypes, process._dyld_get_image_name.restype = [C.c_uint32], C.c_char_p
    expected = {p.name: p for p in native.glob('*.dylib')}
    loaded = {}
    for index in range(process._dyld_image_count()):
        raw = process._dyld_get_image_name(index)
        if not raw:
            continue
        path = Path(raw.decode()).resolve()
        if path.name in expected:
            if path != expected[path.name].resolve():
                raise ValueError('A native image loaded outside the exact public stage')
            loaded[path.name] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    if not MAC_BASE_LIBRARIES <= loaded.keys():
        raise ValueError('The actual CPU Host/engine closure was not observed')
    result = dict(abi=abi, declarations=len(names), loaded=loaded,
                  scope='Actual loaded CPU ABI/exports/images only; no GPU transport claim')
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
