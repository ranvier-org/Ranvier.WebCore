# H11 binary and file value objects plan

## Core and view state

- **Core primitives used:** `createRoot`, `onCleanup`, `runWithOwner` and `batch`. They give each read an owner. The
  Views read helpers (`BlobReads`) start a read under a new root, register its `Cancel` with `onCleanup`, and deliver
  the outcome through `runWithOwner` inside `batch`. Disposing the root, or the owner that holds it, cancels the
  read. This follows `Frames.idle` and its `owned` helper (H01).
- **View-owned state:** none. The engine holds every byte, type, name and modification time. The service holds the
  document that constructs blobs, files and lists, and that document is a native handle, which the core cannot hold.
  A pending read is a `ResourceOperation` from the H05 contract, and the root that owns it is a core owner.

**Goal:** create, slice and read immutable Blob and File values. Build FileList values for file inputs. Read the File
entries of FormData. Every value comes from the engine on native and from the browser on Chromium (Ranvier.WebCore
#114). ReadableStream (`Blob.stream`) is H12 scope. Object URLs (`URL.createObjectURL`) need blob-URL loading, which
follows H13.

**Trees:** native `C:/wk/native-binary`, branch `codex/native-api-binary-values`. Its base is G05 `dc0951a`, then D16
`2fc30ea`, then url1's generator commit `67709dc`. Reservation: Native31/ABI39, DOM alpha.34, Views 0.1.24, backend
alpha.24.

## Pinned source scope

- `Blob`, `File` and `FileList` (`fileapi/`) keep their data in the platform `BlobRegistry`. The host's registry was a
  stub that dropped every part, so `Blob.size` returned 0. It now delegates to WebCore's in-process
  `BlobRegistryImpl`, the way WebKitLegacy's `WebBlobRegistry` does.
- `Blob.text`, `arrayBuffer` and `bytes` return promises, and `FileReader` reads through a `ThreadableLoader` on a
  blob URL. The host loader has no blob-URL path, so neither is bound. Every blob the host creates holds its bytes in
  memory, so `rv_blob_read_bytes` reads them during the call. A blob with any other item, such as a file-backed one,
  returns `RV_ERR_UNSUPPORTED`.

## Measured RED (Native30/ABI38 against Chromium 156.0.8078.4 new headless)

`tests/abi/binary_values_browser.mjs` records `tests/fixtures/binary-values-oracle.json`. On the Native30 runtime,
`artifacts/measure_binary_red.py` finds none of the 17 Blob, File, FileList and read exports. `rv_abi_has` reports 0
for `dom:Blob`, `dom:File` and `dom:FileList`. The FormData entry of an empty file input has the File tag and a NULL
payload. `tests/abi/binary_values.py` fails there with `dom-binary-values advertised`.

## Native surface (ABI39, additive, `rv_abi_has("dom-binary-values")`)

- Generated: `Blob` (constructor, `size`, `type`, `slice`), `File` (constructor, `name`, `lastModified`) and
  `FileList` (`length`, `item`), with the handles `RvBlob` and `RvFileList`, and `HTMLInputElement.files` for reading
  and writing. The `BufferSource` arm of a blob part is an `RvDomByteSpan`, which the glue copies into an
  `ArrayBuffer`.
- D13's File union arm becomes an owned `RvBlob`. `DOMFormData.append` and `set` gain the `(name, Blob, filename)`
  overload.
- Hand-written: `rv_blob_read_bytes` and `rv_file_list_create`.

## Proof

1. **RED:** `tests/abi/binary_values.py` fails on ABI38 because the exports are absent.
2. **Native GREEN** on `artifacts/native31-candidate-N`: every oracle case gives Chromium's bytes, size, type, name
   and modification time. The exception is endings `"native"`, whose expected value depends on the platform: CRLF on
   Windows and LF elsewhere. The cases include blob parts, type normalization, slicing, File metadata, a 1 MiB
   checksum, a FileList through a file input, and FormData File entries with their identity. The probe also checks the
   null, thread, interface, capacity and tag errors, and blobs, slices and lists held past `rv_host_destroy`. The
   teardown driver adds the "blob slice" case.
3. **Managed GREEN:** the shared conformance fixture runs on native JIT, NativeAOT and Chromium. It covers reads with
   owner-bound cancellation, UTF-8 text and data URLs, D13's File entries read through the H11 service, and teardown
   cases, with an evidence JSON.

## Native GREEN (Native31/ABI39, local)

Candidate 4 (WebCore d6396ada, Host 5a279da7, JSC 95149cdc) was built at 00077e3 and frozen at
`artifacts/native31-frozen`. The batch runs 43 probes, all exit 0, with 48,932 assertions: 446 from
`binary_values` and 1,168 from `form_collections`, which now reads a File entry's handle. All 78 teardown cases are
collected, including the two "blob slice" cases. The build borrows the pre-0035 objects. Its receipt records the
narrow `Document.cpp` exemption for G09's Source patch 0035 (`source-exemption.json`). Evidence:
`docs/binary-values-evidence/final-evidence.json`.

Measured qualifications:

- Endings `"native"` write the platform's line break: CRLF on Windows, which equals Windows Chromium's bytes
  `610d0a620d0a630d0a64`, and LF elsewhere. The probe asserts each platform's value.
- No promise and no FileReader engine object is exposed, because the host loader has no blob-URL path. The managed
  layer provides text and data URLs over `rv_blob_read_bytes`, with cancellation.
- `slice` takes int64 arguments, so the `[Clamp]` case `slice(1.9, 4.2)` applies to browsers only.
- String parts are UTF-8 that the caller writes from the USVString, with U+FFFD for a lone surrogate. Invalid UTF-8
  returns `RV_ERR_NULL_ARGUMENT`.
