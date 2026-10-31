"""B22 crypto probe against an actual runtime directory: rv_dom_crypto_get_random_values and rv_dom_crypto_random_uuid.
Replays the Chromium 156 measurements of tests/fixtures/crypto-random-oracle.json as properties only (length, kind,
format, version and variant bits, two calls differ), never a random value: the element kinds that fill and the ones
that raise TypeMismatchError, the 65536-byte QuotaExceededError limit, an empty view, and a subarray whose
neighbouring bytes stay untouched. It also checks the null, thread, interface, kind and capacity errors, and a
document handle used after rv_host_destroy."""

import argparse
import ctypes
import json
from pathlib import Path
import re
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, Case, P, I

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, BUFFER_TOO_SMALL, UNSUPPORTED, WRONG_INTERFACE = 0, -1, -2, -3, -6, -9, -11
ABI = 54
FEATURE = 'dom-crypto-random'
# RV_DOM_ARRAY_BUFFER_VIEW_* and the element size of each kind, in the order of the header's constants.
KINDS = [('Int8Array', 1), ('Uint8Array', 1), ('Uint8ClampedArray', 1), ('Int16Array', 2), ('Uint16Array', 2),
         ('Int32Array', 4), ('Uint32Array', 4), ('Float16Array', 2), ('Float32Array', 4), ('Float64Array', 8),
         ('BigInt64Array', 8), ('BigUint64Array', 8), ('DataView', 1)]
LABELS = {'empty': 0, 'small': 16, 'limit': 65536, 'over': 65544}
UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')


class Crypto:
    def __init__(self, native):
        self.n = native
        self.random = native.bind('rv_dom_crypto_get_random_values', I, [P, I, P, I])
        self.uuid_function = native.bind('rv_dom_crypto_random_uuid', I, [P, P, I, ctypes.POINTER(I)])

    def fill(self, document, kind, buffer, length):
        return self.random(document, kind, buffer, length)

    def uuid(self, document):
        buffer, length = ctypes.create_string_buffer(64), I()
        status = self.uuid_function(document, buffer, len(buffer), ctypes.byref(length))
        self.n.expect(status == OK, f'randomUUID status {status}')
        return buffer.raw[:length.value].decode('ascii')

    def exception_name(self):
        return self.n.exception()


def outcome(crypto, document, kind, size):
    """The status of a fill of `size` bytes, the exception name, and whether the bytes changed from zero."""
    buffer = (ctypes.c_uint8 * max(size, 1))()
    status = crypto.fill(document, kind, buffer, size)
    entry = {'ok': status == OK}
    if status == DOM_EXCEPTION:
        entry['name'] = crypto.exception_name().split(':')[0] if crypto.exception_name() else None
    elif status != OK:
        entry['status'] = status
    return entry, bytes(buffer)[:size]


def kinds(native, crypto, document, oracle, report):
    n = native
    measured = {}
    for index, (name, size) in enumerate(KINDS):
        expected = oracle['typed'][name]
        entry = {}
        for label, length in LABELS.items():
            result, data = outcome(crypto, document, index, length)
            want = expected[label]
            n.expect(result['ok'] == want['ok'], f'{name} {label}: {result} vs {want}')
            if not want['ok']:
                n.expect(result.get('name') == want['name'], f'{name} {label}: exception {result} vs {want["name"]}')
                n.expect(data == bytes(length), f'{name} {label}: bytes unchanged after the exception')
            elif length >= 16:
                # 16 or more random bytes are all zero with probability 2^-128.
                n.expect(data != bytes(length), f'{name} {label}: bytes filled')
            entry[label] = result
        measured[name] = entry
    report['kinds'] = measured


def quota(native, crypto, document, oracle, report):
    n = native
    for count, want in oracle['quota32'].items():
        result, _ = outcome(crypto, document, KINDS.index(('Uint32Array', 4)), int(count) * 4)
        n.expect(result['ok'] == want['ok'], f'Uint32Array({count}): {result}')
        if not want['ok']:
            n.expect(result.get('name') == want['name'], f'Uint32Array({count}) exception {result}')
    report['quota32'] = 'checked'


def subarray_and_differ(native, crypto, document, oracle, report):
    n = native
    base = (ctypes.c_uint8 * 32)()
    view = ctypes.cast(ctypes.addressof(base) + 8, P)
    n.expect(crypto.fill(document, 1, view, 16) == OK, 'subarray fill')
    data = bytes(base)
    untouched = data[:8] == bytes(8) and data[24:] == bytes(8)
    n.expect(untouched == oracle['outsideUntouched'], 'bytes outside the subarray untouched')
    n.expect(data[8:24] != bytes(16), 'subarray filled')
    first, second = (ctypes.c_uint8 * 16)(), (ctypes.c_uint8 * 16)()
    n.ok('rv_dom_crypto_get_random_values', [P, I, P, I], document, 1, first, 16)
    n.ok('rv_dom_crypto_get_random_values', [P, I, P, I], document, 1, second, 16)
    n.expect((bytes(first) != bytes(second)) == oracle['differ'], 'two fills differ')
    report['outsideUntouched'] = untouched
    report['differ'] = bytes(first) != bytes(second)


def uuids(native, crypto, document, oracle, report):
    n = native
    expected = oracle['uuid']
    values = [crypto.uuid(document) for _ in range(64)]
    measured = {
        'length': len(values[0]), 'allMatchV4': all(UUID.match(value) for value in values),
        'allLowercase': all(value == value.lower() for value in values), 'allDistinct': len(set(values)) == len(values),
        'versionNibble': sorted({value[14] for value in values}),
    }
    for key in ['length', 'allMatchV4', 'allLowercase', 'allDistinct', 'versionNibble']:
        n.expect(measured[key] == expected[key], f'randomUUID {key}: {measured[key]} vs {expected[key]}')
    variants = {value[19] for value in values}
    n.expect(variants <= set(expected['variantNibbles']), f'randomUUID variant nibbles {sorted(variants)}')
    report['uuid'] = measured


def errors(native, crypto, case, report):
    n = native
    document = case.document
    buffer = (ctypes.c_uint8 * 8)()
    n.expect(crypto.fill(None, 1, buffer, 8) == NULL_ARGUMENT, 'null document')
    n.expect(crypto.fill(document, 1, None, 8) == NULL_ARGUMENT, 'null buffer with a length')
    n.expect(crypto.fill(document, 1, None, 0) == OK, 'null buffer with length 0')
    n.expect(crypto.fill(document, 1, buffer, -1) == NULL_ARGUMENT, 'negative length')
    n.expect(crypto.fill(document, 13, buffer, 8) == UNSUPPORTED, 'unknown kind')
    n.expect(crypto.fill(document, -1, buffer, 8) == UNSUPPORTED, 'negative kind')
    status = crypto.fill(document, 3, buffer, 3)
    n.expect(status == DOM_EXCEPTION and crypto.exception_name().startswith('RangeError'), 'odd byte length of an Int16Array')
    paragraph = case.node('p')
    n.expect(crypto.fill(paragraph, 1, buffer, 8) == WRONG_INTERFACE, 'element target')
    small, length = ctypes.create_string_buffer(8), I()
    n.expect(crypto.uuid_function(document, small, 8, ctypes.byref(length)) == BUFFER_TOO_SMALL and length.value == 36,
             'randomUUID capacity')
    n.expect(crypto.uuid_function(document, small, 8, None) == NULL_ARGUMENT, 'randomUUID null length')
    n.expect(crypto.uuid_function(None, small, 8, ctypes.byref(length)) == NULL_ARGUMENT, 'randomUUID null document')
    n.expect(crypto.uuid_function(paragraph, small, 8, ctypes.byref(length)) == WRONG_INTERFACE, 'randomUUID element target')
    outcome_by_thread = {}

    def worker():
        outcome_by_thread['random'] = crypto.fill(document, 1, buffer, 8)
        outcome_by_thread['uuid'] = crypto.uuid_function(document, small, 8, ctypes.byref(I()))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    n.expect(all(status == WRONG_THREAD for status in outcome_by_thread.values()), f'wrong thread {outcome_by_thread}')
    report['errors'] = 'checked'


def after_destroy(native, crypto, report):
    """A document handle kept past rv_host_destroy keeps its Window and crypto object, as a detached browser window
    does: both functions still succeed and keep their properties."""
    n = native
    case = Case(n, '<p id=p>x</p>')
    document = case.document
    n.bind('rv_node_retain', P, [P])(document)
    case.close()
    buffer = (ctypes.c_uint8 * 16)()
    random = crypto.fill(document, 1, buffer, 16)
    n.expect(random == OK and bytes(buffer) != bytes(16), f'getRandomValues after destroy {random}')
    value = crypto.uuid(document)
    n.expect(bool(UUID.match(value)), 'randomUUID after destroy is a v4 UUID')
    n.bind('rv_node_release', None, [P])(document)
    report['afterDestroy'] = {'getRandomValues': random, 'randomUUIDv4': True}


def verify(native_directory):
    oracle = json.loads((FIXTURES / 'crypto-random-oracle.json').read_text(encoding='utf-8'))
    native = Native(native_directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    native.expect(native.bind('rv_abi_has', I, [ctypes.c_char_p])(FEATURE.encode()) == 1, FEATURE + ' advertised')
    crypto = Crypto(native)
    report = {'browser': oracle['browser'], 'platform': sys.platform}
    case = Case(native, '<p id=p>x</p>')
    kinds(native, crypto, case.document, oracle, report)
    quota(native, crypto, case.document, oracle, report)
    subarray_and_differ(native, crypto, case.document, oracle, report)
    uuids(native, crypto, case.document, oracle, report)
    errors(native, crypto, case, report)
    case.close()
    after_destroy(native, crypto, report)
    report['assertions'] = native.assertions
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    report = verify(args.native_directory)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"PASS crypto_random: {report['assertions']} assertions", flush=True)


if __name__ == '__main__':
    main()
