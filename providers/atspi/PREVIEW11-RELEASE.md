# Preview11 release preparation

`public-preview11.json` reserves `Ranvier.WebCore.Accessibility.Atspi` version
`0.1.1-preview.11` for the matching Native ABI63 cohort. Both RID qualification
inputs and the independently reviewed candidate hashes are pending. Its prepare
and publish jobs in the existing `build.yml` are disabled; the helper also rejects
the unarmed policy before downloading inputs. P10 qualification is retained under
its original identity. No Host or renderer dependency is added to the provider.

The future publisher re-downloads and verifies the exact accepted two-RID inputs
and candidate before using the existing main-ref trusted publishing subject.
Source revision fields remain unverified caller claims. RID layout selection does
not replace actual provider, protocol, SDK and normal/traced AOT execution.
