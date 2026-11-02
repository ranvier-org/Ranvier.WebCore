import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AsymmetricContractTests(unittest.TestCase):
    def test_c_and_cpp_ffi_layout(self):
        source = '''
#include "RanvierCryptoAsymmetricContract.h"
#include <stddef.h>
#ifdef __cplusplus
#define CHECK static_assert
#else
#define CHECK _Static_assert
#endif
CHECK(sizeof(((RanvierCryptoAsymmetricKeyParams*)0)->modulus_length_bits) == 8, "RSA WebIDL range input");
CHECK(sizeof(((RanvierCryptoAsymmetricSignParams*)0)->salt_length_bytes) == 8, "PSS salt octet range input");
CHECK(offsetof(RanvierCryptoKeyPairResult, size) == 0, "sized pair result");
#if UINTPTR_MAX == UINT64_MAX
CHECK(sizeof(RanvierCryptoRsaOtherPrime) == 72, "other-prime dictionary");
CHECK(sizeof(RanvierCryptoOptionalOtherPrimes) == 24, "optional other-prime sequence");
CHECK(sizeof(RanvierCryptoJsonWebKey) == 424, "full JWK presence and fields");
CHECK(offsetof(RanvierCryptoJsonWebKey, d) == 176, "private scalar or exponent");
CHECK(offsetof(RanvierCryptoJsonWebKey, key_ops) == 368, "omitted versus empty usages");
CHECK(offsetof(RanvierCryptoJsonWebKey, oth) == 400, "other-prime sequence presence");
CHECK(sizeof(RanvierCryptoKeyPairResult) == 24, "pair ownership transfer");
CHECK(offsetof(RanvierCryptoKeyPairResult, private_key) == 16, "second independent key token");
CHECK(sizeof(RanvierCryptoAsymmetricKeyParams) == 112, "key dictionary");
CHECK(offsetof(RanvierCryptoAsymmetricKeyParams, public_exponent) == 96, "copied RSA exponent");
CHECK(sizeof(RanvierCryptoAsymmetricSignParams) == 64, "signature parameters");
CHECK(sizeof(RanvierCryptoAsymmetricOaepParams) == 48, "OAEP parameters");
CHECK(sizeof(RanvierCryptoAsymmetricDeriveParams) == 40, "peer key presence and handle");
CHECK(sizeof(RanvierCryptoAsymmetricKeyData) == 32, "raw or JWK key data");
CHECK(sizeof(RanvierCryptoAsymmetricKeyInfo) == 24, "typed asymmetric algorithm metadata");
CHECK(offsetof(RanvierCryptoAsymmetricKeyInfo, modulus_length_bits) == 8, "RSA bit length");
CHECK(offsetof(RanvierCryptoAsymmetricKeyInfo, hash_present) == 16, "optional bound hash");
#endif
'''
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'asymmetric-contract.c'
            path.write_text(source)
            for language, standard in [('c', 'c11'), ('c++', 'c++20')]:
                with self.subTest(language=language):
                    result = subprocess.run([os.environ.get('CC', 'clang'), '-x', language, '-std=' + standard,
                                             '-fsyntax-only', '-I', str(ROOT / 'host'), str(path)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
