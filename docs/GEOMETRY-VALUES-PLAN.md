# G07/G08 geometry values

## Required result

Expose the pinned engine's existing rectangle, point, quad and matrix operations through the shared browser/native contract. Preserve unrestricted doubles, input defaults, mutable versus read-only identity, copy behavior and engine exceptions. Reuse WebCore mathematics; introduce neither JavaScript execution nor a dependency.

## Ordered implementation

- [x] Add opt-in nested dictionary input transport for DOMQuadInit, preserving field presence and defaults without changing prior dictionary layouts.
- [ ] Add checked concrete-type metadata for externally retained geometry handles. These engine roots have no virtual type query; never downcast an unknown read-only object to a mutable type. Keep existing opaque pointer identities and function signatures.
- [ ] Select rectangle factories/setters, point factories/setters and quad factories/points/bounds. Test input copies, live point mutation, negative extents, NaN/infinity and double precision.
- [ ] Add matrix factories, dictionary aliases and six/sixteen-value sequence adapters, then immutable and self operations using the engine implementation. Test singular inversion, invalid-input preservation, exact alias equality, 2D/3D flags and homogeneous point transforms.
- [ ] Generate shared contracts and implement browser/native providers. Run focused raw/native JIT/AOT/Chromium cases before a combined batch.
- [ ] Review old ABI compatibility, retained-handle cleanup and public F# signatures, then stack the next unpublished package cohort behind Native15. Accept only after platform and official consumer evidence.

## Source constraints

DOMRectReadOnly, DOMPointReadOnly and DOMMatrixReadOnly use NoVirtualDestructorBase; mutable subclasses add no runtime discriminator. An external handle ledger may track trusted concrete producers and C-ABI retain counts, without owning additional engine/document references. All nested owned-result release paths must participate. Read-only exposure cannot upgrade an unknown object.

DOMQuadInit contains nested DOMPointInit dictionaries. Null or absent nested input must retain WebIDL defaults, including point w=1. DOMMatrixInit aliases preserve absence; the engine validates same-value-zero equality and is2D consistency. Singular inverse yields NaNs, and transformPoint does not divide by w.

No geometry binding or runtime acceptance is claimed by this planning checkpoint.

## Nested dictionary checkpoint

The focused test first failed because takeQuad was omitted for unsupported nested dictionaries. Opted-in nonnullable fields with an empty dictionary default now borrow a child input pointer. Parent and child independently check their size before reading each field; absent children retain the engine aggregate defaults. Required, nullable or absence-sensitive nested fields remain explicitly unsupported. No production dictionary has been opted in yet.

All 52 generator tests pass. Production generation check is unchanged at 138 interfaces, 1,739 functions, 20 handle roots and 16 dictionaries. Independent source review found no blocker. Null child pointers, short child structs and default w=1 still require execution in the eventual native quad fixture.
