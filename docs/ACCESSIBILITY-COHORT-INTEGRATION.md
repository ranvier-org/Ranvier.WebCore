# Next optional accessibility cohort integration

This branch prepares optional #182 source on Native main `c70c0c1220ea6f0a45a3572be504e0ad82ef4621`.
That main already contains accepted printing/generator and P7 qualification/recovery commits. The integration delta
imports only the focused #182 commits and PR255/256 delivery changes, without their older branch merge ancestry.
It is currently a private style-only ABI63 source with 345 declarations, not the final 347-function union.
No final native producer, public package version or ARM64 qualification is implied.

## Source merge and ABI order

- Keep final #171 Host/0064 ownership with `windows_gpu`. Do not import prototype `85e` or a diagnostic fault build.
- Obtain the reviewed guarded #171 commit, exact vendor patch and frozen source archive/receipt from that lane.
  Record its identity alongside the main base and each focused #182 cherry-pick. Have acceptance review the delta.
- Integrate only that reviewed source. The #171 history/busy and IME helpers are separate from the #182 AX text-style
  helper. Inspect the actual conflict/diff even when Git applies it automatically; retain main's reviewed printing,
  generator and source policy. Do not import unrelated Mac220/224 or P7 diagnostic changes from candidate branches.
- Preserve all original 344 hand-written ABI signatures and their order. The only tail is zero-based slot344
  `rv_host_ime_surrounding`, slot345 `rv_host_ime_delete_surrounding`, slot346 `rv_ax_text_style_run`.
  The shared ABI is 63 and the total is 347. A style-only345 source/runtime cannot be relabeled final.

## Generate and validate once the union is frozen

- Check the final source declaration count, ABI version, preserved 344-signature prefix and exact three-function tail.
  Record a normalized declaration manifest with source commit, header hash and generator hash. This is source evidence,
  separate from a producer runtime manifest; never authenticate an arbitrary binary from its supplied source label.
- Run `python tests/abi/generate_native.py write` only after that order is settled. Format with the repository's
  pinned Fantomas, then run `python tests/abi/generate_native.py check` and `compare`. Verify normal and traced
  call-count arrays each have the identical347 order. Do not hand-edit or copy private `Native.fs` artifacts.
- Run the DOM generator/source contract checks from the current build workflow, including the reviewed generator924
  behavior, and `python scripts/capability_catalogue.py --check`. Review generated changes for accidental public
  API drift. Use scoped compiled/Sage tooling for F# questions; avoid the failed full-workspace FCS instance.
- Build and run the complete applicable native/managed contract suite and analyzer gates on the exact frozen source.
  Release source must not depend on fault-injection macros or a private diagnostics profile.

## Produce and pin a matching cohort

- Acceptance selects the final producer source and public version. Do not reuse immutable ABI62 package versions.
  The reserved optional package ID is `Ranvier.WebCore.Accessibility.Atspi`; the number is not allocated here.
- Produce the selected Slim/GPU runtime without an unconditional GIO dependency. The standalone optional provider
  consumes that exact host. Retain actual native package manifest, source claim, clean status, flavor, RID, ELF/PE
  architecture, ABI/capabilities, host/provider hashes, dependencies and build commands for independent comparison.
- Rebuild and install the optional provider against that exact host. Preserve `$ORIGIN`-only module lookup; package
  the module, two SDK headers, truthful NOTICE/THIRD-PARTY and LGPL text without a second host or forced renderer flavor.
  A caller-supplied source label remains explicitly unverified. Existing notice metadata convention adds no new approval gate.
- Run real Windows UIA and Linux provider/direct style/protocol tests, all discovery/queued/reentrant modes and
  normal/traced ordinary NuGet restore plus strict NativeAOT Window/Host lifecycle and non-BMP style checks.
  Repeat missing-module and missing-bus controls. Prior frozen private proof is not proof of a newly built cohort.
- Pin the exact reviewed final Native commit/version in the coordinated Core/View/SDK sources only after the native
  source and matching generated interop are fixed. Keep PR66/publication under acceptance ownership.

## ARM64 qualification workflow arming inputs

`.github/workflows/atspi-arm64-qualification.yml` stays `if: ${{ false }}` until a separate reviewed enablement change.
It uses the existing `ubuntu-24.04-arm` native runner. Prepare actual inputs, never a placeholder dispatch:

- `native_run`: the final ARM64 producer run reviewed by acceptance.
- `native_artifact`: its exact matching native package artifact name.
- `native_sha256`: the independently checked SHA256 of its ARM64 `libRanvierWebCoreHost.so`.
- `final_source`: the full clean final union commit declared in that package, matched to independent producer evidence.

The staging gate checks these artifact claims, exact binary hash, ELF64/AArch64 and the three union exports. The
real runtime ABI/capability and provider/direct/protocol/ordinary SDK checks must then pass on actual ARM64. Its
private package remains `ARM64-test-only-unqualified`; a green SDK load alone does not complete real managed
normal/traced Window/AOT or final cohort acceptance. No ARM workflow has been dispatched by this preparation.
