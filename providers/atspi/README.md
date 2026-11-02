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
