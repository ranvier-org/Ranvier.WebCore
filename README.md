# Ranvier.WebCore

Builds WebKit's WebCore and JavaScriptCore with Ranvier's C ABI host (`RanvierWebCoreHost`) and ships them as
NuGet packages for `win-x64`, `win-arm64`, `linux-x64`, `linux-arm64` and `osx-arm64`.

| Package | Purpose |
|---|---|
| `Ranvier.WebCore` | Managed interop for the C ABI (`include/RanvierWebCoreAbi.h` in the native packages). |
| `Ranvier.WebCore.Native` | Aggregate of the four GPU runtime packages, with the CPU host for `win-arm64`. The default. |
| `Ranvier.WebCore.Native.<rid>` | GPU flavor: accelerated compositing, GPU painting and native GPU frames, CPU painting where no GPU context exists. |
| `Ranvier.WebCore.Native.Cpu` | Aggregate of the five CPU runtime packages. |
| `Ranvier.WebCore.Native.Cpu.<rid>` | CPU (Slim) flavor: presentation-focused WebKit without GPU code, CPU painting. |
| `Ranvier.WebCore.Native.Gpu` | Former name of `Ranvier.WebCore.Native`, on which it depends. |
| `Ranvier.WebCore.Accessibility.Atspi` | Optional Linux AT-SPI accessibility provider. |

Documentation is indexed in [docs/README.md](docs/README.md). The WebKit pin and package version are in
[`pins.json`](pins.json); the patch series is [`patches/series`](patches/series).

## Build

On Windows with Visual Studio's x64 C++ build tools, Python 3.12+, Perl, Ruby and gperf:

```
python -I scripts/build.py all
```

[docs/CI.md](docs/CI.md) covers other runtimes, flavors, caches and releasing.
