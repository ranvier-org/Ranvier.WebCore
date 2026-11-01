# RFC HMAC test vectors

- [RFC 4231](https://www.rfc-editor.org/rfc/rfc4231.html), section 4, test cases 1-7: HMAC-SHA-256, HMAC-SHA-384, and HMAC-SHA-512.
- [RFC 2202](https://www.rfc-editor.org/rfc/rfc2202.html), section 3, test cases 1-7: HMAC-SHA-1. Section 1 specifies that the terminating NUL is excluded from ASCII-string inputs.

The JSON files preserve the published key, message, and MAC bytes. RFC 4231 test case 5 publishes 128-bit prefixes for each listed hash; those entries are marked truncated_prefix and contain only the published 16 bytes. RFC 2202 test case 5 publishes both the full HMAC-SHA-1 digest and its 96-bit prefix. No missing full output is invented, and no prefix is treated as a full sign/verify output.

The Python checks validate case coverage, hex parsing, and declared byte lengths only. They do not calculate HMAC or establish backend/runtime acceptance.
