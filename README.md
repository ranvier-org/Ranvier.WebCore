# Ranvier.WebCore

Builds WebKit's WebCore and JavaScriptCore with Ranvier's C ABI host (`RanvierWebCoreHost`) and ships them as
NuGet packages for `win-x64`, `win-arm64`, `linux-x64`, `linux-arm64` and `osx-arm64`.

| Package | Purpose |
|---|---|
| `Ranvier.WebCore` | Managed interop for the C ABI (`include/RanvierWebCoreAbi.h` in the native packages). |
| `Ranvier.WebCore.Native` | Aggregate of the five Slim runtime packages. |
| `Ranvier.WebCore.Native.<rid>` | Slim flavor: presentation-focused WebKit, CPU painting. |
| `Ranvier.WebCore.Native.Gpu.<rid>` | GPU flavor: Slim plus accelerated compositing and native GPU frames. |
| `Ranvier.WebCore.Accessibility.Atspi` | Optional Linux AT-SPI accessibility provider. |

Documentation is indexed in [docs/README.md](docs/README.md). The WebKit pin and package version are in
[`pins.json`](pins.json); the patch series is [`patches/series`](patches/series).

## Build

On Windows with Visual Studio's x64 C++ build tools, Python 3.12+, Perl, Ruby and gperf:

```
python -I scripts/build.py all
```

[docs/CI.md](docs/CI.md) covers other runtimes, flavors, caches and releasing.
