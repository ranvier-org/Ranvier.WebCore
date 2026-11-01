import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests' / 'fixtures' / 'crypto-aes-gcm-cavp.json'
HEX = re.compile(r'\A(?:[0-9A-Fa-f]{2})*\Z')
SHA256 = re.compile(r'\A[0-9a-f]{64}\Z')
KEY_LENGTHS = (128, 192, 256)
TAG_LENGTHS = (32, 64, 96, 104, 112, 120, 128)


def check_hex(value, octets, label):
    if value is None:
        raise AssertionError(f'{label} is missing')
    if not HEX.fullmatch(value):
        raise AssertionError(f'{label} is not even-length hex')
    if len(value) // 2 != octets:
        raise AssertionError(f'{label} has {len(value) // 2} octets, expected {octets}')


class NistCavpAesGcmFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))

    def test_response_provenance_and_size_are_recorded(self):
        source = self.fixture['source']
        self.assertEqual(source['organization'], 'NIST Cryptographic Algorithm Validation Program (CAVP)')
        self.assertRegex(source['archive_sha256'], SHA256.pattern)
        self.assertEqual(set(source['response_file_sha256']), {
            f'gcmEncryptExtIV{bits}.rsp' for bits in KEY_LENGTHS
        } | {f'gcmDecrypt{bits}.rsp' for bits in KEY_LENGTHS})
        for digest in source['response_file_sha256'].values():
            self.assertRegex(digest, SHA256.pattern)
        self.assertLess(FIXTURE.stat().st_size, 1_000_000)

    def test_selected_cases_have_cavp_group_lengths_and_expected_results(self):
        vectors = self.fixture['vectors']
        self.assertEqual(self.fixture['algorithm'], 'AES-GCM')
        self.assertEqual(len(vectors), 33)
        for vector in vectors:
            with self.subTest(source=vector['source']):
                source = vector['source']
                group = source['group']
                self.assertIsInstance(source['count'], int)
                self.assertGreaterEqual(source['count'], 0)
                self.assertEqual(group['Keylen'], len(vector['input']['Key']) * 4)
                self.assertRegex(source['response_file_sha256'], SHA256.pattern)
                self.assertTrue(all(name in group for name in ('IVlen', 'PTlen', 'AADlen', 'Taglen')))

                key_length = group['Keylen'] // 8
                iv_length = group['IVlen'] // 8
                aad_length = group['AADlen'] // 8
                plaintext_length = group['PTlen'] // 8
                tag_length = group['Taglen'] // 8
                self.assertEqual(group['Keylen'] % 8, 0)
                self.assertEqual(group['IVlen'] % 8, 0)
                self.assertEqual(group['PTlen'] % 8, 0)
                self.assertEqual(group['AADlen'] % 8, 0)
                self.assertEqual(group['Taglen'] % 8, 0)
                check_hex(vector['input']['Key'], key_length, 'Key')
                check_hex(vector['input']['IV'], iv_length, 'IV')
                check_hex(vector['input']['AAD'], aad_length, 'AAD')

                if vector['operation'] == 'encrypt':
                    self.assertEqual(source['response_file'], f'gcmEncryptExtIV{group["Keylen"]}.rsp')
                    check_hex(vector['input']['PT'], plaintext_length, 'PT')
                    check_hex(vector['expected']['CT'], plaintext_length, 'CT')
                    check_hex(vector['expected']['Tag'], tag_length, 'Tag')
                else:
                    self.assertEqual(vector['operation'], 'decrypt')
                    self.assertEqual(source['response_file'], f'gcmDecrypt{group["Keylen"]}.rsp')
                    check_hex(vector['input']['CT'], plaintext_length, 'CT')
                    check_hex(vector['input']['Tag'], tag_length, 'Tag')
                    self.assertEqual(vector['expected'], {'result': 'FAIL'})

    def test_fixture_covers_the_requested_cavp_profile_samples(self):
        vectors = self.fixture['vectors']
        encryptions = [vector for vector in vectors if vector['operation'] == 'encrypt']
        tag_coverage = {
            (vector['source']['group']['Keylen'], vector['source']['group']['Taglen'])
            for vector in encryptions if vector['selection'].startswith('tag_length_')
        }
        self.assertEqual(tag_coverage, {(key, tag) for key in KEY_LENGTHS for tag in TAG_LENGTHS})

        for key in KEY_LENGTHS:
            selected = [v for v in encryptions if v['source']['group']['Keylen'] == key]
            self.assertEqual(sum(v['selection'] == 'empty_plaintext_and_empty_AAD' for v in selected), 1)
            self.assertEqual(sum(v['selection'] == 'empty_plaintext_with_nonempty_AAD' for v in selected), 1)
            non96 = [v for v in selected if v['selection'] == 'non_96_bit_IV_with_plaintext_and_AAD']
            self.assertEqual(len(non96), 1)
            self.assertNotEqual(non96[0]['source']['group']['IVlen'], 96)

        failures = [v for v in vectors if v['operation'] == 'decrypt']
        self.assertEqual(len(failures), 3)
        self.assertEqual({v['source']['group']['Keylen'] for v in failures}, set(KEY_LENGTHS))


if __name__ == '__main__':
    unittest.main()
