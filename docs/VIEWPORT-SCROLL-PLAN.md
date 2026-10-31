# G05 fractional viewport scrolling plan

## Core and view state

- **Core primitives used:** none inside the native exports or the scroll service. A view that scrolls in response to
  state calls the service from an effect (`createEffectOnWithComparer` skips unchanged targets). A view that follows
  the scroll position subscribes through the G02 `ViewportService.Subscribe` (`Scrolled`, `ScrollEnded`) under an
  `Owner`, and disposes the subscription with `onCleanup`. It writes the read position into a core signal inside
  `batch`.
- **View-owned state:** none. The engine holds every scroll position. The service holds only the engine document
  it reads and scrolls, and that is a native handle, which the core cannot hold.

**Goal:** read and set the viewport and element scroll positions with `double` coordinates, both absolutely and
relatively, through the `ScrollToOptions` behaviour member. Fractional values, clamping and the scroll/scrollend
events that follow are compared against Chromium (Ranvier.WebCore #50).

**Trees:** native `C:/wk/native-scroll`, branch `codex/native-api-viewport-scroll`, from D13's `b8acc27`
(Native28/ABI36, G02/G12, I12). Reservation Native29/ABI37, DOM alpha.31, Views 0.1.21, backend alpha.21.

## Pinned source scope

- `ScrollPosition` and `ScrollOffset` are `IntPoint` (`platform/ScrollTypes.h`). `LocalDOMWindow::scrollTo` builds
  an `IntPoint` from `mapFromCSSToLayoutUnits(int)`. `Element::scrollTo` uses `clampTo<int>(value * usedZoom)`.
  Both truncate a fractional CSS coordinate toward zero. `scrollBy` adds the delta to the integral position, then
  scrolls to it.
- `LocalDOMWindow::scrollX/scrollY` return `int`. In the IDL they are `double`.
  `Element.scrollTop/scrollLeft` are IDL `long` (webkit.org/b/188045).
- The device scale factor does not enter these conversions: the result is the same at every scale.

## Measured RED (Native28/ABI36 against Chromium 156.0.8078.4 new headless)

`tests/abi/viewport_scroll_browser.mjs` records `tests/fixtures/viewport-scroll-oracle.json`.
`artifacts/measure_scroll_red.py` replays the same 16 steps on the runtime through the existing generated
`Element.scroll*` members of the scrolling element and of a scrolling box, at scales 1, 1.5 and 2.

- The ABI has no Window scroll members. `rv_host_scroll_position` and `rv_host_scroll_to` are `int32_t`.
- Chromium also keeps whole-pixel offsets at every scale, but it rounds to the nearest pixel, where the engine
  truncates. Clamping at 0 and at the maximum agrees.

## Native surface (ABI37, additive, `rv_abi_has("dom-window-scrolling")`)

The generator's `windowBindings` gain readonly attributes. `DOMWindow` binds `scrollX`, `scrollY`, `scroll`,
`scrollTo` and `scrollBy`: each operation in both the (x, y) form and the `ScrollToOptions` form, with `behavior`. Every
function takes the document (`RvNode*`) and returns `RV_ERR_UNSUPPORTED` when the document has no window. The calls
go through `LocalDOMWindow`, so window scrolling and `Element.scroll*` share the engine's conversions. The host's
`int32_t` scroll exports stay as they are.

## Proof

1. **RED:** `tests/abi/viewport_scroll.py` fails on ABI36 because the Window exports are absent.
2. **Native GREEN** on `artifacts/native29-candidate-N`: for every oracle step at every scale, the Window route and
   the scrolling-element route give the backend's expected value. That value is Chromium's, except for the steps
   recorded as the truncation qualification. Clamping and scroll/scrollend delivery are compared too. The probe also
   checks smooth scrolling, the null-argument, wrong-thread and windowless-document errors, and a document handle
   held past `rv_host_destroy`.
3. **Managed GREEN:** the shared conformance fixture runs on native JIT, NativeAOT and Chromium, with teardown cases
   and an evidence JSON.
