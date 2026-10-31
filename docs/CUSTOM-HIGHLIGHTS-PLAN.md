# T03 custom highlights plan

## Core and view state

- **Core primitives used:** none inside the native exports or the highlight service. A view that highlights search
  matches, diagnostics or collaborative cursors computes the match offsets in a memo (`createMemoWithComparer` over
  the query and the text skips unchanged input), and an effect (`createEffectOnWithComparer`) applies the change to
  the registry with `Set` and `Remove`. The owner that registers a name removes it in `onCleanup`.
- **View-owned state:** none. The Highlight objects, their ranges and the registry are engine state of the document,
  like the last value written to a DOM target; the service holds handles to them and no copy.

**Goal:** `new Highlight(...)`, the setlike operations of a Highlight, the maplike operations of `CSS.highlights`,
`priority`, `type` and `::highlight(name)` painting, compared with Chromium 156 (Ranvier.WebCore #74). Overlapping
highlights, registry updates and deletions change the painted colours of their ranges, never the text.

**Trees:** native `C:/wk/native-highlight`, branch `codex/native-api-custom-highlights`, from T06's `901ced5`;
B22, G03, G04 and I08 merge before release. Reservation Native40/ABI48, DOM alpha.43, Views 0.1.33, backend
alpha.33; Views kinds start at 86.

## Measured RED (Native35 frozen-2 against Chromium 156.0.8078.4)

`C:/wk/t03-artifacts/red` holds the measurements.

- WebKit's `Highlight` and `HighlightRegistry` are compiled in (`UnifiedSource-Modules-6`) with no setting gate: the
  pinned IDL has no `EnabledBySetting`, and `UnifiedWebPreferences.yaml` has no `HighlightAPIEnabled`.
  `MarkedText.cpp` paints `document.highlightRegistryIfExists()`.
- The ABI has no highlight export, and `gen/idl.py` skipped `setlike` and `maplike` declarations.
- The pinned WebKit has no `highlightsFromPoint`; Chromium 156 has it.
- WebKit's C++ backing state differs from Web IDL order in three places that its JavaScript bindings hide behind a
  JavaScript Set or Map: `Highlight::addToSetLike` moves a range already in the set to the end, `Highlight::create`
  keeps duplicate ranges, and `HighlightRegistry::clear` empties every registered highlight.

## Native surface (ABI48, generated, `rv_abi_has("dom-custom-highlights")`)

`gen/dom.json`'s `setlikeBindings` and `maplikeBindings` bind the declarations through
`host/dom/RanvierCollectionLike.h`, which keeps Web IDL order: a range added again or a name set again keeps its
position, the constructor adds a repeated range once, and `registry.clear()` unregisters names one by one, so each
highlight keeps its ranges. `values()` and `entries()` return snapshot copies. `CSS.highlights` is
`rv_dom_css_get_highlights`, one registry per document.

## Scope

- `highlightsFromPoint` is browser-only: the service answers `HighlightHitTest.Unsupported` on the native engine.
- Painting follows the registry's iteration order for equal priorities. Chromium paints a name set again as the most
  recently registered while keeping its map position; the probe qualifies those two paint steps.
- Document teardown (a replaced document, `rv_host_destroy`) clears the document's registry and empties every
  highlight registered in it; an unregistered highlight keeps its ranges, and every handle stays usable until it is
  released.

## Proof

1. **RED:** the measurements above.
2. **Native GREEN** on `artifacts/native40-candidate-N`: `tests/abi/custom_highlights.py` against the Chromium oracle
   `tests/fixtures/custom-highlights-oracle.json` (API keys and the colour at the centre of each Ahem cell after each
   paint step), errors, the wrong thread, and the teardown cases; 30 repeated runs.
3. **Managed GREEN:** the shared conformance fixture runs on native JIT, NativeAOT and Chromium.
