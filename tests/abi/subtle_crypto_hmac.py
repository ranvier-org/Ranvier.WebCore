"""Private script-free HMAC bridge: RFC 4231, WebCrypto errors and owning tokens."""

import argparse
import ctypes
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, Case, P, I

U64 = ctypes.c_uint64


class Key(ctypes.Structure):
    _fields_ = [('value', U64)]


class Operation(ctypes.Structure):
    _fields_ = [('value', U64)]


class Bytes(ctypes.Structure):
    _fields_ = [('data', P), ('length', I)]


class Strings(ctypes.Structure):
    _fields_ = [('items', ctypes.POINTER(Bytes)), ('count', I)]


class Params(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('extractable', I), ('hash', Bytes),
                ('length_present', I), ('length_bits', ctypes.c_uint32), ('usages', Strings)]


class Info(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('extractable', I), ('length_bits', U64),
                ('can_sign', I), ('can_verify', I)]


def span(value):
    buffer = ctypes.create_string_buffer(value)
    result = Bytes(ctypes.cast(buffer, P), len(value))
    result.backing = buffer
    return result


def params(extractable=True, usages=(b'sign', b'verify'), hash_name=b'sHa-256', bits=None):
    hash_bytes = span(hash_name)
    names = [span(name) for name in usages]
    array = (Bytes * len(names))(*names)
    result = Params(ctypes.sizeof(Params), extractable, hash_bytes, bits is not None, bits or 0,
                    Strings(array, len(names)))
    result.backing = (hash_bytes, names, array)
    return result


class Probe:
    def __init__(self, native, library):
        self.n, self.library = native, library
        self.operations, self.keys = {}, {}

    def call(self, name, arguments, *values):
        function = getattr(self.library, 'ranvier_crypto_' + name)
        function.restype, function.argtypes = I, arguments
        return function(*values)

    def ok(self, name, arguments, *values):
        self.n.expect(self.call(name, arguments, *values) == 0, name)

    def start(self, name, arguments, *values):
        result = Operation()
        self.ok(name, arguments + [ctypes.POINTER(Operation)], *values, ctypes.byref(result))
        self.n.expect(bool(result.value), name + ' owns operation')
        self.operations[result.value] = result
        ready = I()
        self.ok('operation_ready', [Operation, ctypes.POINTER(I)], result, ctypes.byref(ready))
        self.n.expect(ready.value == 0, name + ' terminal delivery is deferred')
        return result

    def wait(self, operation, page=None):
        deadline, ready = time.monotonic() + 5, I()
        while time.monotonic() < deadline:
            self.ok('operation_ready', [Operation, ctypes.POINTER(I)], operation, ctypes.byref(ready))
            if ready.value:
                return
            if page:
                self.n.call('rv_host_update', [P], page.host)
            self.n.call('rv_run_loop_cycle', [I], 5)
        raise AssertionError('crypto operation timed out')

    def error(self, operation):
        buffer, length = ctypes.create_string_buffer(128), I()
        self.ok('operation_error', [Operation, P, I, ctypes.POINTER(I)], operation, buffer,
                len(buffer), ctypes.byref(length))
        return buffer.raw[:length.value].decode()

    def take(self, operation, page):
        self.wait(operation, page)
        self.n.expect(self.error(operation) == '', 'key result succeeds')
        key = Key()
        self.ok('operation_take_key', [Operation, ctypes.POINTER(Key)], operation, ctypes.byref(key))
        self.n.expect(bool(key.value), 'key token')
        self.keys[key.value] = (key, 1)
        duplicate = Key()
        self.n.expect(self.call('operation_take_key', [Operation, ctypes.POINTER(Key)], operation,
                               ctypes.byref(duplicate)) == -9 and not duplicate.value,
                      'key result transfers once')
        return key

    def bytes(self, operation, page):
        self.wait(operation, page)
        self.n.expect(self.error(operation) == '', 'byte result succeeds')
        buffer, length = ctypes.create_string_buffer(4096), I()
        status = self.call('operation_bytes', [Operation, P, I, ctypes.POINTER(I)], operation,
                           None, 0, ctypes.byref(length))
        self.n.expect(status == -6 and length.value > 0, 'byte result reports required capacity')
        self.ok('operation_bytes', [Operation, P, I, ctypes.POINTER(I)], operation, buffer,
                len(buffer), ctypes.byref(length))
        return buffer.raw[:length.value]

    def import_key(self, page, options=None, raw=None):
        return self.take(self.start('hmac_import_raw', [P, ctypes.POINTER(Params), Bytes],
                                   page.document, ctypes.byref(options or params()),
                                   raw or span(bytes([0x0b]) * 20)), page)

    def close(self):
        for operation in self.operations.values():
            self.ok('operation_release', [Operation], operation)
        for key, references in self.keys.values():
            for _ in range(references):
                self.ok('key_release', [Key], key)


def run(directory, bridge_library=None):
    n = Native(directory)
    library = ctypes.CDLL(bridge_library) if bridge_library else n.library
    probe = Probe(n, library)
    page = Case(n, '<p>crypto owner</p>')
    try:
        supported = I()
        probe.ok('hmac_supported', [P, ctypes.POINTER(I)], page.document, ctypes.byref(supported))
        n.expect(supported.value == 1, 'HMAC registered in this backend')
        key_data = span(bytes([0x0b]) * 20)
        key_operation = probe.start('hmac_import_raw', [P, ctypes.POINTER(Params), Bytes],
                                    page.document, ctypes.byref(params()), key_data)
        key_data.backing[0] = b'X'
        key = probe.take(key_operation, page)
        info = Info(ctypes.sizeof(Info))
        probe.ok('hmac_key_info', [Key, ctypes.POINTER(Info)], key, ctypes.byref(info))
        n.expect((info.extractable, info.length_bits, info.can_sign, info.can_verify) == (1, 160, 1, 1), 'HMAC metadata')
        hash_name, length = ctypes.create_string_buffer(64), I()
        probe.ok('hmac_key_hash', [Key, P, I, ctypes.POINTER(I)], key, hash_name, len(hash_name), ctypes.byref(length))
        n.expect(hash_name.raw[:length.value] == b'SHA-256', 'canonical hash name')
        raw = probe.start('hmac_export_raw', [P, Key], page.document, key)
        n.expect(probe.bytes(raw, page) == bytes([0x0b]) * 20, 'raw export round trip')
        message = span(b'Hi There')
        signed = probe.start('hmac_sign', [P, Key, Bytes], page.document, key, message)
        message.backing[0] = b'X'
        expected = bytes.fromhex('b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7')
        n.expect(probe.bytes(signed, page) == expected, 'RFC 4231 case 1 and invocation-time data copy')
        for signature, expected_valid in [(expected, 1), (bytes(32), 0)]:
            verified = probe.start('hmac_verify', [P, Key, Bytes, Bytes], page.document, key,
                                   span(signature), span(b'Hi There'))
            probe.wait(verified, page)
            n.expect(probe.error(verified) == '', 'verify has no rejection')
            valid = I()
            probe.ok('operation_boolean', [Operation, ctypes.POINTER(I)], verified, ctypes.byref(valid))
            n.expect(valid.value == expected_valid, 'signature verification, including mismatch=false')
        for options, expected_error in [
            (params(hash_name=b'SHA-224'), 'NotSupportedError'),
            (params(usages=(b'encrypt',)), 'SyntaxError'),
            (params(usages=(b'SIGN',)), 'TypeError'),
            (params(usages=()), 'SyntaxError'),
            (params(hash_name=b'unknown', usages=(b'encrypt',)), 'NotSupportedError'),
            (params(bits=0), 'DataError'),
            (params(bits=0, usages=(b'encrypt',)), 'DataError'),
        ]:
            operation = probe.start('hmac_import_raw', [P, ctypes.POINTER(Params), Bytes],
                                    page.document, ctypes.byref(options), span(b'secret'))
            probe.wait(operation, page)
            n.expect(probe.error(operation) == expected_error, expected_error)
        private = probe.import_key(page, params(extractable=False, usages=(b'sign',)))
        for name, arguments, values in [
            ('hmac_export_raw', [P, Key], (page.document, private)),
            ('hmac_verify', [P, Key, Bytes, Bytes], (page.document, private, span(expected), span(b'Hi There'))),
        ]:
            operation = probe.start(name, arguments, *values)
            probe.wait(operation, page)
            n.expect(probe.error(operation) == 'InvalidAccessError', 'extractability/usage enforced above backend')
        generated = probe.take(probe.start('hmac_generate', [P, ctypes.POINTER(Params)],
                                           page.document, ctypes.byref(params())), page)
        probe.ok('hmac_key_info', [Key, ctypes.POINTER(Info)], generated, ctypes.byref(info))
        n.expect(info.length_bits == 512, 'SHA-256 default HMAC key block length')
        in_flight = probe.start('hmac_sign', [P, Key, Bytes], page.document, generated, span(b'retained input key'))
        probe.ok('key_release', [Key], generated)
        del probe.keys[generated.value]
        n.expect(len(probe.bytes(in_flight, page)) == 32, 'operation retains input key after caller release')
        probe.ok('key_retain', [Key], key)
        probe.keys[key.value] = (key, 2)
        wrong_thread = []
        thread = threading.Thread(target=lambda: wrong_thread.append(probe.call('key_retain', [Key], key)))
        thread.start()
        thread.join()
        n.expect(wrong_thread == [-2], 'owning thread enforced')
        n.expect(probe.call('key_retain', [Key], Key(signed.value)) == -11, 'operation cannot masquerade as key')
        n.expect(probe.call('operation_ready', [Operation, ctypes.POINTER(I)], Operation(key.value), ctypes.byref(I())) == -11,
                 'key cannot masquerade as operation')
        abandoned = probe.start('hmac_generate', [P, ctypes.POINTER(Params)], page.document, ctypes.byref(params()))
        probe.ok('operation_release', [Operation], abandoned)
        del probe.operations[abandoned.value]
        n.call('rv_run_loop_cycle', [I], 10)
        n.expect(probe.call('operation_ready', [Operation, ctypes.POINTER(I)], abandoned, ctypes.byref(I())) == -10,
                 'released operation revokes pending delivery')
        pending = probe.start('hmac_sign', [P, Key, Bytes], page.document, key, span(b'pending'))
        page.close()
        page = None
        probe.wait(pending)
        n.expect(probe.error(pending) == 'AbortError', 'owner teardown terminates pending operation')
        page = Case(n, '<p>replacement owner</p>')
        retained = probe.start('hmac_sign', [P, Key, Bytes], page.document, key, span(b'Hi There'))
        n.expect(probe.bytes(retained, page) == expected, 'key survives document teardown and crosses live service contexts')
        partial = probe.import_key(page, params(bits=159))
        probe.ok('hmac_key_info', [Key, ctypes.POINTER(Info)], partial, ctypes.byref(info))
        n.expect(info.length_bits == 159, 'WebCrypto raw-import bit length is preserved')
        partial = probe.take(probe.start('hmac_generate', [P, ctypes.POINTER(Params)],
                                         page.document, ctypes.byref(params(bits=159))), page)
        probe.ok('hmac_key_info', [Key, ctypes.POINTER(Info)], partial, ctypes.byref(info))
        n.expect(info.length_bits == 159, 'WebCrypto generated bit length is preserved')
        return n.assertions
    finally:
        probe.close()
        if page:
            page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--bridge-library')
    arguments = parser.parse_args()
    print(f'SUBTLE_CRYPTO_HMAC PASS assertions={run(arguments.native_directory, arguments.bridge_library)}')
