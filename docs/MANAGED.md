# Hosting from .NET

Most apps never call the C ABI themselves. They reference the `Ranvier.View` packages, which create the host, run
the frame loop, forward input and present frames. This page is a map of those layers: which package does what,
which `rv_` calls it makes and in what order, and what it leaves to the app.

The packages below live in the `Ranvier.View` and `Ranvier.Wgpu` repositories. Versions are those in their project
files on 2026-11-16. For the view side see [Native deployment with WebCore](repo:view/view/native.md).

## The stack

| Layer | Package | Version | Does |
|---|---|---|---|
| Window and presenter | `Ranvier.View.WebCore.Sdl` | 0.2.0 | An SDL3 window: paints the page, forwards mouse, keyboard and input method events, bridges the cursor and the clipboard. |
| Dev host | `Ranvier.View.WebCore.Hmr` | 0.1.2 | `dotnet run -- dev`: keeps the window and page alive and patches edited components into them. JIT only. |
| View backend | `Ranvier.View.WebCore` | 0.1.2 | `WebCoreHost`: owns one page, implements the shared DOM contracts over it, runs timers, microtasks and animation frames. |
| Managed interop | `Ranvier.WebCore` | pairs with the native version | The P/Invoke declarations: `RanvierWebCoreAbi.Native` (hand-written ABI) and `NativeDom` (generated DOM functions). |
| Native | `Ranvier.WebCore.Native` or `.Cpu` | 0.1.3 | `RanvierWebCoreHost`, WebCore and JavaScriptCore for the app's runtime identifier ([Packages and flavors](PACKAGES.md)). |

Beside the stack, `Ranvier.Wgpu.Sdl` (0.2.1) draws a wgpu scene into one element of the page. It does not present
the page.

An app with a window references `Ranvier.View.WebCore.Sdl` and gets the rest. An app that renders offscreen
(tests, snapshots, a server) references `Ranvier.View.WebCore`.

`Ranvier.View.WebCore` 0.1.2 requires ABI 29 or later and the `dom-generated` group. `WebCoreHost.Create` raises
when the loaded library reports less.

## A windowed app

```fsharp
open System
open Ranvier
open Ranvier.View
open Ranvier.View.Dom
open Ranvier.View.WebCore.Sdl

use window = Window.Create("Example", 1280, 800, hidden = true)
let graph = window.Graph
let doc = window.Host.Document
let container = doc.createElement "div"
doc.body.appendChild container |> ignore

let mounted =
    Mounting.mount graph None (fun errs -> raise (AggregateException errs)) container None (fun ctx ->
        Program.run (Component.render app props) ctx.Backend)

try
    window.Show()
    window.Present()
    while window.Step() do
        ()
finally
    graph.Run(fun () -> mounted.Dispose())
    container.remove ()
```

Creating the window hidden and showing it after the mount means the first frame the user sees is the app, not an
empty page.

## A windowless host

```fsharp
open Ranvier
open Ranvier.View
open Ranvier.View.Dom
open Ranvier.View.WebCore

use host = WebCoreHost.Create (320, 200)
use graph = new Graph ()
let container = host.Document.createElement "div"
host.Document.body.appendChild container |> ignore

let mounted =
    Mounting.mount graph None (List.iter host.Report) container None (fun context ->
        Program.run (Component.render counter 1) context.Backend)

host.Click (40, 30) |> ignore // input in page pixels
host.Cycle ()                 // WebCore's timers and the posted callbacks
host.Frame ()                 // animation frame callbacks, then the rendering update

let struct (width, height) = host.PaintSize
let pixels = Array.zeroCreate<byte> (width * height * 4)
host.Paint pixels             // unpremultiplied RGBA8, row by row
```

`Cycle`, `Frame`, `Paint` is the whole loop. `Ranvier.D5.Dashboards --native-probe` is this loop run 300 times a
dashboard.

## What creating a host calls

`WebCoreHost.Create(width, height)`:

1. `rv_abi_version` and `rv_abi_has("dom-generated")`.
2. `rv_host_create(width, height)`.
3. `rv_host_load_html` with an empty HTML document. View code then builds the page through `host.Document`.
4. `rv_host_now`, to continue the engine's `performance.now()` clock.
5. `rv_host_document`, wrapped as the `Document`.
6. `rv_host_set_frame_callback`. The callback only sets a flag.
7. The host installs its `SynchronizationContext` and registers itself as the thread's view host.

There is no process initialisation call. The first host creates what the process needs.

`Window.Create` wraps that. In order, it starts SDL video, creates the window, creates a D3D11 swap chain where
supported, registers the EGL display on Linux (`rv_configure_egl_display`, before the first host), creates the
host, and then:

1. `rv_host_set_accelerated_compositing(host, 1)`, when a GPU consumer exists.
2. `rv_host_set_device_scale`, then `rv_host_resize`.
3. `rv_host_set_screen`, with the `screen` group.
4. `rv_host_attach_uia(host, hwnd)` on Windows, or the AT-SPI bridge on Linux when its module is present.
5. `SDL_StartTextInput`.
6. `rv_host_set_clipboard`, with the `clipboard` group.
7. `rv_host_set_focused(host, 1)` if the window already has input focus.

## What one `Window.Step` does

1. **Settle the previous present.** A lost device marks the frame to be drawn again.
2. **Work out how long to wait.**
   - Zero when work is posted to a host, or the last event drain was cut short.
   - With a frame wanted: until the next timer or GPU retry.
   - Otherwise: the caller's timeout (50 ms by default), cut by the next timer and by held input coming due.
3. **Wait** in `SDL_WaitEventTimeout`.
4. **Drain events** into the input calls below.
5. **Cycle the host** (`host.Cycle`):
   - `rv_run_loop_cycle(0)`;
   - release the native references of wrappers the garbage collector collected;
   - run posted work, then due timers, each followed by a microtask checkpoint;
   - run idle callbacks, only when nothing is posted and no frame is requested.
6. **Present, if a frame is wanted.** `host.Frame` runs the animation frame callbacks and then `rv_host_update`.
   The presenter then acquires a GPU frame or paints on the CPU.

A frame is wanted when the engine's frame callback fired, `RequestAnimationFrame` was called, the window was
exposed, or a full paint is pending.

Three things follow from this shape:

- **The loop rests by itself.** With no frame wanted and no timer due, the thread sleeps for up to 50 ms a turn.
  It still cycles the host each turn, which is what releases collected wrappers.
- **An app that re-arms `RequestAnimationFrame` from every frame never rests.** See
  [Field notes](FIELD-NOTES.md#a-frame-loop-that-rests).
- **Timers, microtasks, animation frames and idle callbacks are managed queues**, inside `WebCoreHost`. The engine
  runs no script, so its own timer queue serves only the engine.

`Step` drains SDL's global event queue for every live Ranvier window. An app that owns the SDL event pump runs its
own loop over `host.Cycle`, `host.Frame` and the presenter instead.

## Presenting paths

The window picks a path from what the loaded library reports through `rv_abi_has`, and falls back a frame at a
time.

| Path | When | Calls |
|---|---|---|
| D3D11 swap chain | Windows, `presentation-d3d11`, a D3D11 device, compositing accepted | `rv_host_acquire_d3d11_frame`, `rv_gpu_frame_info`; a separate "Ranvier present" thread copies the texture to the back buffer and presents; `rv_gpu_frame_release` after the present finishes. |
| EGL | Linux, `presentation-egl` | `rv_host_acquire_egl_frame` with the consumer context current; the EGLImage is bound to an SDL texture. |
| IOSurface | macOS, `iosurface-frames` | `rv_host_acquire_iosurface_frame`; the surface is imported as an SDL texture and held until a Metal completion fence. |
| Bounded pipeline | opt-in (`window.GpuFramePipeline <- true`), `gpu-frame-pipeline-v1` | `rv_host_configure_gpu_pipeline`, `rv_host_submit_gpu_frame`, `rv_host_try_acquire_completed_gpu_frame`. `RV_NOT_READY` defers by one refresh interval. |
| CPU | the CPU flavor, `renderer = "software"`, or any frame whose GPU acquire failed | `rv_host_paint_rgba` for a full paint, else `rv_host_dirty_rect` and `rv_host_paint_rgba_rect`; the buffer is uploaded to a streaming texture or a D3D11 texture. |

Details worth knowing:

- **After any GPU frame the next CPU paint is a full one.** The CPU buffer does not track what the GPU path drew.
- **Damage is widened to the device-pixel grid**, plus one pixel on Linux, where a dirty rectangle can omit a
  glyph's outer antialias pixel.
- **The window never calls `rv_host_set_gpu_painting`.** GPU painting stays at the host's default, on.
- **With the swap chain, `SDL_GetRenderer` returns null** for the window. The window owns its own D3D11 device.
- **On Linux the EGL display, its contexts and its texture pool live until the process exits.**

`window.ReadPixels()` returns top-down straight RGBA8. A GPU frame reads as opaque.

## Input

All input goes through one path that makes the native call, runs a microtask checkpoint and raises on a negative
status. Coordinates are CSS pixels.

| Window event | ABI call |
|---|---|
| Mouse move, buttons, leave | `rv_host_mouse` |
| Wheel | `rv_host_wheel`; one SDL wheel tick is 40 CSS pixels |
| Key down and up | `rv_host_key`; skipped while composing |
| Text | `rv_host_key` with `RV_KEY_CHAR` |
| IME composition | `rv_host_ime_set_composition`, `rv_host_ime_commit`, `rv_host_ime_cancel`; the candidate window is placed from `rv_host_ime_rect` |
| Touch and pen | `rv_host_pointer`, one array of samples a frame |
| Focus gained and lost | `rv_host_set_focused`; on loss the composition and active touches are cancelled first |
| Shown, hidden, minimised, occluded | `rv_host_set_visible` |
| Cursor | `rv_host_cursor` after mouse input, mapped to a system cursor |
| Clipboard | `rv_host_set_clipboard`; the SDL bridge moves `text/plain` only |

**Input rates.** Mouse motion, wheel, pen, touch motion and resize are held and dispatched at most once per display
refresh by default. Held input is flushed before any button, key, focus or text event, so the page sees the
window's order.

## What the window does not wire

The app installs these on `window.Host` when it needs them:

| Service | Install | ABI behind it |
|---|---|---|
| Images and fonts by URL | `Resources.forHost host provider` | `rv_host_set_resource_handler`; each load answered with `rv_resource_load_finish` or `rv_resource_load_fail`. The bytes come from the app's provider: the engine fetches nothing itself. |
| Font faces | `Fonts.forHost` | the `rv_fonts_*` and `rv_font_face_*` calls |
| Drop from outside | `DataTransfers.drop` | `rv_drag_data_create`, `rv_drag_data_add`, `rv_host_drag`. The SDL window does not forward SDL's own drop events. |
| File picker | `WindowsFilePickers.install` (Windows), `FilePickers.install` elsewhere | the `file-picker` group |
| Wake lock | `WakeLocks` (Windows) | `rv_set_sleep_disabler_callback` |
| Constructed stylesheets | `StyleSheets.forHost` | the generated CSSOM functions |
| Snapshots | `Snapshots.forHost`, `BackgroundSnapshots.forHost` | `rv_host_snapshot*`, `rv_image_encode_rgba` |

Nor do the packages call `rv_release_memory`, `rv_collect_garbage` or any working-set function. An app that wants
memory back when its window is hidden makes those calls itself ([Memory](MEMORY.md#giving-memory-back)).

## How view code reaches the DOM

- **No script.** The managed layers never evaluate JavaScript. There is no evaluate function in the ABI.
- **One P/Invoke per DOM member.** The `Ranvier.Dom` interfaces are implemented by generated wrapper classes. Each
  member is one native call and a status check. There is no command buffer.
- **Batching is reactive, not at the ABI.** The graph and the view's commit queue decide how many writes a change
  becomes. The page's pixels change only at the next `Frame` and paint.
- **One wrapper per node.** A table from native handle to wrapper gives one node one wrapper. A second handle to a
  known node is released at once.
- **Wrappers hold native references.** A wrapper's finalizer queues the release, and the host thread performs it in
  `Cycle`. So a window's loop must keep cycling while it is open, or released nodes accumulate.
- **Failures become exceptions.** A negative status raises. A DOM exception's text comes from
  `rv_last_exception`. An exception inside a listener, timer or frame callback is recorded in `host.Errors` and
  written once to standard error; it is never thrown through native frames.

## Threading

- **One thread for everything native.** Every `WebCoreHost` member, and its disposal, runs on the thread that
  created it. The first host or window reserves that thread for all native hosts and SDL windows for the life of
  the process, including after every window has closed.
- **macOS:** that thread is the process main thread, shared with SDL's event pump.
- **Other threads post.** `host.TryPost(action, maximumPending)` returns `Accepted`, `Full` or `Closed` without
  blocking. Posting to an empty queue wakes the window's wait. `SynchronizationContext.Send` from another thread
  raises.

## Hidden windows

`Window.Create(..., hidden = true)` creates a window that is never shown until `Show`.

- The page is told with `rv_host_set_visible(host, 0)`. That queues `visibilitychange`, and a hidden page defers
  `resize`.
- The loop is unchanged. Frames still run when the page requests them.
- Presentation is paced by a sleep of one refresh interval in place of the present, since a hidden window has no
  vertical blank to wait for.

Run soak, benchmark and capture windows hidden. Read [Field notes](FIELD-NOTES.md#measuring) before trusting a
figure from one: unpaced hidden-window timings are optimistic.

## Shutdown

`Window.Dispose`, in order: wait for a running present and release retained GPU frames; detach accessibility
(`rv_host_detach_uia`); dispose the display feed, the window graph, the GPU surfaces and the presenter; dispose the
host; tear down SDL.

`WebCoreHost.Dispose`: stop the posted-work queue (queued callbacks are discarded); clear timers, microtasks and
frames; clear the frame callback; remove every event listener; release every live wrapper; then
`rv_host_destroy`.

Unmount the view before disposing the window. With hot reload the order is: unmount the tree, dispose the props,
dispose the window.

## Hot reload

`Ranvier.View.WebCore.Hmr.Dev.RunWith(argv, title, width, height, root, propsOf)` replaces the app's loop when
`dev` is among the arguments.

- The dev host owns the window and the page for the whole session. Reloads swap code underneath them.
- A watcher on `*.fs` feeds a background worker that compiles; the window thread remounts.
- Keep the view apart from the entry point, and keep what must survive a reload (documents, a GPU context, a
  constructed stylesheet) in an object passed through props.
- Restart after a type change, an edit to the entry point, or a new function in an earlier file.
- The package is not AOT compatible. Reference it from Debug builds only, and keep its call under `#if DEBUG`.

## Publishing

- **Pass a runtime identifier.** `dotnet publish` without `-r` carries the native engine of every platform. A
  project can default it:

  ```xml
  <PropertyGroup Condition="'$(_IsPublishing)' == 'true' and '$(RuntimeIdentifier)' == ''">
    <RuntimeIdentifier>$(NETCoreSdkRuntimeIdentifier)</RuntimeIdentifier>
    <SelfContained>false</SelfContained>
  </PropertyGroup>
  ```

- **Keep the native libraries and `WebKit.resources` beside the executable.** WebCore reads its resources from the
  folder of its own library. A build with a runtime identifier flattens native assets, and the native package's
  build target copies `WebKit.resources` back beside them.
- **NativeAOT works for the exercised paths.** The view backend and the SDL package are marked AOT compatible. A
  publish still reports FSharp.Core and view reflection, trimming and generic-recursion warnings. The WebCore
  libraries stay separate files.
- **To use the CPU flavor under the SDL package on Windows x64**, exclude the assets of
  `Ranvier.WebCore.Native.win-x64` and reference `Ranvier.WebCore.Native.Cpu.win-x64`.
- **To run against a local native build**, set `RanvierWebCoreNativeDir` to the folder that contains
  `runtimes/<rid>/native`. Passing the folder that holds the libraries themselves stages nothing.

## Caveats on record

- Both view packages are marked experimental.
- The view READMEs list Windows x64, Windows ARM64, Linux x64 and macOS arm64 (macOS 26). Linux ARM64 has native
  packages and is still being qualified in the view layer.
- Retina scale 2 and a real input method are manual checks.
- There is no macOS accessibility bridge.
- Drags out of the page have no view API yet.
- One GPU-presented unattended benchmark hung in a D3D11 present and could not be killed from user mode. Unattended
  runs of the dev host use `-software`.
