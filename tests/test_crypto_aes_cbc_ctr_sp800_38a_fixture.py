"""Structural checks for NIST SP 800-38A AES CBC/CTR fixture data; no cipher is run."""
import json
import unittest
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "crypto-aes-cbc-ctr-sp800-38a.json"
EXPECTED_COUNTERS = [
    "f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff",
    "f0f1f2f3f4f5f6f7f8f9fafbfcfdff00",
    "f0f1f2f3f4f5f6f7f8f9fafbfcfdff01",
    "f0f1f2f3f4f5f6f7f8f9fafbfcfdff02",
]

class NistSp80038aFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_all_key_sizes_and_raw_block_lengths(self):
        vectors = self.document["vectors"]
        self.assertEqual(len(vectors), 6)
        self.assertEqual([(v["mode"], v["key_bits"]) for v in vectors],
                         [("CBC", 128), ("CBC", 192), ("CBC", 256),
                          ("CTR", 128), ("CTR", 192), ("CTR", 256)])
        message = self.document["message_blocks_hex"]
        self.assertEqual(len(message), 4)
        self.assertTrue(all(len(bytes.fromhex(block)) == 16 for block in message))
        for vector in vectors:
            with self.subTest(example=vector["example_id"]):
                self.assertEqual(len(bytes.fromhex(vector["key_hex"])), vector["key_bits"] // 8)
                self.assertEqual(len(vector["ciphertext_blocks_hex"]), 4)
                self.assertTrue(all(len(bytes.fromhex(block)) == 16
                                    for block in vector["ciphertext_blocks_hex"]))
                self.assertIn("blocks #1..#4", vector["block_order"])

    def test_cbc_is_raw_no_padding_with_prefix_metadata(self):
        cbc = [v for v in self.document["vectors"] if v["mode"] == "CBC"]
        self.assertEqual(len(cbc), 3)
        for vector in cbc:
            self.assertEqual(vector["padding"], "none (raw block-mode vector)")
            self.assertEqual(len(bytes.fromhex(vector["iv_hex"])), 16)
            self.assertEqual(vector["raw_ciphertext_prefix_bytes"], 64)
        self.assertIn("PKCS#7", self.document["cbc_note"])
        self.assertIn("No padded NIST ciphertext is invented", self.document["cbc_note"])

    def test_ctr_counter_order_is_explicit(self):
        ctr = [v for v in self.document["vectors"] if v["mode"] == "CTR"]
        self.assertEqual(len(ctr), 3)
        for vector in ctr:
            self.assertEqual(vector["initial_counter_hex"], EXPECTED_COUNTERS[0])
            self.assertEqual(vector["counter_field_bits"], 32)
            self.assertEqual(vector["counter_blocks_hex"], EXPECTED_COUNTERS)
            self.assertEqual(len(bytes.fromhex(vector["initial_counter_hex"])), 16)
            self.assertEqual(len(vector["counter_blocks_hex"]), 4)
        self.assertIn("not a claim that NIST mandates", self.document["ctr_note"])

if __name__ == "__main__":
    unittest.main()
