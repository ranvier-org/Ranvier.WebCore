# Immutable preview12 GPU cohort publication

**Goal:** Export the four unchanged native GPU packages through the existing trusted publisher after their actual platform gates, without rebuilding engines or moving the product tag.

**Architecture:** Reuse the reviewed Linux recovery exporter for both Linux packages. Verify the original successful Windows job and its complete native package. Verify the Mac F/H recovery and separate bounded capture replay, retaining the original collection failure. Combine exactly four packages and repeat every verification before authentication.

**Product:** d31c3631ed4bbe6520f7f5f7c7e7d34499c38122, version 0.1.1-preview.12, ABI64/349. Mac control/replay and corrected Linux tests remain separate from product source.

1. Add admission/package/receipt controls for missing RID, wrong source/flavor, payload tampering, original failed Windows job, Mac missing raw captures and changed native bytes. Keep policy unarmed and actual future hashes null.
2. Implement an export-only controller using the existing immutable artifact and native-format checks. Delegate Linux qualification verification to its pinned controller; verify the Windows F job and the stitched Mac proof/replay. Require the four exact package identities before export.
3. Add the mutually exclusive main-only trusted publication mode to build.yml, with verification repeated before NuGet authentication. No producer or alternative publishing route may run in this mode.
4. Run source controls and full suite, obtain independent QA review, merge. Fill actual reviewed qualification/payload pins and dispatch only after every required artifact exists.

**Review focus:** distinct F/H and unsigned/signed bytes; no package inferred from successful job status; no Mac original transport failure hidden; no rebuilt native payload; no missing or extra RID; no authentication before exact artifact/receipt checks.
