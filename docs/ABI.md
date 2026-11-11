# The C ABI and header

`RanvierWebCoreHost` exports a C ABI declared in two headers, shipped in every native package under `include/`:

| Header | Contents |
|---|---|
| `RanvierWebCoreAbi.h` | The hand-written boundary: hosts, nodes, events, input, painting, GPU frames, accessibility, clipboard, observers, diagnostics. Source: `host/RanvierWebCoreAbi.h`. |
| `RanvierWebCoreDom.h` | The generated DOM functions `rv_dom_*`, one per IDL attribute getter, setter and operation of the interfaces in `gen/dom.json`. Source: `host/RanvierWebCoreDom.h`, written by `gen/domgen.py` (`docs/GENERATOR.md`). |

The boundary is C scalars, UTF-8 strings with explicit byte counts, opaque handles and caller-owned buffers. It is
identical on every port that compiles `host/RanvierWebCoreAbi.cpp`. Host/DOM calls are valid on the owner
thread; see `docs/HOSTING.md`. The detached image encoding functions below are an explicit exception.

## Version

`rv_abi_version()` returns the ABI version. The source of truth is its definition in `host/RanvierWebCoreAbi.cpp`
(`scripts/build.py package` reads that definition into the package's `manifest.json`). The version increases with
every change to the header that a consumer must follow, and the managed package and the native package of a release
must report the same value. Within `RanvierWebCoreAbi.h`, `^RV_EXPORT` lines are the hand-written declarations;
`git grep -c "^RV_EXPORT" host/RanvierWebCoreAbi.h` counts them.

The header comments mark the version that introduced each group (`/* v18: "clipboard" ... */`) and note breaking
changes, such as the explicit UTF-8 byte counts on string inputs.

## Detecting features

`rv_abi_has(name)` returns 1 when the loaded library exports and implements the named group, so a newer managed
package can run against an older host. Names mark the version that added them in the header; examples are
`accessibility`, `accessibility-events`, `accessibility-text`, `clipboard`, `drag-out`, `host-errors`,
`host-tracing`, `host-layout-metrics`, `diagnostics`, `printing-pdf`, `snapshot-options` and `media-preferences`.

ABI 66 adds `rv_host_layout_count`: completed main-frame layout passes, including subtree layout,
without flushing pending style/layout. Unlike a trace span around a layout-checking call, a zero counter
delta means no layout pass completed. It excludes child frames and style-only work, wraps at 32 bits,
and resets with the frame view. Compare only within one document lifetime. Synchronous geometry getters
retain their browser semantics.

ABI 70 adds `detached-image-encoding-v1`. `rv_host_snapshot_bounded` captures on the owner with the
existing resource-delivery contract, rejecting cropped/scaled backend dimensions above 8192 or 64 MiB
of RGBA8 before image-buffer allocation or rasterization. The legacy `rv_host_snapshot` remains unchanged.
After host initialization, `rv_image_encode_rgba`, `rv_encoded_image_bytes` and `rv_encoded_image_release`
may run on a worker. They use immutable input pixels and worker-local image objects, retain no host,
and remain valid after host destruction. Serialize access to each encoded-image handle with its release.
The encoder enforces the same input limits; it does not make owner-thread capture asynchronous.

ABI 71 adds `snapshot-pixels-v1`. `rv_host_snapshot_pixels` returns an owned immutable native RGBA
capture (bounded to 64 MiB) instead of copying it through a resource and managed array. Its copy,
encode and release functions work after document replacement and host destruction, including on
workers; callers must serialize release against reads/encoding. Encoding uses worker-local graphics
objects. DOM layout and initial painting still run on the owner thread.

One viewport pixel buffer per host may be reused for identical crop, scale and color space. Pending
style/layout is flushed before checking reuse. Invalidation, scrolling, rendering-update requests,
rendering updates, resize and document replacement discard the cache. Element snapshots always
repaint. The cache retains at most 64 MiB; independently retained capture handles can outlive it.
No cache-hit latency claim applies to changed/animated pages. WebKit's pinned display lists retain
non-thread-safe font objects and are not transferred to workers.

Host trace phases 6, 7, 8 and 9 separately measure buffer creation, snapshot rasterization, image encoding
and pixel copying. They complement layout/paint/submission timings and do not impose latency thresholds.

ABI 67 adds Windows `gpu-frame-pipeline-v1`. Configure a retained consumer device, submit monotonically
increasing nonzero IDs, then try acquiring the newest completed frame. `RV_NOT_READY` (1) is backpressure,
not a paint error: preserve the prior image and retry at a scheduled frame. A submit returning NotReady
accepted no ID. An acquire returning NotReady clears both outputs. `RV_ERR_DEVICE_LOST` (-12) requires
releasing leases, rebuilding the consumer device and configuring it again. Call `rv_host_update` for
rendering updates before submission, as with the legacy frame acquisition API.

The new path uses zero-time keyed mutex checks for producer readiness, completed output and consumer
retirement. Three output slots are shared across resize generations. Retained frames keep their pool alive
after host destruction. Accounted output color/depth storage and external-input cache storage share a
256 MiB process cap; this is not a cap on WebCore backing stores, driver overhead or legacy allocations.
Each allocation is charged at least 64 KiB to bound retirement bookkeeping as well. Destroyed surfaces
retain their storage and charge until zero-time GPU completion queries succeed (or the device is lost).
Later owner-thread pipeline operations collect retirements; remaining process-final retirements are
left to process teardown. Query creation failure conservatively retains the charge while the device lives.
External textures are copied only while owned into one bounded compositor-device cache; a busy producer
reuses its last valid cache, or yields NotReady before the first completed input. Document replacement
invalidates unleased old completions. Layout, paint, driver submission and destruction remain owner-thread
operations; no hard real-time latency guarantee is made. Native trace phase 5 measures GPU submission.

For deeper queries (is a facility exported, implemented, enabled, permitted, available) use the capability queries
in `docs/CAPABILITIES.md`. The full set of names is `host/RanvierCapabilityCatalogue.inc`.

## Errors

Functions return `RV_OK` (0), pipeline `RV_NOT_READY` (1), or a negative `RV_ERR_*` status: `NULL_ARGUMENT`, `WRONG_THREAD`, `DOM_EXCEPTION`
(with `rv_last_exception`), `NOT_ELEMENT`, `PAINT_FAILED`, `BUFFER_TOO_SMALL`, `UNSUPPORTED`, `DETACHED`,
`WRONG_INTERFACE`, `WRONG_HOST` and others. The header lists the full enumeration.

## Managed bindings

`src/Ranvier.WebCore` packs the F# P/Invoke declarations. `tests/abi/Native.fs` is generated from the header by
`python -I tests/abi/generate_native.py write` (`check` verifies it), and `tests/abi/NativeDom.fs` comes from
`gen/domgen.py`. A header change goes with a regenerated `Native.fs` and a test in `tests/abi`.

## Feature guides

| Guide | Covers |
|---|---|
| `docs/HOSTING.md` | Creating a host, the frame loop, presenting, teardown. |
| `docs/ACCESSIBILITY.md` | The accessibility tree, events, actions, text; UI Automation and AT-SPI. |
| `docs/CLIPBOARD-DND.md` | Clipboard, drag and drop styles. |
| `docs/ANIMATIONS.md` | Web Animations and timelines. |
| `docs/MUTATION-OBSERVATION.md` | Mutation observers. |
| `docs/PRINTING.md` | PDF output. |
| `docs/DIAGNOSTICS.md` | Page inspection, host errors, host tracing. |
| `docs/CAPABILITIES.md` | Capability queries. |
| `examples/NativeMedia`, `examples/NativeSpelling` | Application-side Windows playback and spelling adapters. |
