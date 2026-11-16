# Field notes from the showcase apps

Two native apps were built on the published packages, and each recorded what it cost to get there. This page
collects what a host author can use. Each note says what happened, why, and what to do.

| App | What it is | What it exercised |
|---|---|---|
| AstroShowcase | 29 pages of astronautics models, each with a live 3D scene (wgpu, drawn into a `<canvas>` of the page) and charts. | Hot reload, hidden-window verification, soak runs, zoom, fonts, timers, publishing. |
| EditorShowcase | A text view that stays cheap on a 1,000,000-line file. | A frame loop that rests, virtual-list rendering, per-frame style cost, constructed stylesheets, benchmark method. |

Both ran on Windows 11 x64 with the GPU runtime, on `Ranvier.View.WebCore.Sdl` 0.2.0 over `Ranvier.WebCore` 0.1.3.

What neither covers: Linux and macOS were not run. Nothing was driven by a person's input in AstroShowcase.
EditorShowcase draws its own caret and has no selection, input method, clipboard or undo, so it says nothing about
the engine's editing. Every figure below was measured by the app's author on one machine, on 2026-11-15 or
2026-11-16, and the table that holds it names what was run. Compare figures within a table only.

## The engine and its host

### Generic font families were Times New Roman on Windows

- **What happened:** every generic family, an unset family and an unknown family rendered in Times New Roman, in
  HTML text and SVG text.
- **Why:** WebCore's defaults for the generic families are empty. The WebKit layer above WebCore sets them, and the
  host embeds WebCore without that layer. With no match, Skia's last resort on Windows is Times New Roman.
- **Fixed in 0.1.3:** the host maps `serif` to Times New Roman, `sans-serif` to Arial, `monospace` to Consolas,
  `cursive` to Comic Sans MS and `fantasy` to Impact.
- **Still open:** `system-ui` has no mapping on Windows, and an app cannot choose what `sans-serif` means.
- **Do:** name a real font first, for example `'Segoe UI','Noto Sans','DejaVu Sans',system-ui,sans-serif`. SVG
  marks that default to `sans-serif` need the rule too, or they are Arial beside Segoe UI.

### A zero-delay timer could arrive a clock tick late on Windows

- **What happened:** a zero-delay timer started while WebCore was firing timers, and a task queued behind it, could
  arrive up to about 16 ms late. `rv_run_loop_cycle(0)` returned without delivering it.
- **Why:** the Windows shared timer posts its message at once only when it is not already processing one.
  Otherwise it uses a system timer-queue timer, whose callback came 5.6 ms later in one trace and up to 16.3 ms
  later across runs.
- **Fixed in 0.1.3:** patch 0083. `rv_run_loop_cycle` fires due timers once at the start of each pass.
- **Know:** a timer due at the start of a pass now runs before the input and paint of that pass. The system timer
  stays armed for an app that pumps its own message loop and never calls `rv_run_loop_cycle`.

### Choosing the CPU runtime from a view app takes three references

- **Why:** `Ranvier.View.WebCore` depends on the GPU aggregate. Excluding only the aggregate leaves the GPU runtime
  package's files, and two packages then copy a `RanvierWebCoreHost.dll`.
- **Do:** exclude the assets of `Ranvier.WebCore.Native` and of `Ranvier.WebCore.Native.<rid>`, one line per
  runtime the app publishes for, and reference `Ranvier.WebCore.Native.Cpu`.
- **Is it worth it?** On an empty window the CPU runtime saved 7 to 12 MB of working set (see
  [the table](#memory-of-an-empty-window)). It is the choice for machine-independent pixels, not for memory.

## The frame loop

### A frame loop that rests

- **What happened:** EditorShowcase idled at 1.22 ms of CPU per 1/120 s, about 15% of one core, with no input.
- **Why:** its frame callback requested the next frame every time. While a frame is requested, each turn of
  `Window.Step` runs the frame and presents, and the GPU path composites and submits without a damage check. The
  host already rests; the app kept it awake. AstroShowcase uses the same always-on pattern.
- **Do:** request a frame when something changes, on a timer for things like a caret blink, and while an animation
  runs. A frame that leaves nothing moving requests no other.

  ```fsharp
  let mutable armed = false
  let rec tick (_: float) =
      armed <- false
      let moved = frame ()               // true when the frame wrote something
      if moved || animating () then wake ()
  and wake () =
      if not armed then
          armed <- true
          host.RequestAnimationFrame tick |> ignore
  ```

- **Result:** idle fell to 0.10 ms per 1/120 s in one run and 0.23 in a later one.
- **Also:** keep the loop running briefly after the last write. Frames that follow each other cost less than
  frames that each wake the thread. A 150 ms run-on took a scroll event from 5.10 and 5.18 ms to 4.74 and 4.90 ms
  in four alternating runs.

A simulation that advances continuously has a reason to request every frame. A page that is waiting for input does
not.

### Write signals from a frame callback inside the graph

- **What happened:** a signal written from an animation-frame callback outside the graph did nothing visible.
  Under the hot reload host the clock froze.
- **Why:** the callback's exception was stored where nothing read it, and the dev host's graph was not the
  window's.
- **Fixed in `Ranvier.View.WebCore` 0.1.2:** the write takes effect or is reported, and an exception in a frame
  callback or binding is printed once with its stack.
- **Do:** take `Graph.Current` in `setup` and wrap each write: `graph.Run(fun () -> time.Value <- time.Peek + dt)`.

### Order the work inside a frame

EditorShowcase's frame, in order:

1. Read layout (`clientHeight`, `getBoundingClientRect`) before any write, so the read finds layout clean.
2. Write every signal the frame changes in one batch, inside `graph.Run`.
3. Write per-frame element properties such as `scrollTop` directly.
4. Append the frame's stylesheet rules, once.

Input handlers change plain fields and mark the view stale. Only the frame writes signals. AstroShowcase draws its
3D view once a frame however many signals changed: one effect reads every input and sets a `stale` flag.

## What makes a frame expensive

Each figure is EditorShowcase's `--bench`: a hidden 1280 by 800 window that no display paces, the 1,000,000-line
file, 240 timed frames after 30 untimed. "App" is a stopwatch around the app's frame; "turn" is one around
`Window.Step(timeout = 0)` after it.

### Element count, even when the elements are empty

| A row of text is | Scroll 3 lines a frame, app plus turn | Type one character a frame |
|---|---|---|
| 24 span slots (1,225 spans on the page) | 3.73 ms | 2.54 ms |
| one string of markup | 1.42 ms | 1.12 ms |

Engine time grew with the number of elements on the page, including empty and unchanged ones. Which engine step
scales was not traced. A fixed pool of empty slots is costly; build a row as one markup string.

### A custom property that changes every frame on a container

- **What happened:** a Ranvier.Css reader value on a container, changing every frame and drawing nothing, added
  3.3 ms a frame with 1,270 elements under it.
- **Why:** a reader compiles to `property: var(--r-...)` and writes a custom property on the element. An
  unregistered custom property inherits, so changing one restyles the subtree. (That the time is style resolution
  is inferred; no trace split it.)
- **Do:** write a per-frame value straight to its element, or register the property as non-inherited:

  ```css
  @property --r-offset { syntax: "*"; inherits: false; }
  ```

  The engine honours the rule. A registered reader no longer reaches a `descendant` or pseudo-element block.

| How the sheet moves (scroll 3 lines a frame) | App | Turn | Sum |
|---|---|---|---|
| the viewport's `scrollTop` | 0.98 ms | 2.76 ms | 3.74 ms |
| `transform: translateY(...)` set with `style.setProperty` | 0.31 ms | 3.25 ms | 3.55 ms |
| `scrollTop`, plus a reader on the sheet that changes every frame | 3.67 ms | 3.38 ms | 7.04 ms |

### Any change to an adopted stylesheet

Measured in a scratch project on the same packages: a stopwatch around one stylesheet change and one forced
`clientWidth` read, mean of 40 rounds, on a page of 1,308 elements.

| Change | Time |
|---|---|
| `<style>` element, whole text written again | 3.24 to 3.25 ms |
| `replaceSync` of the whole text | 3.22 to 3.56 ms |
| one `insertRule` | 2.92 to 2.99 ms |
| no stylesheet change | 0.16 to 0.18 ms |

`insertRule` is no fast path. Put the stylesheet changes of a frame in together, and have every rule in place
before the first mount where possible.

### Scrolling an element

- Writing `scrollTop` forces a layout inside the app's frame: app time rose from 0.4 ms to 1.3 ms.
- Patch 0075's scroll fast path covers the page's viewport, not a scrolling element.
- A transform written directly to the element costs the same as `scrollTop` (the table above).
- `will-change: transform` made no difference to the benchmark.
- Which mechanism moves pixels and which repaints is not established. The repaint of a scrolled element is inferred
  from WebCore's source, not measured.

### A virtual list that works

`Ranvier.View` has `forEachFixed` and no virtual-list primitive. The recipe EditorShowcase ended on:

- a fixed pool of the visible rows plus six each side;
- a line tied to slot `line mod pool`, so a line keeps its element while it is on screen;
- one component instance per row, so a write re-reads that row's bindings only;
- rows absolutely placed on a 36,000 px sheet with `contain: strict` and a fixed height;
- the scroll anchor rebased every 700 lines, so offsets stay small;
- whole-pixel scroll offsets, to keep glyphs on the pixel grid.

With recycling on, a 3-line scroll writes 3.2 rows a frame and costs 0.71 ms of app time. With it off, 49 rows and
3.49 ms.

## Styles on a native target

- **Constructed stylesheets work through the ABI.** `StyleSheets.forHost`, `replaceSync`, `insertRule`,
  `deleteRule` and document adoption worked on the first attempt, `@property` included. Moving from a `<style>`
  element to a constructed sheet changed no workload by more than the spread between runs.
- **Typed CSS needs its rules delivered.** `styles { ... }` in Ranvier.Css.View 0.1.1 computes the rules and keeps
  the class name. A native app extracts them at build time with `Ranvier.Css.Compile` into a file it loads
  (AstroShowcase), or records them from a copy of the builder (EditorShowcase).
- **Check it.** Both apps fail a scripted run when a class on the page has no rule in the engine's sheet. A clean
  build says nothing about CSS.
- **Before copying a build step from a sample, ask what it is for on this target.** EditorShowcase's first version
  extracted a CSS file because the reference sample did. The rules were already in memory.

## Zoom and density

- **The window has a zoom.** `Window.Create(..., zoom = z)`, a settable `window.Zoom`, and `window.DeviceScale`,
  from `Ranvier.View.WebCore.Sdl` 0.2.0. The zoom multiplies the display's scale: at a zoom of 2 a 3840 by 2160
  window holds a page of 1920 by 1080 CSS pixels.
- **Open the window at the zoom it will hold**, so the first frame is laid out at its final scale.
- **Observed:** with the window's zoom in place of CSS `zoom`, at 3840 by 2160 the page sat one device pixel lower.
  The cause was not looked for.
- **Upgrade Sdl and Hmr together.** An optional parameter added to `Window.Create` changes its compiled signature,
  and an assembly built against the old one fails with `MissingMethodException`.
- **Not verified:** a real 4K panel, and 150 to 200% display scaling. 4K was tested in a hidden window only.

## A GPU scene inside the page

AstroShowcase draws its 3D view with `Ranvier.Wgpu` into a canvas bound with `WgpuSdlSurface.bind`.

- **A clean build says nothing about the shader.** WGSL compiles when the context is created. A reserved word got
  through a clean build. `WgpuContext.ValidateWgsl` compiles it without a window; the app runs it as a build step.
- **A draw the GPU rejects is one line on standard error**, starting `[Ranvier.Wgpu Error`. Watch for it and stop.
  A run that carried on once produced 22 of them before anything else failed.
- **Each 3D draw cost about 1.8 to 2.6 ms of CPU** whatever the resolution or graphics level. This, not the GPU,
  set the frame time. Not profiled.
- **`FrameMetrics.GpuRenderMs` is wall time that includes waiting for the GPU**, not time on the GPU.
- **Keep the GPU context in the props** the dev host builds once a window, so a reload does not recreate it.

## Hot reload

- **Start:** `dotnet run -- dev` in a Debug build. Edits to the page files and the view file apply on save.
- **Publish pages through a registry that lives for the process**, so a page published by a reload reaches the
  running view. The view compares the registry's version in its frame callback.
- **Restart the host** after a type change, an edit to the entry point, or a new function in an earlier file used
  from a later one.
- **A reload runs `setup` again.** Detect it by state already present in the session object, and reuse the style
  element or sheet.
- **A utility edited under the host gets a new class name** the extracted stylesheet does not hold. AstroShowcase
  extracts again in the background and swaps the text in; the element is unstyled for about 13 s.
- **Debug builds need SDK 10.0.404** while `Ranvier.View.WebCore.Hmr` 0.1.2 asks for `FSharp.Core` 10.1.403. A
  Release build, without Hmr, builds on any .NET 10 SDK.
- **Not verified:** neither app ran `dotnet run -- dev` on the current packages.

## Packaging

### Output size

AstroShowcase on the current packages, sum of file sizes, 2026-11-16:

| Command | Size | Files |
|---|---|---|
| `dotnet build -c Release`, no runtime identifier | 599.6 MiB | 109 |
| `dotnet publish -c Release -r win-x64 --self-contained false` | 121.5 MiB | 60 |
| `dotnet publish -c Release -r win-x64 --self-contained true` | 198.2 MiB | 247 |

Without a runtime identifier the output carries native binaries for 14 platforms, five of them with the engine.
[Hosting from .NET](MANAGED.md#publishing) has the project setting that defaults it for `dotnet publish`.

### FSharp.Core floors

Each package declares a minimum `FSharp.Core`. An SDK that ships less gives `NU1605`. On SDK 10.0.1xx that is more
than a warning: a library compiled against 10.1.x references an assembly version that fails to load there. Use
`Update`, not `Include`, for an explicit `FSharp.Core` reference.

## Measuring

Most of both reports is about measurements that turned out wrong. The rules that came out of them:

| Mistake | What it produced | Rule |
|---|---|---|
| A benchmark forced a second draw per loop | A "9.2 ms to 5.8 ms" improvement that was not like for like | Time one thing. Fail a timed span that did not draw exactly once. |
| After a draw-once change, the timed turn drew nothing | 0.18 ms "frames" | The same check. |
| Timing a whole `Window.Step` in a shown window | App work mixed with waiting and presenting | Put the stopwatch around the app's own work. |
| Unpaced hidden-window timing | 5.3 ms a frame, against 8 to 9 ms timer-paced | Say beside the figure that it is unpaced. Prefer a visible, display-paced run for a claim. |
| Hidden timer-paced launches | 4.7 and 8.2 ms for the same scroll in two launches; three visible launches agreed at 6.4 to 6.9 | Not diagnosed; the machine has two GPUs. Record the adapter. |
| Reporting a frame rate from a hidden window | A rate of the loop, not the app | A hidden window is not paced by the display. Print no rate. |
| Visible soak and benchmark windows | Closed by hand mid-run, twice | Hide them, and check in the run that the window is still hidden. |
| An unknown argument was ignored | A "Basic" run that was not at Basic | An unknown argument is an error. |
| Carrying on after an error line | 22 shader errors before a failure | Stop on the first. |
| A 40-cycle soak | The start of the run, where caches fill | Run long, and fit the slope over the second half. |
| Reading working set in a soak | It falls: Windows trims a background process | Read the managed heap and private bytes. |
| A wall-clock budget inside a model | Captures that differ between runs of one build | Advance by a fixed step in checks. |
| A shader on a stopwatch | Two runs differing by up to 44% of the 3D view | A clock the run sets. |
| Comparing with other toolkits from general knowledge | A claim with no measurement | Measure it or leave it out. |

Before trusting a number: save a picture of what the workload drew and look at it. A time shows that something is
slow, not what. Name a cause only after an experiment that isolates it.

The hidden-window API is what made the checks possible: `Window.Create(hidden = true)`, `Step`, `graph.Run`,
`Present` and `ReadPixels` are enough for a screenshot mode, a soak, a benchmark and a display-paced mode.

### Memory of an empty window

A console project referencing only `Ranvier.View.WebCore.Sdl` 0.1.1, published for `win-x64`: a hidden 1280 by 800
window on an empty document, 120 frames, present, read pixels back, collect garbage. Three runs each, 2026-11-15.

| Runtime | Working set | Private memory | Managed heap | Publish size |
|---|---|---|---|---|
| GPU | 127.3 to 132.2 MiB | 382.2 to 414.9 MiB | 4.2 MiB | 101.5 MiB |
| CPU | 120.2 to 120.3 MiB | 353.4 to 385.9 MiB | 8.1 MiB | 92.7 MiB |

The window was hidden, so a visible window's swap chain is not counted. Private memory varied by about 30 MiB
between identical runs. These runs predate lazy commit ([Memory](MEMORY.md)).

### A 10,000-cycle soak

`AstroShowcase --soak 10000 --samples 100`, Release, hidden window. A cycle visits each of the 29 pages for four
frames. 101 samples, each after two forced collections. 16,674 s in all.

| Series | Slope per cycle over the second half | First, last |
|---|---|---|
| Managed heap | +0.157 bytes (standard error 1.862) | 38,958,648; 40,124,152 bytes |
| Private bytes | -1,009 bytes (standard error 2,493) | 1,094 MB; 1,341 MB |
| Handles | 0.000 | 1,249; 1,276 |
| DOM nodes | 0.000 | 485 at every sample |

The managed heap is flat. Private bytes move by tens of megabytes between neighbouring samples, so the run cannot
rule out native growth below about 5 kB a cycle. GPU memory was not measured.

### Three editors

`verification/editors/bench.ps1`: real wheel and key events at 120 a second, 600 events a workload, three runs with
the median shown, visible 1280 by 800 windows, a 20,000-line file. CPU is process time over the editor's process
tree, divided by the events. 2026-11-16.

| | EditorShowcase | VS Code 1.146.0, trimmed | Zed 1.26.2, trimmed |
|---|---|---|---|
| Scroll, CPU ms a line | 1.28 | 2.84 | 1.08 |
| Type, CPU ms an event | 2.71 | 11.09 | 5.23 |
| Idle, CPU ms per 1/120 s | 0.23 | 0.13 | 0.23 |
| Private memory after the run | 500 MiB | 1,356 MiB | 166 MiB |

Caveats the app attaches: Zed drew the file without syntax colours; the text areas differ in width; GPU time and
input-to-frame latency were not measured; what the 500 MiB holds was not verified.

## Open in the toolkit

Found by the apps and not yet addressed in a released package:

| Finding | Where |
|---|---|
| Reader variables inherit; there is no `@property` registration | Ranvier.Css 0.1.1 |
| `styles { ... }` keeps the class name only | Ranvier.Css.View 0.1.1 |
| No virtual-list primitive or recipe | Ranvier.View |
| No helper for a frame loop that rests | Ranvier.View.WebCore |
| The GPU present path composites and presents with no damage check | Ranvier.View.WebCore.Sdl 0.2.0 |
| The 50 ms idle cap of `Step` is not configurable | Ranvier.View.WebCore.Sdl |
| An element's scroll does not use the patch 0075 fast path | Ranvier.WebCore |
| No per-frame counters for painted pixels, styled elements or composited layers | Ranvier.WebCore |
| `system-ui` unmapped on Windows | Ranvier.WebCore |
| A view app cannot cleanly choose the CPU runtime | Ranvier.View.WebCore |
| The hot reload host's window cannot be hidden by the app | Ranvier.View.WebCore.Hmr |
