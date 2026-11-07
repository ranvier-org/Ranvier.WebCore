# Ranvier.WebCore.Native

`Ranvier.WebCore` provides the managed `RanvierWebCoreAbi.Native` and `NativeDom` modules. Reference it alongside
the same version of `Ranvier.WebCore.Native`, which brings the runtime packages into the restore graph: the GPU
runtime for Windows x64, Linux x64/ARM64 and macOS ARM64, and the CPU runtime for Windows ARM64, which has no GPU
build. The runtime identifier selects the native assets. The aggregate pins exact runtime versions because their ABI
must agree.

The GPU runtime composites accelerated layers and paints them on the GPU (`rv_host_set_gpu_painting`). Where it
cannot create a GL or Skia context (no usable GPU driver, some virtual machines and remote sessions) it paints on the
CPU. For a package without the GPU code, or for frames that do not depend on the GPU, such as screenshot tests that
compare pixels across machines, reference `Ranvier.WebCore.Native.Cpu` (`packaging/cpu/`) instead, never both:
the restore graph would hold two `RanvierWebCoreHost` binaries for a runtime. `Ranvier.WebCore.Native.Gpu`, the
GPU aggregate's former name, depends on this package.

The individual runtime packages below can also be referenced directly by native consumers. The aggregate
and managed packages are built only after all five runtime artifacts have matching ABI, WebKit and source
identities. Tagged builds publish them through the repository's NuGet trusted publishing workflow.

WebCore, JavaScriptCore and `RanvierWebCoreHost.dll`, the C ABI that Ranvier's WebCore view calls, for one
runtime identifier. The package puts the DLLs in `runtimes/<rid>/native/`, so a .NET project that
references it finds `RanvierWebCoreHost.dll` by name.

- `runtimes/<rid>/native/WebKit.resources/icons`: images WebCore reads from beside `WebCore.dll` (the
  broken-image icon among them). A build or publish with a runtime identifier flattens native assets,
  so `buildTransitive/<id>.targets` copies this folder to `WebKit.resources` in the output for that runtime only.
- `include/RanvierWebCoreAbi.h`: the C ABI.
- `manifest.json`: the build flavor, the WebKit commit, and each DLL's size and SHA-256.

Built by https://github.com/ranvier-org/Ranvier.WebCore from the WebKit commit in `manifest.json` with the
patches and settings documented there.
