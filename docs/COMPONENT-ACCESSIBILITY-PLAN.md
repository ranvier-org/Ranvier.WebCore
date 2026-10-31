# I11 component accessibility plan

## Core and view state

- **Core primitives used:** none inside the native exports. A view that sets element relationships writes them from an
  effect, through the shared `Element.aria*Element(s)` members. A view that derives them from state uses
  `createEffectOnWithComparer`, so unchanged targets are skipped.
- **View-owned state:** none. The engine holds the explicitly set elements and the accessibility relations. The
  wrappers hold only native handles.

**Goal:** expose the ARIA element relationships that components use without duplicating the AX tree or the ARIA
string setters. That means the reflected element arrays, and the relationship targets of an accessible node. The
behaviour is compared against Chromium (Ranvier.WebCore #106).

**Trees:** native `C:/wk/native-elinternals`, branch `codex/native-api-element-internals`, from G03 `bb9195e`.
Reservation: Native41/ABI49, DOM alpha.44, Views 0.1.34, backend alpha.34.

## Scope

- Generated (`gen/dom.json` `elementArrayReflections`): the seven `[Reflect] FrozenArray<Element>?` members that both
  WebKit and Chromium 156 expose: `ariaActions`, `Controls`, `DescribedBy`, `Details`, `ErrorMessage`, `FlowTo` and
  `LabelledBy` `Elements`.
  - They are bound over `Element::getElementsArrayAttributeForBindings` and `setElementsArrayAttribute`.
  - The getter returns a snapshot sequence; present 0 means null. The setter takes a sequence, or NULL to clear.
  - `ariaActiveDescendantElement` was already bound.
  - `ariaOwnsElements` is left out, because Chromium 156 has no such member.
- `rv_ax_relations` (`accessibility-relations`): the targets of eight relation kinds of an accessible node.
  `docs/ACCESSIBILITY.md` documents its order, de-duplication and teardown.
- **Deferred: ElementInternals.** `HTMLElement::attachInternals` needs a custom element reaction queue and a defined or
  precustomized custom element. The scriptless host has no way to define one, because `CustomElementRegistry.define`
  takes a JavaScript constructor. ElementInternals therefore waits on D07 (custom element definition), browser side
  included, so that the shared contract stays the same on both engines. `red-chromium.json` records what Chromium does.

## Source patch 0039

`Element::setElementsArrayAttribute` called `updateRelations` once per element. Setting `[]` after a target therefore
left the relation on that target: the attribute was already "", so no attribute change refreshed it. The patch calls
`updateRelations` once per set. `red-0039-empty-relations.json` shows the stale relation for all six array kinds, and
`green-0039-empty-relations.json` shows them cleared.

## Proof

- `tests/abi/aria_relations.py` replays the oracle `tests/fixtures/aria-relations-oracle.json` (24 steps) and checks:
  - repeated reads;
  - `[]` for every array kind;
  - errors;
  - a removed target;
  - handles held past `rv_host_destroy`.
- The driver adds the `aria relations` Teardown case.
- Qualified against Chromium:
  - WebKit keeps a duplicate in a reflected array. The relations de-duplicate in both engines.
  - `ariaActionsElements` reports `RV_ERR_UNSUPPORTED`, because WebKit keeps `ARIAActionsSupportEnabled` off.
  - Each native read is a new snapshot, where Chromium returns one frozen array.
