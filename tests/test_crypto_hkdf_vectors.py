import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests' / 'fixtures' / 'crypto-hkdf-rfc5869.json'
HEX = re.compile(r'\A(?:[0-9a-f]{2})*\Z')


class Rfc5869VectorFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))

    def test_all_appendix_a_vectors_have_consistent_hex_lengths(self):
        vectors = self.fixture['vectors']
        self.assertEqual([vector['case'] for vector in vectors], [f'A.{i}' for i in range(1, 8)])

        for vector in vectors:
            with self.subTest(case=vector['case']):
                for name in ('ikm', 'info'):
                    value = vector[f'{name}_hex']
                    self.assertRegex(value, HEX.pattern)
                    self.assertEqual(len(value) // 2, vector[f'{name}_octets'])

                salt = vector['salt_hex']
                if vector['salt_presence'] == 'omitted':
                    self.assertIsNone(salt)
                    self.assertIsNone(vector['salt_octets'])
                else:
                    self.assertRegex(salt, HEX.pattern)
                    self.assertEqual(len(salt) // 2, vector['salt_octets'])

                for name in ('prk', 'okm'):
                    value = vector[f'{name}_hex']
                    self.assertRegex(value, HEX.pattern)
                    expected_octets = vector['hash_len_octets'] if name == 'prk' else vector['l_octets']
                    self.assertEqual(len(value) // 2, expected_octets)

                self.assertLessEqual(vector['l_octets'], 255 * vector['hash_len_octets'])

    def test_empty_and_omitted_salt_are_distinct_cases(self):
        vectors = {vector['case']: vector for vector in self.fixture['vectors']}
        for case in ('A.3', 'A.6'):
            self.assertEqual(vectors[case]['salt_presence'], 'empty')
            self.assertEqual(vectors[case]['salt_hex'], '')
            self.assertEqual(vectors[case]['salt_octets'], 0)
            self.assertEqual(vectors[case]['info_hex'], '')

        self.assertEqual(vectors['A.7']['salt_presence'], 'omitted')
        self.assertIsNone(vectors['A.7']['salt_hex'])
        self.assertIsNone(vectors['A.7']['salt_octets'])
        self.assertIn('HashLen zero octets', self.fixture['source']['salt_semantics'])


if __name__ == '__main__':
    unittest.main()
