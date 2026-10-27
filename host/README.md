# host

The C ABI Ranvier's WebCore view calls, built as `RanvierWebCoreHost.dll`.

- `RanvierWebCoreAbi.h`: the boundary (C scalars, UTF-8 strings, opaque handles, an RGBA8 buffer).
  `rv_abi_version()` returns 14; `scripts/build.py package` records it in `manifest.json`.
  `rv_abi_has()` names the groups of functions added since 11.
- `RanvierWebCoreAbi.cpp`: its implementation over WebCore. Each page has two clients of its own:
  - **Chrome client:** reports invalidations and rendering-update requests as the dirty rectangle and the
    frame callback (patch 0010).
  - **Editor client:** allows editing, and binds keys to editing commands as WebKitLegacy's Windows client
    did.
- `RanvierWebCoreHost.cmake`: appended to `Tools/TestWebKitAPI/CMakeLists.txt` by `build.py prepare`. The
  target links TestWebCore's libraries without `gtest` and `WebCoreTestSupport`.

Ranvier's `evidence/webcore-host/abi` (branch `codex/native-webcore-feasibility`) keeps a copy, and its
F# driver (`evidence/webcore-host/fsharp`) tests it; `Window.fs` covers version 12. Ranvier's managed
bridge must match the ABI version; change both together.
