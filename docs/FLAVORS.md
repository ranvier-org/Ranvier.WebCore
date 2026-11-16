# Flavors and runtimes

A native package is one **flavor** built for one **runtime**. The flavor decides which parts of WebKit are compiled
in. The runtime decides which WebKit port is built, and with it the drawing library, the font stack and the kind of
GPU frame the host can hand over. This page describes both, and what a host sees differently on each.

[Packages and flavors](PACKAGES.md) lists the package ids and how to reference them. [Build settings](SETTINGS.md)
gives the reason and measured size of each CMake setting.

## The three flavors

| Flavor | Build name | Package | What it is |
|---|---|---|---|
| GPU | `gpu` | `Ranvier.WebCore.Native`, `Ranvier.WebCore.Native.<rid>` | The slim flavor with the GPU code kept: ANGLE, Skia's GPU backend, the layer compositor and WebGL. The default. |
| CPU | `slim` | `Ranvier.WebCore.Native.Cpu`, `Ranvier.WebCore.Native.Cpu.<rid>` | WebKit cut to what presentation needs. Every frame is painted on the CPU. |
| Lean | `lean` | `Ranvier.WebCore.Native.Lean.<rid>` | WebKit with every patch option at its default. A reference to compare against, built on request and not released. |

The build name is what `scripts/build.py --flavor` takes and what a package's `manifest.json` records as `flavor`.
The package names changed after `0.1.1-rc.3`: before it, the unsuffixed packages were the CPU flavor
([Packages and flavors](PACKAGES.md)).

A flavor is a CMake cache script in `config/`, loaded with `cmake -C`:

- `gpu.cmake` sets its values, then includes `slim.cmake`.
- `slim.cmake` and `lean.cmake` each include `common.cmake`.
- `common.cmake` includes `wpe.cmake` for a `linux-*` runtime and `mac.cmake` for an `osx-*` runtime.

A cache entry set first is kept, so the order of evaluation is the order of precedence: `gpu.cmake`, then the port
file, then the rest of `common.cmake`, then `slim.cmake` or `lean.cmake`.

## Runtimes

| Runtime | CPU flavor | GPU flavor | WebKit port |
|---|---|---|---|
| `win-x64` | yes | yes | Win |
| `win-arm64` | yes | no | Win |
| `linux-x64` | yes | yes | WPE |
| `linux-arm64` | yes | yes | WPE |
| `osx-arm64` | yes | yes | Mac (Cocoa) |

`win-arm64` has no GPU build. The `Ranvier.WebCore.Native` aggregate gives that runtime the CPU host.

## What the port decides

| | Windows | Linux | macOS |
|---|---|---|---|
| 2D drawing | Skia | Skia | CoreGraphics |
| Text | Skia, with the host's generic-family mapping ([Hosting a page](HOSTING.md#page-content)) | FreeType, HarfBuzz and fontconfig from the distribution | CoreText |
| GPU frame handed to the app | shared D3D11 texture | EGLImage | IOSurface |
| GPU compositing runs on | OpenGL ES through ANGLE over D3D11 | OpenGL ES through EGL | IOSurface and Metal (`RANVIER_MAC_GPU_SPIKE`) |
| ICU | filtered data DLL in the package | static, inside `libRanvierWebCoreHost.so` | the system's `libicucore` |
| Touch input | yes | yes | reported unsupported |
| Oldest system | not stated | the distribution libraries in `scripts/linux-runtime-packages.txt` | macOS 26.0 (`CMAKE_OSX_DEPLOYMENT_TARGET`) |

Two consequences for an app that compares frames:

- **macOS pixels differ from the Skia ports'.** CoreGraphics and CoreText draw and shape differently.
- **A composited frame can differ from a CPU frame, and between GPUs.** A GPU-painted one differs further, in
  antialiasing and blur. For pixels that do not depend on the machine, use the CPU flavor, or turn compositing off
  on the host (`RV_COMPOSITING_OFF`). `rv_host_set_gpu_painting(host, 0)` alone moves layer painting to the CPU
  and still composites on the GPU.

## What every flavor shares

From `config/common.cmake`:

| Setting | Effect |
|---|---|
| `CMAKE_BUILD_TYPE=Release` | Optimised for speed, not size. |
| JIT tiers off (`ENABLE_JIT`, `ENABLE_DFG_JIT`, `ENABLE_FTL_JIT`) | JavaScriptCore runs on its interpreter. The host evaluates no page script. |
| `ENABLE_WEBASSEMBLY=OFF` | Off on Windows and Linux. On macOS it stays on, on the in-place interpreter, because the Cocoa bindings do not compile without it. |
| `USE_SYSTEM_MALLOC=OFF` | bmalloc and libpas on every port. |
| `ENABLE_POINTER_LOCK=ON` | Pointer lock on every port. |
| `ENABLE_TOUCH_EVENTS=ON` | Windows and Linux only. |
| `USE_JPEGXL=OFF`, `USE_AVIF=OFF` | No JPEG XL or AVIF decoding. |
| `RANVIER_ENABLE_PDF=ON` | The native PDF writer ([PDF output](PRINTING.md)). |

JavaScriptCore is in every package because WebCore's types are built on it. A host disallows entry into the
virtual machine, so a page's scripts do not run ([Hosting a page](HOSTING.md#page-content)).

## What the CPU flavor cuts

Each cut is a WebKit option or a patch of this repository whose option defaults to off. [The patch series](PATCHES.md)
describes each patch.

| Setting | Patch | Removes |
|---|---|---|
| `USE_ANGLE_STUB` | 0001 | ANGLE. Its EGL and GLES entry points remain and fail. |
| `USE_NETWORK_STUB` | 0002 | curl and libpsl. No network loads. |
| `USE_CRYPTO_STUB` | 0003 | OpenSSL. Web Crypto keeps the SHA digests. |
| `USE_GPU_STUB` | 0004 | The GPU code in WebCore and Skia. |
| `USE_WEB_API_STUB` | 0005 | IndexedDB, caches, service and shared workers, push, WebSocket. |
| `USE_SQLITE_STUB` | 0006 | SQLite. |
| `USE_BROWSER_API_STUB` | 0007 | WebGPU, WebXR, File System, WebTransport. |
| `USE_INSPECTOR_STUB`, `USE_JSC_INSPECTOR_STUB` | 0008, 0009 | The WebCore and JavaScriptCore inspectors. |
| `ENABLE_WEBGL`, `ENABLE_VIDEO`, `ENABLE_XSLT`, `ENABLE_REMOTE_INSPECTOR`, `ENABLE_WEBDRIVER` | WebKit's own | WebGL, media playback, XSLT, the remote inspector, WebDriver. |
| `USE_LCMS=OFF` | WebKit's own | Colour management. |

Two more options apply to `win-*` runtimes only. Both were merged on 2026-11-16, after the 0.1.3 packages, and ship
with the release that follows. [Memory](MEMORY.md) gives their measurements.

| Setting | Patch | Effect |
|---|---|---|
| `USE_LIBPAS_LAZY_COMMIT` | 0084 | libpas reserves its large mappings and commits them as they are used. |
| `USE_INTERFACE_OBJECT_STUB` | 0085 | Script bindings are generated without interface objects (`window.Node` and the like). |

One setting adds a facility rather than removing one: `USE_AX_EMBEDDER_NOTIFICATIONS` (patch 0011) sends
accessibility notifications to the host ([Accessibility](ACCESSIBILITY.md)).

## What the GPU flavor adds back

`config/gpu.cmake` turns three of the cuts off again and keeps every other one:

| Setting | Value | Brings back |
|---|---|---|
| `USE_ANGLE_STUB` | OFF | ANGLE |
| `USE_GPU_STUB` | OFF | Skia's GPU backend and the layer compositor (TextureMapper) |
| `ENABLE_WEBGL` | ON | WebGL |

On Linux it also sets `USE_RANVIER_STANDALONE_COMPOSITOR=ON` and `ENABLE_ASYNC_SCROLLING=OFF`. On `osx-arm64` it
sets `RANVIER_MAC_GPU_SPIKE=ON`, and its `ENABLE_WEBGL=ON` wins over `mac.cmake`'s `OFF`.

The network, crypto, storage, browser API and inspector cuts stay. A GPU package is the CPU package plus the GPU
code, not a fuller browser.

## Where the port overrides the flavor

- **Linux keeps Skia's GPU backend in every flavor.** `config/wpe.cmake` sets `USE_GPU_STUB=OFF` before `slim.cmake`
  runs, because WPE's WebCore links that backend whatever the compositing setting. The Linux CPU flavor still
  paints every frame on the CPU: its host is built without compositing. A Linux package also loads distribution
  libraries at run time, libsoup, SQLite and libepoxy among them (`scripts/linux-runtime-packages.txt`).
- **macOS keeps most of the Cocoa port.** Video, the remote inspector and WebAssembly stay on, and WebGPU, WebRTC,
  AV1 and media stream stay at the port's defaults, because WebCore's Cocoa sources do not compile without them
  ([Build settings](SETTINGS.md)). The patches hook the Windows platform files, so on macOS
  only 0001, 0011 and 0013 act.
- **Windows alone has patches 0084 and 0085.** `pas_config.h` rejects lazy commit on any other system; elsewhere
  the kernel already backs a mapping on first touch.

## What a host sees differently

| Behaviour | CPU flavor | GPU flavor |
|---|---|---|
| Compositing mode of a new host | `RV_COMPOSITING_OFF` | `RV_COMPOSITING_WHEN_NEEDED` |
| `rv_host_set_accelerated_compositing` with a mode other than off | `RV_ERR_UNSUPPORTED`, mode unchanged | accepted; `RV_COMPOSITING_ALWAYS` fails when no GL context can be created |
| 3D transforms and backdrop filters | 3D transforms are drawn flat and backdrop filters are ignored | rendered in composited frames |
| `rv_host_set_gpu_painting(host, 1)` | `RV_ERR_UNSUPPORTED` | on for a new host on Windows and Linux; `RV_ERR_UNSUPPORTED` on macOS, which draws with CoreGraphics |
| `rv_host_acquire_d3d11_frame`, `rv_host_acquire_egl_frame`, `rv_host_acquire_iosurface_frame` | `RV_ERR_UNSUPPORTED` | a frame without CPU readback, on the matching platform |
| `rv_host_paint_rgba` | always works | always works |
| Display-P3 snapshots | not compiled in | ask the `snapshot-display-p3` capability |

`rv_host_paint_rgba` is the path every flavor and runtime has. An app that calls a GPU function and gets
`RV_ERR_UNSUPPORTED` paints with it instead.

## The GPU flavor without a GPU

The GPU runtime does not need a GPU to run:

- `RV_COMPOSITING_WHEN_NEEDED` creates the GL context on the first composited frame. If that fails, the host
  switches to `RV_COMPOSITING_OFF` and paints that frame on the CPU.
- When Skia's GL context cannot be created, frames are painted on the CPU whatever `rv_host_set_gpu_painting`
  says. `rv_host_gpu_painting` reports which is in effect.
- A frame that does not composite (the mode is off, or it is when-needed and the page has no composited layer) is
  painted on the CPU.

Machines where this happens: no usable GPU driver, some virtual machines, some remote sessions.

## Choosing

| The app | Flavor |
|---|---|
| presents animated frames in a window | GPU |
| uses 3D transforms, backdrop filters or WebGL | GPU |
| embeds its own GPU textures in the page (`rv_host_bind_*`) | GPU |
| compares screenshots across machines | CPU, or GPU with compositing off (`RV_COMPOSITING_OFF`) |
| runs headless, in CI or in a container without a GPU | CPU |
| wants the smallest package | CPU |
| targets `win-arm64` | CPU (the only build) |
| compares against unpatched WebKit | Lean |

Reference one aggregate, never both. The restore graph would otherwise hold two `RanvierWebCoreHost` binaries for a
runtime.

## Finding out what is loaded

| Question | Ask |
|---|---|
| Which flavor is this package? | `flavor` in the package's `manifest.json`: `slim`, `gpu` or `lean`. |
| Which ABI is the library? | `rv_abi_version()`. |
| Does it export a group of functions? | `rv_abi_has(name)` ([The C ABI and header](ABI.md#detecting-features)). |
| Was it built with a given option? | The build-option capability queries ([Capability queries](CAPABILITIES.md)). Every `USE_` and `ENABLE_` option set in `config/*.cmake` is in `host/RanvierCapabilityCatalogue.inc`. |
| Is this host compositing? | Whether `rv_host_set_accelerated_compositing` accepted the mode. |
| Is this host painting on the GPU? | `rv_host_gpu_painting(host)`. |

## Building a flavor

```
python -I scripts/build.py all --flavor gpu --rid win-x64 --work C:/rw
```

`--flavor` is `slim` (the default), `gpu` or `lean`. `--rid` is one of the five runtimes and defaults to `win-x64`.
The steps are `fetch`, `prepare`, `configure`, `build`, `package` and `smoke`; `all` runs them in order. Each flavor
builds into its own tree, `<work>/build-<flavor>`. [CI](CI.md#local-runs) covers the tools a workstation needs and
the options that point at existing checkouts.

A new `USE_` or `ENABLE_` option in `config/*.cmake` needs the capability catalogue regenerated
(`python -I scripts/capability_catalogue.py`). CI's `package-contract` job fails with "Capability catalogue is
stale" otherwise.
