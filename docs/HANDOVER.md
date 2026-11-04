# Handover

State of the project at Native `0.1.1-rc.2`. Every item below comes from a release, an issue or a CI run;
re-check the live source (`pins.json`, `patches/series`, the header) before relying on a number.

## Released and verified

- Native `0.1.1-rc.2` (tag on 6c66723, run 41785462391): `Ranvier.WebCore`, `Ranvier.WebCore.Native`, the five
  runtime packages and `Ranvier.WebCore.Accessibility.Atspi` are public on nuget.org. The GPU cohort is published
  by the `gpu-cohort` dispatch of the same tag (run 41790389124).
- Tag `v0.1.1-rc.1` failed in `atspi` and published nothing. It stays in place: release tags are never moved, and a
  failed release is retried under the next rc number.
- Native `0.1.1-preview.12`: the Slim cohort (seven packages: five runtimes, `Ranvier.WebCore`,
  `Ranvier.WebCore.Native`) and the GPU cohort are public on nuget.org. Product source
  `d31c3631ed4bbe6520f7f5f7c7e7d34499c38122`; ABI 64 with 349 declarations in `RanvierWebCoreAbi.h`.
- `Ranvier.View` 0.1.48 and `Ranvier.View.WebCore` 0.1.0-alpha.48 are published from the `Ranvier.View` repository.

## Closed with signed-cohort evidence

| Issue | Closed on |
|---|---|
| #199 fractional fullscreen | 4 displays at scales 1.0 and 1.25 |
| #220 macOS GPU output | IOSurface output at scales 1, 1.5 and 2; Metal texture input |
| #211 WTF RunLoop timers | eight modes, including cross-thread destroy, with a reviewed exact-runtime owner proof |
| #224 reduced motion | 135 assertions, 45 captures |
| #275 per-page contrast | 83 assertions in both orders, with caller attribution |

The Cocoa evidence (#211, #224, #275) is replay run 41774985234 of `public-cocoa-contracts.yml`, merged through
PRs #329, #335, #336 and #337.

## CI

PR #338 removed every completed per-release route: 22 workflows, 20 `build.yml` jobs with their inputs, and the
scripts and tests that only those routes used. Four workflows remain (`build.yml`, `triage.yml`,
`public-cocoa-contracts.yml`, `atspi-provider.yml`); `docs/CI.md` describes them.

PR #340 added the `atspi` and `atspi-package` release jobs (`providers/atspi/release.py`). PR #342 made CI
version-agnostic: the ABI comes from `rv_abi_version` in `host/RanvierWebCoreAbi.cpp` and the package version
from `pins.json` or the tag, so a release or ABI bump needs no workflow or test edit. A new hard-coded version
or ABI number in CI is a regression.

## Open

- **#176 compositor and presentation.**
  - SDL window presentation at scales 1.5 and 2 on Windows and Linux.
  - Live resize and concurrent hosts on macOS.
  - Transition-snapshot pixel probes are blocked by a stale `assert rv_abi_version == 63` guard (Windows probe 40,
    Linux probe 45). Updating the guard unblocks them.
- The macOS Metal fallback shows an empty SDL frame before the CPU path.
- Linux multi-display move is not replayed publicly.
- The linux-x64 Web Animations memory-growth RED is retained.

## Re-running the Cocoa replay for the next cohort

The workflow is `.github/workflows/public-cocoa-contracts.yml`; its inputs are
`tests/controls/public_cocoa_replay_inputs.json`; the controller and contracts are described in
`tests/controls/README-public-cocoa.md`. The file stays disarmed (`"armed": false`) between cohorts.

1. **Build the inputs for the signed cohort.** Put these in the inputs file:
   - the completion-proof artifact id and sha256 (`artifact`);
   - the policy: Native package id, version, ABI, declaration count, source commit, signed package sha256, audit
     sha256, interop package sha256, header sha256, `controllerSource` (a full commit) and the sidecar manifest
     sha256;
   - the sidecar manifest, sealed against the **signed** package sha256, with the producer's unsigned package
     sha256 beside it;
   - `auditText`, the independently reviewed public-feed audit, byte for byte.
2. **Arm and collect the owner proof.** Set `armed` to true, leave `ownerProofText` null, merge, and dispatch
   phase `collect-owner` from `main`. The run ends red by design.
3. **Review the owner proof.** Review the collected proof (the LLDB destructor inspection of the loaded JavaScriptCore) independently.
4. **Pin it.** Write `ownerProofText` byte for byte and set `reviewedOwnerProofSha256` to its sha256 in the policy.
   Merge.
5. **Dispatch phase `replay`** from `main`. Close issues only on a `replay-receipt.json` with `accepted=true` from
   `refs/heads/main`.
6. **Disarm** (`"armed": false`) and merge, as PR #337 did.

Before step 2 and step 5 re-check `main`: the wrapper runs from the main checkout and the controller from the pinned
`controllerSource` (`docs/FOOTGUNS.md`).

## Where things are

| Need | Look at |
|---|---|
| Build and release process | `docs/CI.md` |
| Moving the WebKit pin | `docs/UPDATING.md`, `docs/PATCHES.md` |
| ABI version and header | `docs/ABI.md`, `host/RanvierWebCoreAbi.h` |
| Pitfalls found the hard way | `docs/FOOTGUNS.md` |
