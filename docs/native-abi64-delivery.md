# ABI64 native delivery preparation

This is source preparation. No version, tag, producer activation or public qualification is allocated by
this change. The source baseline is `e642c5fbea3c8fead82d0607c3c26bf02f6381f2`, which merges current Native
main `cdc119cb60fc2f1df5485bcb59cba99bed66f56f` with the reviewed Cocoa integration. The older private
`2a15536b89aa6a72164762803dac76291973d0a0` proofs establish bounded implementation behavior; they do not
authenticate a future package built from this source.

## Contract and existing build path

The canonical header and generated `tests/abi/Native.fs` contain 349 functions. The previous 347 names and
signatures remain; the two additions are `rv_host_acquire_iosurface_frame` and `rv_host_bind_iosurface`.
ABI64 applies on every RID, including Slim and platforms without IOSurface support. Unsupported builds
retain the declarations, report the transport capabilities false and return the existing unsupported
status; acquisition clears the output pointer. BGRA8 format 2 is additive to existing RGBA8 format 1.
Capability and format checks remain mandatory; ABI64 alone does not establish GPU support.

The existing `gpu` flavor already selects the Cocoa compositor for `osx-arm64` in `config/gpu.cmake`.
`scripts/build.py` copies the matching Mac helpers during preparation. The public path does not need a
new flavor, renderer, plug-in or the old private spike command-line opt-in. Existing dependencies remain
ANGLE, CoreGraphics/Metal/IOSurface and SDL under their current roles. Mac deployment remains 26;
macOS15 is deferred.

`Ranvier.WebCore.Native.Gpu.osx-arm64` follows the existing package-ID construction. The five-RID
`Ranvier.WebCore.Native` aggregate remains Slim. GPU packages remain explicit application selections;
the supported automatic GPU set is Windows x64, Linux x64/ARM64 and macOS ARM64. Windows ARM64 GPU is
not added to that set. Slim and GPU are different compile configurations and require their own truthful
build inputs; an engine cannot be relabeled between them.

## Prepared source changes

1. `tests/abi/abi_expectation.py` retains standalone ABI63 probe behavior and admits ABI64 explicitly.
   The canonical producer verifies ABI, RID, flavor and clean manifest source against its actual checkout
   HEAD before running probes. The child environment is copied and scoped; it cannot override admission.
   `scripts/abi_tests.py`, `scripts/probes.py`, `scripts/check_package_api.py` and current build/release
   callers carry the explicit ABI64 selection. A source fixture verifies that all 39 adapted ABI probe
   assertion ASTs otherwise match their original ABI63 bodies. Historical recovery identities stay pinned.
2. `providers/atspi/RanvierAtspi.cpp` admits exactly ABI63 or ABI64 plus the existing text-style
   capability. The private packer defaults to 63, requires an explicit matching 64 selection and labels
   that candidate unqualified. ABI65 is rejected. GIO remains optional and no Host is bundled. Existing
   published provider versions and the P12-on-P11 ABI63 receipts are unchanged.
3. The existing trusted `build.yml` post-Slim job dispatches all four supported GPU RIDs on the same
   immutable tag only after successful ordinary publication. Recovery/provider dispatches cannot recurse
   into it. Existing publication dependencies and authentication stay in the established workflow.

The normal managed Interop package links the canonical generated bindings and packages the public
header/model inputs. Its package build must check the 349 declaration match and actual loaded ABI64.
It is a .NET native interop project, not a new Fable GPU API. Shared View/Dom Fable source and package
consumers still need their existing normal/traced checks; adding Metal to SDL must not add native calls
to a browser implementation.

## Remaining actual qualification

- Root/QA freeze one clean integrated source F and allocate Native/Interop version N. Existing warm
  incremental producers may be used only under their coordinated ownership and source/config guards.
  This preparation does not start them. Each selected stage must authenticate F, flavor, RID, ABI64,
  its actual payload hashes and the 349 declarations before acceptance.
- All five Slim RIDs need actual load, capability/stub, complete native catalogue and managed package
  checks. All four supported GPU RIDs need their actual native transport, retained-frame/input lifetime,
  loss/error controls and full catalogue. Windows/Linux source-derived clipping qualification remains
  profile-bound and preserves all 54 raw reports, 12 strict masks, 52 unaffected controls and negative
  controls. Unknown drivers/profiles fail closed.
- Mac GPU must resolve the actual second-host backing/counter failure on its matching final engine;
  accepted private glyph-orientation evidence does not waive that failure. The package qualifier invokes
  output and input consumers, but its current fail-fast ordering can hide a later independent group.
  Retain both groups' evidence when preparing the final producer. Add the established glyph oracle as a
  separately reported group. Some diagnostic consumers still use `rv_mac_spike_identity`; distinguish
  that private metadata dependency from the public transport operations rather than advertising a purely
  public SDK consumer until it is removed or isolated.
- Native211/224/275 matched CPU proofs are private 2a evidence. Final delivery needs the final source's
  timer, page/system motion and scoped Theme-contrast checks. Wrong-owner fatal attribution must be
  freshly bound to the exact future runtime/helper and actual instruction branch; prior addresses or a
  blanket SIGKILL allowance cannot authenticate it.
- AT-SPI64 needs a new manifest-bound managed cohort and reviewed fixture, not an environment-variable
  upgrade of the P12/63 route. Per Linux RID require actual 87 protocol assertions in each of three
  processes, 23 direct style assertions, the SDK consumer and all six strict managed profiles. The owner
  of that managed64 successor is to be named by Root/QA. Existing public and ARM64 source routes remain
  pinned to 63 until that work is reviewed; no ARM64 parity is inferred from x64.
- Verify the first public `Ranvier.WebCore.Native.Gpu.osx-arm64` ID's repository/owner trusted-publisher
  policy before authentication. This source cannot establish NuGet account policy. No package-version
  changes belong in this preparation; `pins.json` retains its prior default until coordinated allocation.

## View integration and public consumers

The reviewed Metal feature source `ae534a59682edc30acac4e9ddf38f0ddc6ae00fc` adds IOSurface binding on
Host and Metal presentation in SDL, plus five input tests. Its old project pins point to Native preview10
and DOM alpha57. Do not merge those metadata files wholesale over current View47/Core58. Forward only
the reviewed product/test changes onto the current accepted View source, preserving the formatter-only
successor `5e02890a97c71dca8e69e103bb087f256de3fd09`, Fable metadata repairs and later lifetime fixes.
Reconcile any later reviewed Metal owner leaf before implementing a duplicate. View version V remains
unallocated here; Native N and View V are separate coordinates.

Before publication require normal/traced unfiltered View tests plus the framework-free strict NativeAOT
consumer against the actual ABI64 Mac GPU package, no CPU fallback. Exercise output presentation and
input publication, scroll/resize/scale, unbind/rebind, host/target replacement and provider/frame disposal.
Retain current fractional-edge failures separately; do not turn them into tolerance changes. Verify
normal/traced package graphs reject mixed families and source fallback, and actual loaded product/native
hashes match the chosen packages. After publication repeat fresh package-only JIT/AOT consumers and
the existing Fable package-consumer gates. Historical View46/P11 and private Metal proofs remain distinct.

## Handoff and activation boundary

Review the focused source commits independently, then merge only the reviewed delivery changes into the
coherent source. No private diagnostic workflow, old artifact identity or public version is adopted by
this document. Final producer activation belongs to Root/QA after the runtime blockers and source freeze
are ready. Retain compact source/command/input/output manifests and release all owned workers, leases
and worktrees after acceptance readers copy them.
