# Web Animations (A01 creation; A02, A05 and A04 extend it)

## Surface

The DOM generator produces the Web Animations interfaces from WebKit's IDL (`docs/GENERATOR.md`, "JavaScript object
arguments and custom constructors"):

| Interface | Handle | Members |
|---|---|---|
| `Animation` (IDL `WebAnimation`) | `RvEventTarget` | id, effect, timeline, startTime, currentTime, playbackRate, overallProgress, playState, replaceState, pending; play, pause, finish, cancel, reverse, updatePlaybackRate, persist, commitStyles; `rv_dom_web_animation_create` |
| `AnimationEffect`, `KeyframeEffect` | `RvAnimationEffect` | target, pseudoElement, composite, iterationComposite, setKeyframes; `rv_dom_keyframe_effect_create_3` and `_create_1` (copy); runtime type query |
| `AnimationTimeline`, `DocumentTimeline` | `RvAnimationTimeline` | currentTime, duration; `rv_dom_document_timeline_create`; runtime type query |
| `Element` | `RvNode` | animate, getAnimations; `Document.timeline` and `getAnimations` |

The Promises `ready` and `finished` are not mapped. The `finish`, `cancel` and `remove` events reach
`rv_event_target_add_listener`. `rv_animation_as_event_target` maps a CSS-animation `RvAnimation` to its `RvEventTarget`.

A02 adds getTiming, getComputedTiming, updateTiming and getKeyframes; A05 adds CSSAnimation, CSSTransition and their
metadata; A04 verifies commitStyles.

## Evidence (A01)

`tests/abi/web_animations.py` replays `tests/fixtures/web-animations-cases.json` (23 cases and 17 error cases) against
the Chromium oracle `tests/fixtures/web-animations-oracle.json`. Each case pauses and seeks; the probe compares play
state, current time, computed values and rendered pixels, with a tolerance of 2 per channel for alpha rounding. The
evidence files are in `docs/web-animations-evidence/`.

## Qualifications

- **Refused microtask drain.** Element.animate, the KeyframeEffect constructor and setKeyframes build their keyframes
  under the JavaScript lock. Releasing the lock at depth 0 drains JSC's microtask queue, and the queue is not empty
  (load and window-proxy creation fill it). The drain attempts a VM entry, which the host's DisallowVMEntry refuses.
  No script runs, and the page's canary script stays unrun. Three rounds of 1000 calls keep the private memory flat.
  Calls that take no JavaScript lock run with JSC's crash on a disallowed VM entry armed: Animation construction and
  control, the effect and timeline members, and the timeline constructor. A child process proves the crash is armed.
  Painting is outside the armed scope, because the rendering update attempts its own VM entry.
- **Keyframe input form.** The native transport is the keyframe-sequence form. Property-indexed keyframes
  (`{ opacity: [0, 1] }`) are a browser-only input shape.
- **Absent and null timeline.** In the shared F# contract, an omitted timeline and `Some null` are both the document
  timeline. `AnimationService.CreateAnimationWithoutTimeline` creates an animation with no timeline.
