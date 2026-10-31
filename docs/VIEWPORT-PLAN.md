# G02 viewport dimensions/scale and G12 viewport/document event routing plan

## Core and view state

- **Core primitives used:** none inside the provider or service. A view consumer that subscribes owns its
  subscription through the core: it calls `ViewportService.Subscribe` under an `Owner` and registers the returned
  handle's `Dispose` with `onCleanup`, so owner disposal unsubscribes. Values a view derives from viewport changes go
  into core signals or memos (`createSignal`, `createMemoWithComparer`) written inside `batch`.
- **View-owned state:** none. The service is a `Ranvier.Dom` contract over the engine. The engine holds the window,
  its listeners and the media query lists; the service keeps only its subscription list, the native listener
  registrations it made and the media query list armed for the current device pixel ratio. These are registrations
  on engine event targets, which the core cannot hold.

**Goal:** CSS-pixel inner/outer dimensions and `devicePixelRatio` read from the engine window (G02, Ranvier.WebCore
#47), and resize, scroll, scrollend, visibility, focus and device-scale changes delivered from the native window into
owned callbacks in the engine's rendering-update order (G12, #57). Teardown removes every listener.

**Trees:** native `C:/wk/native-viewport`, branch `codex/native-api-viewport`, from #137 head `e58aa24f`
(Native25/ABI33). I12 (Native26/ABI34) is forward-merged before ABI35 is allocated. Managed: Core and Views branches
stacked on I12's managed branches, or on I02's Core #277 `88e75d3f` and Views #33 `b5dc03e9` until they exist.
Reservation Native27/ABI35, DOM alpha.28, Views 0.1.18.

## Pinned source scope

- `LocalDOMWindow::innerWidth/innerHeight` map `unobscuredContentRectIncludingScrollbars` to CSS units.
  `outerWidth/outerHeight` read `Chrome::windowRect`, which `EmptyChromeClient` reports as empty: the host's chrome
  client reports the viewport as its window rectangle, so the outer size equals the inner size (the host has no
  window decoration).
- `LocalDOMWindow::devicePixelRatio` is `Page::deviceScaleFactor` times the frame and page zoom.
- `Page::updateRendering` runs, in order, the resize steps (window `resize`), the scroll steps (`scroll`, then
  `scrollend`, at the document; they bubble to the window) and media query evaluation (`MediaQueryList` `change`).
  HTML's update-the-rendering has the same order.
- `Page::setIsVisible` changes `document.visibilityState` and queues `visibilitychange` (bubbles to the window).
  The host never calls it today, so a host is always visible.
- `FocusController::setFocused` dispatches window `focus`/`blur` (existing `rv_host_set_focused`).
- No web event reports a device-pixel-ratio change. Browsers observe it with
  `matchMedia("(resolution: <dpr>dppx)")`, re-armed after each change; the native route uses the same engine
  `MediaQueryList`.

## Native surface (ABI35, additive, `rv_abi_has("viewport")`)

- The window target is I12's `rv_host_window_event_target` (ABI34, "input-state"): a new EventTarget reference to the
  current document's window. Listeners use `rv_event_target_add_listener`; `rv_event_get_target(event, 1)` of a
  window listener equals it.
- `int32_t rv_host_window_metrics(RvHost*, RvWindowMetrics*)`: `size`-prefixed struct with `innerWidth`,
  `innerHeight`, `outerWidth`, `outerHeight` (int32 CSS pixels) and `devicePixelRatio` (double).
- `int32_t rv_host_set_visible(RvHost*, int32_t visible)`: page visibility, as the platform window is minimized,
  hidden or occluded.
- `RvEventTarget* rv_host_match_media(RvHost*, const char* query)`: a new `MediaQueryList` reference;
  `int32_t rv_media_query_matches(RvEventTarget*, int32_t* matches)` and `rv_media_query_media` (UTF-8 exact-byte
  protocol). A non-MediaQueryList target returns `RV_ERR_WRONG_INTERFACE`.
- WebCore glue `host/RanvierViewportGlue.cpp` (metrics and media queries need non-exported WebCore members).
- Every handle stays valid after `rv_host_destroy`: reads return `RV_ERR_PAINT_FAILED` once the window has no
  frame, and `rv_listener_remove`/`rv_event_target_release` keep working.

## Managed surface (DOM alpha.28, Views 0.1.18)

`Ranvier.Dom/Viewport.fs`: `ViewportMetrics`, `ViewportVisibility`, `ViewportChange`
(`Resized | Scrolled | ScrollEnded | VisibilityChanged | FocusChanged | ScaleChanged`), `ViewportProvider` and
`ViewportService` (snapshot reads, `Subscribe` returning an idempotent `IDisposable`, `Dispose` unsubscribing every
subscription and provider registration). Browser provider in `Fable.Ranvier.Dom/BrowserViewport.fs` over `window`
and `matchMedia`; native provider in `Ranvier.View.WebCore/Viewport.fs` over `rv_host_window_event_target`/`rv_host_match_media`;
the SDL window maps minimize/restore/hide/show/occlude to `SetVisible`.

## Proof

1. **RED:** `tests/abi/viewport_events.py` against `native25-candidate-3` fails on ABI 33 and absent exports.
2. **Oracle:** `tests/abi/viewport_events_browser.mjs` records in Chromium (CDP device metrics and focus/visibility
   emulation) the metrics for 320x240 at scales 1, 1.25, 1.5, 2 and 0.75, and the delivery order of resize, scroll,
   scrollend, visibilitychange, focus/blur and resolution `change` for one scripted sequence, to
   `tests/fixtures/viewport-events-oracle.json`.
3. **Native GREEN** on `artifacts/native27-candidate-N`: metrics and paint size (`floor(css * scale)`) per scale,
   event order equal to the oracle, listener removal stops delivery, null/thread/interface errors, and new
   Teardown.fs cases holding the window and a media query list past destroy.
4. **Managed GREEN:** shared conformance fixture `Viewport.fs` on native JIT, NativeAOT and Chromium, with teardown
   cases (service dispose, subscription dispose before and after host destroy) and an evidence JSON.
