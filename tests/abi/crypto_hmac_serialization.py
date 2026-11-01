"""Private native test unit: real CryptoKey Data and structured-clone round trips."""

import argparse
import ctypes
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, Case, P, I, U


def run(directory, legacy_file, capture=False, bridge_library=None):
    n = Native(directory)
    library = ctypes.CDLL(bridge_library) if bridge_library else None

    def bind_fixture(name, result, arguments):
        if library is None:
            return n.bind(name, result, arguments)
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
        return function

    page = Case(n, '<p>initialize native fixture</p>')
    try:
        wire = bind_fixture('ranvier_test_hmac_wire', I, [U, P, I, ctypes.POINTER(I)])
        buffer, length = ctypes.create_string_buffer(4096), I()
        n.expect(wire(160, buffer, len(buffer), ctypes.byref(length)) == 0, 'encode byte-aligned HMAC')
        encoded = buffer.raw[:length.value]
        if capture:
            Path(legacy_file).write_text(encoded.hex() + '\n')
            print(f'HMAC_LEGACY_CAPTURE bytes={len(encoded)}')
            return
        n.expect(encoded.hex() == Path(legacy_file).read_text().strip(), 'legacy byte-aligned output remains byte-identical')
        test = bind_fixture('ranvier_test_hmac_serialization', I, [U, U])
        for bits in [0, 153, 154, 155, 156, 157, 158, 159, 160]:
            result = test(bits, 0)
            n.expect(result == 0, f'Data and real serializer round trips length={bits}: checkpoint={result}')
        for corruption in range(1, 7):
            result = test(159, corruption)
            n.expect(result == 0, f'reject malformed/newer key schema case={corruption}: checkpoint={result}')
        print(f'CRYPTO_HMAC_SERIALIZATION PASS assertions={n.assertions}')
    finally:
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--legacy-file', required=True)
    parser.add_argument('--capture-legacy', action='store_true')
    parser.add_argument('--bridge-library')
    arguments = parser.parse_args()
    run(arguments.native_directory, arguments.legacy_file, arguments.capture_legacy, arguments.bridge_library)
