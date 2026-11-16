# Troubleshooting

Symptoms a host author meets, with the cause and the remedy. Entries are grouped by where the symptom shows.
[Footguns](FOOTGUNS.md) covers pitfalls of maintaining this repository, not of using the packages.

## Nothing appears

### The window is blank or white

| Check | Cause | Remedy |
|---|---|---|
| Was `rv_host_update` called before the paint? | Style and layout are stale. | Update, then paint. |
| Is the buffer the size `rv_host_paint_size` reports? | The CSS size was used at a device scale other than 1. | Size the buffer in device pixels. |
| Did the paint return a negative status? | The length passed was too small, or the call left the host thread. | Read the status. |
| Is the page's content waiting on a load? | No resource handler is installed, so every URL load fails. | Install one ([Operating a host](OPERATION.md#resources)). |
| Is the upload treating the pixels as premultiplied? | CPU paint output is unpremultiplied RGBA8. | Upload with blending off, or premultiply. |

### The first frame is an empty page

The window was shown before the view was mounted. Create it hidden, mount, then show and present
([Hosting from .NET](MANAGED.md#a-windowed-app)).

### An image does not draw, and no broken-image icon either

`WebKit.resources/icons` is not beside the WebCore library. A build with a runtime identifier flattens native
assets; the package's build target copies the folder back for that runtime only. Publish with the runtime
identifier the app runs on, and keep the folder when copying the output by hand.

### A `<script>` does nothing

By design. The host disallows entry into the JavaScript virtual machine. Change the page through the DOM calls.

## The page does not move

### Animations and timers are frozen

`rv_run_loop_cycle` is not being called. Call it once a turn. On Windows an app that pumps its own messages still
gets WebCore's timers, but resource loads, completions and accessibility events are delivered only from
`rv_run_loop_cycle`.

### A timer fires late on Windows

Before 0.1.3 a zero-delay timer started while timers were firing could arrive up to about 16 ms late. 0.1.3 fires
due timers at the start of each pass. Upgrade.

### The page updates only when the mouse moves

The loop paints only after input. The frame callback is not connected: register it with
`rv_host_set_frame_callback` and paint when it has fired.

### A signal written from a frame callback has no effect

Write inside the graph: `graph.Run(fun () -> signal.Value <- value)`. From `Ranvier.View.WebCore` 0.1.2 a write
outside it takes effect or is reported, where before it failed silently
([Field notes](FIELD-NOTES.md#write-signals-from-a-frame-callback-inside-the-graph)).

### An image or font never finishes loading

- The load was not completed. Each load must end in `rv_resource_load_finish` or `rv_resource_load_fail`, exactly
  once.
- The loop stopped cycling. A load finished outside the handler is delivered on the next `rv_run_loop_cycle`.

## Input does not work

### Keys do nothing, and there is no caret

The host is unfocused. Call `rv_host_set_focused(host, 1)` when the window has keyboard focus. A host starts
unfocused.

### Typed text does not appear

`RV_KEY_DOWN` runs editing commands and moves focus. Text is inserted by `RV_KEY_CHAR`. Send down, then char with
the text, then up.

### Clicks land in the wrong place at a display scale other than 1

Input coordinates are CSS pixels. Divide the window's pixel coordinates by the device scale.

### Copy and paste stay inside the page

A host starts in the DOM clipboard style, where only the page sees the data. Set the App or Native style with
`rv_host_set_clipboard` ([Clipboard and drag and drop](CLIPBOARD-DND.md)). The Native style is Windows and macOS
only.

### A `<select>` opens nothing

No popup handler is set. Without one a select opens no menu.

### A drop from another app does nothing

The host starts in the DOM drag style, where no drag reaches the page. The SDL window does not forward the
system's drop events; the app builds the payload and calls the drag functions
([Hosting from .NET](MANAGED.md#what-the-window-does-not-wire)).

### Touch input returns an error on macOS

Touch events are not built on macOS. `rv_host_pointer` returns `RV_ERR_UNSUPPORTED` for touch samples there.

## Text looks wrong

### Everything is in Times New Roman on Windows

Before 0.1.3 the host set no generic font families. From 0.1.3, `sans-serif` is Arial, `monospace` is Consolas and
`serif` is Times New Roman. `system-ui` is still unmapped. Name a real font before it:

```css
font-family: 'Segoe UI', 'Noto Sans', 'DejaVu Sans', system-ui, sans-serif;
```

### Chart text differs from the rest of the interface

SVG marks that default to `sans-serif` resolve to Arial on Windows. Add a rule for `svg text`.

### Pixels differ between two machines

A composited frame differs between GPUs. For comparisons use the CPU flavor, or turn compositing off on the host
(`RV_COMPOSITING_OFF`). macOS frames differ from Windows and Linux frames on any flavor, because
macOS draws with CoreGraphics.

### 3D transforms look flat, or a backdrop filter is missing

Compositing is off: 3D transforms are drawn flat and backdrop filters are ignored. That is always so in the CPU
flavor. In the GPU flavor, check that `rv_host_set_accelerated_compositing` succeeded and that a GL context could
be created.

## Loading and versions

### `DllNotFoundException`, or the library fails to load

| Cause | Remedy |
|---|---|
| No native package for the runtime | Reference `Ranvier.WebCore.Native` or `.Cpu`. |
| The host library was copied without WebCore and JavaScriptCore | Keep every file of `runtimes/<rid>/native` together. |
| Linux: a distribution library is missing | Install the packages in `scripts/linux-runtime-packages.txt`. `ldd libRanvierWebCoreHost.so` names what is missing. |
| macOS older than 26.0 | The package's deployment target is macOS 26.0. |

### The host raises about the ABI version

The managed and native packages are from different releases. Reference both at one version. `rv_abi_version()`
and the `abi` in the native package's `manifest.json` say what is loaded.

### Two copies of `RanvierWebCoreHost` in the output

Both aggregates are referenced, or the GPU aggregate arrives through `Ranvier.View.WebCore` beside an explicit CPU
reference. Reference one. To choose the CPU flavor under the view packages, exclude the assets of the GPU packages
([Field notes](FIELD-NOTES.md#choosing-the-cpu-runtime-from-a-view-app-takes-three-references)).

### `MissingMethodException` on `Window.Create`

`Ranvier.View.WebCore.Sdl` and `Ranvier.View.WebCore.Hmr` are from different releases. Upgrade them together.

### `NU1605`, or `FSharp.Core` fails to load

A package asks for a newer `FSharp.Core` than the SDK ships. The hot reload package (0.1.2) needs SDK 10.0.404 for
Debug builds. Use `Update`, not `Include`, for an explicit `FSharp.Core` reference.

### The output folder is about 600 MiB

No runtime identifier: the output carries every platform's native engine. Build or publish with `-r <rid>`
([Field notes](FIELD-NOTES.md#output-size)).

## GPU frames

### Every frame is painted on the CPU

| Check | Meaning |
|---|---|
| `rv_abi_has("compositing")` is 0 | The CPU flavor is loaded. |
| `rv_host_set_accelerated_compositing` returned `RV_ERR_UNSUPPORTED` | No GL context could be created, or the library has no GPU code. |
| `rv_host_gpu_painting(host)` is 0 | Skia's GL context could not be created, or GPU painting was turned off. |
| The page has no composited layer | In the when-needed mode such a frame is painted on the CPU. That is expected. |
| A display scale other than 1 under the SDL window | Its README says unsupported devices and scales other than 1 use CPU painting. |

### `rv_host_acquire_d3d11_frame` returns `RV_ERR_UNSUPPORTED`

- Compositing is not enabled, or the library has no GPU code.
- A frame from the same surface is still held. Release it first.

### A frame acquire returns `RV_NOT_READY`

Only the bounded pipeline returns it. The GPU is busy. Keep the previous image and retry at the next scheduled
frame. Do not retry in a loop.

### `RV_ERR_DEVICE_LOST`

Release the held frames, rebuild the consumer device and configure the pipeline again. On EGL and Metal the host
must be recreated. `rv_host_error_take` gives the D3D11 device-removed reason
([Diagnostics](DIAGNOSTICS.md#host-error-records)).

### Linux: no GPU frames

`rv_configure_egl_display` must be called on the future host thread before the first host, with the display the
consumer uses. It cannot be changed afterwards.

### An unattended run hangs in a present

One GPU-presented unattended benchmark hung in a D3D11 present and could not be killed from user mode. Run
unattended windows hidden, and use the software renderer where the run does not need the GPU path.

## Memory and performance

### Commit is hundreds of megabytes on Windows

Packages up to 0.1.3 commit libpas's reservations whole: about 314 MB after `rv_host_create` in one measurement.
Lazy commit is on `main` and ships with the next release ([Memory](MEMORY.md#why-commit-was-so-high)).

### Working set stays high after the window is hidden

Nothing gives memory back by itself except the kept paint surface, after two to four seconds. Call
`rv_release_memory` and `rv_collect_garbage` when hidden. Most of a GPU app's working set belongs to the GPU
driver, the uploader and the .NET heap, not the engine ([Memory](MEMORY.md#where-an-apps-memory-actually-is)).

### Memory grows as nodes are removed

- Node handles were not released. Each returned `RvNode` is a strong reference.
- In managed code, the loop stopped cycling. Collected wrappers are released in `host.Cycle`.
- `querySelectorAll` results are cached per document and hold their elements until a mutation under the scope or
  `rv_release_memory`.

### The app uses CPU while idle

A frame is requested every frame. See [A frame loop that rests](FIELD-NOTES.md#a-frame-loop-that-rests).

### A frame got slower as the page grew

Engine time grows with element count, with per-frame changes to inherited custom properties, and with any change
to an adopted stylesheet. [Field notes](FIELD-NOTES.md#what-makes-a-frame-expensive) has measurements and
remedies. To see where the time goes, enable host tracing ([Diagnostics](DIAGNOSTICS.md#host-tracing)).

### A benchmark figure does not reproduce

Hidden, unpaced windows give optimistic figures, and hidden timer-paced launches were bimodal on one machine.
Read [Measuring](FIELD-NOTES.md#measuring) before comparing two numbers.

## Statuses

| Status | Usual meaning in practice |
|---|---|
| `RV_ERR_WRONG_THREAD` (-2) | A call from a worker, a timer thread or a finalizer. Post it to the host thread. |
| `RV_ERR_NULL_ARGUMENT` (-1) | A null handle, or free text that is not valid UTF-8. |
| `RV_ERR_DOM_EXCEPTION` (-3) | The DOM refused the operation. `rv_last_exception` has the name. |
| `RV_ERR_BUFFER_TOO_SMALL` (-6) | Not a failure of the operation: the size needed was written. Call again. |
| `RV_ERR_UNSUPPORTED` (-9) | The flavor, platform, struct size or current state does not allow it. |
| `RV_ERR_WRONG_INTERFACE` (-11) | A generated function was given a handle of another interface. |
| `RV_ERR_DETACHED` (-10) | The host was destroyed from inside the call. |

## Reporting a problem

Include:

- the package ids and versions, and the runtime identifier;
- `flavor`, `abi` and the WebKit commit from the native package's `manifest.json`;
- the operating system, and for a GPU problem the adapter and driver;
- the smallest page that shows it, as HTML;
- the status the failing call returned, and `rv_last_exception` for a DOM exception.

A page that reproduces with `rv_host_load_html` and `rv_host_paint_rgba` alone, from Python or C, separates an
engine problem from one in the layers above it.
