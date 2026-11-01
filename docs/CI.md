# CI

`.github/workflows/build.yml` runs `scripts/build.py` step by step for each runtime in its matrix, then
uploads the `.nupkg` with `manifest.json`, and the PDBs as a separate artifact. On a `v*` tag it sets the
package version from the tag and, when the repository variable `NUGET_USER` is set, pushes the packages
to nuget.org by trusted publishing: no API key is stored. The nuget.org account `NUGET_USER` needs a
trusted publishing policy for owner `ranvier-org`, repository `Ranvier.WebCore`, workflow file `build.yml`
and no environment.

A pull request builds `win-x64` only. A pull request from a `codex/batch-*` branch, or one labelled
`full-matrix`, builds every runtime; adding the label starts that run. The five-runtime managed aggregate is
packed only when every runtime is built, so a `win-x64`-only pull request skips it. Pushes to `main` and `v*` tags always
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

`scripts/build_cache.py keys` computes every key in one step after the tool installs, because the build
tree's key names the toolchain.

| Entry | Key | Restored | Saved after |
|---|---|---|---|
| gperf (Windows, from Chocolatey) | its version and the RID: a cache entry holds paths relative to the workspace, whose drive differs between the x64 and ARM64 images | always | its install |
| LLVM (Windows) | the RID's archive hash in `pins.json` | always | fetch |
| build tree | see [Build tree](#build-tree) | unless a manual run sets `clean` | the build |
| vcpkg binary archives (Windows) | the RID, the flavor and vcpkg's ABI inputs: the vcpkg and WebKit pins, any patch that writes WebKit's `vcpkg.json`, `vcpkg-configuration.json` or `WebKitLibraries/triplets/`, the flavor's `VCPKG_MANIFEST_FEATURES`, and the MSVC toolset's identity (as in the build tree's key) | when no build tree was restored | a successful configure |
| vcpkg downloads (Windows) | the RID and the vcpkg, WebKit and ICU pins | when the archives missed | a successful configure |

- A miss restores the newest entry with the same prefix (`vcpkg-<rid>-<flavor>-`, `vcpkg-downloads-<rid>-`):
  archives are named by their ABI hash, so the packages that did not change are not rebuilt. An entry is
  saved only on a miss, because a saved key is never replaced.
- A config edit changes neither vcpkg key unless it changes the manifest features. Until 2026-11-01 the key
  ended in a hash of all of `config/`: each config edit saved a new 272 to 412 MB entry, the repository
  reached its 10 GB limit, and GitHub evicted the entries a run then missed (19 minutes of vcpkg builds on
  `win-x64`).
- A restored build tree holds `vcpkg_installed` under the same vcpkg key, so vcpkg installs nothing and the
  archives are not restored.
- The downloads hold the ports' sources, which vcpkg reads only to build a package whose archive is missing,
  so they have their own entry, the same for every flavor and toolset. ICU's source archive comes from
  vcpkg's downloads; when they were not restored, `build.py` downloads it there itself for the ICU filter,
  checking `pins.json`'s hash.
- Not cached: the WebKit checkout (about 2 GB from GitHub, with retries), vcpkg's own checkout, and the
  Linux and macOS packages.

### Build tree

The CMake and ninja directory, `<work>/build-<flavor>`, is cached for each RID and flavor, so a run compiles
what its commit changed.

```
tree-<rid>-<flavor>-<WebKit pin>-<toolchain>-<core>-<host>
```

| Part | Hash of |
|---|---|
| toolchain | Windows: the MSVC toolset and Windows SDK versions, the hash of `cl.exe`, the paths and sizes of their headers, the LLVM pin and the vcpkg key (the tree holds `vcpkg_installed`). Runner images ship the same toolset version with other binaries and headers: on 2026-11-01 vcpkg's compiler hash differed between `windows-2025` images 20261021.278.1 and 20261030.294.1, both MSVC 14.51.36231. Linux: `clang --version` and the image. macOS: `xcodebuild -version` and the SDK version. |
| core | the blob ids of `patches/`, `config/`, `scripts/build.py` and `scripts/patches.py` |
| host | the blob ids of `host/` |

- An exact hit restores a tree built from the same inputs: ninja has nothing to do, and nothing is saved.
- Otherwise the run restores the newest tree with the same core (only `host/` differs), else the newest with
  the same WebKit pin and toolchain, builds incrementally and saves under its exact key. A fallback stays
  within one WebKit pin and toolchain and, on Windows, one vcpkg key: ninja does not track the compiler, and
  reinstalled vcpkg headers invalidate the precompiled headers.
- After saving, the run deletes the entry it restored if that entry is its own ref's, which keeps one tree per
  RID, flavor and ref. A default-branch entry restored by a pull request stays.
- Saved on pushes and manual runs of `main` and `codex/batch-*`, and on pull requests from `codex/batch-*`;
  restored on every run. A branch sees its own entries and the default branch's, a pull request its own and
  its base branch's, and a tag only the default branch's, so a release tag on `main`'s head restores the tree
  that `main`'s push saved. Pushes to `codex/batch-*` do not start this workflow; their pull request's runs
  save under the pull request's ref.
- A manual run with `clean` builds from an empty tree.

Checkout and the WebKit fetch give every source a new modification time, which ninja reads as a change to every
file. The tree therefore carries `ranvier-sources.json`: the git blob id and modification time, in seconds, of
each file of the WebKit checkout and of this repository, and of each directory, with a hash of the names it
lists. After prepare, `build_cache.py normalise` gives each file whose blob id is unchanged, and each directory
whose listing is unchanged, its recorded time; changed and new files keep the time checkout gave them. The
blob ids come from git's index, which checkout has just written, and only the files git reports as changed
(the patched and installed ones) are read: about 2 s in WSL for the 77,000 files of the sparse checkout, and
about 10 s on a Windows workstation. normalise then writes the manifest of the current sources, which the save
stores with the tree.

Clang records each input's modification time in a precompiled header and rejects the header when a time differs.
CMake builds Clang's PCHs with `-fno-pch-timestamp` on Linux and macOS, but not clang-cl's on Windows, so
`config/win-project.cmake` adds `-Xclang -fno-pch-timestamp` to every C and C++ compile there. Without it a
Visual Studio header whose time differs between runner images rejected WebCore's PCH (`xfacet has been modified
since the precompiled header`), and ninja, which ignores system headers, rebuilt nothing. A PCH is still
rejected when an input's size differs, which the toolchain part of the key covers.

ninja also reruns a rule whose command line changed. WebKit's generator rules name Python and Ruby, and the
runners' paths name their patch versions (`hostedtoolcache/Python/3.14.10`), which change between images: on
macOS the move from 3.14.9 to 3.14.10 reran every generator and 342 edges (24 minutes) on an exact hit. So
`build.py configure` names them by links that keep their path, `<work>/tools/stable/python` and `ruby`
(symbolic links, or junctions on Windows). Configure-time files written only when they change keep their times
too: patches 0005 and 0007 write the stub event factory inputs that way, which otherwise made every configure
regenerate the event factories and recompile 240 WebCore sources on Windows.

Before the build, `build_cache.py explain` prints how many edges ninja will run and its first 20 reasons
(`ninja -n -d explain`), such as `command line changed for ...` or `... older than most recent input ...`.

normalise also deletes the tree's `CMakeCache.txt` and `CMakeFiles/CMakeConfigureLog.yaml`, so every configure
starts without a cache. The config files set options with `set(... CACHE)`, which leaves a value already in a
cache in place: a reused cache kept `ENABLE_POINTER_LOCK=OFF` after `config/common.cmake` changed it to `ON`.
Without a cache, configure sets the options a clean configure sets, and the files it writes rebuild their
dependents. Measured on 2026-11-01 in WSL (linux-x64, slim, `-j 10`), from a tree built at `codex/batch-6`
and a fresh WebKit fetch:

| Change | ninja edges | Build |
|---|---|---|
| none | 0 | 0.3 s |
| one file of `host/` | 2: its compile and the host library's link | 17 s |
| `ENABLE_POINTER_LOCK` from `ON` to `OFF` | 1,159 of 8,019: 1,093 compiles (1,091 objects depend on `cmakeconfig.h`) and their links and generators | not run |
| the same edit with the old cache kept | 2: the option stays `ON` | |

A configure without a cache took 60 s in WSL; the hosted Linux runners configure from scratch in about 20 s.

Compressed as `actions/cache` compresses (zstd level 3, 1 GB window), a tree is about 1.0 GB on Windows
(5.3 GB on disk, of which the linked libraries' PDBs, which `package` copies, are 0.17 GB compressed),
0.57 GB on Linux (2.1 GB on disk, 0.47 GB of it precompiled headers) and, estimated from its 2.1 GB on disk,
about 0.6 GB on macOS: about 3.7 GB for the five RIDs. The repository's 10 GB also holds LLVM (about 2.6 GB)
and the vcpkg entries (about 1 GB), so the default branch's trees and one pull request's fit only narrowly;
GitHub evicts the least recently used entries beyond the limit.

## Probes

After `smoke.py`, one step runs `scripts/probes.py run`: the probes of `tests/abi`, `tests/generator` and
`tests/uia` against the staged runtime, in the order of its `PROBES` list. The list is the only place a probe
is stated. Each entry holds the probe's commands, its condition (a RID, a flavor, both, or neither) and its
timeout, 600 s unless the entry sets one.

- Every probe that applies runs, whatever the earlier ones did. The step fails at the end when any probe failed
  or timed out, and one run reports every failing probe.
- Each probe's output is a collapsed group of the job log, followed by a `PASS` or `FAIL` line with its
  duration; a failure is also an error annotation. The step summary has the table of results.
- The logs, one per probe and `summary.txt`, are in `<work>/probe-logs` and the artifact
  `probe-logs-<rid>-<flavor>`, uploaded whether the job passed or not.
- A probe of several commands, such as the UI Automation teardowns, runs them in order and stops at the first
  that fails. A probe past its timeout is killed with its descendants.
- `probes.py list --rid RID --flavor FLAVOR` prints the probes that apply, as workflow steps would state them.
  `run --only TEXT` runs the probes whose name or commands contain the text.
- In WSL, run with `--no-dump`: each probe's interpreter makes itself non-dumpable, because WSL writes the
  core dump of every crash to the Windows temp folder whatever `ulimit -c` says.

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
`<build>/Source` and build again. CI does not hit this: it reuses a build tree only under the same vcpkg key.

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
