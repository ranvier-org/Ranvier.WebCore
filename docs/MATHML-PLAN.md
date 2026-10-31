# S13 MathML typed element surface plan

**Goal:** Expose the pinned engine's typed MathML element surface and prove its typed, style, focus and data members, plus namespace identity, against a measured browser. Tracking issue: Ranvier.WebCore #89, engine route.

**Tree:** `C:/wk/native-mathml`, branch `codex/native-api-mathml`, from PR132 head `208f04a` (Native21/ABI29, 248 interfaces/2455 functions). No version or ABI allocation happens until a fresh absence check at freeze time. Native22 is reserved for H05, so this producer targets Native23.

## Pinned source scope

`Source/WebCore/mathml/MathMLElement.idl` and `MathMLMathElement.idl`. `ENABLE_MATHML=ON` in the slim cache, and `MathMLEnabled` is a runtime setting.

- `MathMLElement : Element` has no own members. Its mixins are `HTMLOrSVGOrMathMLElement` (dataset, nonce, autofocus, tabIndex, focus(options), blur()), `ElementCSSInlineStyle` (style, attributeStyleMap), and `GlobalEventHandlers`/`DocumentAndElementEventHandlers` (`on*` callback attributes).
- `MathMLMathElement : MathMLElement` has no own members.

## Baseline (already shipped)

Native21 already selects `MathMLElement`, with 11 functions:

- `get_dataset`, `get_nonce`/`set_nonce`, `get_autofocus`/`set_autofocus`, `get_tab_index`/`set_tab_index`;
- `get_style`, `get_attribute_style_map`, `focus`, `blur`.

`tests/abi/svg_mathml_surface.py` covers them on a single `<math>` element: style priority, dataset, nonce, autofocus, tabIndex, focus/blur identity and Tab traversal. That is the "Partial" baseline. It does not accept S13.

## Proposed scope

1. **Typed identity.** Select `MathMLMathElement` (0 new functions). Its node cast tag is `math`, so the F# model distinguishes `<math>` from other MathML elements. Plain MathML children (`mi`, `mo`, `mn`, `mfrac`, `mrow`, `msqrt`) are genuine `MathMLElement` instances, and HTML/SVG nodes are rejected with a subtype error (-11). Namespace and localName are checked through the existing Element API. If the generator needs a shape it lacks, I report that before changing anything.
2. **Members on every MathML element type in the fixture**, not only `<math>`:
   - dataset round trips through the attribute;
   - nonce keeps its value while the `nonce` attribute is hidden after connection;
   - autofocus and tabIndex default to -1 on non-focusable MathML, and an authored `tabindex` makes the element focusable;
   - `focus({preventScroll})` and `blur()` change the active element;
   - Tab order runs through MathML children.
3. **Style effects on real layout.** Set inline `style` and `attributeStyleMap` with typed values (`CSSUnitValue` for `font-size` and `padding`, and `math-depth`/`math-style` keywords). Then compare `getBoundingClientRect` and painted pixels before and after against Chromium for `mfrac`/`msqrt` layout.
4. **Errors and lifetime.** Null, wrong-thread and subtype errors leave the output untouched. The undersized UTF-8 string protocol is checked on nonce. Dataset and style-map handles stay usable after the owner is removed and the host is disposed, and weak owners expire.
5. **Capability.** Record `MathMLEnabled` and `ENABLE_MATHML` through the existing H07 capability catalogue (`dom:MathMLMathElement` and `build:ENABLE_MATHML`, if the catalogue lists it). No synthetic capability is added.
6. **Browser oracle.** Chromium is measured with the same fixture for typed identity, `instanceof` and member state. Members absent from Chromium are recorded as NotExposed, not assumed.

Out of scope, recorded explicitly:

- `on*` event-handler attributes. Generator policy excludes callback attributes, and events go through the existing EventTarget transport.
- MathML-specific HTML presentation attributes as typed members (the pinned IDL has none).
- Rendering engine changes. A RED in layout or paint goes to root as a Source proposal.

## Steps

1. Run a Chromium capability sweep and an exact member/contract list against the pinned IDL. Retain the RED: no `MathMLMathElement` type or cast tag in Native21.
2. Generator selection, regeneration and a private build that borrows Native21 objects read-only. I expect a glue/host-only rebuild, with no engine objects.
3. `tests/abi/mathml_surface.py`, `tests/fixtures/mathml-surface.html` and a Chromium oracle `.mjs`, with RED/GREEN evidence and receipts.
4. Regenerate the capability catalogue. Run gates, the full batch once at freeze, a fresh Native23 absence check, the bump, evidence JSON, and a PR stacked on the H05 Native22 PR, or on PR132 if root says so. Refs #89.

## Open questions for root

- Stack on H05's Native22 branch once it exists, or on PR132 now?
- Is the `MathMLEnabled`-off state required evidence (a disabled-setting host), or out of scope, since the host only reads settings?

## Checkpoint (focused, unallocated)

Root approved the plan: stack on PR132; a MathMLEnabled-off host is out of scope. `MathMLMathElement` is selected (249 interfaces, 2455 functions, 50 roots, 22 dictionaries, 0 stubs) and listed in the capability catalogue. RED: the Native21 runtime lacks `dom:MathMLMathElement`. GREEN: `tests/abi/mathml_surface.py` passes 371 assertions on the private candidate built on `native21-candidate-0032`, matching Chromium 156 on identity and namespace for 13 elements, all 11 mixin members, layout and paint effects of inline and typed style, focus, Tab order, nonce, autofocus and tabIndex, with error and owner-expiry checks (`docs/mathml-evidence/receipt.json`).

Qualifications: Chromium has no `MathMLMathElement` interface (NotExposed). The host always enables MathML, so disabled-setting behaviour is unexercised. The dataset missing-key `""` is the shared contract, not a native difference. Release-after-destroy is covered by six permanent Teardown.fs cases; #134 was a probe bookkeeping error and is closed. Native23 allocation, full batch and PR remain.
