# Packages and flavors

## Packages

| Package | Contents |
|---|---|
| `Ranvier.WebCore` | Managed interop: the `RanvierWebCoreAbi.Native` and `NativeDom` modules, and the shared DOM contracts. Pairs with the same version of the native packages. |
| `Ranvier.WebCore.Native` | Aggregate that depends on the five Slim runtime packages at exactly its own version. The runtime identifier selects the native assets at restore. |
| `Ranvier.WebCore.Native.<rid>` | Slim flavor for one runtime: `win-x64`, `win-arm64`, `linux-x64`, `linux-arm64`, `osx-arm64`. |
| `Ranvier.WebCore.Native.Gpu` | Aggregate that depends on the four GPU runtime packages and the Slim `win-arm64` package, all at exactly its own version. |
| `Ranvier.WebCore.Native.Gpu.<rid>` | GPU flavor for `win-x64`, `linux-x64`, `linux-arm64` and `osx-arm64`. |
| `Ranvier.WebCore.Native.Lean.<rid>` | Reference flavor: WebKit with every patch option at its default. Built on explicit request; not part of a release cohort. |
| `Ranvier.WebCore.Accessibility.Atspi` | Optional Linux AT-SPI provider for `linux-x64`. See `providers/atspi/README.md`. |

A release is one version across the managed package, both aggregates, the five Slim runtimes, the four GPU runtimes
and the AT-SPI provider, published together from one tag run.

The native packages, the managed package and the host must agree on the ABI version. Each native package
records it, with the WebKit commit, the source commit and every file's SHA-256, in `manifest.json`.

## Choosing a flavor

| Flavor | Use when | Painting |
|---|---|---|
| Slim | The app reads CPU pixels (`rv_host_paint_rgba`) or needs the smallest package. | CPU |
| GPU | The app wants accelerated compositing and a native GPU frame without CPU readback: shared D3D11 texture on Windows, EGLImage on Linux, IOSurface on macOS. | CPU, or GPU per `rv_host_set_accelerated_compositing` |
| Lean | Comparing against unpatched WebKit. | CPU |

Slim cuts WebKit to what presentation needs: no network stack, crypto library, GPU code, browser storage, service
workers, WebGPU, WebXR or inspector, and JavaScriptCore without its JIT tiers. GPU keeps every other cut and adds
the GPU code. `docs/SETTINGS.md` lists each setting; `docs/PATCHES.md` lists the patches. Package size depends on
the flavor and runtime: read `manifest.json` in the package or the `.nupkg` on nuget.org.

## Referencing

Reference `Ranvier.WebCore` and `Ranvier.WebCore.Native` at the same version to get the Slim runtimes:

```xml
<PackageReference Include="Ranvier.WebCore" Version="VERSION" />
<PackageReference Include="Ranvier.WebCore.Native" Version="VERSION" />
```

To use the GPU flavor, reference `Ranvier.WebCore.Native.Gpu` in place of `Ranvier.WebCore.Native`:

```xml
<PackageReference Include="Ranvier.WebCore" Version="VERSION" />
<PackageReference Include="Ranvier.WebCore.Native.Gpu" Version="VERSION" />
```

A `win-arm64` build then gets the Slim host, since that runtime has no GPU build. Reference one aggregate, never
both: the restore graph would hold two `RanvierWebCoreHost` binaries for a runtime. A native consumer may reference
a single runtime package directly.

A package carries, for one runtime identifier:

- `runtimes/<rid>/native/`: `RanvierWebCoreHost` (`.dll`, `.so` or `.dylib`), WebCore, JavaScriptCore and their
  dependencies.
- `runtimes/<rid>/native/WebKit.resources/icons`: images WebCore reads from beside the library. A build or publish
  with a runtime identifier flattens native assets, so `buildTransitive/<id>.targets` copies this folder to
  `WebKit.resources` in the output for that runtime only.
- `include/RanvierWebCoreAbi.h`: the C ABI (see `docs/ABI.md`).
- `manifest.json`, `NOTICE.md`.

## Licensing

Each package carries `NOTICE.md` (the repository's `NOTICE.md`), the third-party component table. The AT-SPI provider
package carries its own `NOTICE.md`, `THIRD-PARTY.md` and `licenses/LGPL-2.1.txt`.
