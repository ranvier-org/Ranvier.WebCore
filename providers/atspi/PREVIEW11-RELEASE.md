# Preview11 release preparation

`public-preview11.json` reserves `Ranvier.WebCore.Accessibility.Atspi` version
`0.1.1-preview.11` for the matching Native ABI63 cohort. The accepted two-RID
qualification inputs and independently audited candidate are pinned. Only the
main-branch publisher is enabled in the existing `build.yml`; completed preparation
and relay routes are disabled. P10 qualification is retained under its original identity.
No Host or renderer dependency is added to the provider.

The future publisher re-downloads and verifies the exact accepted two-RID inputs
and candidate before using the existing main-ref trusted publishing subject.
Source revision fields remain unverified caller claims. RID layout selection does
not replace actual provider, protocol, SDK and normal/traced AOT execution.

Candidate run 41642147423 at `708058bcd9ff83575cda85238d586dc31d03231b`
produced the independently accepted unsigned package SHA-256
`bd2b2d0d760d33efedac1aef0381b4019b495812152f3685d4f3520f3a33e1bb`
and candidate binding SHA-256
`9791aedf253c5307e114d50e8ca6f717a8337fd80e70ae1a37845ec40b3f937e`.
The publisher verifies those exact bytes and rebinds both SDK layout receipts
before authentication. This source preparation does not claim publication.

The completed `relay-x64` dispatch accepted the exact reviewed local evidence bundle
from a pinned asset on a draft proof-only release. It validates every manifest
member, raw normal/traced dependency graph, six runtime logs and binaries, SDK
package and qualification receipts. It executes no renderer or qualification
compiler. It is now disabled. The aggregate labels this input `local-qualified-relayed`, separately
from the ARM input's `runner-executed` proof. Neither label authenticates the
caller-supplied source claim. Release 432676483 and asset 705558006 pin the reviewed
draft-only upload, its owner, exact target commit, size and complete SHA-256. The
receiver rejects its retired, unarmed policy before network use.

The first receiver, run 41639994860, stopped with HTTP 403 while reading the draft
release, before asset download. GitHub documents draft release visibility as
requiring push access. The relay job alone requests `contents: write` for draft
visibility; its API commands remain GET-only, checkout does not persist credentials,
and it has no NuGet authentication or publication step. Changed run 41640893465
at `0ac88abef20548c662877991987898c1e9aa9f0d` succeeded. Independent review
compared all 108 original bundle members with zero byte differences. That exact
dispatch/build.yml run and its `atspi-preview11-local-x64-qualified` artifact are
the x64 transport pins; the relay receipt says `testsExecutedByRelay=false`.

Reference: https://docs.github.com/en/rest/releases/releases#list-releases

The ARM qualification is pinned to push run 41627017174 at reviewed source
`5b5ef82a0af3011fc6615d442e9d2618147b08a8` and its exact retained artifact,
SDK package and summary receipt hashes. These pins preserve the actual qualification
sources; they do not relabel either proof as public View46 execution.
