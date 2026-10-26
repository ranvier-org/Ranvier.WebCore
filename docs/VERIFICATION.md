# Verification of this repository's first build

Run on 2026-10-26 on the Windows workstation that produced Ranvier's gate 43 (24 threads, MSVC
14.50.35717, LLVM 23.1.4), in a fresh work directory, `C:/rwv`. To skip downloads, the run took WebKit
from the local clone (`--webkit-repo`) and used the local vcpkg checkout, which is at `pins.json`'s
commit, and the local LLVM (`--vcpkg`, `--llvm`, `--tool-path`).

| Step | Result |
|---|---|
| `fetch` | Shallow checkout of `b95c91b1` |
| `prepare` | All ten patches applied; host installed |
| `configure` | vcpkg built 19 of 23 packages (6.3 min), 4 came from the binary cache; CMake 470 s |
| `build` | `RanvierWebCoreHost` linked; ICU filter: 4,203 items, 113 kept, `icudt77.dll` 7,195,136 bytes |
| `package` | 18 DLLs plus 6 icons, 77.59 MB; `Ranvier.WebCore.Native.win-x64.0.1.0-preview.1.nupkg`, 30.4 MB |

**Against gate 43's slim build:** every DLL has the same size except `JavaScriptCore.dll`, 15,796,224
bytes against 15,795,712. The 512 bytes were not investigated; a different source path in assertion
strings is the likely cause (E).

**A consumer project** (`net10.0`, a `PackageReference` from the local package folder) puts
`WebKit.resources/icons` beside `WebCore.dll` in a RID-less build (under `runtimes/win-x64/native`), a
`-r win-x64` build and a `-r win-x64` publish.

**Ranvier's F# driver**, loading the DLLs only from that publish output, passes both checks
(`RANVIER_FSHARP_ABI`, `RANVIER_FSHARP_RESOURCES`), and its six frames are byte-identical to gate 43's.
Before the icons were packaged, the frame of a page with unserved resources differed (609 bytes): the
broken-image icon was missing.

## Not verified

- The GitHub Actions workflow has not run. Unchecked: the hosted image's Visual Studio version, disk
  space and time, `choco install gperf`, the LLVM download and extraction in `fetch`, and the publish job.
- `pins.json` has no SHA-256 for the LLVM archive yet; `fetch` prints it, for pinning after a first run.
- The lean flavor through `build.py`.
- Ranvier's full conformance run and the timing benchmark against the packaged DLLs.
- The licensing in `NOTICE.md`.
