import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CryptoContractTests(unittest.TestCase):
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
