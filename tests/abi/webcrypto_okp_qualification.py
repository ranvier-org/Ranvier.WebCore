import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import sys
import time


sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Case, Native, P, I


ED_SIGNATURE = bytes.fromhex('e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555f'
                             'b8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')
X_SHARED = bytes.fromhex('4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742')
CASES = [
    ('RFC8032 empty-message sign', 'bytes', ED_SIGNATURE),
    ('RFC8032 valid signature', 'boolean', True),
    ('tampered Ed25519 signature', 'boolean', False),
    ('short Ed25519 signature', 'boolean', False),
    ('small-order Ed25519 public point', 'boolean', False),
    ('small-order Ed25519 R point', 'boolean', False),
    ('Ed25519 sign rejects public key', 'error', 'InvalidAccessError'),
    ('Ed25519 verify rejects private key', 'error', 'InvalidAccessError'),
    ('RFC7748 Alice derives', 'bytes', X_SHARED),
    ('RFC7748 Bob derives', 'bytes', X_SHARED),
    ('X25519 all-zero peer', 'error', 'OperationError'),
    ('X25519 private peer', 'error', 'InvalidAccessError'),
    ('X25519 public base', 'error', 'InvalidAccessError'),
    ('X25519 cross-algorithm peer', 'error', 'InvalidAccessError'),
    ('X25519 excessive output length', 'error', 'OperationError'),
    ('X25519 truncated output', 'bytes', X_SHARED[:16]),
    ('X25519 zero output length', 'bytes', b''),
    ('X25519 absent output length', 'bytes', X_SHARED),
    ('X25519 all-zero peer with absent length', 'error', 'OperationError'),
    ('X25519 all-zero peer with zero output length', 'error', 'OperationError'),
    ('RFC7748 normal peer first 1 bit', 'bytes', bytes([X_SHARED[0] & 0x80])),
    ('RFC7748 normal peer first 7 bits', 'bytes', bytes([X_SHARED[0] & 0xfe])),
    ('RFC7748 normal peer first 9 bits', 'bytes', X_SHARED[:1] + bytes([X_SHARED[1] & 0x80])),
]


def run(arguments):
    n = Native(arguments.native_directory)
    page = Case(n, '<p>private OKP algorithm qualification</p>')
    library = ctypes.CDLL(str(Path(arguments.bridge_library).resolve()))

    def bind(name, types, result=I):
        function = getattr(library, 'ranvier_test_okp_' + name)
        function.argtypes, function.restype = types, result
        return function

    sync = bind('key_ports', [P])
    begin = bind('begin', [P, I])
    status = bind('status', [])
    boolean = bind('boolean', [])
    data = bind('bytes', [P, I])
    error = bind('error', [], ctypes.c_char_p)
    clear = bind('clear', [], None)
    results = []
    try:
        assertions = sync(page.document)
        n.expect(assertions > 0, f'synchronous OKP generation/import/export checkpoint {-assertions}')
        for scenario, (name, kind, expected) in enumerate(CASES):
            n.expect(begin(page.document, scenario) == 0, name + ' starts')
            initial_status = status()
            if scenario in [0, 1, 2, 3, 4, 5, 8, 9, 10, 14, 15, 17, 18]:
                n.expect(initial_status == 0, name + ' completes through context task')
            deadline = time.monotonic() + 10
            while not status() and time.monotonic() < deadline:
                n.call('rv_host_update', [P], page.host)
                n.call('rv_run_loop_cycle', [I], 5)
            terminal = status()
            n.expect(terminal != 0, name + ' completes')
            error_name = error().decode()
            if kind == 'error':
                if terminal != 2 or error_name != expected:
                    buffer = ctypes.create_string_buffer(1024)
                    length = data(buffer, len(buffer)) if terminal == 1 else -1
                    Path(arguments.report).write_text(json.dumps({
                        'result': 'FAIL', 'synchronousAssertions': assertions, 'passedCases': results,
                        'scenario': scenario, 'name': name, 'terminalStatus': terminal,
                        'errorName': error_name, 'expectedError': expected,
                        'unexpectedBytes': buffer.raw[:length].hex() if length >= 0 else None,
                        'bridgeSha256': hashlib.sha256(Path(arguments.bridge_library).read_bytes()).hexdigest()
                    }, indent=2) + '\n')
                n.expect(terminal == 2 and error_name == expected, name + ': ' + error_name)
                actual = error_name
            else:
                n.expect(terminal == 1 and not error_name, name + ' succeeds')
                if kind == 'boolean':
                    actual = bool(boolean())
                else:
                    buffer = ctypes.create_string_buffer(1024)
                    length = data(buffer, len(buffer))
                    n.expect(length >= 0, name + ' byte result')
                    actual = buffer.raw[:length]
                n.expect(actual == expected, name + ' matches primary vector/result')
            results.append({'scenario': scenario, 'name': name, 'kind': kind,
                            'initialStatus': initial_status, 'actual': actual.hex() if isinstance(actual, bytes) else actual})
            clear()
        report = {'result': 'PASS', 'synchronousAssertions': assertions, 'driverAssertions': n.assertions,
                  'cases': results, 'bridgeSha256': hashlib.sha256(Path(arguments.bridge_library).read_bytes()).hexdigest(),
                  'vectorSources': ['https://www.rfc-editor.org/rfc/rfc8032.html#section-7.1',
                                    'https://www.rfc-editor.org/rfc/rfc7748.html#section-6.1'],
                  'scope': 'Private CryptoAlgorithm/CryptoKeyOKP registry, metadata, formats, callbacks and OKP ports; generic algorithm export primitive does not enforce outer SubtleCrypto extractability policy; full eleven-op ABI/JIT/AOT/browser profile remains separate'}
        Path(arguments.report).write_text(json.dumps(report, indent=2) + '\n')
        print(f'WEBCRYPTO_OKP PASS synchronous={assertions}, async/error scenarios={len(results)}')
    finally:
        clear()
        page.close()


def run_focused_x(arguments):
    n = Native(arguments.native_directory)
    page = Case(n, '<p>focused X25519 bit and all-zero peer controls</p>')
    library = ctypes.CDLL(str(Path(arguments.bridge_library).resolve()))

    def bind(name, types, result=I):
        function = getattr(library, 'ranvier_test_okp_' + name)
        function.argtypes, function.restype = types, result
        return function

    begin = bind('begin', [P, I])
    status = bind('status', [])
    data = bind('bytes', [P, I])
    error = bind('error', [], ctypes.c_char_p)
    clear = bind('clear', [], None)
    rows = []
    try:
        for scenario in [19, 20, 21, 22]:
            name, kind, expected = CASES[scenario]
            n.expect(begin(page.document, scenario) == 0, name + ' starts')
            initial = status()
            deadline = time.monotonic() + 10
            while not status() and time.monotonic() < deadline:
                n.call('rv_host_update', [P], page.host)
                n.call('rv_run_loop_cycle', [I], 5)
            terminal = status()
            n.expect(terminal != 0, name + ' completes')
            actual_error = error().decode()
            buffer = ctypes.create_string_buffer(1024)
            length = data(buffer, len(buffer)) if terminal == 1 else -1
            actual_bytes = buffer.raw[:length] if length >= 0 else None
            passed = (terminal == 2 and actual_error == expected) if kind == 'error' else (terminal == 1 and not actual_error and actual_bytes == expected)
            rows.append({'scenario': scenario, 'name': name, 'initialStatus': initial, 'terminalStatus': terminal,
                         'expectedKind': kind, 'expected': expected.hex() if isinstance(expected, bytes) else expected,
                         'actualError': actual_error, 'actualBytes': actual_bytes.hex() if actual_bytes is not None else None,
                         'pass': passed})
            clear()
        report = {'result': 'PASS' if all(row['pass'] for row in rows) else 'FAIL', 'rows': rows,
                  'sourceFixture': 'f56b1c924bb24389ae2a3a3bc2d9b90982cbfd37 plus four explicit controls',
                  'fullRfc7748Secret': X_SHARED.hex(), 'allZeroPeerHex': '00' * 32,
                  'vectorSource': 'https://www.rfc-editor.org/rfc/rfc7748.html#section-6.1',
                  'contractSource': 'https://w3c.github.io/webcrypto/#x25519-operations',
                  'bridgeSha256': hashlib.sha256(Path(arguments.bridge_library).read_bytes()).hexdigest(),
                  'prior699And19Rerun': False, 'full143Closed': False}
        Path(arguments.report).write_text(json.dumps(report, indent=2) + '\n')
        print(f'X25519_FOCUSED {report["result"]} rows={len(rows)} failures={sum(not row["pass"] for row in rows)}')
        if report['result'] != 'PASS':
            raise AssertionError('Focused X25519 controls failed; every actual row is preserved in the report')
    finally:
        clear()
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--bridge-library', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--focused-x', action='store_true')
    arguments = parser.parse_args()
    (run_focused_x if arguments.focused_x else run)(arguments)
