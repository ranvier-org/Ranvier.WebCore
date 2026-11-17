# Documentation

Ranvier.WebCore is WebKit's WebCore behind a C ABI: an app creates a host, builds a page through DOM calls and gets
pixels or a GPU texture back. Start with [How Ranvier.WebCore works](OVERVIEW.md).

## Start here

| Guide | Read it to |
|---|---|
| [How Ranvier.WebCore works](OVERVIEW.md) | See the layers, what the engine does and what the app does, and where each topic is covered. |
| [Packages and flavors](PACKAGES.md) | Choose and reference packages per runtime: Slim, GPU, Lean, the managed interop and the AT-SPI provider. |
| [Flavors and runtimes](FLAVORS.md) | Know what each flavor contains, what each platform's port decides, and how a host behaves on each. |

## Hosting a page

| Guide | Read it to |
|---|---|
| [Hosting a page](HOSTING.md) | Create a host, run the frame loop, present CPU or GPU frames, tear down. |
| [Operating a host](OPERATION.md) | Understand each step of the loop and run a host well: input, resize, focus, resources, idle, teardown. |
| [Hosting from .NET](MANAGED.md) | Use the `Ranvier.View` packages: what they call, what they wire and what they leave to the app. |
| [Memory](MEMORY.md) | Know what a host holds, what an app can give back, and how to measure it. |
| [Troubleshooting](TROUBLESHOOTING.md) | Find the cause of a symptom. |
| [Field notes](FIELD-NOTES.md) | Learn from two apps built on the packages: costs, pitfalls and measuring. |

## The C ABI and its features

| Guide | Read it to |
|---|---|
| [The C ABI and header](ABI.md) | Find the headers, the ABI version, `rv_abi_has` feature detection and the managed bindings. |
| [The ABI in practice](ABI-GUIDE.md) | Learn the rules every call follows, tour the function families and avoid the usual mistakes. |
| [Accessibility](ACCESSIBILITY.md) | Read the accessibility tree, events, actions and text; Windows UI Automation. |
| [AT-SPI provider](../providers/atspi/README.md) | Add Linux screen-reader support. |
| [Clipboard and drag and drop](CLIPBOARD-DND.md) | Choose App, Native or DOM styles. |
| [Animations](ANIMATIONS.md) | Use Web Animations, document, scroll and view timelines. |
| [Mutation observation](MUTATION-OBSERVATION.md) | Observe DOM mutations from native code. |
| [PDF output](PRINTING.md) | Render a page to PDF. |
| [Diagnostics](DIAGNOSTICS.md) | Inspect a page, read host errors, trace host phases. |
| [Capability queries](CAPABILITIES.md) | Ask what the loaded host exports, implements and enables. |
| [Windows playback adapter](../examples/NativeMedia/README.md), [spelling adapter](../examples/NativeSpelling/README.md) | Application-side examples. |

## Maintaining the repository

| Guide | Covers |
|---|---|
| [CI](CI.md) | Workflows, jobs, caches, probes, releasing, per-runtime notes. |
| [Patches](PATCHES.md) | The patch series applied over WebKit. |
| [Build settings](SETTINGS.md) | CMake settings per flavor. |
| [Updating WebKit](UPDATING.md) | Moving the WebKit pin. |
| [DOM generator](GENERATOR.md) | `gen/domgen.py`, its inputs, outputs and scope. |
| [Burn harness](BURN-HARNESS.md) | Bounded, CPU-pinned Windows load runs. |
| [Handover](HANDOVER.md) | Released state, open issues, the Cocoa replay procedure. |
| [Footguns](FOOTGUNS.md) | Pitfalls with their remedies. |

## Repository layout

| Path | Contents |
|---|---|
| `pins.json` | Every external version: WebKit, vcpkg, LLVM, ICU and the package version. |
| `patches/` | The WebKit patch series, applied in `series` order. |
| `host/` | The C ABI (`RanvierWebCoreAbi.h`, `.cpp`), the generated DOM functions and the CMake target added to `Tools/TestWebKitAPI` ([host/README.md](../host/README.md)). |
| `gen/` | The DOM generator and its inputs. |
| `config/` | CMake settings per flavor. |
| `scripts/` | `build.py` (fetch, prepare, configure, build, package), `patches.py`, `smoke.py`, `probes.py`, `release.py`. |
| `packaging/` | The projects `dotnet pack` turns staged files into packages. |
| `src/Ranvier.WebCore/` | The managed interop project. |
| `providers/atspi/` | The optional AT-SPI provider. |
| `tests/` | ABI, generator, packaging, GPU, UIA and AT-SPI tests. |

Rules for changes: one concern per patch; feature-removal options default to OFF; upstream C++ corrections stay
bounded and are paired with permanent regressions in `tests/abi`; member lists that follow a header are generated
from it.
