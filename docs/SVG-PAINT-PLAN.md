# SVG paint servers, filters, clipping and resources implementation plan

> **For agentic workers:** Use superpowers:executing-plans in the existing implementation lane. No additional subagents. Steps use checkbox syntax; coordinator review precedes production changes.

**Goal:** Expose the complete selected S08/S09/S10/S11 typed SVG surface through existing engine APIs, prove reflected state and actual paint/resource effects, and deliver a reviewable producer PR with explicit remaining consumer and resource dependencies.

**Architecture:** Extend the existing selected-interface generator and reuse Native19 SVG value/list handles and actual WebCore renderers. Source fixes, if actual failing fixtures require them, belong exclusively to the coordinator. Browser operations act on real SVG objects; no renderer, filter kernel, URI resolver or decode algorithm is reconstructed.

**Tech stack:** Pinned WebKit C++, generated C ABI/F# contracts, Python ctypes native fixtures, actual Chromium/Playwright oracles, existing resource callbacks and EventTarget transport.

**Spec:** `C:/wk/ranvier-views/docs/superpowers/plans/2026-10-29-shared-native-api-tasks.md`, S08–S11; pinned-source ledger and required groups 85–88 in Ranvier.WebCore. Exact per-member signatures, IDL attributes and predicted native functions are in `svg-paint-scope.json` (276 member contracts plus source constants).

## Global constraints

- Isolated `C:/wk/native-svg-paint`, branch `codex/native-api-svg-paint`, starts frozen Native19 `d5471ced80c72a32e39eba210f89312703a2161a`. Native19 source/runtime/fixtures and consumer21 scope remain frozen.
- Forward-merge H07 Native20 before final version/ABI proof. Native21/ABI29 is only a possible later allocation; fresh package/tag/open-PR checks and coordinator allocation are required.
- No edits to shared `C:/wk/src`; send actual RED plus the smallest existing-engine reuse proposal to the coordinator.
- Private builds may borrow verified Native19 replacement objects read-only. New outputs live only in this tree. Cached `C:/wk/build-win-slim` and other producer outputs are immutable; retain before/after mtime checks.
- RTK prefixes every command, owned build/test leases are granted before work and released only at terminal completion, all created sessions are stopped, source uses CRLF and exact raw proof bytes are preserved.
- All selected members, all filter primitive types and all required dependencies stay visible. Representative paint cases supplement complete typed-member coverage; they do not replace it.
- No script execution, general navigation/network expansion, paused features, invented successful empty values, generated stubs, fake handles or relabeling SVG values as DOM geometry.

## Review focus

1. Inherited paint-server attributes can affect rendering while getters continue to report the element's own authored/default state. Tests distinguish those observations.
2. Animated wrappers are live and have independent value lifetimes; animated values and lists remain read-only. Owner removal and session disposal cannot create a dangling reference.
3. Filter enum/list/numeric changes must reach the actual renderer. Invalid enum/nonfinite restricted input errors preserve prior state; unrestricted outputs retain their engine values.
4. Resource response completion is different from image decode completion. Cancellation, host destruction, handler reentrancy and stale image generations must produce truthful terminal states.
5. Browser exposure and native availability differ. Missing interfaces, decode support, resource policy and script-disabled behavior require explicit capabilities rather than a typed undefined value.

## Exact scope and baseline

The Native19 baseline is 205 interfaces, 2234 functions, 50 value roots, 22 dictionaries and zero stubs. A read-only generator analysis predicts 248 interfaces, 2455 functions, the same 50 roots/22 dictionaries and zero stubs, preserving all 2234 previous function records exactly. This is a planning model, not a compiled/runtime claim.

The candidate adds 43 real node interfaces. Existing Pattern, Marker, Style, Symbol and Convolve exports remain part of their full group proof; their presence does not accept any group. `SVGComponentTransferFunctionElement` is assigned to S09 despite its historical ledger D09/S11 label, because S09 explicitly requires all component-transfer types.

`SVGUnitTypes` contributes the pinned constants Unknown=0, UserSpaceOnUse=1 and ObjectBoundingBox=2. It is not a refcounted native value object; the plan does not invent a handle/factory for it. Shared enum/constant projection must use these actual source values.

The coordinator approved the source-ledger SVGScriptElement boundary: real type/async/href reflection only, with native scripts still disabled. This is inert typed state, not permission to execute SVG scripts. The browser capability oracle inspected a disconnected script element and did not execute SVG scripts.

### S08: gradients, patterns and stops

- SVGGradientElement: gradientUnits, gradientTransform, spreadMethod and SVGURIReference.href.
- SVGLinearGradientElement: x1, y1, x2, y2, inherited gradient state.
- SVGRadialGradientElement: cx, cy, r, fx, fy, fr, inherited gradient state.
- SVGStopElement: offset; stop-color/stop-opacity/color come through the existing CSS declaration APIs consumed from C03.
- SVGPatternElement: patternUnits, patternContentUnits, patternTransform, x/y/width/height, viewBox/preserveAspectRatio, requiredExtensions/systemLanguage and href.

### S09: complete filter type set

All primitive standard x/y/width/height/result attributes remain flattened onto their actual concrete receivers. The source-selected classes and own parameters are:

- SVGFilterElement: filterUnits, primitiveUnits, x/y/width/height and href.
- SVGFEBlendElement: in1, in2, mode.
- SVGFEColorMatrixElement: in1, type, values.
- SVGFEComponentTransferElement: in1.
- SVGComponentTransferFunctionElement: type, tableValues, slope, intercept, amplitude, exponent, offset; actual SVGFEFuncA/B/G/RElement types inherit these members.
- SVGFECompositeElement: in1, in2, operator, k1/k2/k3/k4.
- SVGFEConvolveMatrixElement: in1, orderX/orderY, kernelMatrix, divisor, bias, targetX/targetY, edgeMode, kernelUnitLengthX/Y, preserveAlpha. Native19's supporting Boolean/integer route is retained, with full filter effects newly tested.
- SVGFEDiffuseLightingElement: in1, surfaceScale, diffuseConstant, kernelUnitLengthX/Y.
- SVGFEDisplacementMapElement: in1, in2, scale, xChannelSelector, yChannelSelector.
- SVGFEDistantLightElement: azimuth, elevation.
- SVGFEDropShadowElement: in1, dx/dy, stdDeviationX/Y, setStdDeviation(float,float).
- SVGFEFloodElement: standard attributes plus existing CSS flood-color/flood-opacity.
- SVGFEGaussianBlurElement: in1, stdDeviationX/Y, edgeMode, setStdDeviation(float,float).
- SVGFEImageElement: preserveAspectRatio, href and standard attributes; actual resource success/error effects remain required.
- SVGFEMergeElement: standard attributes and real merge-node children; SVGFEMergeNodeElement.in1.
- SVGFEMorphologyElement: in1, operator, radiusX/Y.
- SVGFEOffsetElement: in1, dx/dy.
- SVGFEPointLightElement: x/y/z.
- SVGFESpecularLightingElement: in1, surfaceScale, specularConstant, specularExponent, kernelUnitLengthX/Y.
- SVGFESpotLightElement: x/y/z, pointsAtX/Y/Z, specularExponent, limitingConeAngle.
- SVGFETileElement: in1.
- SVGFETurbulenceElement: baseFrequencyX/Y, numOctaves, seed, stitchTiles, type.

### S10: clipping, masks and markers

- SVGClipPathElement: clipPathUnits, transform and actual child geometry.
- SVGMaskElement: maskUnits, maskContentUnits, x/y/width/height, requiredExtensions/systemLanguage and actual child mask paint.
- SVGMarkerElement: refX/refY, markerUnits, markerWidth/Height, orientType/orientAngle/orient, setOrientToAuto(), setOrientToAngle(SVGAngle), viewBox/preserveAspectRatio and actual marker references.

### S11: reuse, content and resources

- Document.rootElement returns the actual nullable SVG document root.
- SVGUseElement: x/y/width/height and href; references to live targets and symbols.
- SVGImageElement: x/y/width/height, preserveAspectRatio, nullable crossOrigin, href, and the explicit decode dependency below.
- SVGForeignObjectElement: x/y/width/height with genuine HTML namespace child layout.
- SVGAElement: target, hreflang, rel, relList, type, href.
- SVGStyleElement: disabled, type, media, title and LinkStyle.sheet; existing CSS rule/declaration APIs supply real style effects.
- SVGSymbolElement: viewBox/preserveAspectRatio; SVGDefsElement, SVGGElement, SVGSwitchElement, SVGMetadataElement, SVGDescElement and SVGTitleElement: genuine types, namespace/content, inherited selected SVG state and reference/conditional behavior.
- SVGURIReference.href and SVGTests.requiredExtensions/systemLanguage stay on genuine concrete consumers, not fake mixin handles.
- SVGElement.className/ownerSVGElement/viewportElement remain actual SVG state. Existing generic DOM/style/event members stay consumed dependencies rather than new script/event execution scope.
- SVGScriptElement: approved type/async/href reflection only; scripts stay disabled.

## Per-member contract rules

`svg-paint-scope.json` records each selected member's source file, owner, IDL type/nullability/attributes, arguments, existing raw functions and proposed exact C signatures. Mixins map to the actual concrete receiver functions. Constants retain their exact source values. Browser exposure is currently marked pending actual oracle, not assumed from native IDL.

Readonly SVG property attributes return live SVGAnimated* handles. Mutation uses existing baseVal objects/lists; animVal objects/lists reject edits through the existing engine. Strings keep null versus empty distinctions and the existing UTF-8 length/buffer protocol; URI strings are authored state, not a fabricated fully resolved/rendered resource. The C ABI preserves out parameters on failure and the current null/thread/subtype/exception status rules. Value identity, retain/release, owner detachment and cross-session guards follow the existing provider contract.

Gaussian blur and drop-shadow setStdDeviation arguments are restricted floats: apply the existing finiteNumberInputs policy to exactly those receiver classes. Do not add global finite guards to SVG outputs or unrestricted dictionaries. Enum/domain exceptions come from the actual engine and must be compared with real browser behavior before fixing expectations.

### Required H05 dependency and decode boundary

H05 issue110 is open/not_started. Existing `rv_host_set_resource_handler(RvHost*,RvResourceHandler,void*)`, `rv_resource_load_finish(RvResourceLoad*,const uint8_t*,int32_t,const char*)` and `rv_resource_load_fail(RvResourceLoad*)` provide real asynchronous resource serving on the owning thread. The header requires exactly one completion, frees the opaque load at completion, and permits completion after document cancellation. A raw freed load is never called twice to simulate a managed duplicate-completion error.

The native SVG image `decode()` signature is `void decode(Ref<DeferredPromise>&&)`, forwarding to ImageLoader's promise-based decode API. The generator correctly reports `Promise<undefined>` unsupported. This plan neither constructs JavaScript promises nor turns a network response/load event into a successful decode result.

S11 will prove the existing actual native image/resource load/error/cancellation routes, paint after a valid image has decoded implicitly, owner-thread delivery, late completion after cancellation and teardown. Browser `SVGImageElement.decode()` success/rejection is measured separately. Until a genuine owned H05 completion/decode facade is delivered and consumed, native decode remains explicitly unsupported and H05 stays a required S11 acceptance blocker. A later minimal engine callback bridge requires its own actual RED/source reuse proposal and coordinator ownership; it is not silently included here.

## Task 1: fix exact source contracts and actual browser capabilities

**Files:** `docs/SVG-PAINT-PLAN.md`, `docs/svg-paint-scope.json`; later `tests/fixtures/svg-paint-*.svg` and retained browser oracles.

- [x] Coordinator approved all four group boundaries, Script reflection and H05 decode/blocker treatment before production changes.
- [ ] Measure genuine Chromium types and every proposed property/method, including missing/renamed members, nullable crossOrigin, units, enum rejection, nonfinite restricted offsets, live identity and animated read-only errors.
- [ ] Capture DOM/browser member absence as NotExposed; distinguish Unsupported and Unknown in shared capability planning. Retain exact browser version/source/raw JSON.
- [ ] Fix a member-to-fixture matrix covering all 276 members and every concrete filter type. Own inherited members already proven by Native19 can reference exact baseline proof, but each new concrete producer/parameter route gets actual read/mutate evidence.

## Task 2: S08 paint-server state and effects

**Files:** `gen/dom.json`, generated outputs; `tests/abi/svg_paint_servers.py`; shared `tests/fixtures/svg-paint-servers.svg` and browser oracle.

- [x] Run Native19 missing-gradient-getter RED and actual browser baseline first.
- [x] Select all S08 missing interfaces with the existing generator; no new header/cast primitive was required by the actual compiler.
- [x] Exercise all coordinate/unit/transform/offset property routes, href inheritance, viewBox/aspect-ratio and SVGTests lists. Verify reflected state and pixels at interior sample points after mutations.
- [x] Test stop color/opacity through the existing CSS declaration route. Verify base/animated/read-only list behavior, returned identity, enum failures and retained values after paint-server/root disposal.
- [x] Run complete S08 focused native/browser fixtures and retain the independently reviewable group checkpoint with exact source/runtime proof.

The focused S08 receipt records 565 native assertions, 82 browser state assertions and 25 screenshot pixel assertions. Previously absent pattern viewBox requires real authored attribute initialization before typed live-field edits affect paint in both engines. Raw absent→typed-only behavior is retained separately. Pattern SVGTests lists expose real list/attribute state, but neither typed list changes nor authored strings suppress pattern paint in the measured providers. These are explicit qualifications, not claimed fixes or S08 deferrals.

## Task 3: S09 all filter classes and real effect changes

**Files:** generator selection/output; `tests/abi/svg_filters.py`; `tests/fixtures/svg-filters.svg`; matching actual browser oracle.

- [ ] Run Native19 missing-filter-getter RED; select all 28 S09 class/mixin entries, including inherited component-transfer base and all four actual function children.
- [ ] Cover every listed parameter and each standard primitive property through real typed getters/baseVal/list edits. Test restricted setStdDeviation NaN/±Infinity and atomic failures, enum validation, numeric lists and missing/changed result/in references.
- [ ] Use deterministic isolated cells to prove actual blur, color-matrix, blend/composite, convolve, displacement, drop-shadow/flood, image, merge, morphology, offset, tile/turbulence effects, and diffuse/specular lighting with distant/point/spot sources.
- [ ] Compare qualitative interior pixel changes and exact reflected values; use deterministic turbulence seed and transparent/opaque fixtures. No zero-valued success stand-ins or filter implementation in test/provider code.
- [ ] Verify four component channels independently and real filter graph ordering/inheritance. Dispose returned wrappers/lists/children and prove final owner expiry.
- [ ] Run complete S09 focused fixtures and commit with exact source and runtime proof, without promoting incidental Native19 Convolve exports to prior acceptance.

## Task 4: S10 clipping, masks and markers

**Files:** generator selection/output; `tests/abi/svg_clip_mask_marker.py`; `tests/fixtures/svg-clip-mask-marker.svg`; browser oracle.

- [ ] Capture missing clip/mask binding RED; preserve existing marker bindings.
- [ ] Mutate units, geometry, transforms, viewBox/aspect-ratio, marker dimensions/reference points and automatic versus explicit angle orientation.
- [ ] Verify actual clipping, alpha/luminance mask paint and marker output at interior points. Test references to removed/replaced nodes and retained angle/length/value wrappers.
- [ ] Check SVGTests language/extension list effects honestly against actual providers; do not infer effect solely from reflected list entries.
- [ ] Verify read-only/invalid arguments and final handle/owner expiry; run full focused browser/native fixtures and commit.

## Task 5: S11 reuse/content and truthful resource completion

**Files:** generator selection/output; `tests/abi/svg_resources.py`; `tests/fixtures/svg-resources.svg`; browser/resource oracles; no promise-return stub.

- [ ] Capture missing use/image/foreignObject/link/content type route RED. Select all approved real content classes and URI/test mixin consumers.
- [ ] Verify use/symbol/defs reference geometry/paint and updates after target changes; metadata/desc/title text and namespace; SVG a rel/relList/target/etc.; style disable/rule effects; real foreignObject HTML layout; switch conditional language/extension behavior.
- [ ] Serve deterministic PNG/SVG image fixtures using existing native callbacks and a bounded local browser origin. Verify href/crossOrigin/aspect-ratio and actual decoded paint, failed bytes/network errors, old-generation cancellation and late completion after owner removal.
- [ ] Assert exactly one terminal managed outcome per resource generation and UI-thread delivery where the existing facade supports it. If no shared H05 facade exists, retain that precise required blocker; do not claim this producer closes H05/S11.
- [ ] Record real browser decode Promise success/rejection and native Unsupported capability. Native scripts and foreignObject scripts remain disabled even when typed SVG script state is edited.
- [ ] Exercise null/thread/subtype/exception/output-preservation errors, listener removal, pending load teardown, retained values and final weak-owner expiry; run the whole S11 focused producer fixture and commit.

## Task 6: coherent source freeze, forward merge and reviewable PR

**Files:** final plan/scope/evidence, generated checks, `scripts/abi_tests.py`, `.github/workflows/build.yml`, allocation/version files only after approval.

- [ ] Forward-merge final H07 Native20 into this branch and resolve only owned production files. Preserve all Native19 source patches/DOM functions and H07 capability contracts; root owns any shared Source changes.
- [ ] Obtain fresh allocation proof and coordinator approval; then set the actual final version/ABI and affected version probes. Never move an existing tag or infer managed/native version equality.
- [ ] Freeze exact source/fixtures/canonical/model hashes. Compile private replacement objects and link a coherent runtime, checking borrowed/cached object mtimes.
- [ ] Batch the complete affected native surface/callback/frame/teardown regressions once source is stable; retain each actual exit code, exact executed source snapshot, raw log digest and all shipping DLL hashes. Run generator/.NET/Fable checks and actual browser fixtures; new consumer JIT/AOT/platform/official gates remain separate.
- [ ] Request the existing independent acceptance lane's bounded audit, fix findings and repeat only checks affected by a real change.
- [ ] Commit via a message file/coauthor footer, push and open an attached conventional stacked PR on Native20, add project tracking and hand exact HEAD/run IDs to the sole release/CI owner. Keep issues85–88 open until their complete shared/platform/official acceptance is proven.

## Coordinator review checkpoint

The coordinator approved the complete member/type set, inert Script reflection boundary, constant-only SVGUnitTypes treatment and explicit H05/native decode dependency. S08 now has a focused private checkpoint; S09/S10/S11 remain in progress. No subsequent native version is allocated. Final H07 forward merge, integrated exact-byte proof, independent review, shared consumers and official/platform acceptance remain required.
