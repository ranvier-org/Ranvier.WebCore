# ranvier-webcore

Builds WebKit's WebCore and JavaScriptCore with Ranvier's C ABI host (`RanvierWebCoreHost`) and packs them
as a NuGet native package, `Ranvier.WebCore.Native.<rid>`. Ranvier's WebCore view loads
`RanvierWebCoreHost.dll` through P/Invoke.

The shipped build, **slim**, is WebKit's Windows port cut to what presentation needs: no network stack,
crypto library, GPU code, browser storage, service workers, WebGPU, WebXR or inspector, and JavaScriptCore
without its JIT tiers. It is
77.59 MB in 18 DLLs, against 125.84 MB in 31 for the **lean** reference build.

| | |
|---|---|
| WebKit | `b95c91b1c0ee43cc86d25ff7af73038f67a88e04` (`pins.json`) |
| Runtimes | `win-x64`; other runtimes in `docs/CI.md` |
| Toolchain | clang-cl 23.1.4, MSVC 14.50, vcpkg at `pins.json`'s commit |

## Layout

| Path | Contents |
|---|---|
| `pins.json` | Every external version: WebKit, vcpkg, LLVM, ICU, the package version |
| `patches/` | The WebKit patch series, applied in `series` order (`docs/PATCHES.md`) |
| `host/` | The C ABI (`RanvierWebCoreAbi.h`, `.cpp`) and the CMake target added to `Tools/TestWebKitAPI` |
| `config/` | CMake settings per flavor (`docs/SETTINGS.md`) |
| `scripts/` | `build.py` (fetch, prepare, configure, build, package), `patches.py`, `icu_data.py`, `angle_stub.py` |
| `packaging/` | The project `dotnet pack` turns the staged DLLs into a package |
| `.github/workflows/build.yml` | CI (`docs/CI.md`) |
| `docs/UPDATING.md` | Moving to a new WebKit commit |
| `docs/VERIFICATION.md` | What the first build checked, and what it did not |

## Build

On Windows with Visual Studio's x64 C++ build tools, Python 3.12+, Perl, Ruby and gperf:

```
python -I scripts/build.py all
```

This clones WebKit and vcpkg at their pins into `C:/rw`, downloads LLVM, applies the patches, installs the
host, configures, builds and packs. The package lands in `C:/rw/packages`, and the staged files, with
`manifest.json` listing each DLL's size and SHA-256, in `C:/rw/out/slim`.

## Rules for changes

- One concern per patch, behind a CMake option that defaults to OFF, so the patches stay easy to carry to
  new WebKit releases and a default build is unaffected.
- Patches add files and CMake hunks; they do not edit upstream C++ or IDL files (0003 is the one
  exception, `docs/PATCHES.md`).
- Generate stubs from upstream headers where a member list follows a header.
- Speed over size: the build stays at `/O2`.
