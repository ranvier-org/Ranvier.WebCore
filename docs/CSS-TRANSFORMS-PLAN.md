# C16 typed transform components

## Required result

Expose the engine's typed transform list and translate, rotate, scale, skew, perspective and matrix components through shared browser/native contracts. Reuse DOMMatrix from G08 and the existing typed CSS value transport. Numeric arithmetic C15 and color C17 remain deferred.

## Source audit

The pinned css/typedom/transform implementation supplies all mathematics, serialization and type validation. CSSTransformComponent has virtual type classification, so existing runtime type queries apply. CSSTransformValue extends CSSStyleValue; parsed transform lists must retain that actual subtype. Component toMatrix results use the existing trusted mutable DOMMatrix handle producer.

Three binding gaps remain: overloaded CSSRotate constructors need distinct exports; CSSPerspectiveValue's nested WebIDL union must reach the engine's flat variant; and restricted double arms in CSSNumberish must reject NaN/infinity without restricting unrestricted geometry doubles. Optional scale z can reuse the G08 optional compound input primitive.

## Implementation sequence

- [x] Add arity-aware constructor exports with locked-name preservation, first observing a duplicate-export regression.
- [x] Add selected union flattening and finite numeric arm validation with old-model compatibility checks.
- [x] Select TransformValue, TransformComponent, Translate, Rotate, Scale, Skew, SkewX, SkewY, Perspective and MatrixComponent plus its options dictionary.
- [x] Verify raw typed component construction, mutation, serialization, transform list ordering and toMatrix results against a coherent private producer.
- [ ] Add shared constructor providers and generated native wrappers; compare JIT/AOT/Chromium with exact errors and lifetime checks.
- [ ] Run a combined batch, review source and old ABI compatibility, then allocate the next unpublished producer cohort and stack it behind Native16.
- [ ] Complete all-platform and official consumer acceptance before closing C16.

## Required semantic profiles

Angle-only rotation is 2D; axis rotation is 3D. Omitted translate z and scale z differ from explicitly supplied zero/one in is2D. Skew and perspective is2D setters follow their engine no-op behavior. Translate percentage/relative units may construct successfully but cannot resolve to a matrix without supported absolute units; do not invent layout resolution.

Transform lists retain component identity and ordering, append at length and reject larger indices. MatrixComponent construction copies its input and its matrix getter remains live. The pinned implementation currently aliases its internal matrix from 3D toMatrix, but that is a defect to reproduce rather than a shared identity guarantee. Returned same-object handles elsewhere still own a separate exported reference.

All these assertions require actual probes. This planning checkpoint claims no C16 binding or runtime acceptance.

## Constructor binding primitive

The first regression reproduced duplicate css_rotate_create exports for the angle and axis constructors. New overloaded constructors now use arity suffixes. An exact previously locked plain C signature keeps its name, and subsequent arity-named generations remain stable. Ambiguous same-arity overloads still fail closed through the existing duplicate-export check.

All 57 generator tests pass. Production generation remains unchanged at 143 interfaces and 1,875 functions because no transform component is selected yet. Independent source review found no blocker. This checkpoint is generator proof, not native component execution or C16 acceptance.

## Union input primitives

A regression first observed the perspective typedef as a nested two-arm union where C++ requires three flat arms. Explicitly selected typedefs now flatten into the same leaf order for native and shared contracts. Unselected union shapes remain unchanged; nullable nested unions remain unsupported rather than silently changing their meaning.

A separate regression first observed missing finite-input validation for CSSNumberish. Configured restricted double/float union arms now record a TypeError before constructing the argument or calling the engine when input is NaN/infinite. Unrestricted geometry doubles are unaffected. The finiteInput model flag describes inputs only; output encoding does not discard or reject engine values.

All 59 generator tests pass and production generation is still unchanged at the Native16 surface. Independent source review is clear. Component selection, compiled engine calls and shared runtime verification remain pending.

## Browser baseline and additional source gaps

Actual Chromium 156.0.8078.4 confirms list ordering/index behavior, 2D default distinctions, finite CSSNumberish rejection and perspective/relative-unit behavior. It rejects invalid translate/scale setter dimensions immediately; the pinned engine's corresponding setters omit those checks. Scoped native binding validation may close that gap without changing engine class signatures or mathematics, after a native regression reproduces it.

Chromium also returns a separate matrix from a 3D MatrixComponent. The [Typed OM toMatrix algorithm](https://drafts.css-houdini.org/css-typed-om/#dom-csstransformcomponent-tomatrix) requires a new matrix whose is2D flag matches the component. Audit the pinned component implementations and reproduce any alias/flag defects before repair.

Several component numeric getters return const CSSNumericValue references in C++. They still expose ordinary mutable Typed OM value objects through WebIDL. Add narrowly configured retained const-result handling for these producers; do not broaden generic handle const casts. The ignored browser audit script and JSON are artifacts/c16-browser-audit.mjs and artifacts/c16-browser-audit.json.

## Const getter primitive

Named const getter bindings now require their exact declared object interface and root; unmatched or mismatched configuration fails closed. A helper emitted only for those getters requires an exact const lvalue reference and polymorphic root at compile time, acquires one external reference, and preserves the existing opaque pointer. Generic storeHandle remains unchanged. The audited fields hold mutable Ref<CSSNumericValue> objects; the const qualifier belongs to the C++ accessor, not an immutable WebIDL object.

The regression first failed at the missing specialized retained-result path. All 60 generator tests pass and Native16 production generation remains unchanged. Independent review is clear. Actual component compilation, returned-value identity and reference-lifetime probes remain pending.

## Native17 producer verification

The selected surface now contains 153 interfaces, 1,926 functions, 24 handle roots and 21 dictionaries, with no stubs. Native17 uses ABI25. The final private Windows batch passed 6,384 assertions across 19 raw API probes, the full ABI driver and 42 final teardown cases. The transform fixture contributes 405 assertions, including typed-map assignment and actual element geometry. The evidence manifest, `css-transforms-evidence/evidence.json`, records executed runtime hashes, source hashes and individual log hashes. Immediate engine references can survive until collection; final expiry is the checked teardown requirement.

Native regressions reproduced invalid translate/scale setter acceptance, matrix aliasing and incorrect matrix flags. Scoped input validation checks dimensions before mutation. Patch 0022 makes matrix conversion return an independent matrix with the component's flag, including perspective-none. No engine mathematics or class signatures were replaced.

The browser binding validates actual numeric/keyword objects before WebIDL coercion and prevents the maximum unsigned index from becoming an expando property. A narrowly configured toMatrix adapter preserves all sixteen matrix values while correcting Chromium's observed false-component/true-matrix flag mismatch. Configuration is restricted to the named zero-argument toMatrix operations. All 64 generator tests, four package-contract tests and five publication-barrier tests pass; regeneration is exact.

Shared Core/Views providers, NativeAOT, non-Windows runtimes, official packages and C16 acceptance remain separate gates. This producer evidence does not close C16.
