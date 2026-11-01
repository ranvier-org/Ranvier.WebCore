"""Typed HKDF/PBKDF2 transport, dated WebCrypto validation and owning derivations."""

import argparse
import ctypes
import hashlib
import hmac
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from subtle_crypto_aes import AesProbe, AesInfo, HmacImport, ImportParams, KeyData, MISSING, Strings, algorithm, strings
from subtle_crypto_hmac import Native, Case, Key, Operation, Bytes, span, P, I

U = ctypes.c_uint32
U64 = ctypes.c_uint64
FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


class Hkdf(ctypes.Structure):
    _fields_ = [('size', U), ('hash_present', I), ('hash', Bytes), ('salt_present', I), ('salt', Bytes),
                ('info_present', I), ('info', Bytes)]


class Pbkdf2(ctypes.Structure):
    _fields_ = [('size', U), ('salt_present', I), ('salt', Bytes), ('iterations_present', I),
                ('iterations', U64), ('hash_present', I), ('hash', Bytes)]


class Kdf(ctypes.Structure):
    _fields_ = [('size', U), ('name', Bytes), ('hkdf', ctypes.POINTER(Hkdf)), ('pbkdf2', ctypes.POINTER(Pbkdf2))]


class Length(ctypes.Structure):
    _fields_ = [('present', I), ('bits', U64)]


class DerivedAes(ctypes.Structure):
    _fields_ = [('size', U), ('length_present', I), ('length_bits', U)]


class DerivedKey(ctypes.Structure):
    _fields_ = [('size', U), ('name', Bytes), ('aes', ctypes.POINTER(DerivedAes)), ('hmac', ctypes.POINTER(HmacImport))]


class KdfInfo(ctypes.Structure):
    _fields_ = [('size', U), ('extractable', I), ('can_derive_bits', I), ('can_derive_key', I)]


def parameters(name, hash_name=MISSING, salt=MISSING, info=MISSING, iterations=MISSING):
    name_bytes, hash_bytes = span(name.encode()), span(hash_name.encode() if hash_name is not MISSING else b'')
    salt_bytes, info_bytes = span(salt if salt is not MISSING else b''), span(info if info is not MISSING else b'')
    value = Kdf(ctypes.sizeof(Kdf), name_bytes, None, None)
    backing = [name_bytes, hash_bytes, salt_bytes, info_bytes]
    if name.upper() == 'HKDF':
        body = Hkdf(ctypes.sizeof(Hkdf), hash_name is not MISSING, hash_bytes, salt is not MISSING,
                    salt_bytes, info is not MISSING, info_bytes)
        value.hkdf = ctypes.pointer(body)
        backing.append(body)
    elif name.upper() == 'PBKDF2':
        body = Pbkdf2(ctypes.sizeof(Pbkdf2), salt is not MISSING, salt_bytes, iterations is not MISSING,
                      iterations if iterations is not MISSING else 0, hash_name is not MISSING, hash_bytes)
        value.pbkdf2 = ctypes.pointer(body)
        backing.append(body)
    value.backing = backing
    return value


def target(name, bits=MISSING, hash_name=MISSING):
    name_bytes = span(name.encode())
    value = DerivedKey(ctypes.sizeof(DerivedKey), name_bytes, None, None)
    backing = [name_bytes]
    if name.upper().startswith('AES-'):
        body = DerivedAes(ctypes.sizeof(DerivedAes), bits is not MISSING, bits if bits is not MISSING else 0)
        value.aes = ctypes.pointer(body)
        backing.append(body)
    elif name.upper() == 'HMAC':
        hash_bytes = span(hash_name.encode() if hash_name is not MISSING else b'')
        body = HmacImport(ctypes.sizeof(HmacImport), hash_name is not MISSING, hash_bytes,
                          bits is not MISSING, bits if bits is not MISSING else 0)
        value.hmac = ctypes.pointer(body)
        backing += [hash_bytes, body]
    value.backing = backing
    return value


def reference_hkdf(hash_name, key, salt, info, size):
    digest = hash_name.lower().replace('-', '')
    prk = hmac.digest(salt, key, digest)
    previous, output = b'', b''
    for block in range(1, (size + hashlib.new(digest).digest_size - 1) // hashlib.new(digest).digest_size + 1):
        previous = hmac.digest(prk, previous + info + bytes([block]), digest)
        output += previous
    return output[:size]


class KdfProbe(AesProbe):
    def bytes(self, operation, page):
        try:
            return super().bytes(operation, page)
        except AssertionError as error:
            if str(error) == 'successful byte result':
                raise AssertionError('byte result rejected with ' + self.error(operation)) from error
            raise

    def wait(self, operation, page=None):
        deadline, ready = time.monotonic() + 120, I()
        while time.monotonic() < deadline:
            status = self.call('operation_ready', [Operation, ctypes.POINTER(I)], operation, ctypes.byref(ready))
            if status:
                raise AssertionError(f'operation_ready status={status}')
            if ready.value:
                return
            if page:
                self.n.call('rv_host_update', [P], page.host)
            self.n.call('rv_run_loop_cycle', [I], 5)
        raise AssertionError('KDF operation timed out, including expensive RFC6070 scheduling')

    def base(self, page, name, raw=b'password', usages=('deriveBits', 'deriveKey')):
        return self.import_key(page, name, raw, usages=usages, extractable=False)

    def bits(self, page, key, options, bits=MISSING):
        length = Length(bits is not MISSING, bits if bits is not MISSING else 0)
        return self.start('kdf_derive_bits', [P, ctypes.POINTER(Kdf), Key, Length], page.document,
                          ctypes.byref(options), key, length)

    def derived_key(self, page, key, options, result, usages=('encrypt',), extractable=True):
        return self.start('kdf_derive_key', [P, ctypes.POINTER(Kdf), Key, ctypes.POINTER(DerivedKey), I, Strings],
                          page.document, ctypes.byref(options), key, ctypes.byref(result), extractable, strings(usages))


def check_vectors(probe, page):
    for case in json.loads((FIXTURES / 'crypto-hkdf-rfc5869.json').read_text())['vectors']:
        with probe.check('RFC5869 ' + case['case']):
            key = probe.base(page, 'hkdf', bytes.fromhex(case['ikm_hex']))
            salt = bytes.fromhex(case['salt_hex'] or '')
            options = parameters('HKDF', case['hash'], salt, bytes.fromhex(case['info_hex']))
            output = probe.bytes(probe.bits(page, key, options, case['l_octets'] * 8), page)
            probe.n.expect(output.hex() == case['okm_hex'], 'RFC salt omission maps to explicit empty WebCrypto salt')
    for case in json.loads((FIXTURES / 'crypto-pbkdf2-rfc6070.json').read_text())['vectors']:
        with probe.check('RFC6070 ' + str(case['case'])):
            key = probe.base(page, 'PBKDF2', bytes.fromhex(case['password_hex']))
            options = parameters('PBKDF2', 'SHA-1', bytes.fromhex(case['salt_hex']), iterations=case['iterations'])
            output = probe.bytes(probe.bits(page, key, options, case['dk_len_octets'] * 8), page)
            probe.n.expect(output.hex() == case['derived_key_hex'], 'all RFC6070 rows, including 16777216 iterations and embedded NUL')


def check_hashes_and_derived_keys(probe, page):
    raw, salt, info = b'input\0key', b'salt\0value', b'info\0value'
    for name in ['HKDF', 'PBKDF2']:
        key = probe.base(page, name, raw)
        for hash_name in ['SHA-1', 'SHA-256', 'SHA-384', 'SHA-512']:
            with probe.check(name + ' ' + hash_name):
                options = parameters(name, hash_name, salt, info, 3)
                expected = (reference_hkdf(hash_name, raw, salt, info, 32) if name == 'HKDF'
                            else hashlib.pbkdf2_hmac(hash_name.lower().replace('-', ''), raw, salt, 3, 32))
                probe.n.expect(probe.bytes(probe.bits(page, key, options, 256), page) == expected, 'independent standard-library KDF reference')
                for aes in ['AES-CBC', 'AES-CTR', 'AES-GCM', 'AES-KW']:
                    for bits in [128, 192, 256]:
                        with probe.check(f'{name}/{hash_name} -> {aes}{bits}'):
                            usages = ('wrapKey', 'unwrapKey') if aes == 'AES-KW' else ('encrypt', 'decrypt')
                            derived = probe.take(probe.derived_key(page, key, options, target(aes, bits), usages), page)
                            expected_key = probe.bytes(probe.bits(page, key, options, bits), page)
                            probe.n.expect(probe.bytes(probe.export(page, derived), page) == expected_key, 'deriveKey uses target length then raw import')
                            metadata = AesInfo(ctypes.sizeof(AesInfo))
                            probe.ok('aes_key_info', [Key, ctypes.POINTER(AesInfo)], derived, ctypes.byref(metadata))
                            cipher_usage = aes != 'AES-KW'
                            probe.n.expect((metadata.length_bits, metadata.extractable, metadata.can_encrypt, metadata.can_decrypt,
                                            metadata.can_wrap, metadata.can_unwrap) == (bits, 1, cipher_usage, cipher_usage, not cipher_usage, not cipher_usage),
                                           'derived AES length, extractability and exact usages')
                            buffer, size = ctypes.create_string_buffer(64), I()
                            probe.ok('key_algorithm_name', [Key, P, I, ctypes.POINTER(I)], derived, buffer, len(buffer), ctypes.byref(size))
                            probe.n.expect(buffer.raw[:size.value].decode() == aes, 'derived AES algorithm identity')
                for bits in [MISSING, 160]:
                    with probe.check(f'{name}/{hash_name} -> HMAC{bits is MISSING and "default" or bits}'):
                        derived = probe.take(probe.derived_key(page, key, options, target('HMAC', bits, hash_name), ('sign',)), page)
                        length = (512 if hash_name in ['SHA-1', 'SHA-256'] else 1024) if bits is MISSING else bits
                        probe.n.expect(probe.bytes(probe.export(page, derived), page) == probe.bytes(probe.bits(page, key, options, length), page), 'HMAC default block size or explicit byte length')
                independent = probe.take(probe.derived_key(page, key, options, target('HMAC', 256, 'SHA-512'), ('sign',)), page)
                material = probe.bytes(probe.export(page, independent), page)
                signature = probe.start('hmac_sign', [P, Key, Bytes], page.document, independent, span(b'derived metadata'))
                probe.n.expect(probe.bytes(signature, page) == hmac.digest(material, b'derived metadata', 'sha512'),
                               'derived HMAC hash is independent of derivation hash')
                private = probe.take(probe.derived_key(page, key, options, target('AES-GCM', 128), extractable=False), page)
                probe.error_is(page, probe.export(page, private), 'InvalidAccessError')
                for bits, error in [(159, 'OperationError'), (0, 'TypeError')]:
                    probe.error_is(page, probe.derived_key(page, key, options, target('HMAC', bits, hash_name), ('sign',)), error)


def check_empty_inputs(probe, page):
    for name in ['HKDF', 'PBKDF2']:
        for password in [b'', b'password']:
            for salt in [b'', b'salt']:
                for bits in [0, 8]:
                    with probe.check(f'{name} present input={password!r} salt={salt!r} bits={bits}'):
                        key = probe.base(page, name, password)
                        output = probe.bytes(probe.bits(page, key, parameters(name, 'SHA-256', salt, b'', 1), bits), page)
                        expected = (b'' if not bits else reference_hkdf('SHA-256', password, salt, b'', 1) if name == 'HKDF'
                                    else hashlib.pbkdf2_hmac('sha256', password, salt, 1, 1))
                        probe.n.expect(output == expected, 'present empty password/salt is valid and distinct from missing')


def check_validation(probe, page):
    for name in ['HKDF', 'PBKDF2']:
        key = probe.base(page, name)
        metadata = KdfInfo(ctypes.sizeof(KdfInfo))
        probe.ok('kdf_key_info', [Key, ctypes.POINTER(KdfInfo)], key, ctypes.byref(metadata))
        probe.n.expect((metadata.extractable, metadata.can_derive_bits, metadata.can_derive_key) == (0, 1, 1), 'KDF base key nonextractable metadata')
        for format in ['raw', 'jwk', 'spki', 'pkcs8']:
            probe.error_is(page, probe.export(page, key, format), 'NotSupportedError')
        probe.error_is(page, probe.imported(page, name, b'', usages=('deriveBits',), extractable=True), 'SyntaxError')
        probe.error_is(page, probe.imported(page, name, b'', usages=(), extractable=False), 'SyntaxError')
        probe.error_is(page, probe.imported(page, name, b'', usages=('encrypt',), extractable=False), 'SyntaxError')
        probe.error_is(page, probe.imported(page, name, {'kty': 'oct', 'k': 'AQ'}, format='jwk',
                                            usages=('encrypt',), extractable=True), 'NotSupportedError')
        options = parameters(name, 'SHA-256', b'salt', b'', 1)
        for length, error in [(MISSING, 'OperationError'), (1, 'OperationError'), (9, 'OperationError'), (2**32, 'TypeError')]:
            probe.error_is(page, probe.bits(page, key, options, length), error)
        probe.n.expect(probe.bytes(probe.bits(page, key, options, 0), page) == b'', 'zero length is an empty owning byte result')
        for invalid, error in [
            (parameters(name, salt=b'', info=b'', iterations=1), 'TypeError'),
            (parameters(name, 'SHA-256', info=b'', iterations=1), 'TypeError'),
            (parameters(name, 'SHA-224', b'', b'', 1), 'NotSupportedError'),
        ]:
            with probe.check(name + ' required/hash ' + error):
                probe.error_is(page, probe.bits(page, key, invalid, 128), error)
        only_key = probe.base(page, name, usages=('deriveKey',))
        probe.error_is(page, probe.bits(page, only_key, options, 128), 'InvalidAccessError')
        only_bits = probe.base(page, name, usages=('deriveBits',))
        probe.error_is(page, probe.derived_key(page, only_bits, options, target('AES-GCM', 128)), 'InvalidAccessError')
        for derived, error in [(target('AES-GCM'), 'TypeError'), (target('AES-GCM', 127), 'OperationError'),
                               (target('AES-GCM', 65536), 'TypeError'), (target('HMAC', 128), 'TypeError'),
                               (target('HKDF'), 'OperationError')]:
            with probe.check(name + ' derived target ' + error):
                probe.error_is(page, probe.derived_key(page, key, options, derived), error)
        probe.error_is(page, probe.derived_key(page, key, options, target('AES-GCM', 128), ('sign',)), 'SyntaxError')
        probe.error_is(page, probe.derived_key(page, key, options, target('AES-GCM', 128), ('bogus',)), 'TypeError')
    key = probe.base(page, 'HKDF')
    probe.error_is(page, probe.bits(page, key, parameters('HKDF', 'SHA-256', b''), 128), 'TypeError')
    probe.error_is(page, probe.bits(page, key, parameters('HKDF', 'SHA-256', b'', b''), 255 * 256 + 8), 'OperationError')
    with probe.check('HKDF exact maximum'):
        maximum = probe.bytes(probe.bits(page, key, parameters('HKDF', 'SHA-256', b'', b''), 255 * 256), page)
        probe.n.expect(maximum == reference_hkdf('SHA-256', b'password', b'', b'', 255 * 32), 'HKDF exact maximum and final counter block')
    key = probe.base(page, 'PBKDF2')
    for iterations, error in [(MISSING, 'TypeError'), (0, 'OperationError'), (2**32, 'TypeError'), (-1, 'TypeError')]:
        with probe.check('PBKDF2 iteration/range ' + str(iterations)):
            options = parameters('PBKDF2', 'SHA-256', b'', iterations=iterations)
            probe.error_is(page, probe.bits(page, key, options, 0), error)
    wrong = probe.import_key(page, 'AES-GCM', bytes(16))
    options = parameters('HKDF', 'SHA-256', b'', b'')
    for derived, error in [(target('AES-GCM', 127), 'InvalidAccessError'),
                           (target('AES-GCM', 65536), 'TypeError'),
                           (target('HMAC', 0, 'SHA-256'), 'InvalidAccessError'),
                           (target('HMAC', 159, 'SHA-256'), 'InvalidAccessError')]:
        with probe.check('derived normalization/key/length order ' + error):
            probe.error_is(page, probe.derived_key(page, wrong, options, derived), error)
    probe.error_is(page, probe.bits(page, wrong, parameters('HKDF', 'SHA-256', info=b''), 128), 'TypeError')
    probe.error_is(page, probe.bits(page, wrong, parameters('HKDF', 'SHA-224', b'', b''), 128), 'NotSupportedError')
    probe.error_is(page, probe.bits(page, wrong, parameters('unknown'), 2**32), 'TypeError')


def check_lifetime(probe):
    page = Case(probe.n, '<p>KDF lifetime owner</p>')
    try:
        raw = b'password before mutation'
        source = span(raw)
        data, options = KeyData(ctypes.sizeof(KeyData), 1, source, None), algorithm('HKDF')
        operation = probe.start('secret_import', [P, Bytes, ctypes.POINTER(KeyData), ctypes.POINTER(ImportParams), I, Strings],
                                page.document, span(b'raw'), ctypes.byref(data), ctypes.byref(options), 0, strings(('deriveBits', 'deriveKey')))
        source.backing[0] = b'X'
        key = probe.take(operation, page)
        options = parameters('HKDF', 'SHA-256', b'salt', b'info')
        operation = probe.bits(page, key, options, 256)
        options.backing[2].backing[0], options.backing[3].backing[0] = b'X', b'X'
        expected = reference_hkdf('SHA-256', raw, b'salt', b'info', 32)
        probe.n.expect(probe.bytes(operation, page) == expected, 'password/salt/info copied before admission returns')
        derived = target('HMAC', 256, 'SHA-512')
        operation = probe.derived_key(page, key, parameters('HKDF', 'SHA-256', b'salt', b'info'), derived, ('sign',))
        derived.backing[1].backing[0] = b'X'
        derived_key = probe.take(operation, page)
        signature = probe.start('hmac_sign', [P, Key, Bytes], page.document, derived_key, span(b'copied target'))
        probe.n.expect(probe.bytes(signature, page) == hmac.digest(expected, b'copied target', 'sha512'), 'derived import parameters copied before return')
        retained = probe.base(page, 'HKDF', raw)
        operation = probe.bits(page, retained, parameters('HKDF', 'SHA-256', b'salt', b'info'), 256)
        probe.ok('key_release', [Key], retained)
        del probe.keys[retained.value]
        probe.n.expect(probe.bytes(operation, page) == expected, 'worker retains released base key')
        operation = probe.bits(page, key, parameters('HKDF', 'SHA-256', b'salt', b'info'), 256)
        probe.ok('operation_release', [Operation], operation)
        del probe.operations[operation.value]
        probe.n.call('rv_run_loop_cycle', [I], 10)
        probe.n.expect(probe.call('operation_ready', [Operation, ctypes.POINTER(I)], operation, ctypes.byref(I())) == -10, 'derivation cancellation revokes result')
        pending = probe.bits(page, key, parameters('HKDF', 'SHA-256', b'salt', b'info'), 256)
        page.close()
        page = None
        probe.wait(pending)
        probe.n.expect(probe.error(pending) == 'AbortError', 'KDF owner teardown terminates pending result')
        page = Case(probe.n, '<p>KDF replacement owner</p>')
        probe.n.expect(probe.bytes(probe.bits(page, key, parameters('HKDF', 'SHA-256', b'salt', b'info'), 256), page) == expected,
                       'base key crosses document lifetime safely')
    finally:
        if page:
            page.close()


def run(directory, bridge_library=None):
    n = Native(directory)
    probe = KdfProbe(n, ctypes.CDLL(bridge_library) if bridge_library else n.library)
    page = Case(n, '<p>KDF owner</p>')
    try:
        for name in ['HKDF', 'PBKDF2']:
            supported = I()
            probe.ok('kdf_supported', [P, Bytes, ctypes.POINTER(I)], page.document, span(name.encode()), ctypes.byref(supported))
            n.expect(supported.value == 1, name + ' registered')
        for group in [check_vectors, check_hashes_and_derived_keys, check_empty_inputs, check_validation]:
            with probe.check(group.__name__):
                group(probe, page)
        with probe.check('check_lifetime'):
            check_lifetime(probe)
        if probe.failures:
            raise AssertionError(f'{len(probe.failures)} independent KDF cases failed')
        return n.assertions
    except BaseException:
        print(f'SUBTLE_CRYPTO_KDF FAIL assertions={n.assertions} cases={len(probe.failures)}', flush=True)
        raise
    finally:
        probe.close()
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--bridge-library')
    arguments = parser.parse_args()
    print(f'SUBTLE_CRYPTO_KDF PASS assertions={run(arguments.native_directory, arguments.bridge_library)}')
