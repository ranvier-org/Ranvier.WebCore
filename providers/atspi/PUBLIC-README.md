# Optional Ranvier AT-SPI provider

This package supplies optional native accessibility modules for the Linux RIDs listed in `provider-manifest.json`.
The application selects its matching ABI63 WebCore host separately. The SDK selects the provider for the target RID;
the module loads its sibling host using `$ORIGIN`. No renderer or system GIO/GObject/GLib binary is bundled, and
no renderer dependency is added. A missing module or accessibility bus leaves ordinary rendering available.

The portable interfaces cover Accessible, Application, Component, Action, Value and modern Text operations. Native
work stays on the Host thread, text offsets preserve UTF-16 boundaries, and the application releases provider/window
ownership before destroying a Host. Deprecated TextBefore/At/AfterOffset methods remain explicitly unsupported.

`NOTICE.md`, `THIRD-PARTY.md` and `licenses/LGPL-2.1.txt` preserve component/source notices without assigning an
unspecified project license or inventing an SPDX grant. The original private qualification README and notice remain
under `qualification-input/` as historical input records.

The aggregate manifest records exact input, module, SDK and supplied qualification-receipt hashes. Source strings
remain unverified caller claims. Matching a supplied reviewed receipt hash does not authenticate who reviewed it or
which source produced an arbitrary binary; independent producer/qualification evidence remains separate.
