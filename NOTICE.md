# Third-party components

The package contains these components. Each is under its own license; the license texts are in the
component's source at the pinned version. This list needs a licensing review before a public release, and
the package does not yet carry the full license texts.

| DLL | Component | License |
|---|---|---|
| `WebCore.dll`, `JavaScriptCore.dll` | WebKit (`Source/WebCore`, `Source/JavaScriptCore`, `Source/WTF`, bundled Skia) | LGPL-2.1 and BSD-style, per file; Skia BSD-3-Clause |
| `RanvierWebCoreHost.dll`, `libRanvierWebCoreHost.so`, `libRanvierWebCoreHost.dylib` | This repository's `host/`, with code that follows WebKit's `TestPage.cpp` and `EmptyClients.cpp` (and on Linux embeds WebCore, JavaScriptCore, WTF, Skia, ICU 77.1 and the HarfBuzz-ICU adapter statically) | Ranvier's license; the WebKit-derived parts BSD-2-Clause |
| `icudt77.dll`, `icuin77.dll`, `icuuc77.dll` (Windows); static `libicudata.a`, `libicui18n.a`, `libicuuc.a` in `libRanvierWebCoreHost.so` (Linux) | ICU 77.1 | Unicode License v3 |
| `harfbuzz.dll`, `harfbuzz-icu.dll` (Windows); static `libharfbuzz-icu.a` in `libRanvierWebCoreHost.so` (Linux) | HarfBuzz / HarfBuzz-ICU glue | MIT ("Old MIT") |
| `libxml2.dll` | libxml2 | MIT |
| `jpeg62.dll` | libjpeg-turbo | IJG, BSD-3-Clause, zlib |
| `libpng16.dll` | libpng | libpng license |
| `libwebp.dll`, `libwebpmux.dll`, `libwebpdemux.dll`, `libsharpyuv.dll` | libwebp | BSD-3-Clause |
| `zlib1.dll` | zlib | zlib |
| `brotlicommon.dll`, `brotlidec.dll` | Brotli | MIT |
