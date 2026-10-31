# CI

`.github/workflows/build.yml` runs `scripts/build.py` step by step for each runtime in its matrix, then
uploads the `.nupkg` with `manifest.json`, and the PDBs as a separate artifact. On a `v*` tag it sets the
package version from the tag and, when the repository variable `NUGET_USER` is set, pushes the packages
to nuget.org by trusted publishing: no API key is stored. The nuget.org account `NUGET_USER` needs a
trusted publishing policy for owner `ranvier-org`, repository `Ranvier.WebCore`, workflow file `build.yml`
and no environment.

A pull request builds `win-x64` only. A pull request from a `codex/batch-*` branch, or one labelled
`full-matrix`, builds every runtime; adding the label starts that run. Pushes to `main` and `v*` tags always
build every runtime.

## Runner

| Need | Value | Note |
|---|---|---|
| Image | `windows-2025` by default; repository variable `RANVIER_WINDOWS_RUNNER` overrides | |
| Visual Studio | x64 C++ build tools, found with `vswhere` | Measured with MSVC 14.50.35717 (VS 18) locally. `windows-2025` had 14.51.36231 on 2026-10-26, and its package passed the F# driver (`docs/VERIFICATION.md`). An older toolset is untested. |
| Disk | about 12 GB (E): source 3.3 GB, build 5.0 GB, vcpkg packages and LLVM | |
| Time | 6-hour job limit | Locally, 20 jobs on 24 threads: vcpkg about 6 minutes, a full compile about 9 minutes. On `windows-2025` on 2026-10-26, with empty caches: the job took 1 h 41 min, of which fetch 11 min, configure (vcpkg) 20 min and the compile 65 min. |
| Tools | Python 3.12+, Perl, Ruby, gperf, CMake, Ninja, .NET SDK | The hosted Windows image has Perl, Ruby, CMake and .NET; Ninja comes with Visual Studio's CMake; the workflow installs Python and gperf. |

## Caches

Each downloaded dependency has its own cache entry. The workflow restores it before the step that needs it
and saves it right after the step that fetched it, so a failure later in the job keeps it, and an outage
at a package host matters only on a miss. A step that downloads retries a failure: `build.py`'s
downloads, git fetches and vcpkg bootstrap four times with a growing pause, Chocolatey four times, each
Homebrew install four times, and apt's `Acquire::Retries=5`.

| Entry | Key | Saved after |
|---|---|---|
| gperf (Windows, from Chocolatey) | its version and the RID: a cache entry holds paths relative to the workspace, whose drive differs between the x64 and ARM64 images | its install |
| LLVM (Windows) | the RID's archive hash in `pins.json` | fetch |
| vcpkg binary archives and downloads (Windows) | the RID, the flavor, the vcpkg, WebKit and ICU pins, and `config/` | a successful configure |

- A vcpkg miss restores the newest entry of the RID and flavor: archives are named by their ABI hash, so
  the packages that did not change are not rebuilt. ICU's source archive comes from vcpkg's downloads;
  after a binary cache hit skipped vcpkg's download, `build.py` downloads it there itself for the ICU
  filter, checking `pins.json`'s hash.
- Not cached: the WebKit checkout (about 2 GB from GitHub, with retries), vcpkg's own checkout, and the
  Linux and macOS packages. The repository's Actions cache holds 10 GB, and on 2026-10-27 it held
  9.4 GB, most of it LLVM entries under the old keys that GitHub evicts as they go unused.
- The WebKit build itself is not cached. A compiler cache (sccache with clang-cl) is the next step if
  build time matters.

## Local runs

The same steps run on a workstation, ending with the same check CI runs:

- `scripts/smoke.py` checks that the staged files match the manifest, and that the host loads from them and
  paints a page.
- On Windows and macOS, `scripts/abi_tests.py` then runs the F# ABI tests in `tests/abi` against the staged
  files. They need the .NET 10 SDK, and the WebKit checkout for a test font.

```
python -I scripts/build.py all --work C:/rw
```

Options point at existing checkouts and tools instead of fetching them: `--source`, `--vcpkg`, `--llvm`,
and `--tool-path` (repeatable, or `RANVIER_TOOL_PATH` separated as `PATH` is) for Perl, Ruby, gperf and
Python. `RANVIER_WORK` sets `--work`. `--flavor lean` builds the reference flavor into `<work>/build-lean`
and packs it as `Ranvier.WebCore.Native.Lean.<rid>`. A 24-thread workstation compiles WebKit in about
9 minutes, against 65 on `windows-2025`.

### Releasing from a workstation

A release can take some packages from the owner's machine and build the rest in CI:

```
python -I scripts/release.py --rid win-x64 --work C:/rw
```

`release.py` refuses a working tree with changes, a commit that is on no remote branch, and a version
(`pins.json` `package.version`) whose tag exists. It builds each `--rid` with `build.py --strict`, whose
prepare step fails when the WebKit checkout has edits the patch series does not make (`patches.py verify`).
It checks the packed `.nupkg` with `smoke.py` against the commit, version and flavor, then creates the
GitHub release `v<version>` with `gh`, attaching the packages. `--dry-run` stops before the release.
Options it does not know go to `build.py`.

Creating the release pushes its tag, and the tag's run of this workflow:

- `plan` reads the release. A runtime whose package is attached goes to `prebuilt` instead of `native`, if
  the repository owner created the release and uploaded that package. Anyone who can push a tag could
  otherwise get a package of their own published.
- `prebuilt` downloads the package on a clean runner of its platform and runs `smoke.py` on it. The
  manifest must name the tag's commit, from a clean tree, and the tag's version. Loading on clean
  runners also catches a library the package lacks that the workstation happened to have.
- `native` builds the other runtimes as usual. `publish` requires every selected runtime and the
  package-contract gate to pass before pushing any package. A full slim release also requires the paired
  managed interop and aggregate packages; a manual slim subset can build artifacts but cannot publish a
  partial cohort. Explicit GPU and lean runs retain their selected-runtime gate without rebuilding the
  managed cohort.

A tag pushed without a release builds every runtime in CI, as before. A package built on a workstation
records `"builder": "local"` in the `source` field of its `manifest.json`; CI's record `"ci"`.

#### Coordinated Windows GPU package

`release.py --flavor gpu` builds and checks `Ranvier.WebCore.Native.Gpu.<rid>`; `slim`, `gpu` and `lean`
retain the same clean-source, remote-commit and immutable-version-tag checks. Creating a release always
starts the default **slim** tag run. That run validates/publishes the five slim runtimes, managed interop
and native aggregate; it does not select GPU assets. A GPU release therefore needs a subsequent dispatch
on the **same immutable tag**, after the slim tag run succeeds:

```
gh workflow run build.yml --repo ranvier-org/Ranvier.WebCore --ref v0.1.0-preview.7 --field flavor=gpu --field rids=win-x64
```

The dispatch builds or checks the GPU package against that tag's commit, flavor and version and publishes
`Ranvier.WebCore.Native.Gpu.win-x64` through the existing NuGet OIDC job. The owner's attached-package
check remains in effect; an asset that does not qualify is rebuilt in CI. Do not overlap the two runs:
their concurrency group is keyed by the tag, so the later dispatch would cancel a running slim release.
The managed interop version must remain `0.1.0-preview.7`; choosing the GPU runtime does not change its ABI.

After the GPU version is available from the public v3 feed, run the Views workflow at a ref containing its
strict GPU lane and the matching backend. This example uses the coordinated preview version:

```
gh workflow run ci.yml --repo ranvier-org/Ranvier.View --ref <validated-view-ref> --field gpu_runtime_version=0.1.0-preview.7 --field gpu_runtime_source=https://api.nuget.org/v3/index.json --field gpu_runtime_package=Ranvier.WebCore.Native.Gpu.win-x64
```

The `webcore-gpu` lane verifies the exact package identity, version, flavor and staged hashes, then runs
the counter with JIT and NativeAOT. Its GPU counts, visible SDL backbuffer and independent OS UIA checks
must succeed without CPU fallback before the accelerated release is complete.

An incremental rebuild after vcpkg reinstalls packages can fail with clang rejecting a precompiled header:
the reinstalled headers keep older modification times. Delete `cmake_pch.cxx.obj` under
`<build>/Source` and build again. A fresh build, as in CI, does not hit this.

## win-arm64

Built natively on the `windows-11-arm` runner (Visual Studio 18 with the ARM64 C++ tools, MSVC 14.51.36231
on 2026-10-26; Perl, Ruby, CMake and .NET come with the image) with LLVM's `aarch64-pc-windows-msvc`
release and WebKit's `arm64-windows-webkit` triplet. Two differences from `win-x64`:

- `build.py configure` sets `_LINK_=/BASE:0x180000000` and `VCPKG_KEEP_ENV_VARS=_LINK_`: the ICU port of
  WebKit's registry links its DLLs with bases below 4 GB, which `link.exe` rejects for ARM64 (LNK1355).
- `icu_data.py --machine ARM64` links the filtered ICU data DLL for ARM64.

On 2026-10-26, with empty caches, the job took 1 h 3 min: fetch 4 min, configure (vcpkg) 16 min and the
compile 38 min. The slim package holds 18 DLLs, every one `IMAGE_FILE_MACHINE_ARM64`, 74.73 MB against
`win-x64`'s 77.59 MB. Nobody has loaded these DLLs on an ARM64 machine yet: the package is unverified at
runtime.

## macOS (osx-arm64)

`osx-arm64` builds WebKit's Cocoa port (`PORT=Mac`, `config/mac.cmake`) with Xcode's AppleClang and Swift,
and packs `Ranvier.WebCore.Native.osx-arm64`. It draws with CoreGraphics and CoreText, so its pixels do not
match the Skia ports'.

| Need | Value | Note |
|---|---|---|
| Image | `macos-26` (arm64, standard runner) | `macos-15`'s newest Xcode, 26.3 with the macOS 26.2 SDK, cannot build the pin: PAL's Swift module fails on a module cycle (`_DarwinFoundation3` and `CxxStdlib`), and its Swift and clang warn that they do not know some of the warning flags WebKit passes. Measured 2026-10-26, run 40372523818. |
| Xcode | the newest released Xcode 26 on the image, chosen with `xcode-select` | 26.6 with the macOS 26.5 SDK and Apple clang 21.0.0 on 2026-10-26. `config/mac.cmake` sets the deployment target to macOS 26.0; WebKit's default is the build machine's version. Targeting 15.0 compiles but needs Swift's `libswiftCompatibilitySpan.dylib`, which the package does not carry. |
| Disk | 4.2 GB used: source 1.7 GB, build 2.1 GB | `macos-26` had 96 GB free before the build and 92 GB at its lowest; `macos-15` had 43 GB free. No disk was freed. |
| Time | 19 to 38 min for the job | Run 40387342307 on 2026-10-26: fetch 1 min 10 s, prepare 10 s, configure 29 s, build 35 min 16 s (9,436 steps, including libwebrtc, which the Cocoa port always links into WebCore), package 32 s. Run 40393579564, the same build an hour later: job 18 min 40 s, build 16 min 54 s. |
| Tools | Python 3.12+, CMake, Ninja, gperf, Perl, Ruby, .NET SDK | The image has them; the workflow installs CMake, Ninja or gperf with Homebrew only when one is missing. |

`build.py package` stages each framework's library as a plain dylib (`WebCore.framework/Versions/A/WebCore`
as `libWebCore.dylib`), because a build with a runtime identifier flattens native assets into one folder.
It changes the install names to `@rpath/<file>`, replaces the build tree's rpaths with `@loader_path`,
writes a dSYM per library to `symbols/` (the symbol tables: the Release build has no DWARF), strips local
symbols with `strip -x` and signs each library again ad hoc, since arm64 macOS loads only signed code.

The workflow's last macOS step loads `libRanvierWebCoreHost.dylib` from the staged package with Python's
`ctypes`, checks that no staged library names the build tree, compares `rv_abi_version()` with the manifest,
and paints a 32 by 32 page with a blue square on red, checking one pixel of each.

## Other runtimes

The patches change `OptionsWin.cmake` and the Windows platform CMake files, and `build.py` drives
`vcvars64`, clang-cl and lld-link, so only `win-x64` builds today. Each further runtime identifier needs:

- the same options added to its port's `Options*.cmake` and platform files (`OptionsGTK.cmake` or
  `OptionsWPE.cmake` for Linux, `OptionsMac.cmake` for macOS), behind the same `USE_*_STUB` names;
- a toolchain branch in `build.py` (`toolchain_env`, `closure` for ELF or Mach-O imports, `icu_data` for
  the platform's data library format);
- a matrix entry in `build.yml`.

The package is per runtime identifier (`Ranvier.WebCore.Native.<rid>`), so each runtime ships on its own;
a meta-package that depends on all of them can follow once more than one exists.
