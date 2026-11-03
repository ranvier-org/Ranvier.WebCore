# Preview11 release preparation

`public-preview11.json` reserves `Ranvier.WebCore.Accessibility.Atspi` version
`0.1.1-preview.11` for the matching Native ABI63 cohort. Qualification transport
pins and the independently reviewed candidate hashes are pending. Its prepare
and publish jobs in the existing `build.yml` are disabled; the helper also rejects
the unarmed policy before downloading inputs. P10 qualification is retained under
its original identity. No Host or renderer dependency is added to the provider.

The future publisher re-downloads and verifies the exact accepted two-RID inputs
and candidate before using the existing main-ref trusted publishing subject.
Source revision fields remain unverified caller claims. RID layout selection does
not replace actual provider, protocol, SDK and normal/traced AOT execution.

The main-only `relay-x64` dispatch accepts the exact reviewed local evidence bundle
from a pinned asset on a draft proof-only release. It validates every manifest
member, raw normal/traced dependency graph, six runtime logs and binaries, SDK
package and qualification receipts. It executes no renderer or qualification
compiler. The aggregate labels this input `local-qualified-relayed`, separately
from the ARM input's `runner-executed` proof. Neither label authenticates the
caller-supplied source claim. Release 432676483 and asset 705558006 pin the reviewed
draft-only upload, its owner, exact target commit, size and complete SHA-256. The
receiver rejects an unarmed policy before network use. Public preparation and
publication remain disabled, with pending input/candidate pins.
