"""Private unwrap JWK conversion controls for the dated WebCrypto editor draft."""

import argparse
import base64
import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from subtle_crypto_aes import AesProbe, cipher
from subtle_crypto_hmac import Native, Case


def run(directory, report=None):
    n = Native(directory)
    probe = AesProbe(n, n.library)
    page = Case(n, '<p>dated JWK conversion owner</p>')
    raw = bytes(range(16))
    basic = {'kty': 'oct', 'k': base64.urlsafe_b64encode(raw).rstrip(b'=').decode(),
             'alg': 'A128GCM', 'key_ops': ['encrypt'], 'ext': True}
    encoded = lambda changes: json.dumps({**basic, **changes}, separators=(',', ':')).encode()
    cases = [
        ('empty JSON', b'', 'SyntaxError', ('encrypt',)),
        ('invalid JSON', b'{', 'SyntaxError', ('encrypt',)),
        ('number dictionary', b'1', 'TypeError', ('encrypt',)),
        ('string dictionary', b'"jwk"', 'TypeError', ('encrypt',)),
        ('boolean dictionary', b'true', 'TypeError', ('encrypt',)),
        ('null missing kty', b'null', 'DataError', ('encrypt',)),
        ('array missing kty', b'[]', 'DataError', ('encrypt',)),
        ('object missing kty', b'{}', 'DataError', ('encrypt',)),
        ('missing kty before algorithm usage', b'{}', 'DataError', ('sign',)),
        ('present null kty reaches algorithm usage', encoded({'kty': None}), 'SyntaxError', ('sign',)),
        ('empty kty', encoded({'kty': ''}), 'DataError', ('encrypt',)),
        ('null key_ops', encoded({'key_ops': None}), 'TypeError', ('encrypt',)),
        ('primitive string key_ops', encoded({'key_ops': 'encrypt'}), 'TypeError', ('encrypt',)),
        ('plain object key_ops', encoded({'key_ops': {}}), 'TypeError', ('encrypt',)),
        ('number key_ops', encoded({'key_ops': 4}), 'TypeError', ('encrypt',)),
        ('empty key_ops', encoded({'key_ops': []}), 'DataError', ('encrypt',)),
        ('nested singleton key_ops', encoded({'key_ops': [['encrypt']]}), '', ('encrypt',)),
        ('nested joined key_ops', encoded({'key_ops': [['encrypt', 'decrypt']]}), 'DataError', ('encrypt',)),
        ('array kty DOMString', encoded({'kty': ['oct']}), '', ('encrypt',)),
        ('own noncallable toString', encoded({'kty': {'toString': None}}), 'TypeError', ('encrypt',)),
        ('ordinary object kty', encoded({'kty': {}}), 'DataError', ('encrypt',)),
        ('nested array alg', encoded({'alg': [['A128GCM']]}), '', ('encrypt',)),
        ('ext zero', encoded({'ext': 0}), 'DataError', ('encrypt',)),
        ('ext array true', encoded({'ext': []}), '', ('encrypt',)),
        ('null oth sequence', encoded({'oth': None}), 'TypeError', ('encrypt',)),
        ('empty oth', encoded({'oth': []}), '', ('encrypt',)),
        ('optional other prime fields', encoded({'oth': [{}]}), '', ('encrypt',)),
        ('null other prime dictionary', encoded({'oth': [None]}), '', ('encrypt',)),
        ('array other prime dictionary', encoded({'oth': [[]]}), '', ('encrypt',)),
        ('primitive other prime dictionary', encoded({'oth': [1]}), 'TypeError', ('encrypt',)),
        ('nested dictionary conversion error', encoded({'oth': [{'r': {'toString': None}}]}), 'TypeError', ('encrypt',)),
        ('optional other prime null DOMString', encoded({'oth': [{'r': None}]}), '', ('encrypt',)),
        ('duplicate unknown key_ops', encoded({'key_ops': ['encrypt', 'future', 'future']}), 'DataError', ('encrypt',)),
        ('replacement UTF8 in ignored public field', encoded({'x': 'replace'}).replace(b'replace', b'\xff'), '', ('encrypt',)),
    ]
    measured = []
    try:
        wrapping = probe.import_key(page, 'AES-CBC', raw, usages=('encrypt', 'unwrapKey'))
        params = cipher('AES-CBC', bytes(16))
        for name, data, expected, usages in cases:
            with probe.check(name):
                encrypted = probe.bytes(probe.transform(page, 'encrypt', wrapping, params, data), page)
                operation = probe.unwrap(page, encrypted, wrapping, params, format='jwk', usages=usages)
                probe.wait(operation, page)
                actual = probe.error(operation)
                measured.append({'case': name, 'inputHex': data.hex(), 'expected': expected, 'actual': actual, 'usages': usages})
                n.expect(actual == expected, f'{name}: expected {expected!r}, actual {actual!r}')
                if not actual:
                    key = probe.take(operation, page)
                    n.expect(probe.bytes(probe.export(page, key), page) == raw, name + ' preserves imported key bytes')
        if probe.failures:
            raise AssertionError(f'{len(probe.failures)} independent dated JWK codec cases failed')
        return n.assertions
    finally:
        if report:
            Path(report).write_text(json.dumps({'profile': 'W3C WebCrypto ED2026-10-22', 'rows': measured,
                'failures': probe.failures, 'assertions': n.assertions}, indent=2) + '\n')
        probe.close()
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    print(f'CRYPTO_JWK_CODEC PASS assertions={run(args.native_directory, args.report)}')
