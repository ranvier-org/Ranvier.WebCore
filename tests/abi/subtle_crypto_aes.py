"""AES transport vectors, typed JWK, validation ordering and owning operation results."""

import argparse
import base64
import ctypes
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from subtle_crypto_hmac import Native, Case, Probe, Key, Operation, Bytes, Strings, span, P, I

U = ctypes.c_uint32
MISSING = object()
FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


class OptionalString(ctypes.Structure):
    _fields_ = [('present', I), ('value', Bytes)]


class OptionalStrings(ctypes.Structure):
    _fields_ = [('present', I), ('value', Strings)]


class KeyGen(ctypes.Structure):
    _fields_ = [('size', U), ('name', Bytes), ('length_present', I), ('length_bits', U)]


class Cbc(ctypes.Structure):
    _fields_ = [('size', U), ('iv_present', I), ('iv', Bytes)]


class Ctr(ctypes.Structure):
    _fields_ = [('size', U), ('counter_present', I), ('counter', Bytes), ('length_present', I), ('length_bits', U)]


class Gcm(ctypes.Structure):
    _fields_ = [('size', U), ('iv_present', I), ('iv', Bytes), ('additional_data_present', I),
                ('additional_data', Bytes), ('tag_length_present', I), ('tag_length_bits', U)]


class Cipher(ctypes.Structure):
    _fields_ = [('size', U), ('name', Bytes), ('cbc', ctypes.POINTER(Cbc)),
                ('ctr', ctypes.POINTER(Ctr)), ('gcm', ctypes.POINTER(Gcm))]


class Jwk(ctypes.Structure):
    _fields_ = [('size', U), ('kty', OptionalString), ('k', OptionalString), ('alg', OptionalString),
                ('use', OptionalString), ('key_ops', OptionalStrings), ('ext_present', I), ('ext', I)]


class KeyData(ctypes.Structure):
    _fields_ = [('size', U), ('raw_present', I), ('raw', Bytes), ('jwk', ctypes.POINTER(Jwk))]


class HmacImport(ctypes.Structure):
    _fields_ = [('size', U), ('hash_present', I), ('hash', Bytes), ('length_present', I), ('length_bits', U)]


class ImportParams(ctypes.Structure):
    _fields_ = [('size', U), ('name', Bytes), ('hmac', ctypes.POINTER(HmacImport))]


class AesInfo(ctypes.Structure):
    _fields_ = [('size', U), ('extractable', I), ('length_bits', ctypes.c_uint64), ('can_encrypt', I),
                ('can_decrypt', I), ('can_wrap', I), ('can_unwrap', I)]


def strings(values):
    entries = [span(value.encode()) for value in values]
    array = (Bytes * len(entries))(*entries)
    result = Strings(array, len(entries))
    result.backing = (entries, array)
    return result


def algorithm(name, hash_name=MISSING, bits=MISSING):
    name_bytes = span(name.encode())
    result = ImportParams(ctypes.sizeof(ImportParams), name_bytes, None)
    backing = [name_bytes]
    if hash_name is not MISSING:
        hash_bytes = span(hash_name.encode())
        hmac = HmacImport(ctypes.sizeof(HmacImport), 1, hash_bytes, bits is not MISSING, bits if bits is not MISSING else 0)
        result.hmac = ctypes.pointer(hmac)
        backing += [hash_bytes, hmac]
    result.backing = backing
    return result


def cipher(name, iv=MISSING, ctr_bits=MISSING, aad=MISSING, tag=MISSING):
    name_bytes = span(name.encode())
    iv_bytes = span(iv if iv is not MISSING else b'')
    result = Cipher(ctypes.sizeof(Cipher), name_bytes, None, None, None)
    backing = [name_bytes, iv_bytes]
    if name.upper() == 'AES-CBC':
        body = Cbc(ctypes.sizeof(Cbc), iv is not MISSING, iv_bytes)
        result.cbc = ctypes.pointer(body)
        backing.append(body)
    elif name.upper() == 'AES-CTR':
        body = Ctr(ctypes.sizeof(Ctr), iv is not MISSING, iv_bytes,
                   ctr_bits is not MISSING, ctr_bits if ctr_bits is not MISSING else 0)
        result.ctr = ctypes.pointer(body)
        backing.append(body)
    elif name.upper() == 'AES-GCM':
        aad_bytes = span(aad if aad is not MISSING else b'')
        body = Gcm(ctypes.sizeof(Gcm), iv is not MISSING, iv_bytes, aad is not MISSING, aad_bytes,
                   tag is not MISSING, tag if tag is not MISSING else 0)
        result.gcm = ctypes.pointer(body)
        backing += [body, aad_bytes]
    result.backing = backing
    return result


def jwk(values):
    result = Jwk(ctypes.sizeof(Jwk))
    backing = []
    for field in ['kty', 'k', 'alg', 'use']:
        if field in values:
            value = span(values[field].encode())
            setattr(result, field, OptionalString(1, value))
            backing.append(value)
    if 'key_ops' in values:
        usage = strings(values['key_ops'])
        result.key_ops = OptionalStrings(1, usage)
        backing.append(usage)
    if 'ext' in values:
        result.ext_present, result.ext = 1, values['ext']
    result.backing = backing
    return result


def key_data(value):
    if isinstance(value, dict) or isinstance(value, Jwk):
        body = jwk(value) if isinstance(value, dict) else value
        result = KeyData(ctypes.sizeof(KeyData), 0, Bytes(), ctypes.pointer(body))
    else:
        body = span(value)
        result = KeyData(ctypes.sizeof(KeyData), 1, body, None)
    result.backing = body
    return result


def snapshot(value):
    result = {}
    for field in ['kty', 'k', 'alg', 'use']:
        item = getattr(value, field)
        if item.present:
            result[field] = ctypes.string_at(item.value.data, item.value.length).decode()
    if value.key_ops.present:
        result['key_ops'] = [ctypes.string_at(item.data, item.length).decode()
                             for item in value.key_ops.value.items[:value.key_ops.value.count]]
    if value.ext_present:
        result['ext'] = bool(value.ext)
    return result


class AesProbe(Probe):
    def __init__(self, *arguments):
        super().__init__(*arguments)
        self.failures = []

    @contextmanager
    def check(self, name):
        try:
            yield
        except AssertionError as error:
            self.failures.append({'case': name, 'error': str(error)})
            print('AES_CASE_FAIL ' + json.dumps(self.failures[-1]), flush=True)

    def generate(self, page, name, bits=MISSING, usages=('encrypt', 'decrypt'), extractable=True):
        parameters = KeyGen(ctypes.sizeof(KeyGen), span(name.encode()), bits is not MISSING, bits if bits is not MISSING else 0)
        return self.start('aes_generate', [P, ctypes.POINTER(KeyGen), I, Strings], page.document,
                          ctypes.byref(parameters), extractable, strings(usages))

    def bytes(self, operation, page):
        self.wait(operation, page)
        self.n.expect(self.error(operation) == '', 'successful byte result')
        length = I()
        status = self.call('operation_bytes', [Operation, P, I, ctypes.POINTER(I)], operation, None, 0, ctypes.byref(length))
        self.n.expect(status == (-6 if length.value else 0), 'byte result capacity query')
        buffer = (ctypes.c_uint8 * length.value)()
        self.ok('operation_bytes', [Operation, P, I, ctypes.POINTER(I)], operation, buffer, length.value, ctypes.byref(length))
        return bytes(buffer)

    def imported(self, page, name, data, usages=('encrypt', 'decrypt', 'wrapKey', 'unwrapKey'), extractable=True, format='raw', options=None):
        data, options, usages = key_data(data), options or algorithm(name), strings(usages)
        return self.start('secret_import', [P, Bytes, ctypes.POINTER(KeyData), ctypes.POINTER(ImportParams), I, Strings],
                          page.document, span(format.encode()), ctypes.byref(data), ctypes.byref(options), extractable, usages)

    def import_key(self, page, name, data, **options):
        return self.take(self.imported(page, name, data, **options), page)

    def export(self, page, key, format='raw'):
        return self.start('key_export', [P, Bytes, Key], page.document, span(format.encode()), key)

    def transform(self, page, name, key, parameters, data):
        return self.start('aes_' + name, [P, ctypes.POINTER(Cipher), Key, Bytes], page.document,
                          ctypes.byref(parameters), key, span(data))

    def error_is(self, page, operation, expected):
        self.wait(operation, page)
        actual = self.error(operation)
        self.n.expect(actual == expected, f'expected {expected}, actual {actual!r}')

    def wrap(self, page, key, wrapping, parameters, format='raw'):
        return self.start('aes_wrap', [P, Bytes, Key, Key, ctypes.POINTER(Cipher)], page.document,
                          span(format.encode()), key, wrapping, ctypes.byref(parameters))

    def unwrap(self, page, wrapped, wrapping, parameters, name='AES-GCM', format='raw', usages=('encrypt',), options=None):
        options = options or algorithm(name)
        return self.start('aes_unwrap', [P, Bytes, Bytes, Key, ctypes.POINTER(Cipher), ctypes.POINTER(ImportParams), I, Strings],
                          page.document, span(format.encode()), span(wrapped), wrapping, ctypes.byref(parameters),
                          ctypes.byref(options), 1, strings(usages))


def check_generation(probe, page):
    n = probe.n
    for name in ['AES-CBC', 'AES-CTR', 'AES-GCM', 'AES-KW']:
        with probe.check(f'generation line224: {name!r}'):
            supported = I()
            probe.ok('aes_supported', [P, Bytes, ctypes.POINTER(I)], page.document, span(name.encode()), ctypes.byref(supported))
            n.expect(supported.value == 1, name + ' registered')
            usages = ('wrapKey', 'unwrapKey') if name == 'AES-KW' else ('encrypt', 'decrypt')
            for bits in [128, 192, 256]:
                with probe.check(f'generation line229: {bits!r}'):
                    generated = probe.take(probe.generate(page, name.lower(), bits, usages), page)
                    n.expect(len(probe.bytes(probe.export(page, generated), page)) * 8 == bits, 'generated AES key length')
            for bits, error in [(MISSING, 'TypeError'), (65536, 'TypeError'), (0, 'OperationError'), (127, 'OperationError')]:
                with probe.check(f'generation line232: {(bits, error)!r}'):
                    probe.error_is(page, probe.generate(page, name, bits, usages), error)
            probe.error_is(page, probe.generate(page, name, 128, ()), 'SyntaxError')
            probe.error_is(page, probe.generate(page, name, 128, ('sign',)), 'SyntaxError')

def check_vectors(probe, page):
    n = probe.n
    cases = json.loads((FIXTURES / 'crypto-aes-cbc-ctr-sp800-38a.json').read_text())
    plain = bytes.fromhex(''.join(cases['message_blocks_hex']))
    for case in cases['vectors']:
        with probe.check(f'vectors line238: {case!r}'):
            name = 'AES-' + case['mode']
            key = probe.import_key(page, name.lower(), bytes.fromhex(case['key_hex']))
            initial = case.get('iv_hex', case.get('initial_counter_hex'))
            parameters = cipher(name, bytes.fromhex(initial), ctr_bits=case.get('counter_field_bits', 128))
            encrypted = probe.bytes(probe.transform(page, 'encrypt', key, parameters, plain), page)
            expected = bytes.fromhex(''.join(case['ciphertext_blocks_hex']))
            n.expect(encrypted[:len(expected)] == expected, case['example_id'])
            n.expect(len(encrypted) == len(plain) + (16 if case['mode'] == 'CBC' else 0), 'CBC PKCS7 / CTR exact length')
            n.expect(probe.bytes(probe.transform(page, 'decrypt', key, parameters, encrypted), page) == plain, 'mode decrypt round trip')
            if case['mode'] == 'CBC':
                probe.error_is(page, probe.transform(page, 'decrypt', key, parameters, expected), 'OperationError')
    first_cbc = next((case for case in cases['vectors'] if case['mode'] == 'CBC'))
    cbc_key = probe.import_key(page, 'AES-CBC', bytes.fromhex(first_cbc['key_hex']))
    first_block, original_iv = (bytes.fromhex(first_cbc['ciphertext_blocks_hex'][0]), bytes.fromhex(first_cbc['iv_hex']))
    first_plain = plain[:16]
    for padding in [0, 1, 2, 17]:
        with probe.check(f'vectors line254: {padding!r}'):
            changed_iv = bytearray(original_iv)
            for index in range(1, (padding if 0 < padding <= 16 else 1) + 1):
                with probe.check(f'vectors line256: {index!r}'):
                    changed_iv[-index] ^= first_plain[-index] ^ padding
            operation = probe.transform(page, 'decrypt', cbc_key, cipher('AES-CBC', bytes(changed_iv)), first_block)
            if padding in [0, 17]:
                probe.error_is(page, operation, 'OperationError')
            else:
                n.expect(probe.bytes(operation, page) == first_plain[:-padding], 'CBC validates and removes PKCS7 padding')
    for case in json.loads((FIXTURES / 'crypto-aes-gcm-cavp.json').read_text())['vectors']:
        with probe.check(f'vectors line263: {case!r}'):
            data, expected, group = (case['input'], case['expected'], case['source']['group'])
            key = probe.import_key(page, 'AES-GCM', bytes.fromhex(data['Key']))
            parameters = cipher('AES-GCM', bytes.fromhex(data['IV']), aad=bytes.fromhex(data['AAD']), tag=group['Taglen'])
            if case['operation'] == 'encrypt':
                encrypted = probe.bytes(probe.transform(page, 'encrypt', key, parameters, bytes.fromhex(data['PT'])), page)
                n.expect(encrypted.hex() == expected['CT'] + expected['Tag'], 'NIST GCM ciphertext plus tag')
                n.expect(probe.bytes(probe.transform(page, 'decrypt', key, parameters, encrypted), page).hex() == data['PT'], 'NIST GCM decrypt')
            else:
                encrypted = bytes.fromhex(data['CT'] + data['Tag'])
                operation = probe.transform(page, 'decrypt', key, parameters, encrypted)
                if expected.get('result') == 'FAIL':
                    probe.error_is(page, operation, 'OperationError')
                else:
                    n.expect(probe.bytes(operation, page).hex() == expected['PT'], 'NIST GCM decrypt vector')
    for case in json.loads((FIXTURES / 'crypto-aes-kw-rfc3394.json').read_text())['vectors']:
        with probe.check(f'vectors line278: {case!r}'):
            wrapping = probe.import_key(page, 'AES-KW', bytes.fromhex(case['kek_hex']), usages=('wrapKey', 'unwrapKey'))
            key = probe.import_key(page, 'AES-GCM', bytes.fromhex(case['key_data_hex']))
            wrapped = probe.bytes(probe.wrap(page, key, wrapping, cipher('AES-KW')), page)
            n.expect(wrapped.hex() == case['ciphertext_hex'], 'RFC3394 case ' + case['case'])
            restored = probe.take(probe.unwrap(page, wrapped, wrapping, cipher('AES-KW')), page)
            n.expect(probe.bytes(probe.export(page, restored), page).hex() == case['key_data_hex'], 'KW unwrap raw key')
            probe.error_is(page, probe.transform(page, 'encrypt', wrapping, cipher('AES-KW'), bytes(16)), 'NotSupportedError')

def check_jwk(probe, page):
    n = probe.n
    raw = bytes(range(16))
    key = probe.import_key(page, 'AES-GCM', raw)
    info = AesInfo(ctypes.sizeof(AesInfo))
    probe.ok('aes_key_info', [Key, ctypes.POINTER(AesInfo)], key, ctypes.byref(info))
    n.expect((info.length_bits, info.extractable, info.can_encrypt, info.can_decrypt, info.can_wrap, info.can_unwrap) == (128, 1, 1, 1, 1, 1), 'AES immutable metadata')
    for function, expected in [('key_algorithm_name', b'AES-GCM'), ('key_type', b'secret')]:
        with probe.check(f'jwk line293: {(function, expected)!r}'):
            buffer, length = (ctypes.create_string_buffer(64), I())
            probe.ok(function, [Key, P, I, ctypes.POINTER(I)], key, buffer, len(buffer), ctypes.byref(length))
            n.expect(buffer.raw[:length.value] == expected, 'canonical ' + function)
    exported = probe.export(page, key, 'jwk')
    probe.wait(exported, page)
    view = Jwk(ctypes.sizeof(Jwk))
    probe.ok('operation_octet_jwk', [Operation, ctypes.POINTER(Jwk)], exported, ctypes.byref(view))
    fields = snapshot(view)
    n.expect(fields['kty'] == 'oct' and fields['alg'] == 'A128GCM' and fields['ext'], 'typed JWK export')
    imported = probe.imported(page, 'AES-GCM', view, format='jwk')
    probe.ok('operation_release', [Operation], exported)
    del probe.operations[exported.value]
    restored = probe.take(imported, page)
    n.expect(probe.bytes(probe.export(page, restored), page) == raw, 'JWK snapshot copied before source operation release')
    basic = {'kty': 'oct', 'k': base64.urlsafe_b64encode(raw).decode().rstrip('=')}
    for changes, expected in [({'kty': ''}, 'DataError'), ({'kty': 'OCT'}, 'DataError'), ({'k': ''}, 'DataError'), ({'alg': 'a128gcm'}, 'DataError'), ({'alg': 'A256GCM'}, 'DataError'), ({'use': ''}, 'DataError'), ({'use': 'sig'}, 'DataError'), ({'ext': False}, 'DataError'), ({'key_ops': []}, 'DataError'), ({'key_ops': ['encrypt', 'encrypt']}, 'DataError'), ({'key_ops': ['bogus']}, 'DataError'), ({'key_ops': ['bogus', 'bogus', 'encrypt']}, 'DataError')]:
        with probe.check(f'jwk line309: {(changes, expected)!r}'):
            probe.error_is(page, probe.imported(page, 'AES-GCM', {**basic, **changes}, format='jwk', usages=('encrypt',)), expected)
    private = probe.import_key(page, 'AES-GCM', {**basic, 'ext': False}, format='jwk', extractable=False, usages=('encrypt',))
    probe.error_is(page, probe.export(page, private), 'InvalidAccessError')
    probe.error_is(page, probe.export(page, private, 'spki'), 'InvalidAccessError')
    probe.error_is(page, probe.imported(page, 'AES-GCM', b'', usages=('encrypt',)), 'DataError')
    probe.error_is(page, probe.imported(page, 'unknown', raw, usages=('encrypt',)), 'NotSupportedError')
    probe.error_is(page, probe.imported(page, 'AES-GCM', raw, usages=('sign',)), 'SyntaxError')
    probe.error_is(page, probe.imported(page, 'AES-GCM', raw, usages=()), 'SyntaxError')
    probe.error_is(page, probe.imported(page, 'AES-GCM', raw, format='RAW'), 'TypeError')
    probe.error_is(page, probe.imported(page, 'AES-GCM', raw, format='spki'), 'NotSupportedError')
    probe.error_is(page, probe.imported(page, 'AES-KWP', raw, usages=('wrapKey',)), 'NotSupportedError')
    probe.error_is(page, probe.imported(page, 'unknown', raw, usages=('bogus',)), 'TypeError')
    probe.error_is(page, probe.imported(page, 'unknown', {**basic, 'key_ops': ['bogus']}, format='jwk'), 'NotSupportedError')
    extended = probe.import_key(page, 'AES-GCM', {**basic, 'key_ops': ['encrypt', 'bogus', 'sign']}, format='jwk', usages=('encrypt',))
    n.expect(probe.bytes(probe.export(page, extended), page) == raw, 'unrecognized JWK usages do not change recognized requested usage intersection')
    probe.error_is(page, probe.imported(page, 'AES-GCM', {**basic, 'key_ops': ['encrypt', 'encrypt']}, format='jwk', usages=('sign',)), 'SyntaxError')

def check_cipher_validation(probe, page):
    n = probe.n
    raw = bytes(range(16))
    key = probe.import_key(page, 'AES-GCM', raw)
    ctr_key = probe.import_key(page, 'AES-CTR', raw)
    for parameters, expected in [(cipher('AES-GCM'), 'TypeError'), (cipher('AES-GCM', b''), 'OperationError'), (cipher('AES-GCM', bytes(12), tag=0), 'OperationError'), (cipher('AES-GCM', bytes(12), tag=40), 'OperationError'), (cipher('AES-GCM', bytes(12), tag=256), 'TypeError')]:
        with probe.check(f'cipher_validation line335: {(parameters, expected)!r}'):
            probe.error_is(page, probe.transform(page, 'encrypt', key, parameters, b'message'), expected)
    probe.error_is(page, probe.transform(page, 'encrypt', ctr_key, cipher('AES-GCM'), b''), 'TypeError')
    probe.error_is(page, probe.transform(page, 'encrypt', ctr_key, cipher('AES-GCM', b''), b''), 'InvalidAccessError')
    for parameters, expected in [(cipher('AES-CTR', bytes(16)), 'TypeError'), (cipher('AES-CTR', bytes(16), ctr_bits=0), 'OperationError'), (cipher('AES-CTR', bytes(16), ctr_bits=129), 'OperationError'), (cipher('AES-CTR', bytes(16), ctr_bits=256), 'TypeError'), (cipher('AES-CTR', bytes(15), ctr_bits=128), 'OperationError')]:
        with probe.check(f'cipher_validation line344: {(parameters, expected)!r}'):
            probe.error_is(page, probe.transform(page, 'encrypt', ctr_key, parameters, b'message'), expected)
    probe.error_is(page, probe.transform(page, 'encrypt', ctr_key, cipher('AES-CTR', bytes(16), ctr_bits=1), bytes(33)), 'OperationError')

def check_wrapping(probe, page):
    n = probe.n
    raw = bytes(range(16))
    key = probe.import_key(page, 'AES-GCM', raw)
    basic = {'kty': 'oct', 'k': base64.urlsafe_b64encode(raw).decode().rstrip('=')}
    private = probe.import_key(page, 'AES-GCM', raw, extractable=False, usages=('encrypt',))
    for name in ['AES-CBC', 'AES-CTR', 'AES-GCM']:
        with probe.check(f'wrapping line353: {name!r}'):
            parameters = cipher(name, bytes(16 if name != 'AES-GCM' else 12), ctr_bits=128)
            wrapping = probe.import_key(page, name, raw, usages=('wrapKey', 'unwrapKey'))
            for format in ['raw', 'jwk']:
                with probe.check(f'wrapping line356: {format!r}'):
                    wrapped = probe.bytes(probe.wrap(page, key, wrapping, parameters, format), page)
                    restored = probe.take(probe.unwrap(page, wrapped, wrapping, parameters, format=format), page)
                    n.expect(probe.bytes(probe.export(page, restored), page) == raw, name + ' wrap-only key and unwrap-only key permissions')
            probe.error_is(page, probe.wrap(page, private, wrapping, parameters), 'InvalidAccessError')
            probe.error_is(page, probe.transform(page, 'encrypt', wrapping, parameters, b''), 'InvalidAccessError')
            encrypting = probe.import_key(page, name, raw, usages=('encrypt', 'decrypt'))
            probe.error_is(page, probe.wrap(page, key, encrypting, parameters), 'InvalidAccessError')
            valid_wrapped = probe.bytes(probe.wrap(page, key, wrapping, parameters), page)
            probe.error_is(page, probe.unwrap(page, valid_wrapped, encrypting, parameters), 'InvalidAccessError')
            invalid_json = [(b'{', 'DataError'), (b'1', 'DataError'), (b'null', 'DataError'), (b'[]', 'DataError'), (json.dumps({**basic, 'key_ops': ['encrypt', 'encrypt']}).encode(), 'DataError'), (json.dumps({**basic, 'key_ops': ['bogus']}).encode(), 'DataError'), (json.dumps({**basic, 'key_ops': None}).encode(), 'DataError'), (json.dumps({**basic, 'alg': ''}).encode(), 'DataError')]
            for data, error in invalid_json:
                with probe.check(f'wrapping line373: {(data, error)!r}'):
                    wrapped = probe.bytes(probe.transform(page, 'encrypt', encrypting, parameters, data), page)
                    probe.error_is(page, probe.unwrap(page, wrapped, wrapping, parameters, format='jwk'), error)
            hmac = probe.import_key(page, 'HMAC', b'hmac wrapping target', usages=('sign',), options=algorithm('HMAC', 'SHA-256'))
            for format in ['raw', 'jwk']:
                with probe.check(f'wrapping line377: {format!r}'):
                    wrapped = probe.bytes(probe.wrap(page, hmac, wrapping, parameters, format), page)
                    restored = probe.take(probe.unwrap(page, wrapped, wrapping, parameters, name='HMAC', format=format, usages=('sign',), options=algorithm('HMAC', 'SHA-256')), page)
                    n.expect(probe.bytes(probe.export(page, restored), page) == b'hmac wrapping target', 'HMAC target normalization and round trip')

def check_hmac_import_order(probe, page):
    profile = json.loads((FIXTURES / 'crypto-webcrypto-profile.json').read_text())
    for case in profile['hmacImportOrderCases']:
        with probe.check('dated ED HMAC import ' + json.dumps(case)):
            options = algorithm('HMAC', 'SHA-256', 0 if case['lengthPresent'] else MISSING)
            data = {'kty': 'oct', 'k': 'AQ'} if case['format'] == 'jwk' else b'\x01'
            operation = probe.imported(page, 'HMAC', data, usages=case['usages'], format=case['format'], options=options)
            if case['expected'] == 'success':
                probe.take(operation, page)
            else:
                probe.error_is(page, operation, case['expected'])


def check_lifetime(probe):
    n = probe.n
    raw = bytes(range(16))
    page = Case(n, '<p>AES lifetime owner</p>')
    try:
        key = probe.import_key(page, 'AES-GCM', raw)
        parameters = cipher('AES-GCM', bytes(12))
        source = span(raw)
        options, usage = (algorithm('AES-GCM'), strings(('encrypt',)))
        data = KeyData(ctypes.sizeof(KeyData), 1, source, None)
        pending = probe.start('secret_import', [P, Bytes, ctypes.POINTER(KeyData), ctypes.POINTER(ImportParams), I, Strings], page.document, span(b'raw'), ctypes.byref(data), ctypes.byref(options), 1, usage)
        source.backing[0] = b'X'
        copied = probe.take(pending, page)
        n.expect(probe.bytes(probe.export(page, copied), page) == raw, 'raw import copies caller data at admission')
        plain, iv, aad = (span(b'copied plaintext'), span(bytes(12)), span(b'associated'))
        body = Gcm(ctypes.sizeof(Gcm), 1, iv, 1, aad, 0, 0)
        copied_parameters = Cipher(ctypes.sizeof(Cipher), span(b'AES-GCM'), None, None, ctypes.pointer(body))
        pending = probe.start('aes_encrypt', [P, ctypes.POINTER(Cipher), Key, Bytes], page.document, ctypes.byref(copied_parameters), copied, plain)
        plain.backing[0], iv.backing[0], aad.backing[0] = (b'X', b'X', b'X')
        expected = probe.bytes(probe.transform(page, 'encrypt', key, cipher('AES-GCM', bytes(12), aad=b'associated'), b'copied plaintext'), page)
        n.expect(probe.bytes(pending, page) == expected, 'cipher copies plaintext, IV and AAD before return')
        pending = probe.transform(page, 'encrypt', copied, parameters, b'retained')
        probe.ok('key_release', [Key], copied)
        del probe.keys[copied.value]
        n.expect(bool(probe.bytes(pending, page)), 'in-flight operation retains key after caller release')
        errors = []
        worker = threading.Thread(target=lambda: errors.append(probe.call('aes_key_info', [Key, ctypes.POINTER(AesInfo)], key, ctypes.byref(AesInfo(ctypes.sizeof(AesInfo))))))
        worker.start()
        worker.join()
        n.expect(errors == [-2], 'AES metadata enforces owner thread')
        abandoned = probe.generate(page, 'AES-GCM', 128)
        probe.ok('operation_release', [Operation], abandoned)
        del probe.operations[abandoned.value]
        n.call('rv_run_loop_cycle', [I], 10)
        n.expect(probe.call('operation_ready', [Operation, ctypes.POINTER(I)], abandoned, ctypes.byref(I())) == -10, 'AES cancellation revokes queued completion')
        pending = probe.transform(page, 'encrypt', key, parameters, b'owner teardown')
        page.close()
        page = None
        probe.wait(pending)
        n.expect(probe.error(pending) == 'AbortError', 'AES owner teardown aborts pending operation')
        page = Case(n, '<p>AES replacement owner</p>')
        encrypted = probe.bytes(probe.transform(page, 'encrypt', key, parameters, b'new context'), page)
        n.expect(probe.bytes(probe.transform(page, 'decrypt', key, parameters, encrypted), page) == b'new context', 'AES key survives document teardown and crosses service contexts')
    finally:
        if page:
            page.close()


def run(directory, bridge_library=None):
    n = Native(directory)
    probe = AesProbe(n, ctypes.CDLL(bridge_library) if bridge_library else n.library)
    page = Case(n, '<p>AES owner</p>')
    try:
        for group in [check_generation, check_vectors, check_jwk, check_cipher_validation, check_wrapping, check_hmac_import_order]:
            with probe.check(group.__name__):
                group(probe, page)
        with probe.check('check_lifetime'):
            check_lifetime(probe)
        if probe.failures:
            raise AssertionError(f'{len(probe.failures)} independent AES cases failed')
        return n.assertions
    except BaseException:
        print(f'SUBTLE_CRYPTO_AES FAIL assertions={n.assertions} cases={len(probe.failures)}', flush=True)
        raise
    finally:
        probe.close()
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--bridge-library')
    arguments = parser.parse_args()
    print(f'SUBTLE_CRYPTO_AES PASS assertions={run(arguments.native_directory, arguments.bridge_library)}')
