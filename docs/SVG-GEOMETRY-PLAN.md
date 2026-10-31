# SVG geometry and value bindings

## Required result

Deliver S01 graphics bounds/coordinate transforms, S02 path sampling and fill/stroke hit testing, and S04 SVG value/list factories through the existing shared browser/native contracts. S03 shape-specific reflection remains a separate required group. Reuse WebCore's SVG geometry and mutation machinery; do not implement another geometry engine.

## Audited source and ownership

The source is the pinned WebKit checkout used by Native17, with its 23 applied patches. The isolated producer branch starts at Native17 source 4091b07c5bff99d7acbe91c717165e7f94f40f81. Root owns this producer worktree and the shared engine checkout. The preceding Native17 source and runtime evidence remain frozen.

SVGGraphicsElement supplies getBBoxForBindings, getCTMForBindings and getScreenCTMForBindings. Its transform property uses SVGAnimatedTransformList. SVGGeometryElement supplies getTotalLength, getPointAtLength, isPointInFill and isPointInStroke; the hit tests take the already supported DOMPointInit dictionary. SVGFitToViewBox supplies viewBox and preserveAspectRatio on the root and applicable element types.

The pinned engine returns SVGRect, SVGMatrix and SVGPoint objects. Actual Chromium156 probes also return SVGMatrix/SVGPoint for root factories and getCTM. Preserve the actual values and document the shared projection; do not relabel native pointers as DOMMatrix or DOMRect. The pinned SVG point/rectangle fields use float precision, and matrix fields use double precision. Cross-target fixtures must exercise that distinction rather than claim unrestricted double precision for every SVG value.

SVGSVGElement supplies the SVGNumber, Length, Angle, Point, Matrix, Rect and Transform factories. The value/list interfaces supply checked mutations, identity, unit conversions and base/animated values. SVGProperty has a virtual destructor and owner attachment/detachment machinery. Retained live values, read-only animated values, owner destruction and list ownership require runtime verification.

## Concrete binding gap

Ten selected animated-value interfaces are aliases declared by svg/properties/SVGAnimatedPropertyImpl.h. They have no corresponding individual C++ headers. A regression reproduced the generator's incorrect SVGAnimatedNumber.h include. Scoped interfaceHeaders configuration now identifies the real declaration header without changing C++ types, opaque pointer identity or reference counting. Unselected interfaces, missing headers, absolute paths and parent traversal fail closed. The header list is deduplicated after substitution.

The generator has 73 passing tests. Before selecting SVG, Native17 regenerated exactly at 153 interfaces and 1,926 functions. The complete supporting selection produces 189 interfaces, 2,182 functions, 49 handle roots, 22 dictionaries and no stubs. This includes all viewBox-bearing element types, text-positioning access to length/number lists and polygon/polyline access to point lists. All 1,926 previous function records, dictionaries, containers and runtime queries remain unchanged. [The per-member scope](svg-geometry-scope.json) records the added signatures and implementation routes. The private Windows candidate compiles and passes the focused raw probe; shared and official acceptance remain pending.

## Implementation and acceptance

- [x] Inspect the pinned SVG implementations and identify alias-header requirements.
- [x] Reproduce incorrect alias-header emission and add scoped generation support with rejection cases.
- [x] Review the primitive and preserve exact existing generated output.
- [x] Freeze per-member S01/S02/S04 scope and capability mappings before selecting production interfaces.
- [x] Compile the selected glue against a coherent private producer; preserve every previous ABI record.
- [x] Probe nested/transformed SVG bounds, CTM/screenCTM, viewBox and preserveAspectRatio effects.
- [x] Probe a 100-unit line and its midpoint, curved paths, and fill/stroke tests in the correct coordinate space.
- [x] Probe factory defaults, SVG units, list append/insert/replace/remove, identity and read-only animated values.
- [x] Verify raw retained values and list members across mutation, detach, host disposal and final owner collection, plus wrong-thread rejection.
- [ ] Verify cross-session ownership rejection in shared providers; raw native SVG handles carry no session identity.
- [ ] Add shared browser/native fixtures and run JIT, NativeAOT and browser acceptance in a batch.
- [ ] Allocate an unpublished producer/consumer cohort, stack its PRs, and verify all native platforms and official packages before closing the API groups.

Root owns only the isolated producer, its generator/configuration/generated outputs and native fixtures. Shared Core/Views additions require a separately owned consumer tree after the member scope is frozen. Incidental root view/animation operations exposed by selecting SVGSVGElement do not close S06 or S07 without their own complete acceptance.

## Handover checkpoint

The first actual private compilation reproduced incorrect non-animated C++ getter selection and an incomplete TrustedScriptURL type used by SVGAnimatedString's existing setter parameter. Generation now follows WebKit's Animated suffix convention after ImplementedAs and includes that parameter's declaration without exposing Trusted Types through the ABI. The next compilation reached one remaining SVGSVGElement.getElementById String-to-AtomString mismatch. RequiresExistingAtomString conversion now uses StringView.toExistingAtomString, matching the engine's lookup semantics without interning missing names.

All 69 focused generator tests and 14 repository Python contract/release tests pass after these changes, including regressions observed before each repair. The final C++ repair compiled privately. The first 187-interface geometry probe passed 101 assertions. A reachability audit then added polygon/polyline point-list getters; the expanded 189-interface candidate compiled and passed 466 focused assertions. This includes retained values after host disposal and final document/root/polygon weak-watch expiry after release and collection. The standard ABI test script now runs that probe on every native platform.

Attached SVG list items are cloned when inserted in another list, preserving the original item's owner and identity. Detached items insert by identity. Transform factories create identity matrices with type MATRIX. Point and rectangle fields preserve pinned float precision; matrix coefficients retain double precision. Animated values reject mutation while attached. The native SVGProperty detach operation resets access to read/write once the owner detaches it; shared lifetime behavior must be verified against browser objects separately.

The later dictionary-alias regression reproduced ignored m11/m12/m21/m22/m41/m42 coefficients. Exactly three selected SVG transform operations now reuse DOMMatrixReadOnly::validateAndFixup and pass normalized a/b/c/d/e/f to the existing engine method. No engine signature or geometry algorithm changes. The browser adapter normalizes the dictionary, creates a genuine SVGMatrix, and invokes the actual receiver. Browser probes cover cross-frame input/receiver objects and result realm/identity. Native scalar NaN/Infinity acceptance was separately reproduced; existing finiteNumberInputs checks now enforce the selected SVG restricted float/double inputs. Dictionary fields remain unrestricted on native.

The final Native18/ABI26 candidate passes the strengthened 639-assertion SVG probe, including every earlier case and these boundary regressions. Its exact executed source is retained beside the [final private evidence](svg-geometry-evidence/final-evidence.json). The historical ABI25 6,850/466 receipt is preserved separately; its old466 source bytes were not archived. Five preceding lookup implementations now honor RequiresExistingAtomString through existing-table lookup; all previous ABI records remain unchanged and 1,921 prior glue bodies remain byte-identical after line-ending normalization.

The measured Chromium dictionary adapter cannot copy nonfinite coefficients into restricted SVGMatrix properties, so those three browser routes throw TypeError for such dictionaries. Native dictionary routes retain NaN/Infinity. This route limitation is explicit and does not narrow DOMMatrix2DInit globally. No shared NativeAOT, non-Windows or official SVG acceptance is claimed. The complete preceding Native17 runtime remains frozen in its separate worktree. Polygon/polyline getters make S04 lists reachable and do not complete S03 shape-specific reflection.
