# ranvier-webcore

Builds WebKit's WebCore and JavaScriptCore with Ranvier's C ABI host (`RanvierWebCoreHost`) and packs them
as versioned native packages. `Ranvier.WebCore.Native` aggregates the five runtime packages;
`Ranvier.WebCore` provides the canonical managed interop. Ranvier's WebCore view loads the native host
through those declarations rather than copying them into its own sources.

The current ABI 24 development batch includes typed DOM transports, namespace and document factories,
shared .NET/Fable contracts, CSS support/registration, typed CSS values/maps, geometry values and native Windows UI Automation.
The generator emits 1,875 DOM functions across 143 selected native interfaces, with zero stubs;
[the generator guide](docs/GENERATOR.md) records scope, ownership and omitted members.
[Typed map delivery](docs/STYLE-PROPERTY-MAPS-PLAN.md) distinguishes private verification from remaining
platform/public acceptance. [Geometry delivery](docs/GEOMETRY-VALUES-PLAN.md) records point, rectangle, quad and matrix
producer verification and the remaining shared/platform/public gates. [Accessibility](docs/ACCESSIBILITY.md) lists the Windows bridge's supported
patterns and limitations.

The **slim** flavor cuts WebKit to what presentation needs: no network stack,
crypto library, GPU code, browser storage, service workers, WebGPU, WebXR or inspector, and JavaScriptCore
without its JIT tiers. The initial Windows measurement was 77.59 MB in 18 DLLs,
against 125.84 MB in 31 for the **lean** reference build; this is not a fresh size measurement of ABI 24.

| | |
|---|---|
| WebKit | `b95c91b1c0ee43cc86d25ff7af73038f67a88e04` (`pins.json`) |
| Runtimes | `win-x64`, `win-arm64`, `linux-x64`, `linux-arm64`, `osx-arm64`; build details in `docs/CI.md` |
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
| `docs/ACCESSIBILITY.md` | The accessibility tree and its events, for screen readers |
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

- One concern per patch. Feature-removal options default to OFF; documented correctness repairs apply
  in every flavor, as listed in `docs/PATCHES.md`.
- Keep upstream C++ corrections bounded and paired with permanent regressions in `tests/abi`.
- Generate stubs from upstream headers where a member list follows a header.
- Speed over size: the build stays at `/O2`.
