# Packages and flavors

## Packages

| Package | Contents |
|---|---|
| `Ranvier.WebCore` | Managed interop: the `RanvierWebCoreAbi.Native` and `NativeDom` modules, and the shared DOM contracts. Pairs with the same version of the native packages. |
| `Ranvier.WebCore.Native` | The default aggregate: depends on the four GPU runtime packages and the CPU `win-arm64` package, all at exactly its own version. The runtime identifier selects the native assets at restore. |
| `Ranvier.WebCore.Native.<rid>` | GPU flavor for `win-x64`, `linux-x64`, `linux-arm64` and `osx-arm64`. |
| `Ranvier.WebCore.Native.Cpu` | Aggregate that depends on the five CPU runtime packages at exactly its own version. |
| `Ranvier.WebCore.Native.Cpu.<rid>` | CPU (Slim) flavor for one runtime: `win-x64`, `win-arm64`, `linux-x64`, `linux-arm64`, `osx-arm64`. |
| `Ranvier.WebCore.Native.Gpu` | The default aggregate's former name: depends only on `Ranvier.WebCore.Native` at its own version, so existing references restore the same runtimes. |
| `Ranvier.WebCore.Native.Lean.<rid>` | Reference flavor: WebKit with every patch option at its default. Built on explicit request; not part of a release cohort. |
| `Ranvier.WebCore.Accessibility.Atspi` | Optional Linux AT-SPI provider for `linux-x64`. See `providers/atspi/README.md`. |

A release is one version across the managed package, the aggregates, the five CPU runtimes, the four GPU runtimes
and the AT-SPI provider, published together from one tag run.

Up to `0.1.1-rc.3`, `Ranvier.WebCore.Native` and `Ranvier.WebCore.Native.<rid>` were the Slim (CPU) flavor and the GPU
flavor was `Ranvier.WebCore.Native.Gpu` and `Ranvier.WebCore.Native.Gpu.<rid>`. From the release that follows, the
GPU flavor is the default package and the Slim flavor is `.Cpu`; the manifest's `flavor` keeps the build names,
`slim` and `gpu`.

The native packages, the managed package and the host must agree on the ABI version. Each native package
records it, with the WebKit commit, the source commit and every file's SHA-256, in `manifest.json`.

## Choosing a flavor

| Flavor | Use when | Painting |
|---|---|---|
| GPU (default) | Any app that presents frames: accelerated compositing, GPU painting and a native GPU frame without CPU readback, as a shared D3D11 texture on Windows, an EGLImage on Linux or an IOSurface on macOS. | Composited frames: GPU raster (`rv_host_set_gpu_painting`), CPU raster where no GPU context exists; other frames CPU |
| CPU (Slim) | The app needs the smallest package, no GPU code, or pixels that do not depend on the GPU, such as screenshot tests compared across machines (in the GPU flavor, `rv_host_set_gpu_painting(host, 0)` gives CPU painting per host). | CPU |
| Lean | Comparing against unpatched WebKit. | CPU |

The CPU flavor, Slim, cuts WebKit to what presentation needs: no network stack, crypto library, GPU code, browser storage, service
workers, WebGPU, WebXR or inspector, and JavaScriptCore without its JIT tiers. GPU keeps every other cut and adds
the GPU code. `docs/SETTINGS.md` lists each setting; `docs/PATCHES.md` lists the patches. Package size depends on
the flavor and runtime: read `manifest.json` in the package or the `.nupkg` on nuget.org.

## Referencing

Reference `Ranvier.WebCore` and `Ranvier.WebCore.Native` at the same version to get the GPU runtimes:

```xml
<PackageReference Include="Ranvier.WebCore" Version="VERSION" />
<PackageReference Include="Ranvier.WebCore.Native" Version="VERSION" />
```

A `win-arm64` build gets the CPU host, since that runtime has no GPU build. A machine without a usable GPU driver
paints on the CPU with the GPU runtime: compositing and GPU painting fall back when their GL or Skia context cannot
be created (`rv_host_gpu_painting` reports it). To use the CPU flavor, reference `Ranvier.WebCore.Native.Cpu` in place
of `Ranvier.WebCore.Native`:

```xml
<PackageReference Include="Ranvier.WebCore" Version="VERSION" />
<PackageReference Include="Ranvier.WebCore.Native.Cpu" Version="VERSION" />
```

Reference one aggregate, never both, and not `Ranvier.WebCore.Native.Gpu` beside `Ranvier.WebCore.Native.Cpu`: the
restore graph would hold two `RanvierWebCoreHost` binaries for a runtime. A native consumer may reference
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
