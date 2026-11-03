# Immutable preview12 Slim recovery

This is an unarmed source preparation. It allocates no version, moves no tag, builds no engine and
publishes nothing. Product F remains `d31c3631ed4bbe6520f7f5f7c7e7d34499c38122`, version
`0.1.1-preview.12`, ABI64/349. Root owns the isolated `build.yml` trusted-publishing route; this leaf
does not edit that workflow or add OIDC permissions to the qualification workflow.

## Input and qualification boundary

`docs/preview12-slim-recovery.json` pins four original native package artifacts from Slim run
41719479076. Admission requires its exact push/tag/source/attempt/repository identities, all four
successful native jobs and successful Package, paint, mutation and complete probe steps. It does
not require the GitHub actor or release uploader to be the organization.

The Mac package has a separately pinned workflow H and immutable F manifest. A complete one-job
recovery must retain all three successful independent phases and unchanged-Host sidecars. The actual
helper-failed run can instead be used only with the explicit `macRecovery.helperCompletion` binding:

- Its original build and native qualification remain successful; its helper phase and overall
  acceptance remain failed. The exact original proof-member prefix is required, never a basename search.
- A separate reviewed helper-completion workflow/run must succeed. Its raw receipt, artifact and inputs
  contract hashes bind the old F/package/native/SDK identities, the retained timer/page binaries,
  receipts and capsules, and the two newly compiled AppKit helpers.
- The same completion requires the actual old-clang personality failure and new-clang++ strict-link,
  signature and executed exception/ARC control. No engine, package, native gate or timer/page rebuild
  may be relabeled as reuse. Acquisition credentials must be removed from compiler children.
- `runtimeConsumerQualification=false` is preserved. Compiled sidecars do not claim the later public
  timer/motion/contrast consumer results or GPU/View acceptance.

Every ZIP rejects duplicate, case-colliding, unsafe and symlink members. Native nuspec IDs, manifests,
source, complete resource sets, sizes, hashes and PE/ELF/Mach-O machine identities are checked.

## Canonical managed build

The controller H and actual product checkout F must both be clean and separately identified. It calls
F's unmodified `scripts/package_managed.py` against only the five admitted unsigned native nupkgs.
The outer working directory pins SDK10.0.403; an isolated NuGet cache, local native-feed metadata and
package hashes prevent a public native fallback. The source and native inputs are rechecked after.

The small H-owned metadata reader uses `System.Reflection.Metadata`; it never loads native code.
It decodes all 349 actual P/Invoke return/parameter types, In/Out flags, marshalling descriptors,
library names and calling convention. The expected table comes from F's canonical header generator,
including its exact array/byref rules. Only the equivalent F# `double`/`float` System.Double aliases
are normalized; float32 remains distinct. Packaged headers/model must equal F bytes. Interop and
aggregate nuspec identities/dependencies are checked, with exactly five bracketed native dependencies.

This yields exactly seven packages: five RID packages, `Ranvier.WebCore`, and `Ranvier.WebCore.Native`.
Qualification receipts retain actual child commands/outcomes, managed metadata, original native
origins, partial/stitched Mac boundaries and unchanged source/native identities. Owned children have
an 8 GiB RSS limit, deadlines, group termination and verified absence of live group members.

## Commands and export

The read-only `preview12-slim-recovery.yml` is manual/off by default. After independent source and
input review it checks out policy P, controller H and product F separately and invokes:

```sh
python3 -B -I controller/scripts/recover_preview12_slim.py qualify \
  --policy policy-source/docs/preview12-slim-recovery.json \
  --product-root product --output "$RUNNER_TEMP/preview12-slim-qualified"
```

The artifacts are `qualified-preview12-slim` (actual receipts/logs/metadata) and
`package-preview12-slim-recovered` (all seven unsigned nupkgs). Partial failure evidence is retained.

After independent review, a separate policy pins the successful qualification workflow/source/run,
both artifact digests, raw receipt hash, original qualification policy hash and all seven package
hashes. Root's existing trusted publisher runs the compile-free export before authentication:

```sh
python3 -B -I controller/scripts/recover_preview12_slim.py export \
  --policy policy-source/docs/preview12-slim-recovery.json \
  --product-root product --output "$RUNNER_TEMP/preview12-slim-publication"
```

Export revalidates original origins and the real successful qualification, rejects stale or changed
receipts/packages, repeats metadata/signature-table checks and writes exact bytes to `export/*.nupkg`
plus `pre-authentication.json`. Export builds nothing and never authenticates. These unsigned hashes
remain distinct from subsequent signed public nupkg hashes; public signature/payload auditing remains
a separate requirement. All actual policy hashes are null until acceptance allocates them.
