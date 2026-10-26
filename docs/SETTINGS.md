# Build settings

The CMake settings live in `config/` as `cmake -C` cache scripts: `common.cmake` for both flavors, then
`slim.cmake` or `lean.cmake`. `scripts/build.py` adds only machine paths (compilers, the vcpkg toolchain
file, `VCPKG_INSTALLED_DIR`) and the two non-CMake steps listed at the end.

Sizes are measured on Windows x64 (Ranvier's `evidence/ABI-EXPERIMENT.md`, gates 35 to 43). The lean
flavor's package is 125.84 MB in 31 files; the slim flavor's is 77.59 MB in 18 files.

## Toolchain

| Setting | Value | Reason |
|---|---|---|
| Generator | Ninja | WebKit's supported generator on Windows. |
| Compiler and linker | clang-cl and lld-link from LLVM 23.1.4 (`pins.json`) | WebKit's Windows port builds with clang-cl. |
| C++ library and SDK | MSVC 14.50.35717 (VS 18 Build Tools), through `vcvars64.bat` | The version every measurement used; `build.py` prints the version it finds. |
| `CMAKE_BUILD_TYPE` | Release | `/O2`: speed is preferred over package size. `/O1` would remove a further 13.56 MB. |
| Perl, Ruby, gperf, Python | Perl 5.40, Ruby 3.3.6, gperf 3.0.1, Python 3.14 locally | WebKit's code generators. |

## common.cmake (both flavors)

| Setting | Value | Reason |
|---|---|---|
| `PORT` | Win | |
| `VCPKG_TARGET_TRIPLET` | x64-windows-webkit | WebKit's overlay triplet (`WebKitLibraries/triplets`): dynamic, release only. vcpkg's port versions come from WebKit's own `vcpkg-configuration.json` baselines at the pinned commit. |
| `USE_JPEGXL`, `USE_AVIF` | OFF | Image formats presentation does not use; they add the libjxl and aom dependencies. |
| `ENABLE_API_TESTS` | ON | `RanvierWebCoreHost` is declared in `Tools/TestWebKitAPI` and links TestWebCore's libraries. Only `RanvierWebCoreHost` is built; the host leaves out `gtest` and `WebCoreTestSupport` (1.62 MB). |
| `ENABLE_MINIBROWSER` | OFF | |
| `ENABLE_JIT`, `ENABLE_DFG_JIT`, `ENABLE_FTL_JIT`, `ENABLE_WEBASSEMBLY*` | OFF | JavaScriptCore runs on its interpreter, as WebKit's Linux build. The host evaluates no script of its own. |
| `USE_SYSTEM_MALLOC` | OFF | bmalloc and libpas stay. The system malloc fails to compile on Windows: `bmalloc.h` calls `aligned_alloc`, which the CRT lacks. |

## slim.cmake

| Setting | Value | Reason |
|---|---|---|
| `VCPKG_MANIFEST_FEATURES` | web;skia;woff2 | Lean adds `lcms`. The `web` feature still installs curl, libpsl, OpenSSL and SQLite; the stubs leave them unlinked, so they are not packaged. |
| `USE_LCMS`, `ENABLE_XSLT` | OFF | Colour management and XSLT: 0.60 MB with libxslt. |
| `ENABLE_WEBGL`, `ENABLE_VIDEO`, `ENABLE_REMOTE_INSPECTOR`, `ENABLE_WEBDRIVER` | OFF | Browser features with no use in presentation. With the link folding below, WebKit's own options remove 3.78 MB from `WebCore.dll`. |
| `USE_*_STUB` | ON | The patch series; `docs/PATCHES.md`. |

## Outside CMake (slim only)

- **`_LINK_=/OPT:SAFEICF dwrite.lib`** in the build environment. lld-link appends `_LINK_` after its
  command line, so `/OPT:SAFEICF` overrides `OptionsMSVC.cmake`'s `/OPT:NOICF`: identical functions whose
  address is not taken are folded. `dwrite.lib` is linked because WebCore otherwise receives it only through
  `PlatformWin.cmake`'s MediaFoundation target, which `ENABLE_VIDEO=OFF` removes.
- **Filtered ICU data** (`scripts/icu_data.py`): `icudt77.dll` from 31.90 MB to 7.20 MB. Kept: break
  iterators and their dictionaries, normalisation, IDNA and stringprep, emoji and layout properties,
  converter aliases, supplemental data, and root and English locale data. Removed: converters, character
  names, transliteration and every other locale. The input is `icudt77l.dat` from ICU's release archive,
  checked against `pins.json`; it is the same file vcpkg's ICU port builds from.

## Package contents

`build.py package` stages the DLLs `RanvierWebCoreHost.dll` imports, transitively, from the build and
vcpkg directories, so vcpkg packages the stubs leave unlinked (curl, OpenSSL, SQLite and others) stay out.
It adds `WebKit.resources/icons` (six images, 3 KB), which `WebCoreBundleWin.cpp` reads from beside
`WebCore.dll`; without it a missing image draws no broken-image icon. The build's other
`WebKit.resources` folders, media controls and the inspector UI (8.8 MB), have no reader in the slim
flavor.

## What is measured and what is not

- Both flavors pass Ranvier's conformance run equally (1,011 of 1,039 cases) and render the F# driver's
  pages with identical pixels.
- Timing between the flavors is inconclusive: two sets of 8 alternating pairs disagree on direction.
- Not run: pages that reach Skia's SkSL decal or shader blur paths, page script calling the console,
  startup time and working set, WebKit's own test suites.
