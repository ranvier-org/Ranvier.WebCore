# Optional provider aggregate

`public_aggregate.py` prepares one `Ranvier.WebCore.Accessibility.Atspi` identity/version with x64 and ARM64 native
payloads. The existing private per-RID packer remains unchanged. No per-RID public IDs, renderer package dependency
or second Host is introduced.

Use actual matching Native artifacts to build and qualify each provider independently. Preserve native source and
export checks, direct styles, all three independent protocol modes, ordinary SDK loading, and normal/traced real
Window/Host NativeAOT provider-present, module-absent and no-bus controls. ARM qualification stays active; x64 evidence
does not qualify ARM. `qualification-receipt.example.json` is the unqualified summary shape, not evidence itself.
Fill it only from actual raw reports and retain those reports for independent review.

`public-cohort.example.json` is unarmed and has no initial provider version or expected input hashes. The allocated
Native P9 version/source is recorded, but matching producer artifacts, actual runtime receipts and initial public
version coordination remain necessary. P8's immutable failed producer remains historical evidence.
Supply a cohort spec with the matching allocated version, exact Native/provider source claims, and each private
package/independently supplied receipt SHA256. An input map names each RID's package and receipt files:

```json
{
  "linux-x64": {"package": "/owned/x64.nupkg", "receipt": "/owned/x64.json"},
  "linux-arm64": {"package": "/owned/arm64.nupkg", "receipt": "/owned/arm64.json"}
}
```

Run into owned output and a new work directory:

```sh
rtk proxy python3 providers/atspi/public_aggregate.py --cohort /owned/cohort.json --inputs /owned/inputs.json --output /owned/feed --work /owned/new-sdk-work
```

The aggregate rejects missing/failed qualification, altered receipt/package hashes, source/ABI/capability disagreement,
wrong ELF architecture, unsafe/duplicate paths, extra binaries, and any common SDK/header/tooling/notice byte difference.
The complete reviewed ABI header hash retains all 347 signatures. Required upstream notices/texts remain bundled;
project/XML license unknowns stay truthful metadata limitations, without an invented SPDX grant or additional gate.
Private input notices remain as historical records; the public notice describes the selected aggregate accurately.

The final manifest has a `runtimes` record for each RID, preserving exact Host/provider/input/receipt hashes. SDK/native
payloads are emitted once through the standard .NET10.0.403 NuGet pack task, with no dependency group, and their bytes
are checked after packing. Existing identity/version output is refused. SDK commands use the already reviewed owned
process-tree supervisor, with bounded deadlines and cleanup. No publish or credential command is present.

Source strings and supplied review-record identities are not authenticated by the packager. The manifest keeps
`sourceProvenance=unverified-caller-claim`; comparison with an expected receipt hash does not prove who reviewed it
or which source produced a binary. Independent producer/qualification and publisher artifact/signature evidence
remain separate.

Hermetic tests exercise metadata and malformed inputs without loading synthetic ELF headers. An isolated private
SDK layout control may prove that NuGet selects the x64/ARM64 asset by RID; it is not ARM or renderer execution proof.
Actual per-RID qualification remains required before the public aggregate can be produced from the armed spec.
