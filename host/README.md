# host

The C ABI Ranvier's WebCore view calls, built as `RanvierWebCoreHost.dll`.

- `RanvierWebCoreAbi.h`: the boundary (C scalars, UTF-8 strings, opaque handles, an RGBA8 buffer).
  `rv_abi_version()` returns 11; `scripts/build.py package` records it in `manifest.json`.
- `RanvierWebCoreAbi.cpp`: its implementation over WebCore.
- `RanvierWebCoreHost.cmake`: appended to `Tools/TestWebKitAPI/CMakeLists.txt` by `build.py prepare`. The
  target links TestWebCore's libraries without `gtest` and `WebCoreTestSupport`.

These files come from Ranvier's `evidence/webcore-host/abi` (branch `codex/native-webcore-feasibility`,
commit `6fadb812`). Ranvier's managed bridge must match the ABI version; change both together.
