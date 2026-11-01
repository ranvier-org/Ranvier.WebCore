import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CryptoContractTests(unittest.TestCase):
    def test_aes_c_and_cpp_layout(self):
        compiler = os.environ.get('CC', 'clang')
        source = '''
#include "RanvierCryptoAesContract.h"
#include <stddef.h>
#ifdef __cplusplus
#define CHECK static_assert
#else
#define CHECK _Static_assert
#endif
CHECK(sizeof(((RanvierCryptoAesCtrParams*)0)->length_bits) == 4, "range checked octet transport");
CHECK(sizeof(((RanvierCryptoAesKeyGenParams*)0)->length_bits) == 4, "range checked unsigned short transport");
#if UINTPTR_MAX == UINT64_MAX
CHECK(sizeof(RanvierCryptoOptionalString) == 24, "optional string");
CHECK(sizeof(RanvierCryptoOptionalStrings) == 24, "optional strings");
CHECK(sizeof(RanvierCryptoAesKeyGenParams) == 32, "key generation");
CHECK(sizeof(RanvierCryptoAesCbcParams) == 24, "CBC");
CHECK(sizeof(RanvierCryptoAesCtrParams) == 32, "CTR");
CHECK(sizeof(RanvierCryptoAesGcmParams) == 56, "GCM");
CHECK(sizeof(RanvierCryptoAesCipherParams) == 48, "cipher selection");
CHECK(sizeof(RanvierCryptoOctetJwk) == 136, "typed octet JWK");
CHECK(sizeof(RanvierCryptoSecretKeyData) == 32, "key data union");
CHECK(sizeof(RanvierCryptoAesKeyInfo) == 32, "AES metadata");
CHECK(sizeof(RanvierCryptoHmacImportParams) == 32, "HMAC import dictionary");
CHECK(sizeof(RanvierCryptoSecretImportParams) == 32, "secret import algorithm");
CHECK(offsetof(RanvierCryptoAesGcmParams, additional_data) == 32, "AAD bytes");
CHECK(offsetof(RanvierCryptoOctetJwk, key_ops) == 104, "JWK operations presence");
#endif
'''
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'aes-contract.c'
            path.write_text(source)
            for language, standard in [('c', 'c11'), ('c++', 'c++20')]:
                result = subprocess.run([compiler, '-x', language, '-std=' + standard,
                                         '-fsyntax-only', '-I', str(ROOT / 'host'), str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_c_and_cpp_layout(self):
        compiler = os.environ.get('CC', 'clang')
        source = '''
#include "RanvierCryptoContract.h"
#include <stddef.h>
#ifdef __cplusplus
#define CHECK static_assert
#else
#define CHECK _Static_assert
#endif
CHECK(sizeof(RanvierCryptoKeyHandle) == 8, "key token");
CHECK(sizeof(RanvierCryptoOperationHandle) == 8, "operation token");
CHECK(offsetof(RanvierCryptoHmacParams, size) == 0, "versioned input");
CHECK(sizeof(((RanvierCryptoHmacParams*)0)->length_bits) == 4, "WebIDL unsigned long");
#if UINTPTR_MAX == UINT64_MAX
CHECK(sizeof(RanvierCryptoBytes) == 16, "span");
CHECK(sizeof(RanvierCryptoStrings) == 16, "strings");
CHECK(sizeof(RanvierCryptoHmacParams) == 48, "HMAC params");
CHECK(offsetof(RanvierCryptoHmacParams, usages) == 32, "usages");
CHECK(sizeof(RanvierCryptoHmacKeyInfo) == 24, "metadata");
#endif
'''
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'contract.c'
            path.write_text(source)
            for language, standard in [('c', 'c11'), ('c++', 'c++20')]:
                result = subprocess.run([compiler, '-x', language, '-std=' + standard,
                                         '-fsyntax-only', '-I', str(ROOT / 'host'), str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
