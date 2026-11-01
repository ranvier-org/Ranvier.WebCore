# Windows WebCrypto backend trial

This candidate enables the pinned engine's OpenSSL-family WebCrypto backend for Windows slim and GPU
builds. Patch0060 adds the previously absent Ed25519/X25519 platform methods and registry entries. The
provider is the existing WebKit vcpkg overlay's LibreSSL4.2.1, not an ambient OpenSSL installation.

## Minimum configuration and package change

`config/slim.cmake` sets `USE_CRYPTO_STUB=OFF` only for Windows runtime identifiers. GPU includes this
file and retains its existing ANGLE/Ganesh/compositing overrides. The network, SQLite, browser and
inspector stubs remain enabled. Other ports retain their existing configuration and native providers.
Lean already uses the upstream OpenSSL-family backend default. No rendering or host presentation
behavior is selected by the crypto setting.

Existing patched `OptionsWin.cmake` then finds `OpenSSL::Crypto`, exposes `USE_OPENSSL`, and enables
`HAVE_RSA_PSS` through `wtf/Platform.h`. `PlatformWin.cmake` selects `platform/OpenSSL.cmake` instead of
`crypto/stub/CryptoStub.cmake`; PAL replaces its CryptoAPI digest implementation with the existing
OpenSSL digest unit. No extra CMake command-line override, public header or configure-script change is
needed. The reviewed patch0060 supplies three backend units, two registry registrations and source-list
entries, with only the matching unsupported-platform fallbacks excluded for `USE(OPENSSL)`.

The existing package dependency walk follows WebCore's DLL imports into the installed triplet. It
must include `crypto-57.dll`; the measured x64 provider DLL is1,483,776bytes with SHA256
`33ba954b40e44abb89517d908e3637e561cb7701762ce547334600acecff9e1c`. It does not need an allowlist or a
hardcoded DLL copy. SSL/TLS are not deliberately enabled; the actual final PE dependency closure must
confirm whether any additional DLL is imported. Windows native packages now include the unmodified
vcpkg LibreSSL copyright file at `licenses/LibreSSL-4.2.1.txt` (SHA256
`9853507b8821c3f277aa60bf554eade41441ef06b2df538d247183ad28789b7f`) and identify it in `NOTICE.md`.
Other existing notice limitations remain recorded. No dependency version or package version is changed.

## Predicted rebuild and isolation

Root must integrate the candidate, strict-prepare the source and run the content-aware cache helper
before handing over a build. Changing `USE_CRYPTO_STUB` changes generated `cmakeconfig.h` from the
CryptoStub macro to `USE_OPENSSL`, so expect a broad dependency-complete PCH/consumer rebuild rather
than a three-unit link. The platform source list replaces one stub unit with the existing OpenSSL
backend group plus the three new OKP units, and PAL changes its digest unit. This is a prediction;
the actual freshly configured Ninja dependency graph supplies the edge count. Do not reuse a
CryptoStub PCH to claim the registry or conditional backend paths compile.

Use the protected warm site only after an explicit root handoff, unchanged toolchain/interpreter and
`--work C:/wk/project2/windows-gpu` paths, process-local AMD64 environment, and jobs4. Stage a new
local-only crypto trial package separately from A1, T4 and batch3. No publication or ABI allocation is
part of this candidate. The root controls shared source/configuration mutation.

## Evidence and remaining gates

Before the change, actual CMake preload evaluation selected CryptoStub for all four Windows
RID/flavor combinations, and the package project lacked the provider notice: five RED assertions.
Afterward, four focused tests pass: actual slim/GPU CMake settings for both Windows architectures,
unchanged other-port settings, transitive crypto DLL closure, and packaged notice identity. The full
Python suite passes103tests with3environmental skips. Provider146 checks and the three unconditional
platform bodies' syntax evidence remain separate; they are not native WebCore qualification.

The full native trial must prove actual `USE_OPENSSL`/RSA-PSS registry compilation and linkage,
provider version/path and final package dependency imports, then run the shared vectors, actual
random key generation/export/invalid-key/error/lifetime cases and the complete common/GPU catalogue.
Common patch0062's HMAC bit-length/serialization and Ed JWK use correction are independently owned
and reviewed; no such changes are bundled into0060. The full issue143 profile still includes all
eleven operations: generateKey, importKey, exportKey, sign, verify, encrypt, decrypt, deriveBits,
deriveKey, wrapKey and unwrapKey, with ownership/extractability/usages and deferred error delivery.
Native JIT, NativeAOT and Chromium acceptance across the selected platforms remains pending.
