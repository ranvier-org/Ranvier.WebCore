"""Typed generic import and cross-family wrapping through the private transport."""

import argparse
import ctypes as C
import hashlib
import hmac
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from subtle_crypto_aes import AesProbe, Cipher, HmacImport, MISSING, algorithm, cipher, strings
from subtle_crypto_asymmetric import Jwk, JwkInput, KeyData, KeyParams, OaepParams, read_jwk
from subtle_crypto_hmac import Native, Case, Key, Operation, Bytes, Strings, span, P, I


class ImportParams(C.Structure):
    _fields_ = [('size', C.c_uint32), ('name', Bytes), ('hmac', C.POINTER(HmacImport)), ('asymmetric', C.POINTER(KeyParams))]


class WrappingParams(C.Structure):
    _fields_ = [('size', C.c_uint32), ('name', Bytes), ('aes', C.POINTER(Cipher)), ('oaep', C.POINTER(OaepParams))]


def import_params(name, hash_name=MISSING, bits=MISSING, asymmetric=None):
    secret = algorithm(name, hash_name, bits)
    value = ImportParams(C.sizeof(ImportParams), secret.name, secret.hmac, C.pointer(asymmetric) if asymmetric else None)
    value.backing = (secret, asymmetric)
    return value


def wrapping_params(name, aes=None, oaep=None):
    name_bytes = span(name.encode())
    value = WrappingParams(C.sizeof(WrappingParams), name_bytes, C.pointer(aes) if aes else None, C.pointer(oaep) if oaep else None)
    value.backing = (name_bytes, aes, oaep)
    return value


class GeneralProbe(AesProbe):
    def imported_general(self, page, options, data, *, format='raw', usages=('encrypt',), extractable=True):
        if isinstance(data, dict):
            owner = JwkInput(data)
            value = KeyData(C.sizeof(KeyData), 0, Bytes(), C.pointer(owner.value))
        else:
            owner = span(data)
            value = KeyData(C.sizeof(KeyData), 1, owner, None)
        return self.start('key_import', [P, Bytes, C.POINTER(KeyData), C.POINTER(ImportParams), I, Strings],
            page.document, span(format.encode()), C.byref(value), C.byref(options), extractable, strings(usages))

    def wrap_general(self, page, key, wrapping, options, format='raw'):
        return self.start('key_wrap', [P, Bytes, Key, Key, C.POINTER(WrappingParams)],
            page.document, span(format.encode()), key, wrapping, C.byref(options))

    def unwrap_general(self, page, data, unwrapping, options, target, *, format='raw', usages=('encrypt',), extractable=True):
        return self.start('key_unwrap', [P, Bytes, Bytes, Key, C.POINTER(WrappingParams), C.POINTER(ImportParams), I, Strings],
            page.document, span(format.encode()), span(data), unwrapping, C.byref(options), C.byref(target), extractable, strings(usages))

    def full_jwk(self, page, key):
        operation = self.export(page, key, 'jwk')
        self.wait(operation, page)
        self.n.expect(self.error(operation) == '', 'full JWK export succeeds')
        value = Jwk(C.sizeof(Jwk))
        self.ok('operation_jwk', [Operation, C.POINTER(Jwk)], operation, C.byref(value))
        return read_jwk(value)


def run(directory, bridge_library=None, report=None):
    n = Native(directory)
    library = C.CDLL(bridge_library) if bridge_library else n.library
    missing = [name for name in ['key_import', 'key_wrap', 'key_unwrap', 'operation_jwk']
               if not hasattr(library, 'ranvier_crypto_' + name)]
    assert not missing, 'Missing generic transport: ' + ', '.join(missing)
    probe = GeneralProbe(n, library)
    page = Case(n, '<p>generic key owner</p>')
    try:
        for mode in ['AES-CBC', 'AES-CTR', 'AES-GCM', 'AES-KW']:
            for size in [16, 24, 32]:
                with probe.check('generic import ' + mode + str(size)):
                    usages = ('wrapKey',) if mode == 'AES-KW' else ('encrypt',)
                    raw = bytes(range(size))
                    key = probe.take(probe.imported_general(page, import_params(mode.lower()), raw, usages=usages), page)
                    n.expect(probe.bytes(probe.export(page, key), page) == raw, 'generic raw AES import preserves all key sizes')
                    jwk = probe.full_jwk(page, key)
                    restored = probe.take(probe.imported_general(page, import_params(mode), jwk, format='jwk', usages=usages), page)
                    n.expect(probe.full_jwk(page, restored) == jwk, 'complete generic JWK round trip')
        for hash_name in ['SHA-1', 'SHA-256', 'SHA-384', 'SHA-512']:
            with probe.check('generic HMAC ' + hash_name):
                raw = bytes(range(24))
                key = probe.take(probe.imported_general(page, import_params('HMAC', hash_name), raw, usages=('sign',)), page)
                output = probe.bytes(probe.start('hmac_sign', [P, Key, Bytes], page.document, key, span(b'generic target')), page)
                n.expect(output == hmac.digest(raw, b'generic target', hash_name.lower().replace('-', '')), 'generic HMAC retains hash metadata')
        target = probe.take(probe.imported_general(page, import_params('AES-GCM'), bytes(range(16))), page)
        for mode, body in [('AES-CBC', cipher('AES-CBC', bytes(16))),
                           ('AES-CTR', cipher('AES-CTR', bytes(16), ctr_bits=64)),
                           ('AES-GCM', cipher('AES-GCM', bytes(12), aad=b'copied metadata', tag=128)),
                           ('AES-KW', cipher('AES-KW'))]:
            with probe.check('generic wrap ' + mode):
                wrapping = probe.take(probe.imported_general(page, import_params(mode), bytes(range(32)), usages=('wrapKey', 'unwrapKey')), page)
                options = wrapping_params(mode.lower(), aes=body)
                wrapped = probe.bytes(probe.wrap_general(page, target, wrapping, options), page)
                restored = probe.take(probe.unwrap_general(page, wrapped, wrapping, options, import_params('AES-GCM')), page)
                n.expect(probe.bytes(probe.export(page, restored), page) == bytes(range(16)), 'generic mode wraps with wrap permission without encrypt permission')
        with probe.check('generic cross-family JWK wrap'):
            raw = bytes(range(24))
            key = probe.take(probe.imported_general(page, import_params('HMAC', 'SHA-512'), raw, usages=('sign',)), page)
            wrapping = probe.take(probe.imported_general(page, import_params('AES-CBC'), bytes(32), usages=('wrapKey', 'unwrapKey')), page)
            options = wrapping_params('AES-CBC', aes=cipher('AES-CBC', bytes(16)))
            wrapped = probe.bytes(probe.wrap_general(page, key, wrapping, options, 'jwk'), page)
            restored = probe.take(probe.unwrap_general(page, wrapped, wrapping, options, import_params('HMAC', 'SHA-512'), format='jwk', usages=('sign',)), page)
            n.expect(probe.full_jwk(page, restored) == probe.full_jwk(page, key), 'generic JWK codec preserves secret hash/usages/ext')
        for options, format, expected in [(import_params('unknown-import'), 'jwk', 'NotSupportedError'),
                                          (import_params('AES-GCM'), 'jwk', 'TypeError'),
                                          (import_params('HMAC', 'SHA-256', 0), 'raw', 'DataError')]:
            with probe.check('generic error order ' + expected):
                probe.error_is(page, probe.imported_general(page, options, bytes(16), format=format), expected)
        with probe.check('generic retained wrapping keys'):
            raw, wrapping_raw = bytes(range(16)), bytes(range(32))
            key = probe.take(probe.imported_general(page, import_params('AES-GCM'), raw), page)
            wrapping = probe.take(probe.imported_general(page, import_params('AES-CBC'), wrapping_raw, usages=('wrapKey',)), page)
            options = wrapping_params('AES-CBC', aes=cipher('AES-CBC', bytes(16)))
            operation = probe.wrap_general(page, key, wrapping, options)
            for owned in [key, wrapping]:
                probe.ok('key_release', [Key], owned)
                del probe.keys[owned.value]
            output = probe.bytes(operation, page)
            replacement = probe.take(probe.imported_general(page, import_params('AES-CBC'), wrapping_raw, usages=('unwrapKey',)), page)
            restored = probe.take(probe.unwrap_general(page, output, replacement, options, import_params('AES-GCM')), page)
            n.expect(probe.bytes(probe.export(page, restored), page) == raw, 'in-flight stages retain both keys after caller release')
        with probe.check('generic copied admission buffers'):
            raw = span(bytes(range(16)))
            options = import_params('AES-GCM')
            value = KeyData(C.sizeof(KeyData), 1, raw, None)
            operation = probe.start('key_import', [P, Bytes, C.POINTER(KeyData), C.POINTER(ImportParams), I, Strings],
                page.document, span(b'raw'), C.byref(value), C.byref(options), 1, strings(('encrypt',)))
            C.memset(raw.data, 0xDD, raw.length)
            C.memset(options.name.data, ord('X'), options.name.length)
            restored = probe.take(operation, page)
            n.expect(probe.bytes(probe.export(page, restored), page) == bytes(range(16)), 'generic import owns bytes and normalized parameters before return')
        with probe.check('generic extractability and unsupported export ordering'):
            wrapping = probe.take(probe.imported_general(page, import_params('AES-CBC'), bytes(32), usages=('wrapKey',)), page)
            options = wrapping_params('AES-CBC', aes=cipher('AES-CBC', bytes(16)))
            hidden = probe.take(probe.imported_general(page, import_params('AES-GCM'), bytes(16), extractable=False), page)
            probe.error_is(page, probe.wrap_general(page, hidden, wrapping, options), 'InvalidAccessError')
            kdf = probe.take(probe.imported_general(page, import_params('HKDF'), b'base', usages=('deriveBits',), extractable=False), page)
            probe.error_is(page, probe.wrap_general(page, kdf, wrapping, options), 'NotSupportedError')
        with probe.check('generic cancellation'):
            operation = probe.imported_general(page, import_params('AES-GCM'), bytes(16))
            probe.ok('operation_release', [Operation], operation)
            del probe.operations[operation.value]
            n.call('rv_run_loop_cycle', [I], 5)
            n.expect(probe.call('operation_ready', [Operation, C.POINTER(I)], operation, C.byref(I())) == -10,
                     'released generic operation cannot deliver a result')
        with probe.check('generic owner teardown'):
            retired = Case(n, '<p>retired wrapping owner</p>')
            try:
                key = probe.take(probe.imported_general(page, import_params('AES-GCM'), bytes(16)), page)
                wrapping = probe.take(probe.imported_general(page, import_params('AES-CBC'), bytes(32), usages=('wrapKey',)), page)
                options = wrapping_params('AES-CBC', aes=cipher('AES-CBC', bytes(16)))
                operation = probe.wrap_general(retired, key, wrapping, options)
                retired.close()
                retired = None
                probe.wait(operation)
                n.expect(probe.error(operation) == 'AbortError', 'owner teardown aborts a generic wrapping chain')
            finally:
                if retired:
                    retired.close()
        if probe.failures:
            raise AssertionError(f'{len(probe.failures)} independent generic crypto groups failed')
        return n.assertions
    finally:
        if report:
            Path(report).write_text(json.dumps({'assertions': n.assertions, 'failures': probe.failures}, indent=2) + '\n')
        probe.close()
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--bridge-library')
    parser.add_argument('--report')
    args = parser.parse_args()
    print(f'SUBTLE_CRYPTO_GENERAL PASS assertions={run(args.native_directory, args.bridge_library, args.report)}')
