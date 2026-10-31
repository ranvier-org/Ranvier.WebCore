/// Checks the managed NodeFilter wrapper (Traversal.fs): filter exceptions rethrown after the native call with their
/// identity and the traversal state kept, InvalidStateError for re-entrant traversal, filter identity, and release of
/// the managed function after the last native reference.
module RanvierWebCoreAbi.TraversalProbe

open System
open RanvierWebCoreAbi.Native
open RanvierWebCoreAbi.NativeDom
open RanvierWebCoreAbi.Traversal

let private html =
    "<!doctype html><html><body><div id=root><p id=a></p><p id=b><i id=b1></i></p><p id=c></p></div></body></html>"

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

let private idOf (node: nativeint) =
    if node = 0n then
        null
    else
        readString "element_get_id" (fun buffer capacity length ->
            rv_dom_element_get_id (node, buffer, capacity, length))

let private exceptionName () =
    readString "last_exception" (fun buffer capacity length -> rv_last_exception (0, buffer, capacity, length))

let private release (node: nativeint) =
    if node <> 0n then
        rv_node_release node

/// Steps a walker through the managed wrapper and returns the id of the node it reaches.
let private step (walker: nativeint) =
    let mutable node = 0n
    traversing "tree_walker_next_node" (fun () -> rv_dom_tree_walker_next_node (walker, &node))
    let id = idOf node
    release node
    id

let private current (walker: nativeint) =
    let mutable node = 0n

    rv_dom_tree_walker_get_current_node (walker, &node)
    |> check "tree_walker_get_current_node"

    let id = idOf node
    release node
    id

let private collect () =
    GC.Collect()
    GC.WaitForPendingFinalizers()
    GC.Collect()

/// The filter's function is reachable only through the native filter; the weak reference observes its release.
let private walkerWith
    (document: nativeint)
    (root: nativeint)
    (make: (unit -> nativeint) -> nativeint -> FilterResult)
    =
    let walker = ref 0n
    let filter = make (fun () -> walker.Value)
    let weak = WeakReference filter
    use handle = NodeFilter.Create(document, filter)
    let mutable created = 0n

    rv_dom_document_create_tree_walker (document, root, uint32 RV_DOM_NODE_FILTER_SHOW_ELEMENT, handle.Handle, &created)
    |> check "document_create_tree_walker"

    walker.Value <- created
    created, weak, handle.Handle

let run (_: string) =
    use host = new Host(100, 100)
    host.LoadHtml html
    use root = host.GetElementById "root"
    let mutable document = 0n

    rv_dom_node_get_owner_document (root.Handle, &document)
    |> check "node_get_owner_document"

    // A filter exception surfaces from the traversal call as the same exception object, after native returns;
    // the walker stays on the node it held, and the next call revisits the node that threw.
    let failure = InvalidOperationException "filter failure on b"
    let thrown = ref 0

    let walker, weak, filterHandle =
        walkerWith document root.Handle (fun _ node ->
            if idOf node = "b" && thrown.Value = 0 then
                thrown.Value <- 1
                raise failure

            FilterResult.Accept)

    require (step walker = "a") "walker reaches a"

    let caught =
        try
            step walker |> ignore
            None
        with error ->
            Some error

    require (obj.ReferenceEquals(caught.Value, failure)) $"filter exception rethrown as itself: {caught}"
    require (caught.Value.StackTrace.Contains "TraversalProbe") "rethrown exception keeps the filter's stack"
    require (current walker = "a") "walker state kept after a throwing filter"
    require (step walker = "b") "walker revisits the node after the failure"

    let mutable reported = 0n

    rv_dom_tree_walker_get_filter (walker, &reported)
    |> check "tree_walker_get_filter"

    require (reported = filterHandle) "filter getter returns the created filter"
    require (NodeFilter.FunctionOf(reported).IsSome) "filter getter maps back to the managed function"
    rv_dom_node_filter_release reported

    // Re-entrant traversal of the same walker throws InvalidStateError inside the filter; the outer call continues.
    let inner = ref ""

    let reentrant, _, _ =
        walkerWith document root.Handle (fun walkerOf node ->
            if idOf node = "b" && inner.Value = "" then
                let mutable nested = 0n
                let status = rv_dom_tree_walker_next_node (walkerOf (), &nested)
                inner.Value <- if status = -3 then exceptionName () else $"status {status}"

            FilterResult.Accept)

    require (step reentrant = "a" && step reentrant = "b") "re-entrant walker continues"
    require (inner.Value = "InvalidStateError") $"re-entrant traversal: {inner.Value}"

    // Skip and Reject: skipping b descends into it; rejecting b prunes b1.
    let pruned, _, _ =
        walkerWith document root.Handle (fun _ node ->
            if idOf node = "b" then
                FilterResult.Reject
            else
                FilterResult.Accept)

    let skipped, _, _ =
        walkerWith document root.Handle (fun _ node ->
            if idOf node = "b" then
                FilterResult.Skip
            else
                FilterResult.Accept)

    let order walker =
        List.unfold
            (fun () ->
                match step walker with
                | null -> None
                | id -> Some(id, ()))
            ()

    require (order pruned = [ "a"; "c" ]) "reject prunes the subtree"
    require (order skipped = [ "a"; "b1"; "c" ]) "skip descends into the subtree"

    // An out-of-range result is a filter failure, rethrown as ArgumentOutOfRangeException.
    let invalid, _, _ =
        walkerWith document root.Handle (fun _ _ -> enum<FilterResult> 7)

    let outOfRange =
        try
            step invalid |> ignore
            false
        with :? ArgumentOutOfRangeException ->
            true

    require outOfRange "an out-of-range filter result fails the traversal"

    // The managed function is released once the walker, the last native reference, is released.
    collect ()
    require weak.IsAlive "filter function alive while the walker holds the filter"

    for walker in [ walker; reentrant; pruned; skipped; invalid ] do
        rv_dom_tree_walker_release walker

    collect ()
    require (not weak.IsAlive) "filter function released after the walker"
    rv_node_release document
    printfn "RANVIER_TRAVERSAL_MANAGED PASS"
