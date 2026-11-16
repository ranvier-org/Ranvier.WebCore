# The ABI in practice

`RanvierWebCoreHost` is a service with a C interface. This page is the guide to using it: the rules every call
follows, a tour of what the functions cover, and the places where a reasonable guess is wrong.

[The C ABI and header](ABI.md) is the reference for versions and feature detection. The contract itself is the
header, `include/RanvierWebCoreAbi.h` in every native package (`host/RanvierWebCoreAbi.h` in the repository). Where
this page and the header disagree, the header is right.

## Shape of the interface

- **C only.** Scalars, pointers, opaque handles, plain structs and function pointers. No C++ type crosses.
- **Two headers.** `RanvierWebCoreAbi.h` holds 365 hand-written functions. `RanvierWebCoreDom.h` holds 3,254
  generated ones, named `rv_dom_*` (counted at ABI 71, on 2026-11-16).
- **No initialisation call.** The first `rv_host_create` sets the process up. There is no shutdown call either.
- **Process-wide or per host.** Most functions take a host or a handle that belongs to one. A few act on the
  process or the calling thread and take neither: `rv_run_loop_cycle`, `rv_release_memory`, `rv_collect_garbage`,
  `rv_last_exception`, `rv_resource_cancel`, `rv_resource_release`.

## The five rules

### 1. One thread

Every call is valid only on the thread that first called `rv_host_create`. A call from another thread returns
`RV_ERR_WRONG_THREAD`, or `NULL` from a function that returns a handle, and changes nothing.

The exceptions the header names:

| Functions | Rule |
|---|---|
| `rv_image_encode_rgba`, `rv_encoded_image_bytes`, `rv_encoded_image_release` | Any thread, after a host exists. Serialize access to one handle with its release. |
| `rv_snapshot_pixels_copy`, `rv_snapshot_pixels_encode`, `rv_snapshot_pixels_release` | Any thread, after the capture. The capture itself is on the host thread. |
| `rv_diagnostic_*` | Any thread. A snapshot holds no engine object. |
| `rv_text_segments_release` | Any thread. |
| `rv_configure_egl_display` | The future host thread, before the first host (Linux). |
| `rv_gpu_frame_release` | The host thread, also after the host is destroyed. |

Work from another thread is posted to the host thread by the app. The ABI has no queue of its own.

### 2. Handles are references, and the app releases them

| Handle | What it is | Release | Outlives the host |
|---|---|---|---|
| `RvHost` | one page | `rv_host_destroy` | |
| `RvNode` | a strong reference to a node | `rv_node_release`, before the host is destroyed | no |
| `RvListener` | a listener and a strong reference to its target | `rv_listener_remove`, before the host is destroyed | only on the window or a standalone event target |
| `RvWatch` | a weak reference to a node | `rv_watch_release` | yes |
| `RvEvent` | valid during its callback only | `rv_event_retain` keeps it | |
| `RvAxNode` | an accessibility node | `rv_ax_release`, before the host is destroyed | no |
| `RvAnimation`, `RvObserver` | an animation, an observer | their release calls, before the host is destroyed | no |
| `RvGpuFrame` | a composited frame | `rv_gpu_frame_release` | yes |
| `RvDiagnostic`, `RvSnapshotPixels`, `RvEncodedImage` | copies that hold no engine object | their release calls | yes |
| `RvResourceLoad` | a pending load | ends when the load is finished or failed | |

Three properties to rely on:

- **Each call that returns a handle adds one reference.** Ask for the same node twice and release it twice.
- **A handle is the address of its WebCore object.** Two handles to one node compare equal.
- **An argument borrowed in a callback is valid for that call.** Keep it with the matching retain function.

`rv_watch_alive` answers whether a watched node still exists, which lets an app hold a weak reference without
keeping the node alive.

### 3. Strings are UTF-8, in two forms

**Out.** A getter copies into a buffer the caller owns and writes the byte count:

```c
char buffer[64];
int32_t length;
int32_t status = rv_event_type(event, buffer, sizeof buffer, &length);
if (status == RV_ERR_BUFFER_TOO_SMALL) {
    /* length holds the bytes needed; the buffer was not written. */
}
```

- No terminator is written. `length` is the byte count, or -1 for a null string. Three getters are NUL-terminated
  instead: `rv_blob_read_type`, `rv_blob_read_error` and `rv_file_reader_error`.
- A capacity below the count returns `RV_ERR_BUFFER_TOO_SMALL`, sets `length` and leaves the buffer untouched. So a
  call with capacity 0 asks for the size.

**In.** Two forms, and one function can take both:

```c
rv_element_set_attribute(node, "title", (const uint8_t*)"Caf\xC3\xA9", 5);
/*                              ^ identifier: NUL-terminated     ^ free text: bytes and a count */
```

| Kind | Form | Examples |
|---|---|---|
| Free text | `const uint8_t*` and an `int32_t` byte count. May hold U+0000. -1 means null. | text content, attribute values, HTML, typed text |
| Identifiers and protocol strings | `const char*`, NUL-terminated | element and attribute names, selectors, MIME types, style property names, URLs, feature names |

Invalid UTF-8 in free text returns `RV_ERR_NULL_ARGUMENT`; the font and media calls return `RV_ERR_UNSUPPORTED`
for it. A few functions take a URL or a property name as bytes and a count (`rv_blob_url_read`,
`rv_host_inspect_cascade`): the signature in the header decides.

**Offsets are UTF-16.** Text selection, input method and accessibility text offsets count UTF-16 code units, as
the DOM does, while the strings themselves cross as UTF-8.

### 4. A return value is a status, a value, or both

| Name | Value | Meaning |
|---|---|---|
| `RV_OK` | 0 | Done. |
| `RV_NOT_READY` | 1 | GPU pipeline backpressure. Not an error: keep the last image and retry. |
| `RV_ERR_NULL_ARGUMENT` | -1 | A required argument was null, or a string was invalid. |
| `RV_ERR_WRONG_THREAD` | -2 | Not the host thread. |
| `RV_ERR_DOM_EXCEPTION` | -3 | The DOM threw. Read it with `rv_last_exception`. |
| `RV_ERR_NOT_ELEMENT` | -4 | The node is not an element. |
| `RV_ERR_PAINT_FAILED` | -5 | Painting or a frame release failed. |
| `RV_ERR_BUFFER_TOO_SMALL` | -6 | The size needed was written. |
| `RV_ERR_LISTENER_FAILED` | -7 | A listener callback returned nonzero. |
| `RV_ERR_NOT_INPUT` | -8 | The element is not a form control. |
| `RV_ERR_UNSUPPORTED` | -9 | Not in this build, not on this platform, or not in this state. |
| `RV_ERR_DETACHED` | -10 | The host is being destroyed, or the object is detached: an accessibility object, or a node of a replaced document. |
| `RV_ERR_WRONG_INTERFACE` | -11 | The handle is of another interface. |
| `RV_ERR_DEVICE_LOST` | -12 | The GPU device was lost. |
| `RV_ERR_WRONG_HOST` | -12 | The object belongs to another document. |

Read these with care:

- **Negative is failure. Zero and positive depend on the function.** `rv_host_mouse`, `rv_host_wheel` and
  `rv_host_key` return 1 when the page or the engine handled the event and 0 when not. `rv_host_dirty_rect` and
  `rv_host_ime_rect` return 1 when there is a rectangle. `rv_host_edit` returns 1 when the command ran.
- **Two codes share -12.** Which one it is follows from the function called: device loss comes from the GPU frame
  functions, wrong host from functions that take an object of a document.
- **A function that returns a handle returns `NULL` on failure.** Some also write a status through a parameter.
- **`RV_ERR_UNSUPPORTED` is the fallback signal.** A GPU call on the CPU flavor, a Windows call on Linux, and an
  option the build lacks all return it, and the app takes its other path.

For a DOM exception:

```c
if (rv_node_append_child(parent, child) == RV_ERR_DOM_EXCEPTION) {
    char name[64]; int32_t n;
    rv_last_exception(RV_EXCEPTION_NAME, name, sizeof name, &n);   /* for example HierarchyRequestError */
}
```

### 5. Callbacks run on the host thread, at stated times

Every callback takes the `void* context` given at registration. Setting a handler with `NULL` removes it.

| Callback | Runs | May call the ABI |
|---|---|---|
| Event listeners | synchronously, inside the call that dispatches | yes, including a nested dispatch |
| Frame callback | when the page wants a frame, once until the next update or paint | **no** |
| Resize and intersection observers | during `rv_host_update` | yes |
| Resource handler, form submission, accessibility events, font events, notifications | from `rv_run_loop_cycle` | yes |
| Operation completions (image decode, font load) | from `rv_run_loop_cycle`, or inside `rv_resource_cancel` or `rv_resource_release` when that comes first; never before the call that started the operation returns | yes |
| File picker, print cancel poll | when the engine asks | **no** |

A listener returns 0 for success. A nonzero return makes the dispatching call return `RV_ERR_LISTENER_FAILED`,
and the other listeners still run.

What a request to destroy the host from inside a callback does depends on the call in progress, so the engine is
never torn down under an update, a paint or an edit:

- inside `rv_host_update`, a document load, a print, a snapshot or a frame acquire: the outer call ends and
  returns `RV_ERR_DETACHED`;
- inside an input or editing call: the outer call returns its usual value, then the host is destroyed;
- anywhere else, such as a listener run by a dispatch the app made itself: the host is destroyed at once.

After `rv_listener_remove`, `rv_observer_release` or `rv_fonts_unwatch` returns, its callback does not run again.

## A complete small example

```c
#include "RanvierWebCoreAbi.h"
#include <string.h>

static int frame_wanted;
static void on_frame(void* context) { frame_wanted = 1; }           /* must not call the ABI */

static int32_t on_click(void* context, RvEvent* event) {
    RvNode* label = context;
    rv_node_set_text_content(label, (const uint8_t*)"clicked", 7);
    return 0;
}

int main(void) {
    static const char html[] = "<!doctype html><body style='margin:0;font:20px Arial'></body>";

    RvHost* host = rv_host_create(320, 200);                         /* CSS pixels */
    rv_host_set_frame_callback(host, on_frame, NULL);
    rv_host_load_html(host, (const uint8_t*)html, (int32_t)strlen(html));
    rv_host_set_focused(host, 1);

    int32_t status;
    RvNode* document = rv_host_document(host);
    RvNode* body = rv_node_query_selector(document, "body", &status);
    RvNode* button = rv_document_create_element(host, "button");
    rv_node_set_text_content(button, (const uint8_t*)"Press", 5);
    rv_node_append_child(body, button);
    RvListener* listener = rv_node_add_event_listener(button, (const uint8_t*)"click", 5, 0, on_click, button);

    rv_host_mouse(host, RV_MOUSE_DOWN, 20, 14, RV_BUTTON_LEFT, 1, 0);
    rv_host_mouse(host, RV_MOUSE_UP, 20, 14, RV_BUTTON_LEFT, 1, 0);  /* on_click runs inside this call */

    rv_run_loop_cycle(0);
    int32_t width, height;
    rv_host_paint_size(host, &width, &height);                       /* device pixels */
    static uint8_t rgba[320 * 200 * 4];
    if (frame_wanted) {
        frame_wanted = 0;
        rv_host_update(host);
        rv_host_paint_rgba(host, rgba, width * height * 4);          /* unpremultiplied RGBA8, sRGB */
    }

    rv_listener_remove(listener);
    rv_node_release(button);
    rv_node_release(body);
    rv_node_release(document);
    rv_host_destroy(host);
    return 0;
}
```

The same calls from Python's `ctypes` are how the repository's own probes drive the host (`tests/abi/*.py`).

## The families

Counts are of `RanvierWebCoreAbi.h` at ABI 71. Most families have a feature name for `rv_abi_has`. The core ones
do not: process and version, host lifecycle, the document and node tree, node references, node filters and memory.

### Running a page

| Family | Functions | Start with |
|---|---|---|
| Process, version, features | 3 | `rv_abi_version`, `rv_abi_has` |
| Capability queries | 6 | `rv_host_capability_fact` ([Capability queries](CAPABILITIES.md)) |
| Host lifecycle and loading | 7 | `rv_host_create`, `rv_host_load_html`, `rv_host_load_svg`, `rv_host_destroy` |
| Run loop, frame, update | 5 | `rv_run_loop_cycle`, `rv_host_set_frame_callback`, `rv_host_update`, `rv_host_dirty_rect` |
| Viewport, scale, screen, visibility | 9 | `rv_host_resize`, `rv_host_set_device_scale`, `rv_host_paint_size`, `rv_host_set_visible` |
| Media queries and preferences | 5 | `rv_host_match_media`, `rv_host_set_media_preferences` |
| Memory | 3 | `rv_release_memory`, `rv_collect_garbage` ([Memory](MEMORY.md)) |

### Getting pixels out

| Family | Functions | Start with |
|---|---|---|
| CPU painting | 2 | `rv_host_paint_rgba`, `rv_host_paint_rgba_rect` |
| Compositing and GPU frames | 12 | `rv_host_set_accelerated_compositing`, `rv_host_acquire_d3d11_frame`, `rv_gpu_frame_info`, `rv_gpu_frame_release` |
| Native texture input | 4 | `rv_host_bind_d3d11_texture`, `rv_host_native_texture_changed` |
| Snapshots and image encoding | 11 | `rv_host_snapshot_pixels`, `rv_image_encode_rgba` |
| Printing | 2 | [PDF output](PRINTING.md) |
| Canvas, ImageData, ImageBitmap | 13 | `rv_canvas_get_context` (2D contexts only) |

### The document

| Family | Functions | Start with |
|---|---|---|
| Document and node tree | 28 | `rv_host_document`, `rv_document_create_element`, `rv_node_append_child`, `rv_node_query_selector` |
| Node references and watches | 8 | `rv_node_retain`, `rv_node_release`, `rv_watch_alive` |
| Attributes, classes, style, form state | 14 | `rv_element_set_attribute`, `rv_element_computed_style` |
| Geometry and hit testing | 4 | `rv_element_rect`, `rv_host_element_at` |
| Scrolling | 5 | `rv_host_scroll_position`, `rv_host_scroll_to` |
| Events and listeners | 32 | `rv_node_add_event_listener`, `rv_event_type`, `rv_host_construct_event` |
| Node filters for traversal | 2 | callbacks for the generated TreeWalker and NodeIterator functions |
| Resize and intersection observers | 10 | callbacks in `rv_host_update` |
| Mutation observation | 9 | [Mutation observation](MUTATION-OBSERVATION.md) |
| Animations and view transitions | 19 | [Web Animations](ANIMATIONS.md) |
| Blobs, files, FileReader | 10 | `rv_blob_read_bytes` |
| Text segmentation | 3 | `rv_text_segment` |

For anything else the DOM offers, there is a generated function. See [below](#the-generated-dom-functions).

### Input and the outside world

| Family | Functions | Start with |
|---|---|---|
| Mouse, wheel, keyboard, pointer, touch | 14 | `rv_host_mouse`, `rv_host_wheel`, `rv_host_key`, `rv_host_pointer`, `rv_host_cursor` |
| Focus | 3 | `rv_host_set_focused`, `rv_element_focus` |
| Input method | 8 | `rv_host_ime_set_composition`, `rv_host_ime_commit`, `rv_host_ime_rect` |
| Editing and clipboard | 7 | `rv_host_edit`, `rv_host_set_clipboard` ([Clipboard and drag and drop](CLIPBOARD-DND.md)) |
| Drag and drop | 15 | `rv_host_set_drag`, `rv_host_drag` |
| Select popups and file picker | 9 | `rv_host_set_popup_handler` |
| Resource loading and form submission | 4 | `rv_host_set_resource_handler`, `rv_resource_load_finish` |
| Image decode and fonts | 12 | `rv_image_decode`, `rv_fonts_load` |
| Wake locks, notifications, media capabilities | 17 | policy and presenter callbacks |

### Accessibility and diagnostics

| Family | Functions | Start with |
|---|---|---|
| Accessibility tree and text | 32 | [Accessibility](ACCESSIBILITY.md) |
| Diagnostics and inspection | 12 | [Diagnostics](DIAGNOSTICS.md) |
| Host tracing and layout metrics | 3 | `rv_host_trace_enable`, `rv_host_layout_count` |
| Error records | 3 | `rv_last_exception`, `rv_host_error_take` |

### What is not there

- **Script evaluation.** No function runs JavaScript. `rv_host_scripts_enabled` and
  `rv_host_vm_entry_disallowed` report the state.
- **Navigation.** A document is never navigated. A form submission goes to the app's handler or is dropped.
- **A network client.** Loads go to the resource handler.
- **Media playback and spelling.** These are application-side adapters: `examples/NativeMedia` and
  `examples/NativeSpelling`.
- **A general settings call.** Each setting has its own function. Renderer settings are readable through the
  capability queries.

## The generated DOM functions

`RanvierWebCoreDom.h` gives each IDL attribute and operation of the listed interfaces its own function, so an app
is not limited to the DOM calls someone wrote by hand.

| IDL | Function |
|---|---|
| attribute getter | `rv_dom_<interface>_get_<attribute>` |
| attribute setter | `rv_dom_<interface>_set_<attribute>` |
| operation | `rv_dom_<interface>_<operation>` |
| handle lifetime | `rv_dom_<type>_retain`, `rv_dom_<type>_release` |
| constant | `RV_DOM_<INTERFACE>_<CONSTANT>` |

```c
RvAbstractRange* range;
rv_dom_document_create_range(document, &range);       /* Document.createRange() */
```

Their conventions:

- Each returns `RV_OK` or a negative status and writes its result through the last parameters.
- `target` is the object the member belongs to. A handle of another interface returns `RV_ERR_WRONG_INTERFACE`.
- String inputs are a pointer and a byte length, -1 for null or absent.
- Booleans are `int32_t`. A nullable or optional argument with no default is a pointer, `NULL` for absent.
- A dictionary is a pointer to an `RvDom<Dictionary>` struct whose first field, `size`, is its `sizeof`. `NULL`
  takes the IDL defaults. Fields are added at the end, so an older caller's smaller struct stays valid.
- A handle out is a new reference.
- A member WebKit compiles out, or whose setting is off, returns `RV_ERR_UNSUPPORTED`.

`rv_abi_has("dom-generated")` detects the set and `rv_abi_has("dom:<Interface>")` one interface.
[The generated DOM functions](GENERATOR.md) describes the generator and what it leaves out.

## Structs that carry their size

Structs the ABI may extend have `size` as their first field. The caller sets it to `sizeof` of the struct it was
compiled with:

```c
RvWindowMetrics metrics = { .size = sizeof metrics };
rv_host_window_metrics(host, &metrics);
```

A size that is too small returns `RV_ERR_UNSUPPORTED` for most of them. `RvEventInit` and `RvNotificationOptions`
require the exact size.

## Versions and features

- `rv_abi_version()` is one number for the whole library: 71 on `main` on 2026-11-16.
- `rv_abi_has("name")` is 1 when the library has that group of functions. Test for the group, not for a version.
- The managed and native packages of one release report the same version. A mismatch means two releases are mixed
  in one output folder.
- Two changes broke source compatibility and are marked in the header: ABI 51 for generated string inputs and
  ABI 55 for hand-written ones, both moving free text to a pointer and a byte count.

`rv_abi_has` says a function group exists. It does not say an operation will succeed: `presentation-d3d11` is 1
for the Windows frame API, and a successful acquisition still depends on the GPU, the consumer device and the
scale.

## Defaults that surprise

A new host:

| Is | Until |
|---|---|
| unfocused: no caret blinks and `:focus-visible` does not match | `rv_host_set_focused(host, 1)` |
| unable to load any URL except `data:` and `blob:` | `rv_host_set_resource_handler` |
| dropping form submissions | `rv_host_set_form_submission_handler` |
| keeping the clipboard to the page (DOM style) | `rv_host_set_clipboard` |
| receiving no drags (DOM style) | `rv_host_set_drag` |
| opening no menu for a `<select>` | the popup handler is set |
| without accessibility: the host-rooted calls return `NULL` | `rv_host_set_accessibility` |
| without diagnostics: `rv_host_inspect_*` return `RV_ERR_UNSUPPORTED` | `rv_host_set_diagnostics(host, 1)` |
| denying every wake lock | a policy is set |
| at device scale 1, visible, page scale 1 | the setters |

## Easy to get wrong

**Timing**

- The frame callback only signals. Calling the ABI from it is not allowed.
- A resource load, an image decode completion or an accessibility event arrives in a later `rv_run_loop_cycle`,
  never inside the call that started it. A loop that stops cycling stops receiving them.
- Scroll events, media query changes and observers fire in `rv_host_update`.
- `rv_host_dirty_rect` is relative to the last `rv_host_paint_rgba`. A partial paint clears it only when the
  painted area contains it.

**Pixels and coordinates**

- CPU paint output is **unpremultiplied** RGBA8. GPU frames are **premultiplied**, and BGRA on macOS.
- Input coordinates and dirty rectangles are CSS pixels. `rv_host_paint_size`, element snapshots and drag images
  are device pixels.
- The paint size is the CSS size times the device scale, rounded down.
- With compositing off, 3D transforms are drawn flat and backdrop filters are ignored.

**Memory**

- `rv_node_query_selector_all` leaves its matches in a document cache until a mutation under the scope or a memory
  release. The cached results hold their elements.
- A double `rv_resource_release` is not reported: repeated and unknown tokens return `RV_OK`.

**Platforms**

- The native clipboard style is Windows and macOS only. The native drag style is not supported anywhere yet.
- Touch input returns `RV_ERR_UNSUPPORTED` on macOS.
- `rv_host_attach_uia` returns `RV_ERR_UNSUPPORTED` off Windows.
- On Linux, `rv_configure_egl_display` comes before the first host, and the EGL frame path has no CPU fallback of
  its own: the app paints with `rv_host_paint_rgba` instead.
- Text segmentation follows the ICU in use: the package's own on Windows and Linux (linked statically on Linux),
  the system's on macOS. The header's comment still says Linux uses the system's.
- A GPU frame must be released before the native libraries are unloaded.

## Calling from other languages

| Language | How |
|---|---|
| F#, C# | The `Ranvier.WebCore` package: `RanvierWebCoreAbi.Native` and `NativeDom`, generated from the headers. The library is found by name through the runtime's probing of `runtimes/<rid>/native`. |
| C, C++ | Include the headers from the package's `include/` and link `RanvierWebCoreHost`. |
| Python | `ctypes.CDLL` on the library in `runtimes/<rid>/native`. `tests/abi/form_collections.py` has a small binding helper. |
| Anything else | Any foreign function interface for C. The header uses fixed-width integer types throughout. |

Keep `WebKit.resources` beside the libraries, and load the host library from the folder that holds WebCore and
JavaScriptCore, so that its dependencies resolve.

The managed declarations are generated, so they cannot drift from the header:
`python -I tests/abi/generate_native.py write` regenerates `Native.fs`, and `check` verifies it in CI.

## Changing the ABI

For contributors to this repository:

1. Edit `host/RanvierWebCoreAbi.h` and its implementation. Mark the group with the version that adds it and give
   it a feature name.
2. Raise the number `rv_abi_version` returns in `host/RanvierWebCoreAbi.cpp`. That definition is the source of
   truth; packaging reads it.
3. Run `python -I tests/abi/generate_native.py write`.
4. Add a test in `tests/abi`, and a probe in both `scripts/probes.py` and `scripts/abi_tests.py` if it needs the
   packaged runtime.
5. Never copy the version number into a test or workflow. Read it from the manifest or the source
   ([Footguns](FOOTGUNS.md#abi-version-asserts-in-probes-go-stale-on-every-bump)).

A change to a file under `tests/abi` can fail CI's `package-contract` job, which pins the shape of the ABI probes.
Run that job's scripts locally before pushing.
