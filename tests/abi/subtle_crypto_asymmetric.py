import argparse
import base64
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, Case, P, I
from subtle_crypto_hmac import Probe, Key, Operation, Bytes, Strings, span

U32, U64 = C.c_uint32, C.c_uint64
JWK_FIELDS = ['kty', 'k', 'alg', 'use', 'crv', 'x', 'y', 'd', 'n', 'e', 'p', 'q', 'dp', 'dq', 'qi']
EXPORTS = ['asymmetric_supported', 'asymmetric_generate', 'asymmetric_import', 'asymmetric_sign',
           'asymmetric_verify', 'asymmetric_encrypt', 'asymmetric_decrypt', 'asymmetric_derive_bits',
           'asymmetric_derive_key', 'operation_take_key_pair', 'operation_jwk']
EXPORTS += ['asymmetric_key_info', 'asymmetric_key_hash', 'asymmetric_key_named_curve', 'asymmetric_key_public_exponent']


class OptionalString(C.Structure):
    _fields_ = [('present', I), ('value', Bytes)]


class OptionalStrings(C.Structure):
    _fields_ = [('present', I), ('value', Strings)]


class OtherPrime(C.Structure):
    _fields_ = [(name, OptionalString) for name in ['r', 'd', 't']]


class OptionalOtherPrimes(C.Structure):
    _fields_ = [('present', I), ('items', C.POINTER(OtherPrime)), ('count', I)]


class Jwk(C.Structure):
    _fields_ = [('size', U32)] + [(name, OptionalString) for name in JWK_FIELDS]
    _fields_ += [('key_ops', OptionalStrings), ('ext_present', I), ('ext', I), ('oth', OptionalOtherPrimes)]


class Pair(C.Structure):
    _fields_ = [('size', U32), ('public_key', Key), ('private_key', Key)]


class KeyParams(C.Structure):
    _fields_ = [('size', U32), ('name', Bytes), ('hash', OptionalString), ('named_curve', OptionalString),
                ('modulus_length_present', I), ('modulus_length_bits', U64), ('public_exponent_present', I), ('public_exponent', Bytes)]


class SignParams(C.Structure):
    _fields_ = [('size', U32), ('name', Bytes), ('hash', OptionalString), ('salt_length_present', I), ('salt_length_bytes', U64)]


class OaepParams(C.Structure):
    _fields_ = [('size', U32), ('name', Bytes), ('label_present', I), ('label', Bytes)]


class DeriveParams(C.Structure):
    _fields_ = [('size', U32), ('name', Bytes), ('public_key_present', I), ('public_key', Key)]


class KeyData(C.Structure):
    _fields_ = [('size', U32), ('raw_present', I), ('raw', Bytes), ('jwk', C.POINTER(Jwk))]


class OptionalLength(C.Structure):
    _fields_ = [('present', I), ('bits', U64)]


class KeyInfo(C.Structure):
    _fields_ = [('size', U32), ('modulus_length_present', I), ('modulus_length_bits', U64), ('hash_present', I), ('named_curve_present', I)]


def names(values):
    spans = [span(v.encode()) for v in values]
    array = (Bytes * len(spans))(*spans)
    value = Strings(array, len(spans))
    value.backing = (spans, array)
    return value


def key_params(name, *, hash_name=None, curve=None, modulus=None, exponent=None):
    value = KeyParams(C.sizeof(KeyParams), span(name.encode()))
    backing = [value.name]
    for field, text in [('hash', hash_name), ('named_curve', curve)]:
        if text is not None:
            data = span(text.encode())
            setattr(value, field, OptionalString(1, data))
            backing.append(data)
    if modulus is not None:
        value.modulus_length_present, value.modulus_length_bits = 1, modulus
    if exponent is not None:
        value.public_exponent_present, value.public_exponent = 1, span(exponent)
        backing.append(value.public_exponent)
    value.backing = backing
    return value


class JwkInput:
    def __init__(self, source):
        self.value, self.backing = Jwk(C.sizeof(Jwk)), []
        for name in JWK_FIELDS:
            if name in source:
                data = span(source[name].encode())
                setattr(self.value, name, OptionalString(1, data))
                self.backing.append(data)
        if 'key_ops' in source:
            value = names(source['key_ops'])
            self.value.key_ops = OptionalStrings(1, value)
            self.backing.append(value)
        if 'ext' in source:
            self.value.ext_present, self.value.ext = 1, source['ext']
        if 'oth' in source:
            primes = []
            for item in source['oth']:
                prime = OtherPrime()
                for field in ['r', 'd', 't']:
                    if field in item:
                        data = span(item[field].encode())
                        setattr(prime, field, OptionalString(1, data))
                        self.backing.append(data)
                primes.append(prime)
            array = (OtherPrime * len(primes))(*primes)
            self.value.oth = OptionalOtherPrimes(1, array, len(primes))
            self.backing.append(array)


def read_jwk(value):
    def text(v):
        assert v.length >= 0 and (not v.length or v.data)
        return C.string_at(v.data, v.length).decode()
    result = {name: text(getattr(value, name).value) for name in JWK_FIELDS if getattr(value, name).present}
    if value.key_ops.present:
        result['key_ops'] = [text(value.key_ops.value.items[i]) for i in range(value.key_ops.value.count)]
    if value.ext_present:
        result['ext'] = bool(value.ext)
    if value.oth.present:
        result['oth'] = [{name: text(getattr(value.oth.items[i], name).value) for name in ['r', 'd', 't'] if getattr(value.oth.items[i], name).present} for i in range(value.oth.count)]
    return result


class AsymmetricProbe(Probe):
    def metadata(self, key):
        def bytes_for(name):
            length = I()
            status = self.call(name, [Key, P, I, C.POINTER(I)], key, None, 0, C.byref(length))
            self.n.expect(status == -6 and length.value > 0, name + ' reports exact metadata length')
            buffer = C.create_string_buffer(length.value)
            self.ok(name, [Key, P, I, C.POINTER(I)], key, buffer, len(buffer), C.byref(length))
            return buffer.raw[:length.value]
        result = {'name': bytes_for('key_algorithm_name').decode()}
        info = KeyInfo(C.sizeof(KeyInfo))
        self.ok('asymmetric_key_info', [Key, C.POINTER(KeyInfo)], key, C.byref(info))
        if info.modulus_length_present:
            result['modulusLength'] = info.modulus_length_bits
            result['publicExponent'] = bytes_for('asymmetric_key_public_exponent').hex()
        if info.hash_present:
            result['hash'] = {'name': bytes_for('asymmetric_key_hash').decode()}
        if info.named_curve_present:
            result['namedCurve'] = bytes_for('asymmetric_key_named_curve').decode()
        return result

    def pair(self, operation, page):
        self.wait(operation, page)
        self.n.expect(self.error(operation) == '', 'generated pair succeeds')
        result = Pair(C.sizeof(Pair))
        self.ok('operation_take_key_pair', [Operation, C.POINTER(Pair)], operation, C.byref(result))
        self.n.expect(bool(result.public_key.value) and bool(result.private_key.value), 'pair contains two key tokens')
        self.n.expect(result.public_key.value != result.private_key.value, 'pair tokens are independent')
        for key in [result.public_key, result.private_key]:
            self.keys[key.value] = (Key(key.value), 1)
        again = Pair(C.sizeof(Pair), Key(99), Key(99))
        self.n.expect(self.call('operation_take_key_pair', [Operation, C.POINTER(Pair)], operation, C.byref(again)) == -9 and not again.public_key.value and not again.private_key.value, 'pair transfers atomically once')
        return Key(result.public_key.value), Key(result.private_key.value)

    def jwk(self, operation, page):
        self.wait(operation, page)
        self.n.expect(self.error(operation) == '', 'JWK export succeeds')
        result = Jwk(C.sizeof(Jwk))
        self.ok('operation_jwk', [Operation, C.POINTER(Jwk)], operation, C.byref(result))
        return read_jwk(result)

    def import_key(self, page, params, data, format='jwk', usages=(), extractable=True):
        owner = JwkInput(data) if format == 'jwk' else span(data)
        value = KeyData(C.sizeof(KeyData))
        if format == 'jwk':
            value.jwk = C.pointer(owner.value)
        else:
            value.raw_present, value.raw = 1, owner
        operation = self.start('asymmetric_import', [P, Bytes, C.POINTER(KeyData), C.POINTER(KeyParams), I, Strings],
                               page.document, span(format.encode()), C.byref(value), C.byref(params), extractable, names(usages))
        return self.take(operation, page)

    def export(self, page, key, format='jwk'):
        operation = self.start('key_export', [P, Bytes, Key], page.document, span(format.encode()), key)
        return self.jwk(operation, page) if format == 'jwk' else self.bytes(operation, page)


def run(directory, library_path, exports_only=False):
    native = Native(directory)
    library = C.CDLL(library_path) if library_path else native.library
    assert getattr(library, 'ranvier_crypto_hmac_generate'), 'wrong baseline crypto library'
    missing = [name for name in EXPORTS if not hasattr(library, 'ranvier_crypto_' + name)]
    assert not missing, 'Missing production asymmetric transport: ' + ', '.join(missing)
    if exports_only:
        return {'result': 'PASS', 'exports': len(EXPORTS), 'full143Closed': False}
    probe = AsymmetricProbe(native, library)
    page = Case(native, '<p>production asymmetric tokens</p>')
    try:
        for name, curve, usages in [('ECDSA', 'P-256', ['sign', 'verify']), ('ECDH', 'P-256', ['deriveBits', 'deriveKey']), ('Ed25519', None, ['sign', 'verify']), ('X25519', None, ['deriveBits', 'deriveKey'])]:
            params = key_params(name, curve=curve)
            public, private = probe.pair(probe.start('asymmetric_generate', [P, C.POINTER(KeyParams), I, Strings], page.document, C.byref(params), 1, names(usages)), page)
            for key, private_part in [(public, False), (private, True)]:
                native.expect(probe.metadata(key) == ({'name': name, 'namedCurve': curve} if curve else {'name': name}), name + ' complete algorithm metadata')
                jwk = probe.export(page, key)
                native.expect(('d' in jwk) == private_part, name + ' exported key type')
                native.expect(jwk['kty'] == ('OKP' if curve is None else 'EC'), name + ' JWK family')
                native.expect(jwk['crv'] == (curve or name), name + ' JWK curve')
                expected = 32
                native.expect(len(base64.urlsafe_b64decode(jwk['x'] + '=' * (-len(jwk['x']) % 4))) == expected, name + ' fixed-width x')
                imported = probe.import_key(page, key_params(name, curve=curve), jwk, usages=usages if private_part and name in ['ECDH', 'X25519'] else ['sign'] if private_part else [] if name in ['ECDH', 'X25519'] else ['verify'])
                native.expect(probe.export(page, imported) == jwk, name + ' production JWK roundtrip')
        return {'result': 'PASS', 'assertions': native.assertions, 'full143Closed': False}
    finally:
        probe.close()
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--bridge-library')
    parser.add_argument('--exports-only', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        result = run(args.native_directory, args.bridge_library, args.exports_only)
    except BaseException as error:
        result = {'result': 'FAIL', 'error': repr(error), 'full143Closed': False}
        if args.report:
            args.report.write_text(json.dumps(result, indent=2) + '\n')
        raise
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + '\n')
    print('SUBTLE_CRYPTO_ASYMMETRIC', json.dumps(result))
