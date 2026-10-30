# SVG shapes, text, views and SMIL

This producer continues S03, S05, S06 and S07 from frozen Native18 source `9b6ad4445dcce0124008d1033eb7469355be4cf2`. Native18, its runtime and the Core19/Views0.1.9 consumer scope remain unchanged. The coordinator allocated Native19/ABI27 after fresh absence checks retained in `svg-surfaces-evidence/allocation-absence.json`. A managed consumer version for this cohort remains unallocated.

## S03: editable shapes

Select circle, ellipse, line and rectangle animated-length properties. Polygon/polyline point and animated-point lists already exist in Native18 and require shape-specific mutation, read-only, identity and resulting-bounds proof. Select the SVGPathElement type while leaving its legacy path-segment API outside the current selected scope. The historical source ledger labels associated legacy types S12; that group is absent from the active checklist and this delivery does not add it.

The shared path-data facade reads the nullable authored `d` value through Element.getAttribute, writes through setAttribute, and removes through removeAttribute. It accepts an actual SVGPathElement, never an HTMLElement cast. WebCore and the browser parse/render the authored value; bounds, length and samples come from their existing geometry methods. The facade supplies no path parser, serializer or geometry engine.

## S05: text metrics and positioning

Native18 already exports the eleven SVGTextContentElement and five SVGTextPositioningElement members. Select Text, TSpan and TextPath concrete types and TextPath startOffset/method/spacing/href. Verify plain and path text with the same pinned Ahem font, including character start/end/extents/rotation, substring lengths, textLength/lengthAdjust, positioning lists, hit queries, selection and invalid indices. Use real font readiness and preserve float precision.

The retained textLength regression showed actual adjusted paint with unadjusted queries. Patch 0026 reuses the existing fragment length-adjust transform for logical advances, positions, extents and hit bounds. Six horizontal/plain/path rows with spacing versus glyph scaling and rotation match measured Chrome positions/extents exactly. Vertical text preserves pinned WebKit's existing orientation, which differs from Chrome. WebKit's preexisting hit test uses axis-aligned glyph bounds: a point near a rotated glyph boundary can differ from Chrome. The fixture records that qualification and verifies every glyph extent center against both the actual hit result and painted Ahem glyph.

## S06: root and view state

Native18 already exposes root factories, dimensions, viewBox/aspect-ratio, currentScale/currentTranslate, intersection/enclosure lists and predicates, ViewSpec and ViewElement members. Prove their effects and returned-handle ownership on a known diagram. Distinguish root viewport coordinates from screen coordinates.

Measured Chromium156 does not expose currentView or useCurrentView. Native SVGViewSpec remains a genuine engine introspection capability. A common facade must distinguish NotExposed, Unsupported and Unknown; it must not return undefined as a nonnullable view object or treat requested attributes/URL fragments as proof of actual applied view state. Observable browser view-element/render effects need their own tests.

Pinned SVGSVGElement.suspendRedraw returns 1; unsuspendRedraw, unsuspendRedrawAll and forceRedraw have empty bodies. Chromium also exposes the deprecated calls. Preserve these inherited exports as deprecated no-op contracts, without claiming redraw suspension or using them as proof of effective S06 support.

The host now loads genuine `image/svg+xml` documents through the existing DocumentWriter and XML parser, with scripts disabled. Status zero means the document load completed; malformed XML produces WebKit's actual parser-error document. HTML keeps its existing insertion path. Focused proof covers MIME/namespace, Unicode, foreignObject HTML, script and VM guards, null/thread errors, XML errors, document transitions and surviving SVG values.

Pinned WebKit implements standalone currentScale through frame page zoom. At scale two a 500×300 host reports innerWidth/Height 250×150 and DPR two; BCR and screen CTM remain in CSS coordinates. Measured Chromium instead retains innerWidth/Height 500×300 and DPR one while applying SVG zoom to screen CTM. This provider difference is explicit. Native currentTranslate also affects inline legacy SVG rendering, while the measured Chrome inline assignment had no effect.

Source patch 0024 attaches the live currentTranslate point to its root and detaches it on root destruction, using the existing property commit path to update paint. Patch 0025 includes that existing renderer pan offset in screen CTM composition. The private coordinate receipt records 318 checks across default, border/padding, CSS zoom, transform and viewBox cases, comparing screen CTM, actual BCR and paint. It includes a temporary window-metrics export and is distinct from final shipping-runtime proof.

## S07: SMIL controls

Select SVGAnimationElement and concrete animate, animateMotion, animateTransform and set types, with mpath references. Bind targetElement, start/current/simple-duration queries, begin/end and offset variants. Reuse root pause/unpause/current-time operations and actual SMIL interpolation. Restricted offsets reject nonfinite values before the engine's finite assertions. EventTarget listeners provide begin/end/repeat subscriptions; unsupported EventHandler-valued properties are not fabricated.

Verify paused begin/seek/end/resume and delayed starts on rendered geometry, plus target identity, indefinite-duration errors, event transport, wrong subtype/thread, detach/disposal and final owner expiry. A03/A12 dependencies remain explicit; exporting SMIL methods does not accept those groups.

Real host pages previously inherited EmptyChromeClient's utility-page classification, so SMIL remained at zero. Patch 0023 permits the actual host client to identify itself as a normal page while preserving the default empty-client behavior. The focused fixture now observes running begin/repeat/end events and actual interpolation. Chrome's paused-seek sequence produces no begin/end events; its real resumed sequence does. Event timing is qualified per provider.

## Evidence and delivery

The initial browser audit uses the pinned `Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf`. Chromium156 measures plain/path ABC at 60 units and two characters at 40 units, rejects invalid indices with IndexSizeError, finds the expected intersection/enclosure target, and seeks a two-second SMIL x animation to its 250-unit midpoint.

The selected model contains 205 interfaces, 2234 functions, 50 roots, 22 dictionaries and zero stubs. All 2182 Native18 function records remain unchanged. The real SVGFEConvolveMatrixElement.preserveAlpha getter supplies the previously missing S04 Boolean producer; its supporting integer wrappers and other selected filter getters are incidental S09 scope, not S09 acceptance.

Native18 missing-binding and utility-page failures are retained separately from repaired proof. The final private Windows Native19/ABI27 runtime passes 9049 raw assertions across 24 exact source snapshots, the complete ABI callback/frame driver and 42 final teardown cases. The new SVG fixtures account for 2026 assertions: surfaces 1560, documents 78, coordinate/paint controls 318 and concrete animation variants 70. All 26 recorded processes exit zero. The temporary coordinate-probe runtime remains separately qualified and linked to a repeated 318-check shipping-runtime run.

The generator's 73 tests and 14 package/release tests pass. The generated canonical contracts and ABI driver compile with zero warnings/errors, canonical formatting and generation checks pass, and the complete generated Fable browser contract program passes. Actual Chromium fixtures retain 126 surface assertions, nine concrete animation assertions, ten detailed text-query rows, standalone view/control observations and screenshot pixel checks. These direct browser fixtures do not prove the future shared consumer facade.

Independent final receipt review and producer PR/CI remain. Shared Core21/Views11 providers, JIT/NativeAOT/compiled-browser consumer checks, platform CI and official packages remain delivery requirements. Root owns every edit to the shared WebKit checkout; no group is accepted from this producer-only checkpoint.
