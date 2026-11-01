# PBKDF2 empty-salt fallback proposal

Codex. Review checkpoint only: no0066 implementation or engine application yet. This addresses [WebCore237](https://github.com/ranvier-org/Ranvier.WebCore/issues/237) within143 without changing the selected profile.

## Evidence and provenance

The private007602 Linux bridge rejects a present empty PBKDF2 salt at positive output length. The public libgcrypt1.10.3 C probe rejects both NULL and non-NULL salt pointers at length0. Its public dispatcher checks salt length, so a pointer substitution cannot fix this. The newer KDF handle API does not support PBKDF2. All13primary HKDF/PBKDF2 rows, including16,777,216 iterations, pass; the current native candidate also passes AES3932/HMAC266/realserializer19.

The reference is [RFC8018 section5.2](https://www.rfc-editor.org/rfc/rfc8018#section-5.2), under the pinned WebCrypto ED22Oct2026 requirements. A vetted comparison implementation is [BoringSSL PKCS5_PBKDF2_HMAC](https://github.com/google/boringssl/blob/5ed1348ba336f2d205fdc17c863b6427c2d18607/crypto/evp/pbkdf.cc), source SHA256 `d89fbb3fe2bdc395af2c59824410a905a9691f56f68c424433f78aa7f358baec`. That source is Apache2.0; its exact LICENSE SHA256 is `827c8d8fc207c2392794eef9e00fe246f9f61fdcc132556c275be3dd8c3cd97f`.

Proposed code is independently written from the RFC algorithm, with BoringSSL used to review block limits and iteration structure. No BoringSSL or LGPL libgcrypt implementation text/comments will be copied. The existing WebKit port license remains, with this reference and independent authorship recorded. A later choice to copy implementation code would require separate attribution/license review.

## Narrow implementation

Only `CryptoAlgorithmPBKDF2GCrypt.cpp` changes. Nonempty salt retains the current `gcry_kdf_derive` path byte for byte. Empty salt enters a small internal helper using public `gcry_md_open` with HMAC, `gcry_md_setkey`, reset/write/read and RAII close. No private symbols, provider build, new dependency, public ABI or config change.

For each big-endian32-bit block index, calculate the first PRF over that four-byte index (salt is empty), then apply the RFC iteration/XOR recurrence and append only the requested block prefix. The password is passed with its exact length; an empty password gets a valid pointer with length0. The helper never substitutes a nonempty password/salt. The existing digest mapping covers SHA1/256/384/512. A public-HMAC API primitive probe will verify empty-key behavior before engine compilation.

Reject zero iterations. Generic deriveBits already handles null/non-byte lengths and the typed bridge preserves its explicit zero-iteration/zero-output rejection. Zero output remains an owning empty result for positive iterations. Before allocation, validate digest length and compute block count as `(outputBytes - 1) / hashBytes + 1`, avoiding addition/multiplication overflow; reject counts above UINT32_MAX. Use a64-bit loop index to prevent the last legal block increment from wrapping. The selected WebIDL output range remains unchanged.

The HMAC handle closes on every path. Explicitly initialized scratch arrays hold U and the XOR accumulator; all relevant bytes are overwritten before use, then wiped on success/error. A guarded output vector is wiped on failure and transferred normally on success. Allocation or provider failures return OperationError through the existing callback. This promises cleanup of introduced buffers, not forensic erasure of pre-existing engine key storage. Preserve provider FIPS restrictions: the empty-salt fallback must not bypass a mode that forbids empty salt.

## Required private proof

The baseline now isolates both empty-password and nonempty-password failures without preventing other validation cases. The test-only child covers16 empty/present combinations, exact target metadata/usages, derivation-hash versus HMAC-hash independence, copied target parameters, maximum HKDF expansion and all error/lifetime cases. It retains all13primary rows.

Before accepting0066, compare the fallback against independent standard-library results for all four hashes, iterations1/2/4096 and outputs0/1/hLen-1/hLen/hLen+1/multiple blocks, including empty and embedded-NUL passwords. Keep missing salt TypeError separate from valid empty salt. Preserve the nonempty provider path and16M primary vector. Compile/link only a private VFS closure after exact owner grants, then run full KDF/AES/HMAC/serializer plus independent backend qualification. Corrupt/error/cancellation cases must remain failures; no row is skipped or qualified away.
