# CI

## Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `build.yml` | push to `main`, `v*` tags, pull requests, manual | Builds, tests, packages and publishes the native packages. |
| `triage.yml` | new or reopened issue, manual | Calls the shared issue-triage workflow of `ranvier-org/.github`. A manual run defaults to a dry run. |
| `public-cocoa-contracts.yml` | manual | Disarmed signed-cohort Cocoa CPU replay, re-armed for each cohort. See [Cocoa replay](#cocoa-replay). |
| `atspi-provider.yml` | manual | Builds, tests and packs the optional AT-SPI provider against a reviewed native producer artifact (`providers/atspi/README.md`). |

## build.yml

Manual dispatch inputs:

| Input | Values | Meaning |
|---|---|---|
| `flavor` | `slim` (default), `gpu`, `lean` | The build flavor. |
| `rids` | comma-separated runtime identifiers, empty for all | The runtimes to build. |
| `clean` | boolean | Builds from an empty build tree. |

Jobs, in dependency order:

| Job | Runs | Does |
|---|---|---|
| `package-contract` | always, on `ubuntu-latest` | The unit tests of packaging, release, probe and generator contracts (the explicit list of `python -I tests/...` steps in the job), `capability_catalogue.py --check`, `generate_native.py check`, the managed contract builds, Fantomas, Fable and Chromium proofs of the generated DOM. A new test file runs in CI only when it is added to this list. |
| `plan` | always | Computes the matrix of runtime and flavor cells (filtered by `rids`): the selected flavor's runtimes, plus the four GPU runtimes on a `v*` tag push. On a tag whose release holds a package the repository owner attached for a cell, that cell goes to `prebuilt` instead of `native`. |
| `prebuilt` | when `plan` lists attached packages | Downloads the package on a clean runner of its platform and runs `smoke.py`. The manifest must name the tag's commit, a clean tree and the tag's version. |
| `native` | one job per runtime and flavor | Builds with `scripts/build.py` step by step, runs `smoke.py`, the F# ABI tests (Windows, macOS) and `scripts/probes.py`, packs the `.nupkg`, and uploads `package-*` artifacts. The five runtimes are `win-x64`, `win-arm64`, `linux-x64`, `linux-arm64`, `osx-arm64`. |
| `managed` | after `native`, `prebuilt`, `package-contract` | Packs `Ranvier.WebCore` and the `Ranvier.WebCore.Native.Cpu` aggregate from the five Slim packages with `scripts/package_managed.py`. On a tag it also packs the default `Ranvier.WebCore.Native` aggregate from the four GPU packages and the CPU `win-arm64` package, and its `Ranvier.WebCore.Native.Gpu` alias; a partial GPU set fails the job. Skipped for a pull request that is neither from a `codex/batch-*` branch nor labelled `full-matrix`. |
| `result` | always | The `CI result` check that branch protection requires. Fails when any job above failed or was cancelled, when `package-contract` or `plan` did not succeed, or when `native` did not succeed outside a `v*` tag. |
| `publish` | on a `v*` tag, when the repository variable `NUGET_USER` is set | Pushes every `package-*` artifact to nuget.org by trusted publishing. Requires `package-contract`, every selected runtime and, for a Slim release, `managed` to succeed. |

A pull request builds `win-x64` only. A pull request from a `codex/batch-*` branch, or one labelled `full-matrix`,
builds every runtime; adding the label starts that run. Pushes to `main` and `v*` tags build every runtime.

Trusted publishing exchanges GitHub's OIDC token for a one-hour API key under the nuget.org account named by
`NUGET_USER`; no API key is stored. That account needs a trusted publishing policy for owner `ranvier-org`,
repository `Ranvier.WebCore`, workflow file `build.yml` and no environment. Without `NUGET_USER` the packages stay
workflow artifacts.

## Releasing

1. Set `package.version` in `pins.json` and merge to `main`.
2. Tag the merged commit `v<version>` and push the tag. One `build.yml` run builds the five Slim runtimes and the
   four GPU runtimes side by side, packs the managed package and both aggregates, and publishes every package in one
   push: five Slim runtimes (`Ranvier.WebCore.Native.Cpu.<rid>`), four GPU runtimes (`Ranvier.WebCore.Native.<rid>`),
   `Ranvier.WebCore`, `Ranvier.WebCore.Native`, `Ranvier.WebCore.Native.Cpu`, `Ranvier.WebCore.Native.Gpu` and the
   AT-SPI provider. A failed cell of either flavor blocks the whole
   publication. Each GPU runtime must pass its native transport and lifetime checks: Windows runs shared D3D11 acceptance with the pinned SDL package in
   `scripts/sdl_runtime.py`; macOS runs the public IOSurface frame and input checks; Linux runs
   `tests/gpu/linux_egl.py` under `EGL_PLATFORM=surfaceless` and `LIBGL_ALWAYS_SOFTWARE=1`.
To build or retry GPU runtimes alone, for example on a tag that predates the combined run:

```
gh workflow run build.yml --repo ranvier-org/Ranvier.WebCore --ref v<VERSION> --field flavor=gpu --field rids=win-x64
```

A manual GPU run publishes its runtime packages only, not the default aggregate. Concurrency is keyed by tag and the
selected flavor, so a GPU dispatch cannot cancel the tag's own run. Windows ARM64 has no GPU build; the default
aggregate takes its CPU package.

To build some packages on a workstation and the rest in CI, run `python -I scripts/release.py --rid win-x64 --work C:/rw`.
It refuses a working tree with changes, a commit on no remote branch and a version whose tag exists; builds with
`build.py --strict`; checks the package with `smoke.py`; then creates the GitHub release `v<version>` with the
packages attached. Creating the release pushes the tag, whose run takes the attached runtime through `prebuilt`.
`--flavor gpu` builds `Ranvier.WebCore.Native.<rid>` and the default `--flavor slim` builds `Ranvier.WebCore.Native.Cpu.<rid>`; `--dry-run` stops before the release. The attached
package must come from the repository owner; anyone who can push a tag could otherwise get a package of their own
published. A workstation package records `"builder": "local"` in `manifest.json`; CI records `"ci"`.

## Cocoa replay

`public-cocoa-contracts.yml` replays the Cocoa CPU contracts (timer modes, reduced motion, per-page contrast)
against a signed public cohort on `macos-26`. It is disarmed: `tests/controls/public_cocoa_replay_inputs.json` holds
`"armed": false`, and a dispatch with phase `off`, or with the file disarmed, does nothing. Each cohort re-arms it
by editing that file. The phases are `collect-owner` and `replay`; `docs/HANDOVER.md` has the procedure and
`tests/controls/README-public-cocoa.md` describes the controller, the sidecars and the contracts.

## Runner

| Need | Value | Note |
|---|---|---|
| Image | `windows-2025` by default; repository variable `RANVIER_WINDOWS_RUNNER` overrides | |
| Visual Studio | x64 C++ build tools, found with `vswhere` | Measured with MSVC 14.50.35717 (VS 18) locally. `windows-2025` had 14.51.36231 on 2026-10-26. An older toolset is untested. |
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
| ICU (Linux) | the RID, whether data is filtered, `pins.json`'s ICU pin, `scripts/icu_data.py`, `scripts/linux_icu.py` and the toolchain | always | fetch |
| build tree | see [Build tree](#build-tree) | unless a manual run sets `clean` | the build |
| vcpkg binary archives (Windows) | the RID, the flavor and vcpkg's ABI inputs: the vcpkg and WebKit pins, any patch that writes WebKit's `vcpkg.json`, `vcpkg-configuration.json` or `WebKitLibraries/triplets/`, the flavor's `VCPKG_MANIFEST_FEATURES`, and the MSVC toolset's identity (as in the build tree's key) | when no build tree was restored | a successful configure |
| vcpkg downloads (Windows) | the RID and the vcpkg, WebKit and ICU pins | when the archives missed | a successful configure |

- A miss restores the newest entry with the same prefix (`vcpkg-<rid>-<flavor>-`, `vcpkg-downloads-<rid>-`):
  archives are named by their ABI hash, so the packages that did not change are not rebuilt. An entry is
  saved only on a miss, because a saved key is never replaced.
- A tag run saves none of these entries. A later run cannot restore an entry saved under a tag, so it would
  only take space from the default branch's entries: until 2026-11-04 every release tag saved its own copy
  of the 140 MB `vcpkg-win-x64-gpu-*` archives.
- The GPU flavor's build trees are not in the cache. They would be restorable only if saved by `main`, which
  builds Slim only, and the four of them (about 2.7 GB) do not fit beside the Slim trees, LLVM and vcpkg within
  the repository's 10 GB. They travel as artifacts instead ([GPU build trees](#gpu-build-trees)).
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
| toolchain | Windows: the MSVC toolset and Windows SDK versions, the hash of `cl.exe`, the paths and sizes of their headers, the LLVM pin and the vcpkg key (the tree holds `vcpkg_installed`). Runner images ship the same toolset version with other binaries and headers: on 2026-11-01 vcpkg's compiler hash differed between `windows-2025` images 20261021.278.1 and 20261030.294.1, both MSVC 14.51.36231. Linux: `clang --version`, the image and the static ICU key. macOS: `xcodebuild -version` and the SDK version. |
| core | the blob ids of `patches/`, `config/`, `scripts/build.py`, `scripts/patches.py`, `scripts/icu_data.py` and `scripts/linux_icu.py` |
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

### GPU build trees

A tag run's GPU cell packs its tree with `scripts/tree_artifacts.py pack` and uploads it as an artifact named by
the tree's cache key, kept for 90 days. A GPU cell whose cache restore found nothing, in any later run, restores
with `tree_artifacts.py restore`. The order is the cache's: the exact key, else the newest artifact under the first
matching restore prefix, so a tree crosses releases only within one WebKit pin and toolchain. A restored tree goes
through `normalise` like a cached one.

- Artifacts have their own storage, free for this public repository, and any later run can download them, which
  the cache does not offer a tag. About 2.7 GB per release, expiring after 90 days.
- Pack and upload are `continue-on-error`: a failure costs the next release's GPU cell a cold build, never this
  release. A failed restore deletes any partial tree and builds without one.
- The restore streams the tarball out of the downloaded zip into `tar`, so the tarball and the tree are never both
  on the macOS runner's single volume. On Windows it uses GNU tar from Git for Windows, as the tree's paths need.

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

### GPU clipping qualification

The Windows and Linux x64 GPU producers run `scripts/qualify_producer_gpu_clipping.py` on their own staged
runtime. Admission checks the current manifest, native hashes, generated ABI, exact clean checkout HEAD and reviewed WebKit source pin;
it does not select an oracle by a package version or a previous producer's binary hash.

`background-content-clipping-regression.json` retains the original 54 comparisons and every raw RGBA image.
The 12 strict content masks and 52 other controls keep their existing rules, including the separately recorded
Windows DPR1 half-coverage rule. Only the promoted 1.5× and 2× cases can use the source-derived GPU model.
The original comparison can still report those two failures while the separate qualification passes.

`gpu-clipping-qualification` retains the actual renderer profile, model inputs, complete per-pixel result,
ten negative controls, source/native hashes and child logs. Windows checks all 16 binary sampling patterns in
FLOAT32, UNORM8 and source-over-white paths against independent ideals with the reviewed numerical policy.
The failed historical FLOAT32-to-UNORM cross-draw comparison remains explicit; the supplied-value store check
has its own 0.6-unit bound. Linux requires the reviewed Mesa profile and shader-capture fingerprint and
byte-identical plain, instrumented and canonical captures. Unknown drivers, precision profiles or shader
fingerprints fail pending independent qualification. These are tested-profile contracts, not a universal
GPU error theorem. Neither ARM nor macOS is admitted by this gate.

The GPU x64 jobs install NumPy 2.4.3 for these test tools. The producer stage stays read-only; shader caches,
the query-only Linux interposer and reports stay in the qualification output. Each child is bounded within a
540-second aggregate run and an 8 GiB sampled process-tree guard. Windows child bodies wait for assignment to
an owned kill-on-close job; a real descendant-timeout control runs in the GPU job. The evidence is uploaded even on failure.

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
`win-x64`'s 77.59 MB. 

## macOS (osx-arm64)

`osx-arm64` builds WebKit's Cocoa port (`PORT=Mac`, `config/mac.cmake`) with Xcode's AppleClang and Swift,
and packs `Ranvier.WebCore.Native.Cpu.osx-arm64`. It draws with CoreGraphics and CoreText, so its pixels do not
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
