import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests' / 'fixtures' / 'crypto-aes-kw-rfc3394.json'
HEX = re.compile(r'\A(?:[0-9a-f]{2})*\Z')


class Rfc3394AesKwFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))

    def test_appendix_vectors_have_consistent_hex_lengths(self):
        self.assertEqual(self.fixture['algorithm'], 'AES-KW')
        iv = self.fixture['default_iv_hex']
        self.assertEqual(iv, 'a6a6a6a6a6a6a6a6')
        self.assertRegex(iv, HEX.pattern)
        self.assertEqual(len(iv) // 2, 8)

        vectors = self.fixture['vectors']
        self.assertEqual([vector['case'] for vector in vectors], [f'4.{i}' for i in range(1, 7)])
        self.assertEqual({vector['kek_bits'] for vector in vectors}, {128, 192, 256})
        self.assertEqual({vector['key_data_bits'] for vector in vectors}, {128, 192, 256})

        for vector in vectors:
            with self.subTest(case=vector['case']):
                for name, bits in (('kek', vector['kek_bits']), ('key_data', vector['key_data_bits'])):
                    value = vector[f'{name}_hex']
                    self.assertRegex(value, HEX.pattern)
                    self.assertEqual(len(value) // 2, bits // 8)

                ciphertext = vector['ciphertext_hex']
                self.assertRegex(ciphertext, HEX.pattern)
                self.assertEqual(len(ciphertext) // 2, vector['ciphertext_octets'])
                self.assertEqual(vector['ciphertext_octets'], vector['key_data_bits'] // 8 + 8)
                self.assertEqual(vector['key_data_bits'] % 64, 0)


if __name__ == '__main__':
    unittest.main()
