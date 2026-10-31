/// Managed NodeFilter callbacks for the generated TreeWalker and NodeIterator functions of RanvierWebCoreDom.h.
module RanvierWebCoreAbi.Traversal

open System
open System.Runtime.ExceptionServices
open System.Runtime.InteropServices
open RanvierWebCoreAbi.Native
open RanvierWebCoreAbi.NativeDom

/// The result of a filter, equal to NodeFilter's FILTER_* constants.
type FilterResult =
    | Accept = 1
    | Reject = 2
    | Skip = 3

// Filter exceptions caught during the innermost traversal call, in the order they were raised.
let private filterFailures = ResizeArray<exn>()

let private invokeFilter (context: nativeint) (node: nativeint) =
    try
        let filter = GCHandle.FromIntPtr(context).Target :?> (nativeint -> FilterResult)

        match filter node with
        | FilterResult.Accept
        | FilterResult.Reject
        | FilterResult.Skip as result -> int result
        | other -> raise (ArgumentOutOfRangeException("filter", other, "a NodeFilter returns Accept, Reject or Skip"))
    with error ->
        filterFailures.Add error
        0

let private releaseFilter (context: nativeint) = GCHandle.FromIntPtr(context).Free()

let private filterCallback = NodeFilterCallback invokeFilter

let private filterCallbackPointer =
    Marshal.GetFunctionPointerForDelegate<_> filterCallback

let private filterRelease = NodeFilterRelease releaseFilter

let private filterReleasePointer =
    Marshal.GetFunctionPointerForDelegate<_> filterRelease

/// <summary>
/// Runs a traversal call. An exception thrown by a filter during the call is rethrown, with its original stack,
/// after the native call returns; it never unwinds through native frames. Otherwise the status is checked.
/// </summary>
let traversing (operation: string) (call: unit -> int) =
    let start = filterFailures.Count
    let status = call ()

    if filterFailures.Count > start then
        let error = filterFailures[start]
        filterFailures.RemoveRange(start, filterFailures.Count - start)
        ExceptionDispatchInfo.Capture(error).Throw()

    check operation status

/// <summary>
/// A host NodeFilter that calls a managed function with a borrowed node handle. Dispose drops the caller's reference;
/// walkers and iterators keep the filter alive, and the function is released after the last reference goes.
/// </summary>
type NodeFilter(handle: nativeint) =
    let mutable released = false

    member _.Handle = handle

    /// Creates a filter in the document of target.
    static member Create(target: nativeint, filter: nativeint -> FilterResult) =
        let context = GCHandle.Alloc filter

        let handle =
            rv_node_filter_create (target, filterCallbackPointer, GCHandle.ToIntPtr context, filterReleasePointer)

        if handle = 0n then
            context.Free()
            failwith "node_filter_create returned NULL"

        new NodeFilter(handle)

    /// The managed function of a host filter handle, or None for a filter the host did not create.
    static member FunctionOf(filter: nativeint) =
        let mutable context = 0n
        rv_node_filter_context (filter, &context) |> check "node_filter_context"

        if context = 0n then
            None
        else
            Some(GCHandle.FromIntPtr(context).Target :?> (nativeint -> FilterResult))

    interface IDisposable with
        member _.Dispose() =
            if not released then
                released <- true
                rv_dom_node_filter_release handle
