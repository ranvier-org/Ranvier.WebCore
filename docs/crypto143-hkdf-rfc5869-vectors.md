# HKDF vector provenance

`tests/fixtures/crypto-hkdf-rfc5869.json` transcribes all seven test cases in Appendix A of [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869.html): A.1–A.3 use SHA-256 and A.4–A.7 use SHA-1. The IKM, salt, info, requested output length, PRK, and OKM are copied from the RFC; expected outputs were not calculated from project code.

RFC 5869 §2.2 says an omitted salt defaults to `HashLen` zero octets. The fixture preserves that separately from an explicitly empty salt: A.3 and A.6 use `salt_hex: ""` with `salt_presence: "empty"`; A.7 uses `salt_hex: null` with `salt_presence: "omitted"`. Empty `info` remains an explicit zero-length string in A.3, A.6, and A.7.

`tests/test_crypto_hkdf_vectors.py` checks case coverage, hex syntax, and declared octet lengths only. It does not implement HKDF or derive expected values.
