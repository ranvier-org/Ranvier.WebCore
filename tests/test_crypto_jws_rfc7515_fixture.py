import base64
import json
import unittest
from pathlib import Path


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "crypto-jws-rfc7515-signatures.json"
)


def decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


class Rfc7515JwsFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.vectors = {item["id"]: item for item in cls.document["vectors"]}

    def test_fixture_covers_only_the_two_published_examples(self) -> None:
        self.assertEqual(
            set(self.vectors), {"RFC7515-A.2-RS256", "RFC7515-A.3-ES256"}
        )
        self.assertEqual(self.document["source"]["rfc"], "RFC 7515")
        self.assertEqual(
            self.document["source"]["sections"],
            ["A.2.1", "A.2.2", "A.3.1", "A.3.2"],
        )

    def test_published_signing_input_segments_and_hex_are_exact(self) -> None:
        payload_segment = (
            "eyJpc3MiOiJqb2UiLA0KICJleHAiOjEzMDA4MTkzODAsDQog"
            "Imh0dHA6Ly9leGFtcGxlLmNvbS9pc19yb290Ijp0cnVlfQ"
        )
        payload_octets = (
            b'{"iss":"joe",\r\n "exp":1300819380,\r\n '
            b'"http://example.com/is_root":true}'
        )
        for vector_id, header_segment, header_octets in (
            ("RFC7515-A.2-RS256", "eyJhbGciOiJSUzI1NiJ9", b'{"alg":"RS256"}'),
            ("RFC7515-A.3-ES256", "eyJhbGciOiJFUzI1NiJ9", b'{"alg":"ES256"}'),
        ):
            with self.subTest(vector=vector_id):
                vector = self.vectors[vector_id]
                self.assertEqual(vector["protected_segment_b64url"], header_segment)
                self.assertEqual(vector["payload_segment_b64url"], payload_segment)
                self.assertNotIn("=", header_segment + payload_segment)
                self.assertEqual(decode_base64url(header_segment), header_octets)
                self.assertEqual(decode_base64url(payload_segment), payload_octets)

                signing_input = (header_segment + "." + payload_segment).encode("ascii")
                self.assertEqual(vector["signing_input_hex"], signing_input.hex())
                self.assertEqual(vector["signing_input_byte_length"], len(signing_input))

    def test_rsa_jwk_and_published_signature_lengths(self) -> None:
        vector = self.vectors["RFC7515-A.2-RS256"]
        jwk = vector["jwk"]
        self.assertEqual(set(jwk), {"kty", "n", "e", "d", "p", "q", "dp", "dq", "qi"})
        self.assertEqual(jwk["kty"], "RSA")
        for name, value in jwk.items():
            if name != "kty":
                self.assertEqual(encode_base64url(decode_base64url(value)), value, name)
        self.assertEqual(len(decode_base64url(jwk["n"])), 256)
        self.assertEqual(len(decode_base64url(jwk["e"])), 3)
        self.assertEqual(len(decode_base64url(jwk["d"])), 256)
        for name in ("p", "q", "dp", "dq", "qi"):
            self.assertEqual(len(decode_base64url(jwk[name])), 128, name)

        signature = decode_base64url(vector["signature_b64url"])
        self.assertEqual(encode_base64url(signature), vector["signature_b64url"])
        self.assertEqual(vector["signature_byte_length"], 256)
        self.assertEqual(vector["signature_hex"], signature.hex())
        self.assertEqual(len(signature), 256)
        self.assertEqual(vector["signature_format"], "RSASSA-PKCS1-v1_5 signature octets")
        self.assertFalse({"spki", "pkcs8", "public_key_der", "private_key_der"} & set(vector))

    def test_es256_jwk_and_raw_p1363_signature_lengths(self) -> None:
        vector = self.vectors["RFC7515-A.3-ES256"]
        jwk = vector["jwk"]
        self.assertEqual(set(jwk), {"kty", "crv", "x", "y", "d"})
        self.assertEqual((jwk["kty"], jwk["crv"]), ("EC", "P-256"))
        for name in ("x", "y", "d"):
            decoded = decode_base64url(jwk[name])
            self.assertEqual(encode_base64url(decoded), jwk[name], name)
            self.assertEqual(len(decoded), 32, name)

        signature = decode_base64url(vector["signature_b64url"])
        self.assertEqual(encode_base64url(signature), vector["signature_b64url"])
        self.assertEqual(vector["signature_byte_length"], 64)
        self.assertEqual(vector["signature_hex"], signature.hex())
        self.assertEqual(len(signature), 64)
        self.assertEqual(vector["signature_component_byte_length"], 32)
        self.assertIn("raw P-256 R || S", vector["signature_format"])
        self.assertIn("not ASN.1 DER", vector["signature_format"])


if __name__ == "__main__":
    unittest.main()
