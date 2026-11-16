# How Ranvier.WebCore works

Ranvier.WebCore is WebKit's layout and rendering engine, WebCore, built as a library with a C interface in front of
it. An app links no browser. It creates a **host**, which is one page rendered offscreen, builds that page through
DOM calls, and gets pixels or a GPU texture back. This page explains the pieces and how they fit. The pages it
links to give the detail.

## What you get, and what you do not

| The engine does | The app does |
|---|---|
| Parse HTML, SVG and CSS | Own the window and its event loop |
| Style, layout, paint and compositing | Decide when a frame happens |
| Text shaping, fonts, images | Put the frame on screen |
| DOM, events, hit testing, focus, editing | Forward mouse, keyboard, touch and input method events |
| Animations and transitions | Supply the bytes of any image or font the page asks for |
| The accessibility tree | Run all application logic |

Three things a browser does are absent on purpose:

- **No page script.** JavaScriptCore is in the package because WebCore's types are built on it, but a host
  disallows entry into the virtual machine. A `<script>` does not run. The app changes the page through the ABI.
- **No network.** A load for any URL other than a `data:` URL, such as an image, a stylesheet or a font, goes to a
  callback the app installs. Without one the load fails.
- **No window.** The host never creates one. It paints into a buffer the app passes, or hands over a GPU frame.

## The layers

```text
 your app                     F#, C#, C, C++, Python: anything that can call C
 ───────────────────────────────────────────────────────────────────────────────
 Ranvier.View.WebCore.Sdl     window, input, presenting              (optional)
 Ranvier.View.WebCore         WebCoreHost: DOM contracts, timers     (optional)
 Ranvier.WebCore              P/Invoke declarations                  (.NET only)
 ───────────────────────────────────────────────────────────────────────────────
 RanvierWebCoreHost           the C ABI: rv_* functions
 WebCore                      DOM, style, layout, paint, compositing
 JavaScriptCore               the object model under WebCore; runs no script
 Skia or CoreGraphics         2D drawing; ANGLE and EGL in the GPU flavor
```

Everything below the second line is in one native package for one runtime. Everything above the first is managed
code from the `Ranvier.View` repository; a C or C++ app skips it and calls the ABI directly.

- [Hosting a page](HOSTING.md) is the order of ABI calls.
- [Hosting from .NET](MANAGED.md) is what the managed layers do with them.

## The host library

`RanvierWebCoreHost` is one shared library: `RanvierWebCoreHost.dll`, `libRanvierWebCoreHost.so` or
`libRanvierWebCoreHost.dylib`. It exports the whole ABI and links WebCore and JavaScriptCore, which sit beside it.

At ABI 71 it exports 365 hand-written functions (`RanvierWebCoreAbi.h`) and 3,254 generated ones
(`RanvierWebCoreDom.h`), counted as `^RV_EXPORT` lines on 2026-11-16.

| Part | Source | What it is |
|---|---|---|
| The hand-written ABI | `host/RanvierWebCoreAbi.h`, `.cpp` | Hosts, nodes, events, input, painting, GPU frames, accessibility, clipboard, observers, diagnostics. |
| The generated DOM functions | `host/RanvierWebCoreDom.h`, `.cpp`, `host/dom/` | One `rv_dom_*` function per IDL attribute and operation of the interfaces in `gen/dom.json` ([The generated DOM functions](GENERATOR.md)). |
| Glue compiled into WebCore | `host/Ranvier*Glue.cpp` | Code that needs members WebCore does not export. Patch 0012 compiles it into WebCore, and the host re-exports each function under its `rv_` name. |
| Platform frame handoff | `RanvierWebCoreD3D11.cpp`, `RanvierWebCoreEGL.cpp`, `RanvierMacGpuSpike.mm` | The shared texture, EGLImage and IOSurface paths. |
| Windows accessibility | `RanvierWebCoreUia.cpp` | The UI Automation bridge. |

Each page has two clients of its own inside the host:

- The **chrome client** turns WebCore's invalidations and rendering-update requests into the dirty rectangle and
  the frame callback.
- The **editor client** allows editing and binds keys to editing commands.

The host is built as a target inside WebKit's own build tree (`Tools/TestWebKitAPI`), from the WebKit commit pinned
in `pins.json` with the patch series in `patches/` applied.

## One host, one page, one thread

A host is created with a viewport size in CSS pixels, and `rv_host_load_html` gives it a document. From then on:

- Every call for that host is made on the thread that created it. Another thread gets `RV_ERR_WRONG_THREAD`.
- The app holds **handles**: a host, nodes, listeners, accessibility nodes, GPU frames. Each is released by the
  app. A node handle is a strong reference to the node.
- Strings cross as UTF-8 with an explicit byte count. Results are copied into buffers the caller owns.
- A call returns `RV_OK` or a negative `RV_ERR_*` status. Nothing throws across the boundary.

A process can hold several hosts. They share the process-wide parts of the engine, so a second host is much
cheaper than the first ([Memory](MEMORY.md#what-the-engine-holds)).

[The ABI in practice](ABI-GUIDE.md) covers these rules and each family of functions.

## A frame

Nothing in the engine runs unless the app calls it. One turn of an app's loop:

1. **Cycle the run loop** (`rv_run_loop_cycle`). WebCore's timers fire, queued work runs.
2. **Forward input** (`rv_host_mouse`, `rv_host_key` and the others). Events dispatch synchronously to the page's
   listeners, which are the app's own callbacks.
3. **Change the page** through DOM calls. Each change invalidates style, layout or paint, and the engine calls the
   app's frame callback once to say a frame is wanted.
4. **Update** (`rv_host_update`). Animations advance, observers fire, style and layout are brought up to date.
5. **Paint or present.** `rv_host_paint_rgba` fills the app's buffer, or the app acquires a composited GPU frame.

When nothing is wanted, the app sleeps. [Operating a host](OPERATION.md) goes through each step, and through
resize, focus, visibility, memory and teardown.

## Flavors and runtimes

A package is one flavor for one runtime.

- The **GPU** flavor is the default. It composites accelerated layers, paints them on the GPU, and hands the app a
  frame without reading pixels back.
- The **CPU** flavor has no GPU code and paints every frame on the CPU. Its pixels do not depend on the machine's
  GPU.
- Five runtimes: `win-x64`, `win-arm64`, `linux-x64`, `linux-arm64`, `osx-arm64`. Windows and Linux draw with
  Skia; macOS draws with CoreGraphics, so its pixels differ.

[Packages and flavors](PACKAGES.md) says what to reference. [Flavors and runtimes](FLAVORS.md) says what each one
contains and how a host behaves on it.

## Versions and compatibility

- The native packages, the managed package and the host agree on one **ABI version**, returned by
  `rv_abi_version()`. It increases with every change to the header a consumer must follow.
- A newer managed package can run against an older host by asking `rv_abi_has(name)` before using a group of
  functions.
- [Capability queries](CAPABILITIES.md) answer deeper questions: is a facility exported, implemented, enabled,
  permitted, available.
- A release is one version across every package, published together from one tag ([CI](CI.md#releasing)).

## Where to go next

| You want to | Read |
|---|---|
| add the packages to a project | [Packages and flavors](PACKAGES.md) |
| open a window from F# | [Hosting from .NET](MANAGED.md) |
| call the ABI from C or another language | [Hosting a page](HOSTING.md), then [The ABI in practice](ABI-GUIDE.md) |
| understand the frame loop and its costs | [Operating a host](OPERATION.md) |
| choose between CPU and GPU | [Flavors and runtimes](FLAVORS.md) |
| know what memory to expect | [Memory](MEMORY.md) |
| fix something that does not work | [Troubleshooting](TROUBLESHOOTING.md) |
| learn from two real apps | [Field notes](FIELD-NOTES.md) |
| change the engine or its build | [CI](CI.md), [The patch series](PATCHES.md), [Build settings](SETTINGS.md) |
