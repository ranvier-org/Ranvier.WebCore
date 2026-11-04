# The C ABI and header

`RanvierWebCoreHost` exports a C ABI declared in two headers, shipped in every native package under `include/`:

| Header | Contents |
|---|---|
| `RanvierWebCoreAbi.h` | The hand-written boundary: hosts, nodes, events, input, painting, GPU frames, accessibility, clipboard, observers, diagnostics. Source: `host/RanvierWebCoreAbi.h`. |
| `RanvierWebCoreDom.h` | The generated DOM functions `rv_dom_*`, one per IDL attribute getter, setter and operation of the interfaces in `gen/dom.json`. Source: `host/RanvierWebCoreDom.h`, written by `gen/domgen.py` (`docs/GENERATOR.md`). |

The boundary is C scalars, UTF-8 strings with explicit byte counts, opaque handles and caller-owned buffers. It is
identical on every port that compiles `host/RanvierWebCoreAbi.cpp`. Calls are valid on one thread; see
`docs/HOSTING.md`.

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
`host-tracing`, `diagnostics`, `printing-pdf`, `snapshot-options` and `media-preferences`.

For deeper queries (is a facility exported, implemented, enabled, permitted, available) use the capability queries
in `docs/CAPABILITIES.md`. The full set of names is `host/RanvierCapabilityCatalogue.inc`.

## Errors

Functions return `RV_OK` (0) or a negative `RV_ERR_*` status: `NULL_ARGUMENT`, `WRONG_THREAD`, `DOM_EXCEPTION`
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
