# C16 typed transform components

## Required result

Expose the engine's typed transform list and translate, rotate, scale, skew, perspective and matrix components through shared browser/native contracts. Reuse DOMMatrix from G08 and the existing typed CSS value transport. Numeric arithmetic C15 and color C17 remain deferred.

## Source audit

The pinned css/typedom/transform implementation supplies all mathematics, serialization and type validation. CSSTransformComponent has virtual type classification, so existing runtime type queries apply. CSSTransformValue extends CSSStyleValue; parsed transform lists must retain that actual subtype. Component toMatrix results use the existing trusted mutable DOMMatrix handle producer.

Three binding gaps remain: overloaded CSSRotate constructors need distinct exports; CSSPerspectiveValue's nested WebIDL union must reach the engine's flat variant; and restricted double arms in CSSNumberish must reject NaN/infinity without restricting unrestricted geometry doubles. Optional scale z can reuse the G08 optional compound input primitive.

## Implementation sequence

- [x] Add arity-aware constructor exports with locked-name preservation, first observing a duplicate-export regression.
- [ ] Add selected union flattening and finite numeric arm validation with old-model compatibility checks.
- [ ] Select TransformValue, TransformComponent, Translate, Rotate, Scale, Skew, SkewX, SkewY, Perspective and MatrixComponent plus its options dictionary.
- [ ] Verify raw typed component construction, mutation, serialization, transform list ordering and toMatrix results against a coherent private producer.
- [ ] Add shared constructor providers and generated native wrappers; compare JIT/AOT/Chromium with exact errors and lifetime checks.
- [ ] Run a combined batch, review source and old ABI compatibility, then allocate the next unpublished producer cohort and stack it behind Native16.
- [ ] Complete all-platform and official consumer acceptance before closing C16.

## Required semantic profiles

Angle-only rotation is 2D; axis rotation is 3D. Omitted translate z and scale z differ from explicitly supplied zero/one in is2D. Skew and perspective is2D setters follow their engine no-op behavior. Translate percentage/relative units may construct successfully but cannot resolve to a matrix without supported absolute units; do not invent layout resolution.

Transform lists retain component identity and ordering, append at length and reject larger indices. MatrixComponent construction copies its input, its matrix getter remains live, and toMatrix may preserve identity for a 3D component while a 2D component returns a flattened copy. Returned same-object handles still own a separate exported reference.

All these assertions require actual probes. This planning checkpoint claims no C16 binding or runtime acceptance.

## Constructor binding primitive

The first regression reproduced duplicate css_rotate_create exports for the angle and axis constructors. New overloaded constructors now use arity suffixes. An exact previously locked plain C signature keeps its name, and subsequent arity-named generations remain stable. Ambiguous same-arity overloads still fail closed through the existing duplicate-export check.

All 57 generator tests pass. Production generation remains unchanged at 143 interfaces and 1,875 functions because no transform component is selected yet. Independent source review found no blocker. This checkpoint is generator proof, not native component execution or C16 acceptance.
