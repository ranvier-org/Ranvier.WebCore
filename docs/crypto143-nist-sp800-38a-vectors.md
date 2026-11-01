# NIST SP 800-38A AES CBC and CTR examples

Fixture `tests/fixtures/crypto-aes-cbc-ctr-sp800-38a.json` transcribes the AES-128, AES-192, and AES-256 encryption examples from NIST SP 800-38A Appendix F.2 and F.5. The official NIST PDF URL, download size, and SHA-256 are recorded in the fixture. The downloaded PDF was used only for transcription and is not committed.

CBC examples are raw no-padding vectors over four full 16-byte blocks. WebCrypto AES-CBC adds PKCS#7 padding, so a future runtime test should compare the published 64-byte ciphertext prefix and separately test padded output length and decrypt roundtrip. The fixture contains no invented padded ciphertext.

CTR examples record the initial counter and each of the four published counter blocks in order. The rightmost 32-bit field varies in the NIST sequence; this is recorded as the replay counter width without asserting a normative width requirement. These files are input data only: the Python tests validate hex and byte lengths and do not run AES or establish backend support.
