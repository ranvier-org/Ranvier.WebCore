# Stylesheet named lookup browser facade repair

The public Fable facade emits ordinary JavaScript property access for StyleSheetList.namedItem. Actual published alpha.11 tests fail for length/item/0/__proto__: results have the wrong type or identify the indexed sheet. Native normal/traced probes correctly return the HTML style sheet selected by document ID or null.

## Contract

Pinned StyleSheetList.cpp93-107 performs document.getElementById(name), accepts only HTMLStyleElement, and returns its sheet. Shadow-root/document-less lists return null. The first document ID wins; a preceding non-style duplicate blocks a later style. Link/SVG style/name attributes are excluded. Preserve this native extension without arbitrary JavaScript property lookup or scanning owner IDs as the lookup algorithm.

The typed document stylesheet getter records a WeakRef to the document in a per-realm WeakMap and, where permitted, a non-enumerable own Symbol property on the list. The versioned symbol enables facade code executing in another realm to recover the same weak association. It returns the original list. This covers detached Chromium documents whose list was populated while empty, then retains zero entries despite inserted style elements having sheets. A nonempty list received from external JavaScript can also recover its document through a sheet owner; the list must be the document's list. Shadow-root lists return null. Use namespace/localName rather than ambient-realm instanceof. Preserve null results and object identity.

DOMStringMap.namedItem also emitted ordinary property access. Published browser probes returned inherited functions/prototypes for missing reserved names, while native returns an empty string. The browser facade must read own dataset keys and return an empty string for missing keys, preserving setter/deleter behavior and the map's prototype.

## Tasks

- [x] Add focused generator regressions and an actual compiled Fable fixture covering reserved/numeric names, ordinary names, missing/null, first non-style duplicate, link/SVG exclusion, empty/document/shadow-root lists, live changes and SVG/MathML dataset missing/present/deleted keys.
- [x] Repair canonical gen/interfaces.py. Generated output changes only browser Emit attributes; native model, signatures and ABI21/1702 functions are unchanged. Core regeneration/publication remains below.
- [x] Run complete generator tests and the real Chromium fixture; prove the unchanged baseline facade fails and the generated repaired facade passes. Check pinned native source semantics for added cases.
- [ ] Publish the Core follow-up with appropriate version/source checks and permanent regression coverage, using normal/traced native/Fable gates. Keep Views geometry/CSSOM and native keyframe releases independent.

## Review focus

Document association must not turn shadow-root lookup into document lookup. Numeric names must never become indexes. Prototype names must never return inherited values. Duplicate IDs and non-style elements must use getElementById's first match. Avoid cross-realm instanceof and selector parsing. Browser-only emission must leave native ABI21 and1702 functions unchanged.

## Local evidence

The generated facade compiled with Fickl 0.6.9 / Fable 5.24.0 and passed 121 assertions in the installed Chromium 1248 binary. The fixture includes a detached document, a same-origin iframe document, and independent facade modules executing in the parent and iframe realms with lookups in both directions. All 34 generator tests pass; canonical generation reports 128 interfaces, 1702 functions and zero stubs. The prior first-sheet document inference failed 15 assertions in the detached-document case and was replaced by explicit association. These local results do not establish hosted CI, publication or official consumer acceptance.

The same fixture compiled against unchanged HEAD contracts executes all 121 assertions and fails 63, including reserved-property/prototype leaks, numeric aliasing, shadow-root lookup and missing dataset values. The repaired .NET contracts compile for net10.0 and netstandard2.1 with zero warnings/errors; the existing complete Fable contract fixture passes. Generated layout, deterministic generation, and the new fixture's XML audit pass.

An empty list supplied directly by external JavaScript must first be obtained through the typed document stylesheet getter to establish its association. The public shared API does this automatically. The Symbol metadata is observable through Reflect.ownKeys; ordinary string-key enumeration and the platform list/prototype identity are preserved. Registry values and Symbol metadata hold WeakRef objects rather than strong Document values; deterministic garbage-collection behavior remains unverified. If a provider permits freezing an unassociated empty list, its typed getter can register it locally, but another realm cannot universally recover that association. The tested Chromium provider refuses preventing extensions on a real StyleSheetList, so no frozen-host result is claimed.
