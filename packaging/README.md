# Ranvier.WebCore.Native

`Ranvier.WebCore` provides the managed `RanvierWebCoreAbi.Native` and `NativeDom` modules. Reference it alongside
the same version of `Ranvier.WebCore.Native`, which brings the five runtime packages into the restore graph:
Windows x64/ARM64, Linux x64/ARM64 and macOS ARM64. The runtime identifier selects the native assets.
The aggregate pins exact runtime versions because their ABI must agree. Managed interop keeps the native
flavor selectable: an accelerated Windows app can reference the matching `Ranvier.WebCore.Native.Gpu.win-x64`
package instead of the aggregate, avoiding duplicate slim and GPU native assets.

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
