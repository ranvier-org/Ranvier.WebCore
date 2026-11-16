# Memory

What a host process holds, which part of it the engine owns, what an app can give back, and how to measure it.
Every figure on this page names what was run. Compare two figures only when they sit in the same table.

## Two numbers, two meanings

| Number | Windows name | What it counts | Who cares |
|---|---|---|---|
| Private commit | "Commit size", `PrivateUsage` | Memory the process has asked the system to back, touched or not. | The system's commit limit: a machine runs out of commit before it runs out of RAM. |
| Working set | "Memory" in Task Manager, `WorkingSetSize` | Pages resident in RAM right now. | What a user sees, and what other processes compete with. |

On Linux the nearest figures are virtual size and resident set size. Linux backs a mapping on first touch, so there
is no commit charge to pay for memory that is reserved and never used.

The two move apart. A change that stops committing untouched memory lowers commit and leaves working set where it
was, because the pages it saves were never resident.

## What the engine holds

Measured on Windows 11 x64 on 2026-11-16: a Python process loads `RanvierWebCoreHost.dll` from a slim `win-x64`
build of the patch series through 0086, before the kept paint surface, creates a 1280 by 800 host and paints a
page of 12,250 nodes on the CPU.

| After | Working set | Private commit |
|---|---|---|
| `rv_host_create` | 40.1 MB | 36.2 MB |
| the page is painted | 62.1 MB | 52.0 MB |
| a second host paints the same page | 74.7 MB | 64.3 MB |

The first host carries the process-wide cost: the libraries, the allocator's heaps, the font and style caches. A
second host adds about 12 MB in this run.

The same script against the `Ranvier.WebCore.Native.Cpu.win-x64` 0.1.1 package reported 68.8 MB of working set and
315.0 MB of commit with the page painted. The difference in commit is patch 0084, below.

Under WSL (Ubuntu, `linux-x64`, slim, the same day and page), resident memory was 114.8 MB after `rv_host_create`
and 142.4 MB with the page painted, from an unstripped library. See [Linux](#linux) for what that includes.

## What changed after 0.1.3

Three patches and one host change were merged on 2026-11-16. They are on `main` and ship with the release after
0.1.3. [The patch series](PATCHES.md) has the full account of each patch.

| Change | Applies to | Measured effect |
|---|---|---|
| Patch 0084: libpas commits its large reservations as they are used | `win-*` | Commit after `rv_host_create`: 314.2 MB to 36.4 MB. Working set unchanged. |
| Patch 0085: script bindings without interface objects | `win-*` | `WebCore.dll` 45.76 MB to 43.38 MB; 2.3 MB fewer of its pages resident. |
| Patch 0086: opaque pixels skip the unpremultiply division | every Skia runtime | A 1280 by 800 `rv_host_paint_rgba`: 3.96 ms to 2.68 ms. |
| The host keeps the surface of a whole-viewport paint | every runtime | The same paint: 2.38 ms to 1.69 ms; page faults per paint 1,003 to 0. |

Each row is its own benchmark, run before and after that change alone. The two paint rows cannot be added.

### Why commit was so high

libpas, WebKit's allocator, maps its memory in large blocks. On Windows it committed each block as it reserved it,
where on other systems the same call is a mapping the kernel backs on first touch. Four blocks cost commit a
process mostly never used: a 128 MB reservation, 32 MB per megapage, and 64 MB plus 20 MB of expendable memory.
With `USE_LIBPAS_LAZY_COMMIT` each is reserved, and committed as it is handed out.

What is left: JavaScriptCore's structure heap is a 16 MB megapage in memory a client reserved, and it is still
committed whole. It is most of what `rv_host_create` commits.

A commit that fails for want of memory now asserts, after ten retries of 50 ms. Upstream would have returned null
to a caller that can take it.

### Why interface objects cost memory

Each interface object's class record points at a symbol imported from `JavaScriptCore.dll`. The linker cannot
resolve that, so the compiler emits a function that fills the record in when `WebCore.dll` loads. There were 529
of them, a page apart through the bindings, so loading the library touched 2.64 MB of bindings code it never ran
again. The host runs no script, so nothing reads an interface object.

## The kept paint surface

`rv_host_paint_rgba` draws into a surface and converts it into the caller's buffer. The host keeps that surface
between paints of the whole viewport, so the next paint does not allocate and fault in a new one.

| | |
|---|---|
| Size | 4 bytes per device pixel: 4 MB at 1280 by 800, 16 MB at 2560 by 1600. |
| Kept when | the paint covers the whole viewport, and the size and device scale match the last one. |
| Not kept | by `rv_host_paint_rgba_rect` over part of the viewport. |
| Dropped | two to four seconds after the last whole-viewport paint, by a timer on the host. |
| Dropped at once | by `rv_release_memory`, for every host. |

The peak is what it was before: the surface always existed during the call. What changed is the two to four
seconds after the last paint.

The timer is a WebCore timer. It fires in `rv_run_loop_cycle` and in an app's own message loop alike, so an app
that pumps Windows messages itself and never calls `rv_run_loop_cycle` still gets the surface back.

Measured on Windows 11 x64 on 2026-11-16, slim `win-x64`, median of 40 `rv_host_paint_rgba` calls, the build
before the kept surface against the one with it, two alternating rounds:

| Frame | Before | After | Page faults per paint |
|---|---|---|---|
| 1280 by 800, 12,250 nodes | 2.38, 2.29 ms | 1.69, 1.70 ms | 1,003 to 0 |
| 1280 by 800, 980 nodes | 1.91, 1.97 ms | 1.32, 1.32 ms | 1,003 to 0 |
| 2560 by 1600, 980 nodes | 5.47, 5.43 ms | 3.13, 3.16 ms | 4,009 to 0 |

In a whole application frame the gain is small. `Ranvier.D5.Dashboards --native-probe` frames were 3 to 7%
shorter, which is inside that run's spread.

## Giving memory back

| Call | Does | Use when |
|---|---|---|
| `rv_release_memory()` | Releases WebCore's caches as under critical memory pressure, synchronously. Among them are each document's cached `querySelectorAll` results, which hold their elements. Drops every host's kept paint surface. | The window is hidden or minimised, or the system reports memory pressure. |
| `rv_collect_garbage()` | Runs a full JavaScriptCore collection, then returns free memory to the system. | After tearing down a large page, or before reading memory in a test. |
| `rv_collect_garbage_eden()` | Collects objects allocated since the last collection and keeps free memory. | A cheap collection between frames. |

All three run on the host thread and return when done. Caches refill on the next paint, so a release in a frame
loop costs time on every frame.

The host runs no script, so the collector's heap holds only what WebCore itself allocates there. The host sets
JavaScriptCore to one collector marker thread.

## Where an app's memory actually is

The engine is not the largest consumer in a GPU app. In `AstroShowcase` on the 0.1.1 GPU engine, with a working
set of about 470 MB (measured on Windows 11 x64 on 2026-11-16 by reading the process's large private blocks):

| Owner | Roughly |
|---|---|
| The engine's heap | 74 MB |
| The engine's code (`WebCore.dll`, `JavaScriptCore.dll`) | 22 MB |
| Two blocks of 64 MB holding 32-bit float data, attributed to wgpu's upload memory | 128 MB, resident six seconds after launch |
| The .NET heap, the GPU driver and the rest | the remainder |

Three .NET garbage collector settings left the soak's peak inside its normal swing of 440 to 560 MB. The upload
block size is not adjustable through the wgpu-native headers the packages pin.

So the same patches that removed 230 to 290 MB of commit from five example apps left their peak working set within
6%:

| Application and mode | Peak commit, 0.1.1 | Peak commit, `main` |
|---|---|---|
| AstroShowcase `--check` | 908.2 MB | 638.8 MB |
| AstroShowcase `--soak 20` | 1,140.9 MB | 907.4 MB |
| AstroShowcase `--bench` | 1,038.7 MB | 778.7 MB |
| Ranvier.D5.Dashboards `--native-probe` | 447.5 MB | 195.7 MB |
| Ranvier.D5.Dashboards `--capture` | 482.4 MB | 201.9 MB |
| Ranvier.D5.Gallery `--capture` | 332.2 MB | 89.8 MB |
| RanvierWgpuBim `--smoke` | 886.9 MB | 609.8 MB |
| RanvierWgpuAtlas `--smoke` | 920.7 MB | 677.4 MB |

Each app ran in an unattended mode that exits by itself, first with the 0.1.1 GPU engine its packages ship and then
with the GPU flavor of `main` copied over it. All eight runs exit 0 with both.

### Trimming the working set

An app can ask the system to trim its working set. Pages that are still needed fault back in; the rest stay out.
Measured on 2026-11-16 by emptying the working set from outside while each app kept running:

| App | Before | After |
|---|---|---|
| AstroShowcase `--soak` | 462 to 552 MB | 283 MB, 20 s later |
| Ranvier.D5.Dashboards `--native-probe` | 160 to 185 MB | 140 MB after 10 s, still rising |

The trim itself took about 2 ms of one frame in the AstroShowcase run. No package does this for the app today. A
host that wants it calls the system's own function (`SetProcessWorkingSetSize` on Windows) when its window is
hidden, alongside `rv_release_memory`.

## Linux

Measured under WSL on 2026-11-16, slim `linux-x64`:

- **One freed frame stays resident.** After any paint, the process keeps about one frame of pixels resident
  (16 MB at 2560 by 1600). Three builds gave 53.4, 53.2 and 53.5 MB of anonymous resident memory after a paint and
  `rv_collect_garbage`: without the kept surface, with it, and the 0.1.1 package. No call returns it. It is the allocator's
  behaviour, so resident memory cannot show the kept surface being given back there.
- **The GL driver stack is about 50 MB resident**, in the CPU flavor too. WebCore asserts that a shared display
  exists whenever something asks for one, and constructing the display initialises EGL, which loads the driver.
  Removing it needs a display that initialises EGL on first use, which is a change inside WebKit.

Neither was measured on a machine with a hardware GPU driver.

## Measuring

Read the process's own counters, from inside the process, after the caches a paint fills are full.

| System | Private commit | Resident |
|---|---|---|
| Windows | `PrivateUsage` from `K32GetProcessMemoryInfo` | `WorkingSetSize` from the same call |
| Linux | none | `RssAnon` in `/proc/self/status` for anonymous memory |

Rules that kept these measurements honest:

- **Warm up first.** Paint a few frames before taking a baseline. The first paint fills font and glyph caches.
- **Collect before reading.** Call `rv_collect_garbage` before each reading, so memory the engine has freed is back
  with the system.
- **Alternate.** Run before and after builds in alternating rounds. Two runs minutes apart on a busy machine differ
  by more than most changes.
- **Name the unit of work.** A paint call, a frame of one app and a whole run are three benchmarks.
- **Hide the window.** Run soak, benchmark and capture windows hidden.

`tests/abi/paint_surface_release.py` is a worked example: it reads private commit on Windows, asserts that a host
holds one surface while painting, and that it is given back when idle and on `rv_release_memory`.
`tests/libpas_commit` measures libpas alone, outside WebKit.

## Not covered

- macOS memory was not measured.
- No measurement here ran on Linux with a hardware GPU.
- Pixel hashes of one build changed once between two runs minutes apart, for a reason not found; text rendering
  settings are the suspect. Builds agree when run one after the other.
