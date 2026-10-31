# Animation timelines (A06 document timelines; A07 scroll timelines; A08 view timelines and ranges)

These groups extend the Web Animations surface of `docs/WEB-ANIMATIONS-PLAN.md`. Timeline handles are
`RvAnimationTimeline` references; `rv_dom_animation_timeline_get_interface_name` names the runtime type.

## A06: document timelines

A06 adds no export. The A01 surface covers it: `Document.timeline` (`rv_dom_document_get_timeline`), the
`DocumentTimeline` constructor with `originTime` (`rv_dom_document_timeline_create`), and `AnimationTimeline.currentTime`
and `duration`.

| Member | State |
|---|---|
| `Document.timeline`, `AnimationTimeline.currentTime`, `AnimationTimeline.duration`, `new DocumentTimeline(options)` | Supported |
| `DocumentTimeline.maximumFrameRate`, `Animation.frameRate` | Unsupported: `[EnabledBySetting=WebAnimationsCustomFrameRateEnabled]`, a testable WebKit setting that is off; Chromium has neither member. No export. |
| `DocumentTimeline.animate(CustomEffectCallback)` | Covered by A09 |

`tests/abi/animation_timelines.py` compares with the Chromium oracle `tests/fixtures/animation-timelines-oracle.json`:
the current time of a timeline with origins 100, 0, -50 and 1e9 against `document.timeline` (to within a microsecond),
the null duration, the inactive timeline of a document without a browsing context and an animation played on it, start
times shared by animations started before one rendering update, and timelines held past `rv_host_destroy`, which read a
null current time. Teardown kind "document timeline" proves a held timeline and an animation on it keep no document alive.
The timeline calls run with JSC's crash on a disallowed VM entry armed. The evidence files are in
`docs/animation-timelines-evidence/`.

### Qualifications

- **Start time on a timeline with an origin.** The pinned WebKit gives every pending animation on a monotonic timeline
  the document timeline time as its start time (`AnimationTimelinesController::processPendingAnimations`). An animation
  on `new DocumentTimeline({originTime})` starts at the document time, not at the document time minus `originTime`,
  as Chromium and the specification give. `tests/fixtures/animation-timelines-qualified.json` records both values.
- **Cancel with a pending pause task.** Cancelling rejects the ready promise, which attempts a VM entry (A03). The
  armed scope settles the pause with `finish` first.

## A07: scroll timelines

The DOM generator produces `ScrollTimeline` from WebKit's IDL; the pinned WebKit enables it without a setting.

| Function | Contract |
|---|---|
| `rv_dom_scroll_timeline_create(document, options, result)` | `new ScrollTimeline(options)`; `options` may be NULL for every default |
| `rv_dom_scroll_timeline_get_source` | the source element, a new `RvNode` reference, or NULL |
| `rv_dom_scroll_timeline_get_axis` | `RV_DOM_SCROLL_AXIS_BLOCK`, `_INLINE`, `_X` or `_Y` |

`RvDomScrollTimelineOptions.source` is `RvNode* const*`: NULL for absent, which follows the document's scrolling element,
and a pointer to NULL for a null source, which gives an inactive timeline. A source of another node type is
`RV_ERR_WRONG_INTERFACE`; an axis outside the enumeration is `RV_ERR_UNSUPPORTED`. `currentTime` and `duration` are the
`CSSNumericValue` arm of the time union: a `CSSUnitValue` in `percent` of the source's scroll range, or absent while
the source has no scrollable box. The progress reads the value cached by the last rendering update (`rv_host_update`).

The probe compares, after two rendering updates as the oracle after two frames: the four axes; element, nested, root,
unscrollable, null and default sources; progress at the start, quarter, middle and end of the scroll range; animations
created by `Element.animate` with the `timeline` option and by the Animation constructor; a content resize; and a
removed source. Teardown kind "scroll timeline" proves a held timeline and an animation on it keep no document alive.

### Qualifications

- **Single precision.** WebKit computes scroll progress in single precision; the probe compares percentages to within
  1e-4.
- **Scroll anchoring.** Chromium anchors the root scroll position when content above it is removed, and WebKit does not.
  The scroll page sets `overflow-anchor: none`.
- **Removed source.** Once the source leaves the tree, both engines read a null current time. The pinned WebKit keeps
  the last effect value until the target's style is next invalidated; Chromium drops it at once. The probe asserts both
  values and that a restyle matches Chromium.

## A08: view timelines and animation ranges

| Function | Contract |
|---|---|
| `rv_dom_view_timeline_create(document, options, result)` | `new ViewTimeline(options)`; an invalid inset is `RV_ERR_DOM_EXCEPTION` with TypeError |
| `rv_dom_view_timeline_get_subject` | the subject element, a new `RvNode` reference, or NULL |
| `rv_dom_view_timeline_get_start_offset`, `_get_end_offset` | the cover range's scroll offsets, a new `CSSUnitValue` in `px` |
| `rv_dom_web_animation_get_range_start`, `_get_range_end` | the range union, owned until `rv_dom_union_timeline_range_offset_or_css_numeric_value_or_cssom_keyword_value_or_dom_string_release` |
| `rv_dom_web_animation_set_range_start`, `_set_range_end` | a range offset, a `CSSNumericValue`, a `CSSKeywordValue` or a range string |

`RvDomViewTimelineOptions.inset` is the union of a string and a sequence of lengths, percentages or `auto`; NULL is the
IDL default `auto`. `RvDomKeyframeAnimationOptions` gains `range_start` and `range_end` at its end, so callers compiled
against the earlier struct keep the default `normal`. `RvDomTimelineRangeOffset.offset` is NULL for absent; in a result
it is a new reference that the union's release drops. The ScrollTimeline functions answer for a ViewTimeline, and the
runtime type query names it.

The probe compares the subject, source, axis and offsets with four insets, two invalid insets, a subject in a nested
scrollport, animations created with range offsets and strings at eight scroll positions, and the range setters. Teardown
kind "view timeline" proves a held timeline and an animation on it keep no document alive.

### Qualifications

- **Range resolution.** A set range resolves in WebKit's next rendering update: the probe reads ranges after one.
- **Range setter edge cases** (both values asserted in `tests/fixtures/animation-timelines-qualified.json`): a
  `CSSNumericValue` range (WebKit keeps the offset with the range name `omitted`; Chromium reads `none` at 0%), the
  keyword `normal` (WebKit reads neither a name nor an offset; Chromium reads `none` at 0%), a bare `exit` (WebKit
  gives 100%, as specified; Chromium 1%), and an unparsable string (WebKit's setter has no exception path and ignores
  it; Chromium throws TypeError).
- **Cached progress past teardown.** A ViewTimeline held past `rv_host_destroy` keeps the progress of the last
  rendering update.
