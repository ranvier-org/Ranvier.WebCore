# Optional Linux accessibility provider

This provider mirrors the existing `rv_ax_*` tree through GDBus. It stays outside the lean WebCore renderer and
does not connect WebCore's platform AT-SPI wrappers. The application owns its native window, host and event pump.

The current module remains a private delivery candidate. Its
interfaces are Accessible, Application, Component, Action, Value and Text. It preserves native object identity and
performs native work exclusively on the host thread. AT-SPI character offsets are converted at the UTF-16 boundary.
Unknown screen position reports unsupported screen coordinates; window coordinates remain available.

The provider owns the host accessibility callback while attached. The application releases it before host destruction,
as required for every retained `RvAxNode`; the SDL adapter must enforce this during Host/Window cleanup. A failed attach
retains neither the callback nor native nodes. Document replacement retires old node paths and exposes the new root.

Qualification uses an isolated owned accessibility bus and an independent client, never the user's accessibility bus.
It covers discovery, names/roles/states, focus/invoke/value, Unicode text/selection, physical geometry, events, detached
nodes, replacement and owner teardown. The protocol fixture starts a real AT-SPI registry and verifies discovery and
unembedding through an independent libatspi client. It uses the ordinary `rv_run_loop_cycle` pump. Reentrant release
inside an accessibility action completes its reply before the connection closes.
Windows uses its existing UI Automation implementation and acceptance fixture. macOS follows after Linux.

The protocol checkpoint qualifies offscreen Hosts. A separate managed adapter owns SDL Window/Host cleanup. The provider exposes
forward ARIA relations available through `rv_ax_relations`, native hit-testing, and physical text-range geometry.
Opacity queries return unsupported because the portable accessibility contract does not expose opacity. Text attribute
runs use the renderer-backed `rv_ax_text_style_run` boundary, including ignored inline spans, hidden text and UTF-16
non-BMP offsets. Bounded ranges and inverse relationships are implemented. Native child additions/removals emit identity-
preserving children and cache events; detached nodes are unregistered and their native references released.

A null bus address discovers `AT_SPI_BUS_ADDRESS`, then the session's `org.a11y.Bus.GetAddress`; connection work is
bounded to two seconds. Tests provide isolated services for both discovery paths. Queued property setters use GIO's
method dispatcher so unregistering an application rejects already queued `Properties.Set` calls before accessing its
lease. GLib 2.80's direct setter callback lacks that admission check.

The optional asset targets a matching ABI63 host with `accessibility-text-style`; the final #171/#182 cohort must be
qualified together before publication. Build this standalone project against the application's selected Slim or GPU
host, then `cmake --install` into a private prefix. `package.py` accepts only the installed `$ORIGIN`-relative provider,
checks ELF architecture and the actual host capability, and packs the module without bundling a second host or adding
a dependency on a renderer flavor. System GIO, GObject and GLib provide the D-Bus implementation; libatspi is used only
for build headers and independent test clients. A missing module or accessibility bus leaves ordinary window rendering
usable and reports accessibility attachment as unavailable.

## Delivery and SDK integration

The reserved public package ID is `Ranvier.WebCore.Accessibility.Atspi`. A public version is not allocated.
Its version must follow the final matching Native ABI63 cohort; immutable ABI62 releases cannot supply this module.
Current artifacts use explicitly private identities and versions. `provider-manifest.json` records the reviewed provider
source commit, selected host hash, provider hash, payload hashes and private style-only qualification scope.
`--source-revision` names the commit that produced the binary; repackaging an archived binary must retain that commit.
The packager rejects public package IDs and versions while the final cohort, version and source licenses await review.

Only `linux-x64` is currently eligible for packaging and the opt-in workflow. ARM64 source/compilation is preparatory:
enable distribution only after a matching actual ARM64 Native ABI63 host, provider, protocol and ordinary Window/AOT
cohort passes. Windows continues through UIA. macOS has no adapter in this package.

Use an ordinary SDK `PackageReference` to the provider alongside the application's chosen matching renderer package.
The SDK copies `runtimes/linux-x64/native/libRanvierWebCoreAtspi.so` into RID-specific publish output. The optional module
shares that directory with the selected `libRanvierWebCoreHost.so`; no search-path environment override is required.
Native consumers use both packaged headers from `include/` with `#include "RanvierAtspi.h"`.

`tests/atspi/consumer.py` restores from an owned local feed, publishes an ordinary .NET 10 SDK application, checks the
provider payload hash and resolves its four exports through assembly-aware `NativeLibrary.Load`. It copies only the
explicitly hash-matched selected host for this distribution check. This verifies package discovery and dynamic loading;
the separate protocol and managed Window normal/traced NativeAOT receipts supply rendering and accessibility proof.
The opt-in CI workflow retains this consumer receipt with native/protocol reports and the private package. It does not
publish to NuGet. Final integration must repeat all gates against the frozen #171/#182 union and public managed cohort.

Public release review must supply applicable project/source license texts and finalize notices. The current qualification
notice records packaged and system components without assigning an unreviewed license to the provider.
