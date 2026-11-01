# RFC 6070 PBKDF2-HMAC-SHA1 vectors

The fixture at `tests/fixtures/crypto-pbkdf2-rfc6070.json` transcribes all six test
vectors published in [RFC 6070, section 2](https://www.rfc-editor.org/rfc/rfc6070.html#section-2).
The RFC defines its inputs as ASCII strings and uses `\\0` to denote a literal NUL
octet; case 6 therefore records the byte inputs explicitly as hex as well as preserving
the RFC spelling.

The fixture validator checks JSON structure, case coverage, and input/output byte lengths.
It does not calculate PBKDF2 or claim runtime/backend acceptance. Case 4 is retained with
its exact cost of 16,777,216 iterations and is marked for deliberate scheduling; it must not
be silently omitted from later runtime coverage.
