import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GeneralContractTests(unittest.TestCase):
    def test_c_and_cpp_typed_composition_layout(self):
        source = '''
#include "RanvierCryptoGeneralContract.h"
#include <stddef.h>
#ifdef __cplusplus
#define CHECK static_assert
#else
#define CHECK _Static_assert
#endif
CHECK(offsetof(RanvierCryptoImportParams, size) == 0, "sized import dictionary");
CHECK(offsetof(RanvierCryptoWrappingParams, size) == 0, "sized wrapping dictionary");
#if UINTPTR_MAX == UINT64_MAX
CHECK(sizeof(RanvierCryptoImportParams) == 40, "typed import union arms");
CHECK(offsetof(RanvierCryptoImportParams, hmac) == 24, "HMAC import metadata");
CHECK(offsetof(RanvierCryptoImportParams, asymmetric) == 32, "asymmetric import metadata");
CHECK(sizeof(RanvierCryptoWrappingParams) == 40, "typed wrapping union arms");
CHECK(offsetof(RanvierCryptoWrappingParams, aes) == 24, "AES wrapping metadata");
CHECK(offsetof(RanvierCryptoWrappingParams, oaep) == 32, "OAEP wrapping metadata");
#endif
'''
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'general-contract.c'
            path.write_text(source)
            for language, standard in [('c', 'c11'), ('c++', 'c++20')]:
                with self.subTest(language=language):
                    result = subprocess.run([os.environ.get('CC', 'clang'), '-x', language, '-std=' + standard,
                        '-fsyntax-only', '-I', str(ROOT / 'host'), str(path)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
