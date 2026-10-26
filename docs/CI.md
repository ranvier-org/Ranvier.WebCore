# CI

`.github/workflows/build.yml` runs `scripts/build.py` step by step for each runtime in its matrix, then
uploads the `.nupkg` with `manifest.json`, and the PDBs as a separate artifact. On a `v*` tag it sets the
package version from the tag and, when the repository variable `NUGET_USER` is set, pushes the packages
to nuget.org by trusted publishing: no API key is stored. The nuget.org account `NUGET_USER` needs a
trusted publishing policy for owner `shayanhabibi`, repository `Ranvier.WebCore`, workflow file `build.yml`
and no environment.

## Runner

| Need | Value | Note |
|---|---|---|
| Image | `windows-2025` by default; repository variable `RANVIER_WINDOWS_RUNNER` overrides | |
| Visual Studio | x64 C++ build tools, found with `vswhere` | Measured with MSVC 14.50.35717 (VS 18) locally. `windows-2025` had 14.51.36231 on 2026-10-26, and its package passed the F# driver (`docs/VERIFICATION.md`). An older toolset is untested. |
| Disk | about 12 GB (E): source 3.3 GB, build 5.0 GB, vcpkg packages and LLVM | |
| Time | 6-hour job limit | Locally, 20 jobs on 24 threads: vcpkg about 6 minutes, a full compile about 9 minutes. On `windows-2025` on 2026-10-26, with empty caches: the job took 1 h 41 min, of which fetch 11 min, configure (vcpkg) 20 min and the compile 65 min. |
| Tools | Python 3.12+, Perl, Ruby, gperf, CMake, Ninja, .NET SDK | The hosted Windows image has Perl, Ruby, CMake and .NET; Ninja comes with Visual Studio's CMake; the workflow installs Python and gperf. |

## Caches

- **vcpkg** binary archives and downloads (`VCPKG_BINARY_SOURCES`, `VCPKG_DOWNLOADS`), keyed on
  `pins.json` and `config/`. A hit skips building the dependencies. ICU's source archive is then not
  downloaded by vcpkg, and `build.py` downloads it itself for the ICU filter, checking `pins.json`'s hash.
- **LLVM**, keyed on `pins.json`.
- The WebKit build itself is not cached. A compiler cache (sccache with clang-cl) is the next step if
  build time matters.

## Local runs

The same steps run on a workstation:

```
python -I scripts/build.py all --work C:/rw
```

Options point at existing checkouts and tools instead of fetching them: `--source`, `--vcpkg`, `--llvm`,
and `--tool-path` (repeatable) for Perl, Ruby, gperf and Python. `--flavor lean` builds the reference
flavor into `<work>/build-lean` and packs it as `Ranvier.WebCore.Native.Lean.<rid>`.

An incremental rebuild after vcpkg reinstalls packages can fail with clang rejecting a precompiled header:
the reinstalled headers keep older modification times. Delete `cmake_pch.cxx.obj` under
`<build>/Source` and build again. A fresh build, as in CI, does not hit this.

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
