# G03 visual viewport plan

## Core and view state

- **Core primitives used:** none inside the native exports or the visual viewport service. A view that follows the
  visual viewport subscribes through `VisualViewportService.Subscribe` (`Resized`, `Scrolled`) under an `Owner`,
  disposes the subscription with `onCleanup`, and writes the delivered state into a core signal inside `batch`.
- **View-owned state:** none. The engine holds the page scale, the obscured insets and the visual viewport. The
  provider holds only the engine's `VisualViewport` event target, which is a native handle that the core cannot hold.

**Goal:** expose `VisualViewport` offsets, page position, size and scale with its `resize` and `scroll` events, plus
the host inputs that drive a zoomed or occluded viewport: the page scale (pinch zoom) and the obscured insets. The
behaviour is compared against Chromium (Ranvier.WebCore #48). An unavailable feature reports `Detached` or
`Unsupported`, never zeros.

**Trees:** native `C:/wk/native-vv`, branch `codex/native-api-visual-viewport`, from G09's `fb87eb0`
(Native32/ABI40). Reservation: Native37/ABI45, DOM alpha.40, Views 0.1.30, backend alpha.30, Views Kind 74.

## Pinned source scope

- `VisualViewport.idl` has `[EnabledBySetting=VisualViewportAPIEnabled]` and seven `double` attributes, plus the
  `onresize` and `onscroll` handlers. `DOMWindow+VisualViewport.idl` adds `[SameObject] visualViewport` under the
  same setting.
- WebCore's default for `VisualViewportAPIEnabled` is false. While it is off, `LocalFrameView::layoutOrVisualViewportChanged`
  never calls `VisualViewport::update`, and every member reads 0.
- The members derive from `LocalFrameView::visualViewportRect` and `layoutViewportRect`, divided by the page zoom.
  `scale` is `Page::pageScaleFactor`. A window without a frame reads 0, and 1 for `scale`.
- `Page::setPageScaleFactor(scale, origin)` applies the scale unclamped. `Page::setObscuredContentInsets`
  contracts the unobscured content rectangle, so the visual viewport and the window's inner size shrink.

## Measured RED (Native32/ABI40 against Chromium 156.0.8078.4 new headless)

`docs/visual-viewport-evidence/red_chromium.mjs` writes `red-chromium.json`. `red_native.py` writes `red-native.json`.

- Native32 has no visual viewport export, no page scale input and no obscured inset input. `rv_abi_has` reports
  0 for `visual-viewport`, `page-scale` and `obscured-insets`.
- On desktop headless, Chromium follows `Emulation.setPageScaleFactor`. A wheel at scale 2 pans only the visual
  viewport. `Input.synthesizePinchGesture` has no effect. No host input drives occlusion.

## Native surface (ABI45, additive)

- The host sets `VisualViewportAPIEnabled`.
- Generated (`rv_abi_has("visual-viewport")`, `dom:VisualViewport`):
  - `rv_dom_window_get_visual_viewport` (Document receiver), and `rv_dom_visual_viewport_get_*` for the seven
    members.
  - A `VisualViewport` handle is an `RvEventTarget`: `gen/dom.json` `eventTargetObjects`. Listeners use
    `rv_event_target_add_listener`, and `rv_event_target_release` frees the handle.
  - A member called once the window has no frame returns `RV_ERR_DETACHED`.
- Hand-written:
  - `rv_host_set_page_scale(host, scale, originX, originY)` and `rv_host_page_scale` (`page-scale`).
  - `rv_host_set_obscured_insets(host, top, right, bottom, left)` (`obscured-insets`).
  - Rejected values return `RV_ERR_UNSUPPORTED`, as `rv_host_set_device_scale` does: a scale that is non-finite
    or at most 0, and an inset that is non-finite or negative.

## Proof

- `tests/abi/visual_viewport.py` replays the oracle `tests/fixtures/visual-viewport-oracle.json`
  (`tests/abi/visual_viewport_browser.mjs`) and adds the native-only checks: arguments, unclamped scales,
  LayoutUnit sizes, insets and hit testing, errors and teardown. The driver's Teardown adds the `visual viewport`
  case. `build.yml` runs the probe on every slim runtime.
- Qualified against Chromium:
  - While page-scaled, WebKit keeps the layout viewport at the document origin, so the offsets equal the page
    position.
  - A wheel pan at scale 2 also scrolls the window. The return to scale 1 adds a window scroll.
  - `innerWidth` is the visual viewport's width at page scale 2 (150 in WebKit, 300 in Chromium).
  - Browser-only: Chromium's `onscrollend`, and the all-zero members (scale 0) of a detached frame.
