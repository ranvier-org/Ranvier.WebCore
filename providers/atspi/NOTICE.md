# Private optional provider qualification artifact

This artifact contains the Ranvier native AT-SPI provider and its public C header. It does not contain WebCore,
JavaScriptCore, GLib, GIO, GObject or libatspi binaries. The application selects and installs a matching native
WebCore host separately. GLib/GIO/GObject are dynamically supplied by the operating system. AT-SPI headers and the
independent client are development and qualification inputs, rather than bundled runtime assets.

The package identity used by the qualification app is private and has no public release allocation. Public package
metadata and applicable source notices must be finalized with the coordinated delivery cohort.
