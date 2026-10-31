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
