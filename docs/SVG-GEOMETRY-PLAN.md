# SVG geometry and value bindings

## Required result

Deliver S01 graphics bounds/coordinate transforms, S02 path sampling and fill/stroke hit testing, and S04 SVG value/list factories through the existing shared browser/native contracts. S03 shape-specific reflection remains a separate required group. Reuse WebCore's SVG geometry and mutation machinery; do not implement another geometry engine.

## Audited source and ownership

The source is the pinned WebKit checkout used by Native17, with its 23 applied patches. The isolated producer branch starts at Native17 source 4091b07c5bff99d7acbe91c717165e7f94f40f81. Root owns this producer worktree and the shared engine checkout. The preceding Native17 source and runtime evidence remain frozen.

SVGGraphicsElement supplies getBBoxForBindings, getCTMForBindings and getScreenCTMForBindings. Its transform property uses SVGAnimatedTransformList. SVGGeometryElement supplies getTotalLength, getPointAtLength, isPointInFill and isPointInStroke; the hit tests take the already supported DOMPointInit dictionary. SVGFitToViewBox supplies viewBox and preserveAspectRatio on the root and applicable element types.

The pinned engine returns SVGRect, SVGMatrix and SVGPoint objects, while current Chromium uses DOM geometry objects for several equivalent operations. Preserve the actual engine values and document the shared projection; do not relabel native pointers as DOMMatrix or DOMRect. The pinned SVG point/rectangle fields use float precision, and matrix fields use double precision. Cross-target fixtures must exercise that distinction rather than claim unrestricted double precision for every SVG value.

SVGSVGElement supplies the SVGNumber, Length, Angle, Point, Matrix, Rect and Transform factories. The value/list interfaces supply checked mutations, identity, unit conversions and base/animated values. SVGProperty has a virtual destructor and owner attachment/detachment machinery. Retained live values, read-only animated values, owner destruction and list ownership require runtime verification.

## Concrete binding gap

Ten selected animated-value interfaces are aliases declared by svg/properties/SVGAnimatedPropertyImpl.h. They have no corresponding individual C++ headers. A regression reproduced the generator's incorrect SVGAnimatedNumber.h include. Scoped interfaceHeaders configuration now identifies the real declaration header without changing C++ types, opaque pointer identity or reference counting. Unselected interfaces, missing headers, absolute paths and parent traversal fail closed. The header list is deduplicated after substitution.

The generator has 66 passing tests. With no production configuration change, Native17 still regenerates exactly at 153 interfaces and 1,926 functions. A temporary source audit selecting the complete supporting type set produces 181 interfaces, 2,131 functions, 49 handle roots, 22 dictionaries and no stubs. That prospective model is not compiled or accepted support.

## Implementation and acceptance

- [x] Inspect the pinned SVG implementations and identify alias-header requirements.
- [x] Reproduce incorrect alias-header emission and add scoped generation support with rejection cases.
- [x] Review the primitive and preserve exact existing generated output.
- [ ] Freeze per-member S01/S02/S04 scope and capability mappings before selecting production interfaces.
- [ ] Compile the selected glue against a coherent private producer; preserve every previous ABI record.
- [ ] Probe nested/transformed SVG bounds, CTM/screenCTM, viewBox and preserveAspectRatio effects.
- [ ] Probe a 100-unit line and its midpoint, curved paths, and fill/stroke tests in the correct coordinate space.
- [ ] Probe factory defaults, SVG units, list append/insert/replace/remove, identity and read-only animated values.
- [ ] Verify retained values and list members across mutation, detach, document disposal and final collection, including wrong-thread and cross-session rejection.
- [ ] Add shared browser/native fixtures and run JIT, NativeAOT and browser acceptance in a batch.
- [ ] Allocate an unpublished producer/consumer cohort, stack its PRs, and verify all native platforms and official packages before closing the API groups.

Root owns only the isolated producer, its generator/configuration/generated outputs and native fixtures. Shared Core/Views additions require a separately owned consumer tree after the member scope is frozen. Incidental root view/animation operations exposed by selecting SVGSVGElement do not close S06 or S07 without their own complete acceptance.
