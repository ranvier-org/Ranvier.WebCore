# AES key-wrap vector provenance

`tests/fixtures/crypto-aes-kw-rfc3394.json` transcribes the six known-answer cases in [RFC 3394](https://www.rfc-editor.org/rfc/rfc3394.html), Section 4, cases 4.1–4.6. It records each KEK, plaintext key data, and ciphertext as listed in the RFC. The fixture's default IV is copied from Section 2.2.3.1 (`A6A6A6A6A6A6A6A6`).

The cases cover 128-, 192-, and 256-bit KEKs and key-data lengths of 128, 192, and 256 bits. They are the RFC 3394 AES Key Wrap (AES-KW) vectors, with the specified default IV. They are not AES Key Wrap with Padding vectors from RFC 5649.

`tests/test_crypto_aes_kw_vectors.py` checks case coverage, hex syntax, key/plaintext/ciphertext lengths, and the default IV size. It does not implement AES-KW or calculate expected ciphertext.
