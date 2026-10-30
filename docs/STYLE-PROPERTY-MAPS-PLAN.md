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

## Basic map binding checkpoint

The next private checkpoint selects 138 interfaces, 1,738 functions and 20 handle roots, with zero stubs. Configured non-node CallWith operations take an explicit checked Document parameter. The generated code promotes the validated pointer to Ref<Document> before passing a reference to the real engine methods. No-context scalar size and existing node CallWith behavior remain unchanged. Model metadata names contextReceiver/contextParameter so providers can bind the acquisition document without consuming an IDL argument.

Nullable CSSStyleValue sequence elements use a distinct container from the existing nonnullable parseAll result. All 1,725 previous function records, 26 container records, 16 dictionaries, eight enums, 214 tag records and four runtime queries remain unchanged. All 48 generator cases pass, including observed failures for absent context support and the nullable-container collision. Generated F# passes Fantomas; the coherent private Windows glue and host compile successfully without changing cached or parent outputs.

The old producer fails the permanent new raw fixture at the missing map-get export. The new candidate executes missing-get monostate and typed/scalar/liveness cases, then fails multi-image set with TypeError/Invalid values. Reduction confirms single-image and multi-animation-name writes work, as does ordinary CSS text with multiple images. CSSProperties.json incorrectly supplies space separators for the four comma-layered background properties; an independent source audit confirms the separator is consumed by Typed OM list construction.

A separate diagnostic control uses the passing animation-name list to reach declared-map tests without removing the permanent failing image assertion. It passes 91 basic checks, then fails the owning-rule edit after cache-sharing stylesheet COW. The repair must acquire the backing StyleRule after RuleMutationScope can clone/reattach it. The source repairs are being prepared and are not yet verified in a rebuilt candidate. Entry enumeration and the complete shared/platform/public gates remain outstanding. This source checkpoint is not a releasable package cohort or C13 acceptance.

## Focused engine repair evidence

The repaired private candidate passes 189 permanent typed-map assertions, including three image values, set/append on all four background properties, inner background-size spaces, animation-name comma and grid-auto-columns space controls, and the owning-rule/COW-copy/44px layout check. Existing typed-value coverage also passes all 190 assertions. Both outputs release their retained handles. This replaces the earlier failing result for these focused cases without removing either assertion.

Patches 0019/0020 independently review clear; all 21 patches dry-run against the pinned source. Private property regeneration changes only four separator returns in CSSPropertyNames.cpp and its gperf input, plus the source metadata copy. All generated headers and other derived outputs remain identical. Compiling a newly generated CPP beside duplicate private headers initially caused header redefinitions; the private build now compiles the exact same generated CPP from its output root against the verified unchanged cached headers. Cached and borrowed build artifacts are verified unchanged.

The corrected runtime is artifacts/typed-maps-repaired/runtime, separate from the retained failing candidate in artifacts/typed-maps/runtime. Broader six-mutator COW, priority and expired-owner probes are still being added; entry enumeration, shared providers and final gates remain incomplete.

The broader acceptance probe exposed a further real defect in both declared and inline typed custom setters: important declarations retained their previous values. Patch 0021 routes explicit replacement through setProperty rather than the cascade merge helper, preserving the separate stylesheet parser behavior. Changed-value and same-value importance removal now pass in both paths.

The final focused runtime at artifacts/typed-maps-priority-complete/runtime passes 189 map assertions, 2,069 independently authored declared-map assertions, 190 existing typed-value assertions and 231 existing registration assertions (2,679 total). The declared-map gate covers all six fresh-pair COW mutation branches, complete copied/owning-sheet preservation, wrapper identity, actual geometry, invalid mutation preservation, both priority replacement profiles and expired weak owners. The custom setter's success/no-op profile after owner expiry is characterized explicitly; it is not misreported as a TypeError.

All 22 patches dry-run against the pin and the three new repairs independently review clear. The two map probes are wired as separate steps on every slim platform and are also included in the ABI harness and extracted-package audit. These are private Windows focused results. Snapshot entries, shared provider conformance, the final combined gate, platform CI and official normal/traced consumption remain required before C13 acceptance.

## Entry snapshot binding checkpoint

The opt-in iterable binding now exports one engine snapshot facade, bringing the model to 1,739 functions. The parser preserves the pinned key/value iterable declaration. The ABI accepts a checked map and Document and collects public createIterator(context)/next results, introducing no iterator-lifetime handles or owner registry. The shared service exposes Entries; the generated DOM interface does not misdeclare JavaScript's iterator method as an array method.

Each owned entry pair contains a UTF-8 key span and a nullable-element value sequence. Pair and outer sequence releases clear all nested ownership; retaining a value before releasing the snapshot preserves its independent lifetime. All old 1,725 function records, 26 containers, dictionaries, enums and runtime-query records remain identical. All 49 generator tests pass after observing the missing export failure. The full C++ glue/host compile succeeds; generated managed interop builds with the installed .NET10 SDK, zero warnings/errors.

The previous producer fails the entry fixture at its missing export. The new coherent private runtime at artifacts/typed-map-entries/runtime passes 144 explicit entry assertions: empty/inline/computed/declared/detached maps, declaration order and Unicode keys, list cardinality, snapshots across mutation/clear, retained values after nested/outer release, release resets and checked context/thread errors. Per-entry storage invariants additionally reject malformed data without counting successful phase markers as assertions. Computed vocabulary is validated without asserting equal whole-map sizes across engines. The fixture is wired independently on every slim CI platform, in the ABI harness and extracted-package audit. New shared Entries decoding, provider conformance, the final combined gate and public/platform acceptance remain pending.

## Next unpublished cohort allocation

The release lane verified all 33 candidate package/version pairs and corresponding repository tags were absent, with no other lane reservation. This development branch now allocates Native preview.15 / ABI23, separate from preview.14. The paired Core DOM packages allocate alpha.15; Views allocate 0.1.5 and backend/SDL alpha.5. Frozen profiles and earlier proof caches remain unchanged.

The ABI23 host-only rebuild reuses the verified entry-enabled WebCore and unchanged host objects, replacing only the ABI implementation object and relinking the host. The new private runtime at artifacts/cohort15/runtime passes all five focused gates: maps189, declared2069, entries144, typed values190 and registration231, totaling2,823 assertions. Existing ABI driver and exact-version probes now require23. This allocation is not a publication or complete platform/consumer acceptance claim; the final source pin will follow the final producer cohort.
