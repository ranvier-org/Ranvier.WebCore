# Optional native provider notices

This package contains the Ranvier native AT-SPI provider, its public C header and the portable host ABI header.
Supported payload RIDs and their exact selected Host hashes are listed in `provider-manifest.json`. The application
selects and installs its matching native WebCore host separately. No WebCore, JavaScriptCore, GLib, GIO, GObject or
libatspi binary is bundled. GIO/GObject/GLib are dynamically supplied by the operating system; AT-SPI headers and
independent clients are development/qualification inputs.

The provider embeds interface declarations derived from eight XML files at the pinned WebKit source recorded in
`THIRD-PARTY.md`. Their exact upstream origin is preserved without assigning terms absent from those XML files.
The verbatim LGPL-2.1 text accompanies the identified GLib/AT-SPI header/dependency notices. It does not assign the
whole provider a license. Original project license metadata remains unspecified. No new license grant or SPDX
expression is asserted by this notice.

Source labels in the package remain explicit caller claims. Independent producer and actual per-RID qualification
receipts, rather than a label or ABI number, provide the separate evidence for the selected payloads.
