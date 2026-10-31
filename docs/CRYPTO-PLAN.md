# B22 crypto plan

## Core and view state

- **Core primitives used:** none. Random values, UUIDs and digests are pure calls that return before the provider
  returns (a digest resolves through `Async`); no value outlives the call, so no owner, root, memo or projection is
  involved. The shared fixture activates no graph.
- **View-owned state:** none. The Views native provider holds the host, which is a native handle the core cannot
  hold, and reads the host's current document at each call. It keeps no cache, key table or queue.

**Goal:** `crypto.getRandomValues`, `crypto.randomUUID` and `crypto.subtle.digest` (SHA-1, SHA-256, SHA-384,
SHA-512) through one `CryptoService` on native and on Chromium (Ranvier.WebCore #119). Every other SubtleCrypto
algorithm and operation reads as `CryptoOutcome.Unsupported`. Keys, import, export, sign, verify, encrypt and derive
are a follow-up group.

**Trees:** native `C:/wk/native-crypto`, Core `C:/wk/rv-crypto-core`, Views `C:/wk/rv-crypto`, branch
`codex/native-api-crypto`, from H11 `6610b57` / `b1048a5f` / `6b48817`, with G09, H13, D14 and T06 merged forward.
Reservation: Native36/ABI44, DOM alpha.39, Views 0.1.29, backend alpha.29.

## Pinned source scope

- `page/Crypto.idl`: `getRandomValues([ReturnValue] ArrayBufferView)` and `[SecureContext] randomUUID()`, reached
  through `WindowOrWorkerGlobalScope.crypto`. `Crypto::getRandomValues` rejects a view that is not an integer or
  BigInt typed array with TypeMismatchError, then a view over 65536 bytes with QuotaExceededError.
- SubtleCrypto compiles on every port at the pin; the backend decides the algorithms. win-x64 and win-arm64 (slim,
  patch 0003 `USE_CRYPTO_STUB`) register SHA-1/256/384/512 only. linux-x64 and linux-arm64 (WPE) link libgcrypt and
  libtasn1 and register the full set, as osx-arm64 does through CommonCrypto. SubtleCrypto is promise-only, which the
  ABI has no transport for, so it is not bound; digests come from the established platform providers instead
  (System.Security.Cryptography on .NET, `crypto.subtle` on Chromium).

## Measured RED (Chromium 156.0.8078.4 new headless; Native31/ABI39)

`docs/crypto-evidence/chromium-red.json` (`crypto-red-browser.mjs`): integer and BigInt views fill and return the same
object; Float16/32/64 and DataView raise TypeMismatchError at every length; 65536 bytes fill and 65544 raise
QuotaExceededError (Uint32Array 16384 / 16385); an empty view fills; a subarray writes only its range. randomUUID is
36 lowercase characters, version 4, variant 8/9/a/b. On `about:blank` (insecure) randomUUID and `crypto.subtle` are
undefined; on `http://localhost` both exist. `red-native31.json`: no crypto export or feature.

## Native surface (ABI44, additive, `rv_abi_has("dom-crypto-random")`)

- `rv_dom_crypto_get_random_values(document, kind, bytes, byteLength)`: `kind` is an `RV_DOM_ARRAY_BUFFER_VIEW_*`
  element kind. The glue builds a view of that kind over a copy of the bytes, calls `Crypto::getRandomValues`, and
  copies the bytes back on `RV_OK`. A byte length that is not a multiple of the element size raises RangeError; an
  unknown kind returns `RV_ERR_UNSUPPORTED`.
- `rv_dom_crypto_random_uuid(document, buffer, capacity, length)`.
- The generator gains `windowObjectBindings` (operations of the object a readonly Window attribute holds) and
  `typedArrayViewTypes` (a top-level `[ReturnValue]` view as an in/out span). Both functions are facades.
- The host exposes no page script, so neither function checks `[SecureContext]`.

## Proof

- Generator: three tests failed before the change (`generator-red.log`) and pass after it.
- `tests/abi/crypto_random.py` replays `tests/fixtures/crypto-random-oracle.json` by properties only, plus null,
  thread, interface, kind and capacity errors and a document kept past `rv_host_destroy`, which keeps working as a
  detached browser window does. It runs on every slim runtime (build.yml) and 30 times on the frozen runtime.
- The teardown driver holds a document with crypto past destroy.
- Managed: `CryptoChecks` runs on native JIT, NativeAOT and Chromium; Chromium also runs `http://insecure.test`, where
  randomUUID and digest read as Unsupported.

## Qualifications

- **Secure context.** Native: always available. Fable: an insecure context reads randomUUID, digest and digest
  availability as Unsupported.
- **Copied ranges.** A provider fills a copy and writes it back, so the range needs no element alignment.
- **Digest provider.** Native digests come from .NET, not from the engine's SubtleCrypto; the values are defined by
  FIPS 180 and the fixture checks published vectors on both engines.
