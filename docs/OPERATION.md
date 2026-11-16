# Operating a host

[Hosting a page](HOSTING.md) gives the order of calls. This page explains what each step does inside the engine,
what it costs, and how to run a host well over a long session: frames, time, resize, focus, visibility, resources,
memory and teardown.

## The model

The engine does nothing by itself. It has no thread of its own for the page, starts no timer the app does not pump,
and draws nothing the app does not ask for. Three calls drive everything:

| Call | Moves forward |
|---|---|
| `rv_run_loop_cycle` | time: timers, queued work, deferred callbacks |
| `rv_host_update` | the page: animations, observers, style, layout |
| `rv_host_paint_rgba` or a GPU frame acquire | the pixels |

Input and DOM calls change the page in between. An app that stops calling these has a frozen page, which is also
the cheapest state a host can be in.

## One turn of the loop

```c
for (;;) {
    wait_for_events(timeout);                     /* the app's own wait: window events, a wake, a timer */

    rv_run_loop_cycle(0);                         /* 1. time */
    forward_input(host);                          /* 2. input */
    run_app_logic(host);                          /* 3. DOM changes */

    if (frame_wanted) {                           /* 4. set by the frame callback */
        frame_wanted = 0;
        rv_host_update(host);                     /* 5. the page */
        present(host);                            /* 6. the pixels */
    }
}
```

### 1. Time: `rv_run_loop_cycle`

`rv_run_loop_cycle(milliseconds)` cycles the calling thread's run loop until the time has elapsed, at least once.
A cycle does not wait for a source. `0` runs exactly one cycle. It returns the number of cycles run.

What happens inside it:

- Due WebCore timers fire. On Windows, from 0.1.3, they fire first in each pass, before pending messages.
- The resource handler is called for each load still pending.
- Deferred completions are delivered: image decodes, font loads, form submissions, notifications, pointer lock
  events, view transition steps.
- Accessibility events are delivered.
- The host's own timers run, such as the one that drops the kept paint surface.

Without it, timers, animations that depend on them, loads and accessibility events do not advance.

**An app with its own message loop.** On Windows, WebCore's timers are also driven by window messages on the host
thread, so an app that pumps messages itself still gets timers. Call `rv_run_loop_cycle(0)` once a turn anyway:
the deferred callbacks above are delivered from it.

**How long to pass.** Pass 0 and do the waiting in the app's own event wait, where a window event or a wake from
another thread can end it. A nonzero value blocks the thread for that long.

### 2. Input

Input calls dispatch synchronously. By the time `rv_host_mouse` returns, the page's listeners have run, default
actions have happened, and the page may want a frame.

| Call | Notes |
|---|---|
| `rv_host_mouse(host, action, x, y, button, clickCount, modifiers)` | CSS pixels in the viewport. `clickCount` is 1 for a press, 2 for a double, 0 for a move. The SDL window reports the pointer leaving as a move to (-1, -1) with `RV_BUTTON_NONE`. |
| `rv_host_wheel(host, x, y, deltaX, deltaY, modifiers)` | Deltas in CSS pixels, positive right and down. The app chooses how many pixels a wheel notch is. |
| `rv_host_key(host, action, key, code, text, text_length, modifiers, repeat)` | `key` and `code` are the DOM's `KeyboardEvent` values. Send `RV_KEY_DOWN`, then `RV_KEY_CHAR` with the text for a key that produces characters, then `RV_KEY_UP`. |
| `rv_host_pointer(host, samples, count)` | Pen and touch. A touch frame carries one sample per active contact. |
| `rv_host_ime_*` | Composition from an input method. Do not send key events while composing. |

After each mouse call, read `rv_host_cursor(host)` and apply the cursor.

Each returns 1 when the page or the engine handled the event and 0 when not. Use that to decide whether an
unhandled key should reach the app's own shortcuts. A 0 does not mean no listener ran: in a check on 2026-11-16
(slim `win-x64`, ABI 71), a press and release over a button whose `click` listener ran both returned 0.

**Coalesce high-rate input.** A mouse can report a thousand moves a second. Hold moves, wheel deltas and resizes,
and send the latest once a frame. Flush what is held before any button, key or focus event so the page sees events
in order.

### 3. Changing the page

Each DOM write marks style, layout or paint dirty. The cost is paid later, in the update. So:

- **Writes are cheap to make and add up in the update.** Ten writes to one element cost one restyle.
- **A read of layout forces it.** `rv_element_rect`, `scrollTop`, `clientHeight` and the like bring style and
  layout up to date at once. Read first, then write, and layout runs once a frame instead of twice.
- **One native call per write.** There is no batch call. An app reduces work by writing less, not by packing calls.

[Field notes](FIELD-NOTES.md#what-makes-a-frame-expensive) has measured costs for element count, per-frame custom
properties, stylesheet changes and scrolling.

### 4. Knowing a frame is wanted

`rv_host_set_frame_callback(host, callback, context)` registers the signal. The engine calls it when the page
wants a frame: an invalidation, a running animation, a scroll.

- It is called once, then not again until the next `rv_host_update` or `rv_host_paint_rgba`.
- It is never called during those two.
- It must not call the ABI. Set a flag, or wake the loop.

A loop that paints only when the flag is set does no work for an idle page. An app's own animation, driven outside
the page, requests frames for itself.

### 5. The page: `rv_host_update`

Runs WebCore's rendering update for the current time:

- Animations and transitions advance.
- Resize and intersection observers run, and the window's resize, scroll and media query events fire.
- Style and layout are brought up to date.

Call it once a frame, before painting or acquiring a GPU frame. It returns `RV_ERR_DETACHED` when a callback
inside it asked to destroy the host.

### 6. The pixels

**CPU.** `rv_host_paint_rgba(host, rgba, length)` lays out and paints the viewport into the caller's buffer:
`width * height * 4` bytes of the size `rv_host_paint_size` reports, unpremultiplied RGBA8 in sRGB.

To paint less, ask what changed:

```c
int32_t x, y, w, h;
if (rv_host_dirty_rect(host, &x, &y, &w, &h))                     /* CSS pixels; 1 when there is a rectangle */
    rv_host_paint_rgba_rect(host, rgba, length, x, y, w, h);      /* into its place in the same full-size image */
```

- The rectangle covers what was invalidated since the last `rv_host_paint_rgba`. A viewport scroll invalidates
  all of it.
- `rv_host_paint_rgba_rect` leaves the rest of the image as it was, so the buffer must persist between frames.
- At a fractional device scale the edges are rounded down to whole device pixels. Widen the rectangle to the
  device-pixel grid before using it for an upload.
- A whole-viewport paint keeps its surface for the next one; a partial paint does not
  ([Memory](MEMORY.md#the-kept-paint-surface)).

**GPU.** With the GPU flavor and compositing on, the app acquires the composited frame as a texture and never sees
the pixels:

| Platform | Acquire | The frame is |
|---|---|---|
| Windows | `rv_host_acquire_d3d11_frame(host, device, &frame)` | an `ID3D11Texture2D*` on the app's device, RGBA8 premultiplied |
| Linux | `rv_host_acquire_egl_frame(host, &frame)`, after `rv_configure_egl_display` | an EGLImage |
| macOS | `rv_host_acquire_iosurface_frame(host, &frame)` | an `IOSurfaceRef`, BGRA8 premultiplied |

`rv_gpu_frame_info` reads the texture, its size in device pixels and its format. Row 0 is the top of the page.
`rv_gpu_frame_release` gives the frame back, on the host thread, after the app's present has finished with it.

Rules that hold on every platform:

- Call `rv_host_update` first.
- One outstanding frame per surface on Windows: a second acquire returns `RV_ERR_UNSUPPORTED` at once.
- A held frame survives a resize and the host's destruction.
- `RV_ERR_UNSUPPORTED` means paint this frame with `rv_host_paint_rgba`. `RV_ERR_DETACHED` and
  `RV_ERR_DEVICE_LOST` are handled as in [Errors while running](#errors-while-running).

The bounded pipeline (`gpu-frame-pipeline-v1`) separates submitting a frame from acquiring a completed one, so a
busy GPU delays a frame without blocking the host thread. `RV_NOT_READY` means keep the previous image and retry
at the next scheduled frame. Do not spin, and do not fall back to CPU painting for congestion
([The C ABI and header](ABI.md#detecting-features)).

## Size, scale and the screen

| Call | Sets | Units |
|---|---|---|
| `rv_host_resize(host, width, height)` | the viewport | CSS pixels |
| `rv_host_set_device_scale(host, scale)` | device pixels per CSS pixel, 0.25 to 8, 1 at creation | |
| `rv_host_paint_size(host, &width, &height)` | reads the image size | device pixels |
| `rv_host_set_screen(host, &metrics)` | what `screen` and the device media features report | CSS pixels |
| `rv_host_set_page_scale(host, scale, x, y)` | pinch zoom | |

For a window of `pw` by `ph` physical pixels on a display of scale `s`: set the device scale to `s` and resize to
`ceil(pw / s)` by `ceil(ph / s)`. The paint size is the CSS size times the scale, rounded down, so reallocate the
pixel buffer from `rv_host_paint_size`, not from the window.

An app-level zoom multiplies the device scale. At a zoom of 2, a 3840 by 2160 window holds a page of 1920 by 1080
CSS pixels drawn at device scale 2.

A resize invalidates everything: paint the whole viewport next. A size or scale change also replaces the kept
paint surface.

## Focus and visibility

| Window event | Call | Effect |
|---|---|---|
| gains keyboard focus | `rv_host_set_focused(host, 1)` | The caret blinks, `:focus-visible` matches, the window is active. |
| loses it | `rv_host_set_focused(host, 0)` | Also ends a pointer lock. Cancel a composition first. |
| hidden, minimised, occluded | `rv_host_set_visible(host, 0)` | `visibilitychange` is queued; `resize` is deferred; wake locks are released. |
| shown again | `rv_host_set_visible(host, 1)` | |

A host starts unfocused and visible. A page that seems dead to the keyboard usually has not been told it has
focus.

Hiding the page does not stop the engine. To stop spending, stop requesting frames, and consider
[giving memory back](MEMORY.md#giving-memory-back).

## Time

`rv_host_now(host, &milliseconds)` reads the document's `performance.now()`. A document loaded with
`rv_host_load_html` keeps the time origin of the host's window. Use it as the timestamp for animation frame
callbacks an app runs itself, so they share the clock of the page's own animations and observer entries.

## Resources

A page that names a URL (an image, a stylesheet, a font) starts a load. `data:` and `blob:` URLs resolve inside
the engine. Every other URL goes to the app:

```c
static void on_resource(void* context, RvResourceLoad* load, const char* url) {
    Bytes bytes;
    if (lookup(url, &bytes))
        rv_resource_load_finish(load, bytes.data, bytes.length, "image/png");   /* copied by the engine */
    else
        rv_resource_load_fail(load);
}

rv_host_set_resource_handler(host, on_resource, context);
```

- The handler is called from `rv_run_loop_cycle`, after the call that started the load has returned.
- Complete each load exactly once, inside the handler or later on the host thread, even if the document cancelled
  it. Completing frees the handle.
- The response is a status 200 with the content type given, and it allows every origin.
- Without a handler each load fails.

To know when an image or a font is usable without polling, use the operation calls (`rv_image_decode`,
`rv_fonts_load`): each completes with a callback from a later `rv_run_loop_cycle`.

## Several hosts

Hosts in one process share the thread, the allocator, the font and glyph caches and the process-wide parts of the
engine.

- All of them belong to the one host thread.
- `rv_run_loop_cycle`, `rv_release_memory` and `rv_collect_garbage` act on all of them at once.
- Each has its own document, frame callback, focus, kept paint surface and GPU surfaces.
- A second host added about 12 MB in one measurement ([Memory](MEMORY.md#what-the-engine-holds)).

## Running idle

A page with nothing to do should cost almost nothing:

| Do | Why |
|---|---|
| Wait in the app's event wait with a timeout, not in a spin | An idle turn then costs one `rv_run_loop_cycle(0)`. |
| Paint only when the frame callback fired | No invalidation, no paint. |
| Request your own frames only while something moves | A callback that always re-arms keeps the loop presenting ([Field notes](FIELD-NOTES.md#a-frame-loop-that-rests)). |
| Keep cycling while the window is open | Deferred callbacks and the kept surface's timer need it. |
| Cap the wait by the next timer due | So a timer does not fire late. |

## Errors while running

| Status | From | Do |
|---|---|---|
| `RV_ERR_DOM_EXCEPTION` | a DOM call | Read `rv_last_exception` for the name and message. |
| `RV_ERR_LISTENER_FAILED` | a dispatching call | One of the app's listeners returned nonzero. The others still ran. |
| `RV_ERR_UNSUPPORTED` | a GPU or platform call | Take the fallback path. |
| `RV_ERR_PAINT_FAILED` | painting | Paint the whole viewport again next frame. |
| `RV_ERR_DEVICE_LOST` | the GPU pipeline | Release held frames, rebuild the consumer device, configure again. On EGL and Metal, recreate the host. |
| `RV_ERR_DETACHED` | an update or acquire | The host is being destroyed. Stop using it. |
| `RV_ERR_WRONG_THREAD` | anything | A call left the host thread. |

For presentation failures, `rv_host_error_enable(host, 1)` keeps the latest failure, with the D3D11 device-removed
reason, for `rv_host_error_take` ([Diagnostics](DIAGNOSTICS.md#host-error-records)).

To see where a frame's time goes, `rv_host_trace_enable(host, 1)` records update requests, style and layout,
paint, rendering update and GPU submission spans into a buffer of 256 records, drained with
`rv_host_trace_drain` ([Diagnostics](DIAGNOSTICS.md#host-tracing)).

## Replacing the document

`rv_host_load_html` replaces the document and keeps the host.

- **Kept:** the window, its listeners and the `performance.now()` origin.
- **Reset:** editing history.
- **Ended:** in-flight operations complete as invalidated, and custom effect callbacks are revoked.

After a load, get the document again with `rv_host_document` and paint the whole viewport.

## Teardown

In order:

1. Stop requesting frames and remove the frame callback (`rv_host_set_frame_callback(host, NULL, NULL)`).
2. Wait for a present in flight, then release GPU frames.
3. Detach accessibility bridges (`rv_host_detach_uia`).
4. Remove listeners (`rv_listener_remove`) and release observers and animations.
5. Release nodes and accessibility nodes.
6. `rv_host_destroy(host)`.

Watches, diagnostic snapshots, encoded images and held GPU frames remain valid after the host and are released
whenever the app is done with them. There is no process shutdown call. Release every GPU frame before the native
libraries are unloaded.

## A checklist

- Every call is on the thread that created the first host.
- `rv_run_loop_cycle(0)` runs once a turn while the window is open.
- The frame callback only sets a flag.
- `rv_host_update` runs before each paint or frame acquire.
- The pixel buffer is sized from `rv_host_paint_size`.
- Focus and visibility are forwarded.
- A resource handler is installed if the page names any URL.
- Every handle that needs it is released before `rv_host_destroy`.
- A GPU failure falls back to `rv_host_paint_rgba`.
- The loop sleeps when nothing is wanted.
