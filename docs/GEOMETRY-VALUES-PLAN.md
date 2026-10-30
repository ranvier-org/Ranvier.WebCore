# G07/G08 geometry values

## Required result

Expose the pinned engine's existing rectangle, point, quad and matrix operations through the shared browser/native contract. Preserve unrestricted doubles, input defaults, mutable versus read-only identity, copy behavior and engine exceptions. Reuse WebCore mathematics; introduce neither JavaScript execution nor a dependency.

## Ordered implementation

- [x] Add opt-in nested dictionary input transport for DOMQuadInit, preserving field presence and defaults without changing prior dictionary layouts.
- [x] Add checked concrete-type metadata for externally retained geometry handles. These engine roots have no virtual type query; never downcast an unknown read-only object to a mutable type. Keep existing opaque pointer identities and function signatures.
- [x] Select rectangle factories/setters, point factories/setters and quad factories/points/bounds. Test input copies, live point mutation, negative extents, NaN/infinity and double precision in the private native producer.
- [x] Add matrix factories, dictionary aliases and six/sixteen-value sequence adapters, then immutable and self operations using the engine implementation. Test singular inversion, invalid-input preservation, exact alias equality, 2D/3D flags and homogeneous point transforms in the private native producer.
- [ ] Generate shared contracts and implement browser/native providers. Run focused raw/native JIT/AOT/Chromium cases before a combined batch.
- [ ] Review old ABI compatibility, retained-handle cleanup and public F# signatures, then stack the next unpublished package cohort behind Native15. Accept only after platform and official consumer evidence.

## Source constraints

DOMRectReadOnly, DOMPointReadOnly and DOMMatrixReadOnly use NoVirtualDestructorBase; mutable subclasses add no runtime discriminator. An external handle ledger may track trusted concrete producers and C-ABI retain counts, without owning additional engine/document references. All nested owned-result release paths must participate. Read-only exposure cannot upgrade an unknown object.

DOMQuadInit contains nested DOMPointInit dictionaries. Null or absent nested input must retain WebIDL defaults, including point w=1. DOMMatrixInit aliases preserve absence; the engine validates same-value-zero equality and is2D consistency. Singular inverse yields NaNs, and transformPoint does not divide by w.

No geometry binding or runtime acceptance is claimed by this planning checkpoint.

The selected geometry scope does not require generic toJSON object transport or named Float32Array/Float64Array factories. These incidental IDL members are outside this checkpoint; matrix values still need lossless double input/output and the selected matrix operations.

## Nested dictionary checkpoint

The focused test first failed because takeQuad was omitted for unsupported nested dictionaries. Opted-in nonnullable fields with an empty dictionary default now borrow a child input pointer. Parent and child independently check their size before reading each field; absent children retain the engine aggregate defaults. Required, nullable or absence-sensitive nested fields remain explicitly unsupported. No production dictionary has been opted in yet.

All 52 generator tests pass. Production generation check is unchanged at 138 interfaces, 1,739 functions, 20 handle roots and 16 dictionaries. Independent source review found no blocker. Null child pointers, short child structs and default w=1 still require execution in the eventual native quad fixture.

## Tracked handle primitive checkpoint

An opt-in root-to-direct-mutable-subtype configuration now selects trusted producer tracking. Compile-time conversion checks constrain each producer's concrete type; casts reject unknown and read-only records. Direct results, nested result containers, root retains and both release paths update external reference counts. The metadata table owns no engine references and removes an entry on its last exported release. Internal argument references do not enter this table.

The initial generator regression failed at the missing tracked producer path. All 53 generator tests now pass, with production generation still unchanged. Independent source review found no blocker. The actual generated helper and raw-pointer conversion compile under clang-cl C++20 with warnings as errors and pass 23 explicit checks against minimal nonvirtual reference-counted types. A deliberately incorrect mutable producer annotation is rejected by the compiler. This helper proof covers const concrete references, read-only rejection, retained references, last-release erasure and conservative address reuse; it does not prove engine bindings or native geometry acceptance. Logs are in the ignored artifacts/geometry-handle-proof directory.

## Private G07 producer checkpoint

The selected source generates 141 interfaces, 1,775 functions, 22 handle roots and 19 dictionaries, with zero stubs. Real DOMQuadInit fields use ImplementationDefaultValue={} rather than an IDL default; production generation exposed this difference, and a regression now requires the actual shape. The opt-in transport accepts both forms while still rejecting unsupported presence-sensitive fields. Point matrixTransform awaits G08 integration.

The old private producer failed at the missing point constructor export. The new generated glue and host compile and link against the coherent private WebCore candidate without changing cached or parent objects. The raw geometry fixture passes exactly 260 assertions: factory defaults, mutable/read-only constructors and type queries, setter policy, unrestricted doubles, copies, signed rectangle bounds, quad point identity/liveness, bounds snapshots, all corner ordering, truncated nested dictionaries and thread/context checks. Existing fragment geometry passes 140 controls and typed entry snapshots pass 144 controls.

All 54 generator tests and four package contract tests pass. The generated ABI driver builds with SDK10, zero warnings/errors. All prior 1,739 function records, 16 dictionary layouts, 32 compound container records and five runtime queries remain equal. The durable geometry-values-evidence directory records the three focused logs, source hashes and executed DLL hashes. This is Windows native producer evidence; shared providers, Chromium, NativeAOT consumers, other platforms and official releases remain unverified.

## G08 optional constructor primitive

The pinned matrix constructor takes an optional string-or-double-sequence variant. The previous generator decoded an absent pointer as a required value and dereferenced the decoded result. The regression first failed at the missing optional carrier. An omitted nonnullable compound argument with no explicit default now remains an empty std::optional; every present input still runs the strict decoder and error checks. Empty strings and empty sequences remain present values, allowing the engine to distinguish identity from a wrong-length sequence.

All 55 generator tests pass and production generation remains unchanged. No previously selected argument had this optional compound shape. Independent review is clear. Matrix bindings and execution are not yet selected or verified at this checkpoint.

## Private G08 producer checkpoint

The combined geometry producer generates 143 interfaces, 1,875 functions, 23 handle roots and 20 dictionaries, with zero stubs. Matrix constructors preserve omission versus present empty values. Static factories use the existing checked Document receiver; pure operations reuse the engine implementation. Mutable matrix handles use the same trusted producer ledger. setMatrixValue takes an explicit checked Document and a length-delimited string. Point matrixTransform is now included.

The first C++ build exposed a generated enum identifier containing the sequence's human-readable label. A regression requires the stable compound C type in both C and F# enum names. Tag values, layouts and prior records are unchanged. The repaired glue and host compile and link successfully.

The native matrix fixture passes exactly 1,091 assertions: omitted/string/6-value/16-value initialization, literal matrix and matrix3d parsing, embedded NUL rejection, finite serialization roundtrip, nonfinite serialization errors, matrix replacement and failure preservation, exact aliases and defaults, ordered multiplication, inversion and singular NaNs, mutable and immutable transform families, optional rotation/scaling behavior, homogeneous point transforms, unrestricted doubles and thread/context checks.

The combined private Windows batch passes 5,979 assertions across 18 raw probes, the complete ABI driver, and 42 final teardown cases. Some objects remain alive until collection; all final document/target weak references expire. SDK10 builds the generated ABI driver without warnings/errors; 55 generator tests and four package contract tests pass. All G07 checkpoint records remain equal: 1,775 functions, 19 dictionaries, 32 containers and seven runtime queries. Independent review verified the source/runtime/log hashes in matrix-values-evidence/evidence.json and the saved teardown results.

These proofs apply to the private Windows producer. Shared Core/Views providers, Chromium parity, NativeAOT geometry/matrix consumers, other platforms and official packages remain open. No G07/G08 acceptance or public release is claimed.

## Native16 / ABI24 allocation

The release lane checked all 17 native/managed/flavor candidate package IDs, the tag and open producer reservations before allocating unpublished preview16 and ABI24. Native14 and Native15 retain their own release cohorts.

After changing only package allocation, the ABI version constant and matching version checks, the separate ABI24 candidate passes 1,772 affected/focused assertions, the full SDK10 ABI driver and 42 final teardown checks. The earlier 5,979-assertion geometry batch is preserved rather than rerun unnecessarily. cohort16-abi24-evidence/evidence.json records the final executed DLL hashes and six probe logs. Canonical header/Native.fs signatures remain equal at 181 declarations, with zero differences. No platform or public-package result is implied.
