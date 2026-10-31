# Passive capability observations

H07 adds six read-only host exports in ABI28/Native20. The existing host ABI and
all generated DOM contracts remain available. Native19/ABI27 is the integration
parent; managed surface versions are allocated independently.

Each query returns independent Exported, Implemented, Enabled, Permitted and
Available facts, using -1 for unknown,0 for no and1 for yes. ABI feature names
describe exported entry surfaces only. An arbitrary unrecognized name remains
unknown. Build-option values are actual configured producer values; disabling a
stub alone does not prove a working facility. Compiled-out/stubbed implementations
can establish a negative for their recognized facility.

The image domain describes MIMETypeRegistry support queries and the font domain
describes the current document's CSS font-format query. Neither establishes that
arbitrary supplied data decodes, loads or renders. Browser ImageDecoder can reject
SVG while HTML images still render it; that difference is retained in provider
provenance and broader availability remains unknown.

The explicit host implementation allowlist describes these bounded facilities:

- Clipboard: RvEditorClient and rv_host_set_clipboard DOM clipboard integration.
- Drop: native drag event dispatch and text insertion through the host drag client.
- Tooltip: RvChromeClient tooltip state and rv_host_tooltip retrieval.
- Input: rv_host_mouse/rv_host_key event handling and editor dispatch.
- IME: rv_host_ime_set_composition/commit/cancel/rect editor operations.
- Scroll: rv_host_scroll_position/rv_host_scroll_to viewport operations.

This allowlist is independent of rv_abi_has. An external OS callback working,
permission being granted or hardware being ready remains a separate observation.
Callback registration reports current enablement only. RvLoaderStrategy's fixed
isOnLine/resource-finished answers are not capability evidence.

Value kinds distinguish absent0,boolean1,number2 andtext3. Boolean numeric values
are exactly0/1. String lengths and capacities count UTF-8 bytes without any copied
NUL terminator. A size query/undersized buffer reports the length and leaves the
buffer untouched. Wrong-kind getters leave every output untouched.

The normal prepare path installs both capability .inc files alongside the host.
The catalogue checker covers current profile switches and canonical ABI/model
names without changing the DOM generator. Non-Windows/official-package proof is
reported separately from private Windows source/runtime proof.

S06 view selection is a separately scoped host operation in the same producer
cohort. Capability discovery never invokes it or changes SVG state.

B06 adds three facilities. "media-capabilities" is implemented when rv_abi_has reports the
rv_media_decoding_info family. "media-decoding-provider" and "media-encoding-provider" are implemented
and available when a media engine configuration provider answers MediaCapabilities queries. No current
flavor has one (the engine's providers are Cocoa and GStreamer only), so every valid query answers
unsupported, not smooth and not power efficient. Neither facility enables playback, a codec or a setting.
