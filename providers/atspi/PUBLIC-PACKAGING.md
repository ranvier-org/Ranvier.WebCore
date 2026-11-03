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
Native P10 version/source (`233c8045`) is recorded, but matching producer artifacts, actual runtime receipts and initial public
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

The disabled artifact workflow also restores/publishes the resulting package through the ordinary SDK for each RID.
Both selection checks are explicitly `--layout-only`; the x64 runner does not execute ARM64 code. Actual per-RID
renderer/protocol and six-profile NativeAOT receipts remain separate prerequisites. The workflow retains the exact
selected cohort file, both SDK receipts and `release-candidate.json`, binding their hashes to the package bytes.
That record always has `publicationEnabled=false` and preserves unverified source-claim metadata.

For initial distribution, Root coordinates the reserved public ID's matching version before assembly; independent
acceptance then reviews the exact candidate bytes and uses the organization's configured NuGet trusted-publishing route. Existing Native publishing
uses the `build.yml` policy and `NUGET_USER`; this optional artifact workflow does not assume that policy authorizes
it, request a token, or push a package. Its job remains statically disabled and its example version/hashes remain
null until the matching actual inputs are supplied. Historical private P9 x64/ARM qualification is retained and is
not relabeled as P10 or a final public View46 consumer graph.
# Initial preview10 candidate route

`public-preview10.json` contains the allocated initial ID/version and the independently reviewed P10 per-RID package and receipt hashes. It permits candidate assembly, with source revisions still recorded as unverified caller/artifact claims. It does not enable publication.

The existing `build.yml` workflow accepts `atspi_preview10=prepare` to download those exact qualification runs, assemble the ordinary SDK package and check both RID layouts without building an engine. `atspi_preview10=publish` is restricted to the actual main ref and verifies the unchanged reviewed candidate before using the existing `NuGet/login` policy. `preview10-publication.json` must first contain the independently reviewed candidate run, source head, package hash and candidate-receipt hash; incomplete pins fail before authentication. The publisher refuses an already existing package version and pushes only that exact provider nupkg.

