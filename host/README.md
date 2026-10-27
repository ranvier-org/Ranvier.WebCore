# host

The C ABI Ranvier's WebCore view calls, built as `RanvierWebCoreHost.dll`.

- `RanvierWebCoreAbi.h`: the boundary (C scalars, UTF-8 strings, opaque handles, an RGBA8 buffer).
  `rv_abi_version()` returns 19; `scripts/build.py package` records it in `manifest.json`.
  `rv_abi_has()` names the groups of functions added since 11.
- `RanvierWebCoreAbi.cpp`: its implementation over WebCore. Each page has two clients of its own:
  - **Chrome client:** reports invalidations and rendering-update requests as the dirty rectangle and the
    frame callback (patch 0010).
  - **Editor client:** allows editing, and binds keys to editing commands as WebKitLegacy's Windows client
    did.
- `RanvierWebCoreHost.cmake`: appended to `Tools/TestWebKitAPI/CMakeLists.txt` by `build.py prepare`. The
  target links TestWebCore's libraries without `gtest` and `WebCoreTestSupport`.

`tests/abi` tests the ABI from F#. It has one module per area, and `Native.fs`'s P/Invoke declarations
are generated from the header by `tests/abi/generate_native.py`. Each change to the header goes with:

1. `python tests/abi/generate_native.py write`;
2. a test in `tests/abi`.

`build.py smoke` runs the tests against the staged package on Windows and macOS, through
`scripts/abi_tests.py`. Ranvier's managed bridge must match the ABI version, so change both together.
