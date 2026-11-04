# Ranvier.WebCore.Accessibility.Atspi

Optional AT-SPI accessibility modules for the Ranvier WebCore host on `linux-x64` and `linux-arm64`.

Install this package beside the `Ranvier.WebCore.Native` package of the same version. Each module loads its sibling
host through `$ORIGIN`; `provider-manifest.json` records the host ABI and the sha256 of every module and of the host
it was built against. The package adds no package dependencies and bundles no GLib, GIO, GObject, libatspi or WebCore
binary: GIO/GObject/GLib come from the operating system. A missing module or accessibility bus leaves rendering
unaffected.

The provider implements the Accessible, Application, Component, Action, Value and Text interfaces. Native work runs on
the host thread, text offsets keep UTF-16 boundaries, and the application releases the provider and window before it
destroys a host. The deprecated `TextBefore/At/AfterOffset` methods are unsupported.

The C API is `include/RanvierAtspi.h`; the host ABI it binds is `include/RanvierWebCoreAbi.h`. `NOTICE.md`,
`THIRD-PARTY.md` and `licenses/LGPL-2.1.txt` carry the component notices.
