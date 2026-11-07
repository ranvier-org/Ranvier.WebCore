# Hosting a page

A host is one WebCore page rendered offscreen. The app owns the window, the event loop and the presentation;
the host owns the DOM, style, layout and painting. `include/RanvierWebCoreAbi.h` is the
contract; this guide is the order of calls.

## Threading and lifetime

- Every call is valid only on the thread that first called `rv_host_create`. Another thread gets
  `RV_ERR_WRONG_THREAD` (or `NULL`), and the DOM is unchanged.
- Each returned `RvNode` is a strong reference, released with `rv_node_release` before `rv_host_destroy`. The same
  holds for listeners (`rv_listener_remove`) and accessibility nodes (`rv_ax_release`). `RvWatch` is a weak
  reference that survives the node and the host.
- A returned pointer to a WebCore object is its address, so two handles to one object compare equal.
- Getters that return strings copy UTF-8 into a caller buffer and write the byte count; a small buffer returns
  `RV_ERR_BUFFER_TOO_SMALL` with the length set. Hand-written and generated string inputs carry a pointer and a
  byte count, so a string may hold U+0000.
- Event listener callbacks run synchronously inside the dispatching call and may call any function of the ABI.

## The frame loop

```c
RvHost* host = rv_host_create(width, height);          /* viewport in CSS pixels */
rv_host_set_frame_callback(host, on_frame_wanted, ctx);
rv_host_load_html(host, html, html_length);

for (;;) {
    rv_run_loop_cycle(0);                              /* timers, messages, accessibility events */
    /* ... forward input: rv_host_mouse, rv_host_wheel, rv_host_key, rv_host_set_focused ... */
    if (frame_wanted) {                                /* set by on_frame_wanted */
        frame_wanted = 0;
        rv_host_update(host);                          /* animations, observers, style, layout */
        rv_host_paint_rgba(host, rgba, length);        /* or a GPU frame, below */
    }
}
rv_host_destroy(host);                                 /* after releasing every handle */
```

- `rv_run_loop_cycle(ms)` cycles the calling thread's run loop until `ms` elapse, at least once; 0 runs exactly one
  cycle. It fires due WebCore timers and dispatches pending messages. The app calls it from its own loop; without
  it timers, animations and accessibility events do not advance.
- The frame callback runs on the host thread when the page wants a frame, once until the next `rv_host_update` or
  `rv_host_paint_rgba`. It must not call the ABI. The app schedules the frame, such as on its next vertical blank.
- `rv_host_update` runs WebCore's rendering update. `rv_host_dirty_rect` reports the invalidated area.
- `rv_host_resize` and `rv_host_set_device_scale` (0.25 to 8) change the viewport; `rv_host_paint_size` reports the
  size in device pixels that `rv_host_paint_rgba` writes (unpremultiplied RGBA8, sRGB).

## Presenting

- **CPU:** `rv_host_paint_rgba` into a caller buffer, uploaded by the app.
- **GPU (GPU flavor):** `rv_host_set_accelerated_compositing` selects off, always or when-needed. The app then
  acquires the composited frame without readback: `rv_host_acquire_d3d11_frame` (Windows, shared texture on the
  app's device), `rv_host_acquire_egl_frame` after `rv_configure_egl_display` (Linux), or
  `rv_host_acquire_iosurface_frame` (macOS), reads it with `rv_gpu_frame_info` and releases it with
  `rv_gpu_frame_release`. `rv_host_bind_d3d11_texture`, `rv_host_bind_egl_image` and `rv_host_bind_iosurface`
  feed an app texture into an element, and `rv_host_native_texture_changed` marks it updated. Where the library
  has no GPU code, or a call does not apply to the platform, the call returns `RV_ERR_UNSUPPORTED` and the app
  paints with `rv_host_paint_rgba`.
- **GPU painting (GPU flavor, Windows and Linux):** a composited frame rasterizes layer contents (text, borders,
  blurred shadows, filters) with Skia's GPU backend in the compositor's GL share group, so a repaint over a blurred
  `box-shadow` costs GPU time, not a CPU blur. It is on for a new host; `rv_host_set_gpu_painting(host, 0)` paints
  layer contents on the CPU, the same pixels the slim flavor would paint, for screenshot tests that compare frames
  across machines. When Skia's GL context cannot be created (no usable GPU driver), frames are painted on the CPU
  whatever the setting; `rv_host_gpu_painting` reports which. Frames that do not composite are painted on the CPU.
- Check `rv_abi_has` before relying on a group (see `docs/ABI.md`).

## Input

`rv_host_mouse`, `rv_host_wheel` and `rv_host_key` take viewport coordinates in CSS pixels. `RV_KEY_CHAR` inserts
text into the focused editable element; Tab moves focus. IME composition uses the `rv_host_ime_*` calls. A host
starts unfocused, with no caret blink, until `rv_host_set_focused(host, 1)`. Clipboard and drag-and-drop styles are
in `docs/CLIPBOARD-DND.md`.

## Page content

`rv_host_load_html` replaces the document. The host disallows JavaScript VM entry (`rv_host_vm_entry_disallowed`), so page scripts do not run; the app builds
and changes the page through the DOM calls: the hand-written `rv_document_*`, `rv_node_*`, `rv_element_*` calls and
the generated `rv_dom_*` functions (`docs/GENERATOR.md`).

## Teardown

Release nodes, listeners, watches' targets, accessibility nodes, GPU frames and diagnostic snapshots, detach any
UI Automation bridge, then call `rv_host_destroy`. A destruction request made from inside a callback is deferred
until the call ends.
