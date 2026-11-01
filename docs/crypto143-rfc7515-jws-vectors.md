# RFC 7515 RS256 and ES256 fixtures

`tests/fixtures/crypto-jws-rfc7515-signatures.json` transcribes the published
RS256 example in RFC 7515 Appendix A.2 and the ES256 example in Appendix A.3.
The source is [RFC 7515](https://www.rfc-editor.org/rfc/rfc7515.html).

The protected and payload base64url segments are preserved exactly, including
the payload's CRLF and space octets as represented by its published segment.
The signing input is the ASCII byte sequence `protected-segment + "." +
payload-segment`. JWK values and signature bytes are represented as published;
the JSON records decoded hex alongside base64url only as an alternate byte
representation for consumers and structural checks.

The ES256 signature is the RFC's raw 64-byte `R || S` sequence (32 bytes per
component), not ASN.1 DER. The fixture contains no generated SPKI/PKCS#8 value.
The examples can later supply import and verify controls. In particular, the
published ECDSA signature is not an expected output for a new signing call.

`python -m unittest discover -s tests -p test_crypto_jws_rfc7515_fixture.py`
checks JSON shape,
published segments, base64url decoding and declared byte lengths. It performs
no RSA/ECDSA signing or verification operation.
