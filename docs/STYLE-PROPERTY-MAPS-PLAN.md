# C13 typed style maps

## Required outcome

Expose attributeStyleMap, computedStyleMap and CSSStyleRule.styleMap, with typed get/getAll/has/size, set/append/delete/clear and entry enumeration. Read-only computed maps remain read-only. The shared browser/native contract preserves missing values, structured typed values, list order and canonical serialization. C15 numeric arithmetic and C17 color operations remain deferred.

This branch starts at reviewed Native14 producer 8f2a8c68c8f665c3f961f616c6a14d79f3bf746d. Its parent PR124 and released dependencies remain separate acceptance gates. No native JavaScript, new dependency or global map-owner registry is required.

## Source audit

The pinned WebKit b95c91b1 supplies all map behavior in css/typedom. ElementCSSInlineStyle+Typedom.idl supplies the same-object inline map; dom/Element+Typedom.idl supplies the computed map; CSSStyleRule+Typedom.idl supplies the same-object declared map. StylePropertyMapReadOnly.idl declares get, getAll, has, size and iterable entries. StylePropertyMap.idl declares set/append, delete (C++ remove) and clear.

Read-only get returns Variant<monostate, Ref<CSSStyleValue>>. getAll and iterator entries contain nullable CSSStyleValue elements in this pinned implementation; preserve them rather than filtering. Mutable variadic arguments already match the existing union-to-sequence input machinery. StylePropertyMapReadOnly::createIterator(context) snapshots entries; next returns optional KeyValuePair<String, Vector<RefPtr<CSSStyleValue>>>.

Actual generator gaps are non-node CallWith context (currently explicitly rejected), a transport for the undefined union arm, and iterable entry output. Existing C14 owned sequences, reference/string unions, USV spans, checked documents, subtype dispatch and releases are reusable. A bounded entries snapshot through the public engine iterator avoids adding iterator-lifetime handles. New context parameters must apply only to configured map operations and leave every prior ABI record/layout unchanged.

Inline/computed maps weakly reference their element; declared maps weakly reference their rule. Checked session/document context and wrapper anchoring must make owner loss and foreign inputs explicit. Returned value objects are independently reified: mutations to a returned unit value do not imply an update to its map. Test liveness by reading again after map edits.

## Implementation and proof sequence

- [x] Audit exact pinned IDL/C++ and existing generator support independently.
- [x] Observe real Chromium map behavior before selecting shared assertions.
- [ ] Add failing generator cases for selected map context, undefined result, nested owned entries, aliases and read-only dispatch. Implement only these missing mechanics.
- [ ] Select the two map interfaces and three acquisition paths. Generate get/getAll/has/size and set/append/delete/clear; provide checked explicit Document context for operations that need it. Do not infer an owner from a global registry.
- [ ] Represent get's undefined branch faithfully, mapping it to shared None. Preserve nullable entries in getAll/entries. Entry results own their property bytes and retained value arms until matching release/reset; cleanup must work after partial decode failure.
- [ ] Add native raw focused tests, first observe the old producer fail at the new export, then use a coherent private candidate. Check live declared/inline/computed values and list mutation before broader gates.
- [ ] Probe two identical cache-sharing stylesheets with retained declared maps before any engine repair. set/remove/clear currently capture the backing StyleRule before RuleMutationScope; determine whether COW reattachment can redirect edits. If reproduced, add the smallest patch and a permanent geometry/isolation regression.
- [ ] Add generated browser contracts and the borrowed Core service; add native/browser providers using the same public contract. Preserve wrapper identity for same-object maps and actual typed subtypes for values.
- [ ] Add shared focused fixtures: missing get/empty getAll, invalid properties, list ordering/cardinality/zero arguments, shorthand/custom-property restrictions, associated-property mismatch, null/foreign references, USV/NUL, explicit read-only rejection, inline priority agreement and canonical declared/computed values.
- [ ] Verify snapshot enumeration before/after mutation, nullable elements, required key ordering and owned-result cleanup. Compare fixture vocabulary rather than requiring engines to expose identical complete computed-property sets or sizes.
- [ ] Verify owner/rule/document/session disposal, thread checks and independently retained returned values. Preserve existing teardown checks.
- [ ] Run focused JIT/NativeAOT/Chromium first, then one combined native/browser batch. Audit source comments/XML, fresh FCS and old ABI/model compatibility; obtain independent review.
- [ ] Allocate the next unpublished package/ABI cohort separately from Native14, commit canonical producer pins, open/attach PRs and use the existing CI/release lane. Complete all-platform and official normal/traced consumer gates before acceptance.

## Observed browser baseline

Actual Chromium 156.0.8078.4, using the repository's Playwright installation, confirms inline typed height 20px, declared width 30px and live computed reads. A missing inline width is undefined, getAll returns an empty array and has is false. Invalid property, wrong numeric dimension, empty set and null typed input throw TypeError. Empty append to an invalid property currently succeeds, matching the pinned engine's explicit early-return caveat; retain this observation rather than inventing stricter behavior.

Three background-image values preserve set/append order. An entries iterator created before adding opacity excludes that later entry, consistent with snapshot semantics. Editing the declared width to 44px updates the computed width to 44px. delete removes a property and clear leaves size zero. An unparsed NUL segment is replaced by U+FFFD when parsed into the custom-property declaration; this is a parser result, distinct from C14's length-preserving unparsed object transport.

The ignored audit script/result are artifacts/c13-browser-audit.mjs and artifacts/c13-browser-audit.json. These are exploratory observations, not C13 acceptance or evidence of native map execution. No native map binding is implemented yet.

## First binding primitive checkpoint

The undefined-result union now has an explicit monostate arm, a reserved zero int32 transport slot and no owned handle for that arm. Generated Fable unboxing checks strict undefined separately; CSSStyleValue uses its intrinsic stringifier as a brand check that accepts actual subclasses and rejects forged object tags. The initial generator case failed at transport_cpp with an IndexError, then exposed the inherited base-tag rejection before repair.

All 46 generator tests pass and production generation remains byte-equivalent after newline normalization: no map interface is selected yet and no previous generated contract changes. An actual Fickl 0.6.9/Fable 5.24 synthetic generated-interface probe passes seven assertions in Chromium 156.0.8078.4: undefined, actual parsed unit/keyword/unparsed/image outputs, and null/forged-tag rejection. Independent source review is clear. Native monostate execution awaits the real map bindings; this checkpoint does not claim native or complete C13 conformance.
