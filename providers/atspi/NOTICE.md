# Private optional provider qualification artifact

This artifact contains the Ranvier native AT-SPI provider and its public C header plus the portable Ranvier host ABI
header used by that public header. It does not contain WebCore,
JavaScriptCore, GLib, GIO, GObject or libatspi binaries. The application selects and installs a matching native
WebCore host separately. GLib/GIO/GObject are dynamically supplied by the operating system. AT-SPI headers and the
independent client are development and qualification inputs, rather than bundled runtime assets.

The package identity used by the qualification app is private and has no public release allocation. Public package
metadata and applicable source notices must be finalized with the coordinated delivery cohort.

The reserved public identity is Ranvier.WebCore.Accessibility.Atspi; no public version is allocated. The current
artifact is private style-only ABI63 qualification, with linux-x64 distribution only. ARM64 and macOS are not
qualified runtime assets. The package manifest records an explicitly unverified caller source claim and selected
host binary hash; source provenance requires separate producer evidence.

The provider binary embeds generated AT-SPI interface declarations derived from eight XML files in the pinned
WebKit source. `THIRD-PARTY.md` records those exact inputs, system/header dependencies and unresolved source terms.
The embedded declarations require attribution/license review even though no WebKit binary is bundled. A verbatim
LGPL-2.1 text accompanies the identified GLib/AT-SPI dependency notices; it does not assign the whole provider a license.
