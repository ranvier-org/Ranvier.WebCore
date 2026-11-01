# Proposed common WebCrypto corrections (reserved 0062)

Codex. This is a review proposal; no shared source application or engine patch generation has occurred. Windows owns canonical 0060, including only the unsupported-platform fallback guard in CryptoKeyOKP.cpp. The proposed JWK validation hunk is disjoint from that guard.

## Evidence and required behavior

Pinned CryptoKeyHMAC rejects non-byte generation/import, derives metadata from byte count, and passes byte storage to existing backends. Its generic generateKey already distinguishes present zero from absent and rejects zero with OperationError. Generic importKey currently discards that distinction through value_or(0); explicit zero must reject with DataError before the algorithm's usage validation.

Installed Chrome 156.0.8078.79, revision a21ce95c24ce3964416f09ae1862f53f319eb4d0, was measured in a genuine secure localhost context. This is a development control, not the pinned final Chromium acceptance version. Receipts are under the lane's crypto143/browser-control artifact directory.

- Generation accepts logical lengths 1, 7, 9, 153, 159 and 161, with ceiling-byte storage and cleared unused low bits. Generation zero rejects OperationError.
- Importing twenty 0b octets with length159 exports nineteen 0b octets followed by 0a. Metadata remains159, and signing Hi There produces 944edeba2ad096630491b7710d2697544996bc4442720577f59a1c8be13f9712. Length153 clears the last byte to00. Length152,161 and0 reject DataError for that input.
- AES-GCM raw/JWK wrap and unwrap preserve those canonical bytes. An explicit unwrap HMAC length159 preserves logical length159; an absent length yields160. Both sign the same canonical bytes. There is no nonstandard JWK field carrying the logical bit count.
- HKDF deriveKey to HMAC159 rejects OperationError because HKDF requires a byte-aligned derived length. Target zero rejects TypeError; absent target length derives512 bits, and160 succeeds. Preserve each derivation algorithm's constraints rather than rounding every request upward.

These results agree with the [HMAC operation rules](https://w3c.github.io/webcrypto/#hmac-operations). They require representation and byte normalization, not only a changed metadata value.

## Proposed HMAC representation

Keep an explicit logical bit length in CryptoKeyHMAC, alongside canonical byte storage. Its invariant is nonzero logical length, byte count equal to ceiling(length/8), and zero unused low bits of the final byte. Existing byte-aligned factory callers infer their logical length from byte count. Generation uses overflow-safe division/remainder to choose storage size, then masks the final byte. Raw/JWK import validates the requested length against the source bit count, masks the retained bits and stores the requested logical length.

algorithm().length, a small lengthBits accessor, and CryptoKey::Data.lengthBits use the stored logical length. Raw/JWK exports continue using canonical byte storage; existing HMAC backends therefore compute the same signatures as the browser control. CryptoKey::create already reconstructs HMAC via its JWK and Data.lengthBits, so its transport can preserve logical length after importRaw is fixed. Wrap/unwrap and deriveKey continue through the generic algorithms; no private export or derivation shortcut is introduced.

The existing structured-clone HMAC serializer stores only bytes and hash, so it would otherwise lose logical length. Before editing that wire format, review this compatibility proposal: retain key-format1 output for existing byte-aligned keys, write key-format2 only for a non-byte HMAC key with an explicit logical length field, and let the new reader accept both versions. Old readers already reject unsupported newer key versions; legacy bytes and other key classes remain unchanged. A VM-free CryptoKey::Data round trip plus legacy/new structured-clone round trips must verify this. No serialization version is allocated by this proposal.

## Proposed Ed25519 JWK correction

Change the common CryptoKeyOKP::importJwk Ed check from use=sign to use=sig. Keep the generic algorithm's usage/type checks, paired-key verification and extractability validation. X25519's generic importer already checks use=enc; its platform port does not replace that validation. The normative rules are in [Ed25519 import](https://w3c.github.io/webcrypto/#ed25519-operations) and [X25519 import](https://w3c.github.io/webcrypto/#x25519-operations).

The RFC8032 test1 key was used for a browser control: absent/sig succeed for public verify and private sign; sign/enc/empty reject DataError. Paired x/d mismatch, missing x, wrong curve/type, ext=false with extractable=true, omitted requested key_ops and duplicate key_ops reject DataError. Ed25519 and EdDSA alg values succeed; ES256 rejects DataError. Those are required native matrix rows, not claims that the existing lower C++ class validates every row. The host's typed JWK normalization must preserve the checks normally supplied by the script binding.

## Validation and boundaries

First compile/replay the current private TypeError-name fix, retaining the complete HMAC probe. Then demonstrate the engine bit-length RED before generating 0062, apply the reviewed common delta only in an owned overlay, and rerun all vector/error/ownership rows. Add explicit generate-zero, import-zero/error-order, byte boundary, metadata/export/signature, Data round-trip, wrap/unwrap and derive constraints. No catch-and-skip, qualification or shortened profile closes the issue.

Private common changes are expected in CryptoKeyHMAC.h/.cpp, CryptoAlgorithmHMAC.cpp and the disjoint CryptoKeyOKP.cpp validation line. SerializedScriptValue.cpp depends on review of the compatibility proposal above. No public Ranvier ABI, package version, generated kind, platform provider upgrade or shared build/configuration change is allocated here.
