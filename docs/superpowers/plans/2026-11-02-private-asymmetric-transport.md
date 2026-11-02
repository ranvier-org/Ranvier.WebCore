# Private Asymmetric Transport Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task. Root has assigned the common facade to gpu_apis and the separate asymmetric module to windows_gpu; do not introduce another registry or edit another owner's files.

**Goal:** Add production RSA/EC/Ed25519/X25519 transport through the existing private crypto operation/key registry, preserving the full eleven-operation WebCrypto profile.

**Architecture:** A new asymmetric C++ module normalizes its typed C dictionaries and calls WebCore CryptoAlgorithm methods. The common owner provides opaque operation/key admission and result delivery, key pairs, complete JWK storage/codecs and cross-family export/import/wrap/unwrap/derived-target composition.

**Tech Stack:** C11/C++20 private contracts, pinned WebCore, Python ctypes/native fixtures, actual Windows LibreSSL 4.2.1 and WPE/libgcrypt.

**Spec:** `C:/wk/project2/crypto143/asymmetric-production-design/source-map.md`; root's explicit separate-module/shared-facade ownership ruling; selected ED22October2026 profile.

## Global constraints

- Base 619e122455bd9261360560ccefec109afc7c638a; carry only canonical 0067/0068 from reviewed241. Existing direct-fixture lineage and proof remain separately retained.
- windows_gpu owns only new AsymmetricGlue.cpp/.h/Contract.h and new production tests/fixtures. gpu_apis owns common Glue/Internal, pair/JWK results and shared composition.
- Root alone writes shared C:/wk/src and coordinates source/build windows. Private read-only compiler overlays require a root grant and a max-three native slot.
- No public rv_* ABI, feature/kind/version allocation, public package or capability claim in this private slice.
- Inputs are copied, keys retained while work is pending, one terminal result delivered through the owner document, and context teardown becomes AbortError.
- Preserve unsupported format/operation versus nonextractable precedence. In particular KDF export remains NotSupportedError before extractability checks.

## Review focus

- Public zero-usage keys are valid; secret/private zero-usage results reject where WebCrypto requires it.
- Pair take is atomic and once, with independent key-token lifetime after transfer.
- Complete JWK presence, exact encoded bytes and private fields survive export/wrap/unwrap; no octet-only projection.
- Caller mutation, token release, teardown and replacement between asynchronous stages cannot use freed inputs or deliver twice.
- Error precedence and C admission errors remain distinct from deferred WebCrypto errors, including missing versus empty and zero versus absent values.

### Task 1: Typed transport and layout

Files: new host/RanvierCryptoAsymmetricContract.h, host/RanvierCryptoAsymmetricGlue.h, tests/test_crypto_asymmetric_contract.py.

- [ ] Agree exact Internal functions and JWK/pair shapes with the common owner.
- [ ] Write a failing C11/C++20 compile/layout test that consumes the exact structs and field widths used by Python.
- [ ] Run it against the missing header and retain the RED diagnostic.
- [ ] Define size/presence-aware RSA/EC/OKP key, signature/OAEP/derive parameters and complete JWK/pair types, then verify C and C++ compatibility.
- [ ] Add a Python ctypes shape fixture and a private native-export presence RED against the unextended CD9 runtime.

### Task 2: Generate/import/export/key pairs

Files: new host/RanvierCryptoAsymmetricGlue.cpp and tests/abi/subtle_crypto_asymmetric.py; shared pair/JWK/export functions are common-owner work.

- [ ] Test pair metadata/usages, private extraction, one-time pair transfer, retained keys, wrong-result access and key release.
- [ ] Implement name/hash/curve/exponent/format normalization and actual generic generate/import callbacks using the agreed facade.
- [ ] Exercise raw/JWK/SPKI/PKCS8, exact RFC fixtures, malformed keys, nonextractability and 0067/0068 coordinate/scalar controls through production tokens.
- [ ] Prove zero-usage public imports and generated public halves remain valid.

### Task 3: Sign/verify and OAEP

- [ ] Add production-interface RFC7515/8032 verification, sign/verify roundtrips, RSA PSS salt0/7/32, OAEP labels and invalid-access/error-order controls.
- [ ] Implement actual generic sign/verify/encrypt/decrypt with copied inputs, retained key references and deferred results.
- [ ] Check verify-false is a Boolean success, not a transport or WebCrypto exception.

### Task 4: Derive and cross-family composition

- [ ] Add RFC5903/7748 production deriveBits and AES/HMAC deriveKey fixtures, omitted/zero/nonbyte/UINT32_MAX lengths and zero-peer errors.
- [ ] Implement ECDH/X derive parameter resolution, retaining both base and peer keys. Reuse the common owner's derived-target import/length helpers.
- [ ] Coordinate shared AES/RSA-OAEP wrap/unwrap tests across raw/JWK/SPKI/PKCS8 source and target formats without an asymmetric-only shortcut.
- [ ] Test release and owner-context teardown between each chain stage.

### Task 5: Actual qualification and handoff

- [ ] Compile/link only under an explicitly coordinated read-only native window, with private outputs and exact producer replacement counts.
- [ ] Run complete production asymmetric fixtures plus existing HMAC/AES/KDF/ownership regressions, preserving all failures and reporting per-platform scope.
- [ ] Hash protected inputs/producer/PCH/package bytes before and after, request independent source/runtime review, and push the clean checkpoint.
- [ ] After borrowers release, retain compact immutable source/proof, stop owned processes/slots and remove the disposable checkout and private outputs.

Public ABI/frontends/all-RID/JIT/AOT/browser closure remains required later. A direct-engine fixture or one platform's private transport does not close #143.
