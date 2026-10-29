# Retained CSSOM settings context repair

Required C21 proves typed position fallback edits, actual placement and retained objects after rule removal. The Views fixture at `C:/wk/rv-position-try` passes 44 Chromium assertions but official native preview.11 fails at `CSSPositionTryRule.style` after deletion. This is separate from the resolved frame-phase preference difference.

## Existing behavior and root cause

`gen/domgen.py::setting_check` recovers a CSS rule/declaration's settings document exclusively through its current parent stylesheet. CSSRule deliberately clears that relationship on removal. WebKit's JavaScript binding exposure instead uses its wrapper-global script context. The native glue therefore returns Unsupported for a legitimate retained object.

There are two further source defects in retained descriptors: PropertySetCSSDescriptors.willMutate refuses edits without a parent sheet, and its parser context falls back to default property settings after removal. A context-only gate change is insufficient. CSSPositionTryDescriptors' invalidation callback also asserts that a sheet exists even for detached objects.

## Design

- Preserve the live-parent-first setting check and fail closed for disabled or expired/missing document contexts. No last-active-host fallback or global raw-pointer registry.
- Add one owned context pointer to CSSRule. Its sidecar holds a weak original Document captured while attached and an optional parser-context snapshot captured before parent links are cleared. The base class's explicit size assertion must model this one extra pointer; the source rule AST layout is unchanged.
- Capture original weak document context when a CSSOM rule is created or given a parent. Before clearing/replacing its parent link, copy the live stylesheet parser context. Prefer the live parent context for all attached operations.
- Add a narrow documentForBindings helper to CSSRule. Keep parserContext returning the live context while attached and the retained snapshot after detachment. PropertySetCSSDescriptors can copy that context through a narrow friend relationship.
- Give each descriptor object its own weak original Document and parser-context snapshot. Its parentRule is already weak and can expire independently, so a descriptor cannot rely on retaining the rule or sheet.
- Permit detached descriptor edits on the retained property set. Preserve attached willMutateRules/didMutate notification and copy-on-write pairing. Detached edits clear value caches but notify no stylesheet.
- Make detached position-try invalidation return normally without parent-sheet assertions. Attached edits continue invalidating remembered placement choices.
- Use the helper only for CSSRule and the actual PropertySetCSSDescriptors-derived scoped interfaces in the canonical generator. Preserve native signatures, ABI21 and all 1702 functions.

## Ownership and files

Root owns WebKit CSSRule.h/.cpp, PropertySetCSSDescriptors.h/.cpp and CSSPositionTryDescriptors.cpp, plus a numbered `0017` patch and generator changes in this isolated Native worktree. The counter-style lane owns CSSCounterStyleRule.h/.cpp and patch0016. A single agreed owner will compile/stage the shared source after both patches are reviewed.

## Verification

- [x] Review this bounded design, particularly the one-pointer CSSRule size change, weak owner graph, parser snapshot and attached mutation pairing. Independent review also covered live stylesheet scope and detached parent-rule propagation.
- [x] Add a generator regression for helper-based gates and retain exact disabled-setting checks. The old generator fails the new helper assertion; all32 tests pass after the change.
- [x] Preserve the current raw/typed native RED; implement patch0017 plus canonical generator changes. Official preview.11 returns-9 after deletion. All18 patches dry-run against exact WebKit pin b95c91b1c0ee43cc86d25ff7af73038f67a88e04.
- [x] Run a direct ABI regression for retained rule/declaration identity, typed and base edits after deletion, descriptor retention after rule release, no effect on rendered styles, invalid/foreign/thread calls, and expired owner context. The private candidate passes389 assertions. Expiry is asserted through weak Document watches after full GC and run-loop processing; a second live Document is checked independently. Settings-toggle behavior is not exercised by this test.
- [x] Compile the counter/context patch batch once; run focused regressions, existing CSS support/computed/rectangle/keyframe regressions and the32-test generator suite. Patch-series dry-run and generated source checks pass; regeneration after merging the canonical generator remains required.
- [ ] Run the shared C21 Windows JIT/AOT/Chromium batch; request independent review and open a PR stack. Public/platform acceptance remains pending release gates.

The results below are private candidate evidence. Public package and platform acceptance remain pending.

The shared C21 fixture passes44 assertions plus zero-object teardown in both Windows JIT and NativeAOT against the private candidate; Chromium also passes44. The initial JIT launch resolved the packaged runtime and reproduced the expected failure; the passing launch stages the candidate into the runtime-specific native directory. NativeAOT was published with OS=Windows_NT because this shell provides an empty OS property; the SDK reports win-x64. Existing FSharp.Core IL3053/IL2104 warnings remain. Native package preview.13 is reserved for this counter/context batch; ABI21 is unchanged.

## Implementation checkpoint

Patch0017 and helper-based glue are implemented and independently reviewed; private compilation and direct ABI regressions pass. Review found and resolved a hidden strong stylesheet ref in ownerDocument() on the destruction path and a detached shared-property-set COW risk. The source now uses borrowed root/owner-node access and preserves only parser state during destruction; position-try/font-face detached edits clone shared rule backing and reattach the same declaration, or copy the standalone declaration set after rule expiry. Function/Page/unknown detached descriptor mutation remains rejected.

The private build compiled the full44-object header dependency closure plus fresh generated glue into artifacts/cssom-context and preserved the cached baseline build outputs. Its first diagnostics required the standard fast-allocated sidecar marker and NodeDocument.h inline definition include. Both were applied to the persisted patch. The raw lifecycle regression includes descriptor edits while the detached rule is retained and again after releasing it; a surviving shared anchored popup remains37px while the detached copy changes to71px/83px. The candidate passes389 detached-context assertions,86 counter-style assertions, and805 existing regression assertions: CSS supports72, computed style93, fragment rectangles140, CSSOM407 and keyframes93. Shared C21 JIT/AOT and released-package checks remain pending.
