# Ranvier.WebCore.Native

WebCore, JavaScriptCore and `RanvierWebCoreHost.dll`, the C ABI that Ranvier's WebCore view calls, for one
runtime identifier. The package puts the DLLs in `runtimes/<rid>/native/`, so a .NET project that
references it finds `RanvierWebCoreHost.dll` by name.

- `runtimes/<rid>/native/WebKit.resources/icons`: images WebCore reads from beside `WebCore.dll` (the
  broken-image icon among them). A build or publish with a runtime identifier flattens native assets,
  so `buildTransitive/<id>.targets` copies this folder to `WebKit.resources` in the output.
- `include/RanvierWebCoreAbi.h`: the C ABI.
- `manifest.json`: the build flavor, the WebKit commit, and each DLL's size and SHA-256.

Built by https://github.com/<owner>/ranvier-webcore from the WebKit commit in `manifest.json` with the
patches and settings documented there.
