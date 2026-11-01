"""Structural checks for published HMAC RFC fixtures; no HMAC is computed."""
import json
import unittest
from pathlib import Path
FIXTURES = {
    "rfc4231": Path(__file__).parent / "fixtures" / "crypto-hmac-rfc4231.json",
    "rfc2202": Path(__file__).parent / "fixtures" / "crypto-hmac-rfc2202.json",
}
class HmacRfcFixtureTests(unittest.TestCase):
    def load_fixture(self, name):
        return json.loads(FIXTURES[name].read_text(encoding="utf-8"))
    def test_published_inputs_and_mac_lengths(self):
        for name in ("rfc4231", "rfc2202"):
            fixture = self.load_fixture(name)
            self.assertEqual([case["case"] for case in fixture["cases"]], list(range(1, 8)))
            for case in fixture["cases"]:
                with self.subTest(rfc=name, case=case["case"]):
                    self.assertEqual(len(bytes.fromhex(case["key_hex"])), case["key_bytes"])
                    self.assertEqual(len(bytes.fromhex(case["data_hex"])), case["data_bytes"])
                    self.assertEqual(set(case["macs"]), set(fixture["algorithms"]))
                    for algorithm, outputs in case["macs"].items():
                        full_len = fixture["algorithms"][algorithm]
                        for output in outputs:
                            mac = bytes.fromhex(output["hex"])
                            self.assertEqual(len(mac), output["byte_length"])
                            if output["kind"] == "full_digest":
                                self.assertEqual(len(mac), full_len)
                                self.assertNotIn("truncation_bits", output)
                            else:
                                self.assertEqual(output["kind"], "truncated_prefix")
                                self.assertEqual(output["truncation_bits"], len(mac) * 8)
                                self.assertLess(len(mac), full_len)
    def test_published_prefixes_are_not_mislabeled_as_full(self):
        rfc4231 = self.load_fixture("rfc4231")
        for outputs in rfc4231["cases"][4]["macs"].values():
            self.assertEqual(len(outputs), 1)
            self.assertEqual(outputs[0]["kind"], "truncated_prefix")
            self.assertEqual(outputs[0]["truncation_bits"], 128)
            self.assertEqual(outputs[0]["byte_length"], 16)
        rfc2202 = self.load_fixture("rfc2202")
        outputs = rfc2202["cases"][4]["macs"]["HMAC-SHA-1"]
        self.assertEqual([output["kind"] for output in outputs], ["full_digest", "truncated_prefix"])
        self.assertEqual(outputs[1]["truncation_bits"], 96)
        self.assertEqual(bytes.fromhex(outputs[0]["hex"])[:12], bytes.fromhex(outputs[1]["hex"]))
if __name__ == "__main__":
    unittest.main()
