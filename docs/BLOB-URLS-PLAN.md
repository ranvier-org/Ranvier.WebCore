# #144 blob URLs, blob: loading and FileReader plan

## Core and view state

- **Core primitives used:** none natively. The managed layer (Ranvier.Dom `BlobUrlService`) settles each read through
  the H05 `ResourceOperation` contract; a view that reads in a scope disposes the operation with `onCleanup`, which
  cancels the native read.
- **View-owned state:** `FileReaderObject` (Views Kind 98), the wrapper of the engine's FileReader handle, and the
  provider's table of completion contexts for native reads in flight. Both are native handle state.

**Goal:** object URLs, blob: loads in the host loader (images, stylesheets and reads), FileReader as an engine object,
Blob.text/arrayBuffer/bytes as engine reads, and file-backed Files (Ranvier.WebCore #144, after H11 #114 and H13 #115).

**Trees:** native `C:/wk/native-blob`, branch `codex/native-api-blob-urls`, from T03 `828fb2b`, merged with I11
`5eee88a` and H08 `acf26e3`. Reservation: Native44/ABI52 (preview.44), DOM alpha.47, Views 0.1.37, backend alpha.37.

## Pinned source scope

- `RvLoaderStrategy` handed every load except data: to the host's resource handler, so blob: loads failed. WebCore's
  `BlobRegistryImpl` registers a builtin "blob" `ResourceHandle` constructor (`BlobResourceHandle`), so the host now
  starts blob: loads in WebCore, as it starts data: loads. No other scheme changes.
- `DOMURL.createObjectURL` registers the blob with the document's `PublicURLManager`, which revokes every URL when the
  document stops. `FileReader` and `Blob.text()` read through `FileReaderLoader` over a `ThreadableLoader` on a blob URL.
- The host has no subframes (`EmptyFrameLoaderClient::createFrame` returns null), so an iframe loading a blob URL is
  browser-only, and native `fetch()` does not exist; `rv_blob_url_read` is the native read of a blob URL.
- No source patch.

## Native surface (ABI52, additive, `rv_abi_has("blob-urls")`)

- Generated: `URL.createObjectURL`/`revokeObjectURL` (static bindings, feature `blob-urls`) and `FileReader` (event
  target object: constructor, `readyState`, the four `readAs*` methods and `abort`; `dom:FileReader`).
- Hand-written: `rv_blob_read` (TEXT or BYTES), `rv_blob_url_read`, `rv_blob_read_result`, `rv_blob_read_type`,
  `rv_blob_read_error`, `rv_file_create_from_path`, `rv_file_reader_result` and `rv_file_reader_error`. Reads follow the
  H05 operation contract (delivery after the call, cancel, release, INVALIDATED at document replacement and destroy).
- `rv_blob_url_read` refuses a URL the document's origin cannot request: the blob registry is process-wide, and two
  hosts' opaque documents must not read each other's URLs.

## Proof

1. **RED:** on Native42 the exports are absent; candidate-1 leaked a blob URL across hosts through `rv_blob_url_read`
   (`docs/blob-urls-evidence/red-candidate1-cross-host-leak.json`), fixed before allocation.
2. **Native GREEN:** `tests/abi/blob_urls.py` replays `tests/fixtures/blob-urls-cases.json` against the Chromium oracle
   `blob-urls-oracle.json`: URL format and lifetime, images, URL reads, engine reads, FileReader order and state, file-backed
   Files, isolation in both directions and teardown. Two differences are qualified (`blob-urls-qualified.json`). The
   teardown driver adds the "blob reads" cases. 30 repeats of the probe and of the oracle.
3. **Managed GREEN:** `BlobUrlChecks` on native JIT, NativeAOT and Chromium, with the native lifetime checks.
