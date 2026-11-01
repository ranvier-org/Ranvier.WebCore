"""Structural checks for the transcribed RFC 6070 PBKDF2 vectors.

This module intentionally does not execute PBKDF2.
"""
import json
import unittest
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "crypto-pbkdf2-rfc6070.json"


class Rfc6070FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_all_published_vectors_and_lengths_are_preserved(self):
        self.assertEqual(self.document["algorithm"], "PBKDF2-HMAC-SHA1")
        self.assertEqual([v["case"] for v in self.document["vectors"]], [1, 2, 3, 4, 5, 6])

        for vector in self.document["vectors"]:
            with self.subTest(case=vector["case"]):
                password = bytes.fromhex(vector["password_hex"])
                salt = bytes.fromhex(vector["salt_hex"])
                derived_key = bytes.fromhex(vector["derived_key_hex"])
                self.assertEqual(len(password), vector["password_octets"])
                self.assertEqual(len(salt), vector["salt_octets"])
                self.assertEqual(len(derived_key), vector["dk_len_octets"])
                self.assertGreater(vector["iterations"], 0)

    def test_literal_nuls_and_expensive_case_are_explicit(self):
        vectors = {v["case"]: v for v in self.document["vectors"]}
        self.assertIn(bytes((0,)), bytes.fromhex(vectors[6]["password_hex"]))
        self.assertIn(bytes((0,)), bytes.fromhex(vectors[6]["salt_hex"]))
        self.assertEqual(vectors[6]["password_text"], "pass\\0word")
        self.assertEqual(vectors[6]["salt_text"], "sa\\0lt")

        expensive = vectors[4]
        self.assertEqual(expensive["iterations"], 16_777_216)
        self.assertIn("Very high cost", expensive["execution_note"])
        self.assertIn("does not execute", expensive["execution_note"])


if __name__ == "__main__":
    unittest.main()
