# D01 filtered tree traversal plan

**Goal:** Expose `Document.createTreeWalker`/`createNodeIterator`, `TreeWalker`, `NodeIterator` and `NodeFilter`, all through the pinned engine's own traversal code. Prove that a mixed node tree traverses in the same order as a measured browser for `whatToShow` and for filter accept/skip/reject, and that roots and filter callbacks are released after disposal. Tracking issue: Ranvier.WebCore #17, engine route.

**Tree:** `C:/wk/native-traversal`, branch `codex/native-api-traversal`, from PR135 head `aaaf8dc` (Native23/ABI31). There is no allocation until freeze. This lane takes Native25/ABI33 after a fresh absence check; Native24 is I02's.

## Pinned source scope

`dom/NodeFilter.idl` is a callback interface: `acceptNode(Node) -> unsigned short`, three FILTER_* constants and thirteen SHOW_* constants. `dom/TreeWalker.idl` has `root`, `whatToShow`, `filter`, `currentNode` (read/write), `parentNode`, `firstChild`, `lastChild`, `previousSibling`, `nextSibling`, `previousNode` and `nextNode`. `dom/NodeIterator.idl` has `root`, `referenceNode`, `pointerBeforeReferenceNode`, `whatToShow`, `filter`, `nextNode`, `previousNode` and `detach`. `Document.idl` has `createNodeIterator(root, whatToShow = SHOW_ALL, filter = null)` and `createTreeWalker(...)`. Today the generator leaves both factories out because of the `NodeFilter` callback argument.

## Is a native filter callback needed?

Yes. Acceptance requires filter accept/skip/reject cases and callback-handle release, and `whatToShow` alone cannot express FILTER_REJECT (pruning a subtree in TreeWalker) or FILTER_SKIP. A whatToShow-only surface would still be a real subset, since a null filter is legal IDL, but it would not meet D01. The shared contract question for root is below.

Proposed host-side filter:
- `typedef int32_t (*RvNodeFilterCallback)(void* context, RvNode* node)` returns 1, 2 or 3. Any other value marks the filter as failed. The engine's traversal then stops with the existing `CallbackResultType::ExceptionThrown` path, and the calling traversal function returns a failure status, mirroring `RvEventCallback` failure semantics. The node is borrowed for the duration of the call.
- `RvNodeFilter* rv_node_filter_create(RvNode* document, RvNodeFilterCallback, void* context, void (*release)(void*))` creates a refcounted native subclass of WebCore's `NodeFilter`/`ActiveDOMCallback`, bound to the document's `ScriptExecutionContext`. The release callback runs exactly once, when the engine drops its last reference: after the walker or iterator, and any filter getter results, are released. It runs on the owning thread. `rv_node_filter_release` drops the caller's handle.
- `filter` getters return the same `RvNodeFilter*` (identity), or NULL for a null filter.
- Reentrancy uses the engine's existing `NodeIteratorBase` active flag. A callback that starts another traversal on the same object gets InvalidStateError. DOM mutation inside a callback is allowed, as the engine allows.

This is new hand-written host glue (one subclass and three exports) beside the generated bindings. It is not a generator change to callback interfaces in general. The generated factories take `RvNodeFilter*` through a single generator config entry.

## Generated surface

Select `TreeWalker` and `NodeIterator` (new refcounted value roots), the two `Document` factories, `NodeFilter` constants (shared constant projection, as with SVGUnitTypes) and the `filter` getters. Output preservation, null/thread/subtype errors and the existing UTF-8 string protocol are unchanged. `currentNode` set takes a non-null node; a null node returns a TypeError. `detach()` is a no-op in the pinned engine and in browsers, and it is tested as such.

## Proof

1. **RED:** factories are absent in Native23. Then a Chromium oracle over one mixed fixture (elements, text, comments, a processing instruction, a CDATA-less HTML document fragment, an attribute-free shadow-less tree) records:
   - order for `whatToShow` masks (ALL, ELEMENT, TEXT, COMMENT, ELEMENT|COMMENT);
   - filter results by tag: accept, skip and reject (reject prunes in TreeWalker and acts as skip in NodeIterator);
   - every walker step method from several `currentNode` positions;
   - iterator `referenceNode`/`pointerBeforeReferenceNode` across removal of the reference node and its ancestors (the NodeIterator pre-removal steps);
   - an exception-throwing filter;
   - a filter that mutates the tree.
2. **Native** `tests/abi/tree_traversal.py` must match the oracle exactly, plus:
   - `filter` identity;
   - a callback count equal to the browser's acceptNode calls;
   - a failure status that matches the browser's exception propagation, with state preserved;
   - InvalidStateError on reentrant traversal;
   - null/thread/subtype errors.
3. **Lifetime:** release counters prove that the filter's release callback runs exactly once, after the walker, iterator and filter handles are released. This holds whether they are released before or after host destroy and document replacement, with per-entry bookkeeping. Roots and reference nodes expire. New Teardown.fs cases cover a walker and an iterator held past destroy.
4. The final full batch, the gates, the absence check, Native25/ABI33, evidence, and a PR stacked on #135, refs #17.

## Decisions (root, 2026-10-31)

1. One API with an optional managed filter: the contract declares `NodeFilter = Node -> NodeFilterResult` (an integer enumeration equal to FILTER_*), `createTreeWalker`/`createNodeIterator` take `root * ?whatToShow * ?filter`, and the `filter` getters return `NodeFilter option`. No filter is the whatToShow-only form. The acceptNode object form is browser-only.
2. Host exports: `rv_node_filter_create` and the identity export `rv_node_filter_context`; release and retain are the generated `rv_dom_node_filter_release`/`_retain` of the `callbackObjectRoots` handle root. A failing callback stops the traversal as a throwing filter does: RV_ERR_DOM_EXCEPTION, with `rv_last_exception` naming ExistingExceptionError. Managed exceptions are caught, stored and rethrown after the native call (`Traversal.traversing`), never unwound through native frames.
3. Re-entrant NodeIterator keeps the engine behaviour, as a measured qualification: the inner call throws InvalidStateError and the results match Chromium; afterwards the reference node is null (the DOM standard continues the iteration), and native reads it as NULL where Chromium 156's renderer crashes.
4. Native25/ABI33, stacked on I02 (#136), which carries Native24/ABI32.
