# Optional Linux accessibility provider

This provider mirrors the existing `rv_ax_*` tree through GDBus. It stays outside the lean WebCore renderer and
does not connect WebCore's platform AT-SPI wrappers. The application owns its native window, host and event pump.

The first implementation is a private module prototype, with no core ABI/version/kind allocation. Its intended
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

This checkpoint is offscreen Host qualification. Automatic SDL Window/Host ownership is pending. The provider exposes
forward ARIA relations available through `rv_ax_relations`, native hit-testing, and physical text-range geometry.
Opacity queries return unsupported because the portable accessibility contract does not expose opacity. Text attribute
runs, bounded ranges, inverse relationships and incremental cache events are not yet implemented.
