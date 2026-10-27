/// Probes what keeps a document and its nodes alive after the host's destruction. Each probe runs one action on a fresh
/// host, destroys the host, and reads the watched nodes before and after a run-loop cycle.
module RanvierWebCoreAbi.Teardown

open System.IO
open System.Text.Json
open RanvierWebCoreAbi.Native

let private html = "<!doctype html><html><head></head><body></body></html>"

let private valueProperty = 6

let private titleProperty = 8

let private cycleMilliseconds = 20

let private longCycleMilliseconds = 1000

/// The references beyond the reading handle of a watched node, or -1 once WebCore destroyed it.
let private refsOf (watch: nativeint) =
    if watch = 0n then
        -1
    else
        let node = rv_watch_node watch

        if node = 0n then
            -1
        else
            let count = rv_node_ref_count node - 1
            rv_node_release node
            count

let private cycleFor (milliseconds: int) =
    if rv_run_loop_cycle milliseconds < 0 then
        failwith "run_loop_cycle failed"

let private cycle () =
    cycleFor cycleMilliseconds

/// A one-pixel GIF.
let private gif =
    "data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="

type ProbeResult =
    {
        probe: string
        /// "none", "single" (one RunLoop::cycle) or "20 ms".
        cycleBeforeDisposal: string
        documentRefsAfterDisposal: int
        targetRefsAfterDisposal: int
        documentRefsAfterCycle: int
        targetRefsAfterCycle: int
        documentRefsAfterLongCycle: int
        targetRefsAfterLongCycle: int
        documentRefsAfterCollection: int
        targetRefsAfterCollection: int
    }

/// Runs the action on a fresh host, with the host, its document and its body; the action returns the node it targets,
/// or 0. A node reads -1 once WebCore destroyed it.
let private probe (name: string) (cycleBefore: string) (action: nativeint -> nativeint -> nativeint -> nativeint) =
    let host = rv_host_create (64, 64)

    rv_host_load_html (host, html)
    |> check "load_html"

    let document = rv_host_document host
    let body = rv_document_body host
    let target = action host document body
    let documentWatch = rv_node_watch document

    let targetWatch = if target = 0n then 0n else rv_node_watch target

    if target <> 0n then
        rv_node_release target

    rv_node_release body
    rv_node_release document

    match cycleBefore with
    | "single" -> cycleFor 0
    | "20 ms" -> cycle ()
    | _ -> ()

    rv_host_destroy host
    let documentAfterDisposal = refsOf documentWatch
    let targetAfterDisposal = refsOf targetWatch
    cycle ()

    let result =
        {
            probe = name
            cycleBeforeDisposal = cycleBefore
            documentRefsAfterDisposal = documentAfterDisposal
            targetRefsAfterDisposal = targetAfterDisposal
            documentRefsAfterCycle = refsOf documentWatch
            targetRefsAfterCycle = refsOf targetWatch
            documentRefsAfterLongCycle = 0
            targetRefsAfterLongCycle = 0
            documentRefsAfterCollection = 0
            targetRefsAfterCollection = 0
        }

    if rv_run_loop_cycle longCycleMilliseconds < 0 then
        failwith "run_loop_cycle failed"

    let result =
        { result with
            documentRefsAfterLongCycle = refsOf documentWatch
            targetRefsAfterLongCycle = refsOf targetWatch
        }

    rv_collect_garbage ()

    let result =
        { result with
            documentRefsAfterCollection = refsOf documentWatch
            targetRefsAfterCollection = refsOf targetWatch
        }

    rv_watch_release documentWatch

    if targetWatch <> 0n then
        rv_watch_release targetWatch

    result

/// Appends a new element of the tag to the body and focuses it.
let private focused (tag: string) (host: nativeint) (_: nativeint) (body: nativeint) =
    let element = rv_document_create_element (host, tag)

    rv_node_append_child (body, element)
    |> check "append_child"

    rv_element_focus element |> check "focus"
    element

/// Focuses an input inside a container under the body, then removes the container from the document.
let rec private inRemovedContainer (valueAttribute: bool) (host: nativeint) (document: nativeint) (body: nativeint) =
    removedFrom true valueAttribute host document body

/// Appends an input inside a container under the body, focuses it when <c>focus</c> is set, then removes the
/// container from the document.
and private removedFrom (focus: bool) (valueAttribute: bool) (host: nativeint) (_: nativeint) (body: nativeint) =
    let container = rv_document_create_element (host, "div")

    rv_node_append_child (body, container)
    |> check "append_child"

    let input = rv_document_create_element (host, "input")

    if valueAttribute then
        rv_element_set_attribute (input, "value", "x")
        |> check "set_attribute"

    rv_node_append_child (container, input)
    |> check "append_child"

    if focus then
        rv_element_focus input |> check "focus"

    rv_node_remove container |> check "remove"
    rv_node_release container
    input

/// Appends an image with the source to the body, and removes it from the document when <c>remove</c> is set.
let private image (source: string) (remove: bool) (host: nativeint) (_: nativeint) (body: nativeint) =
    let element = rv_document_create_element (host, "img")

    rv_element_set_attribute (element, "src", source)
    |> check "set_attribute"

    rv_node_append_child (body, element)
    |> check "append_child"

    if remove then
        rv_node_remove element |> check "remove"

    element

/// Runs each probe without a run-loop cycle before disposal, with a single cycle and with a 20 ms cycle, and writes
/// teardown-probes.json.
let run (outDir: string) =
    let results =
        [
            for cycleBefore in [ "none"; "single"; "20 ms" ] do
                probe "control" cycleBefore (fun _ _ _ -> 0n)

                probe "document title" cycleBefore (fun _ document _ ->
                    rv_node_set_string (document, titleProperty, "Probe")
                    |> check "set title"

                    0n)

                probe "focused input" cycleBefore (focused "input")
                probe "focused textarea" cycleBefore (focused "textarea")
                probe "focused button" cycleBefore (focused "button")

                probe "focused input, value written" cycleBefore (fun host document body ->
                    let input = focused "input" host document body

                    rv_node_set_string (input, valueProperty, "x")
                    |> check "set value"

                    input)

                probe "focused input, container removed" cycleBefore (inRemovedContainer false)
                probe "focused input with a value attribute, container removed" cycleBefore (inRemovedContainer true)
                probe "unfocused input, container removed" cycleBefore (removedFrom false false)

                probe "focused input removed" cycleBefore (fun host document body ->
                    let input = focused "input" host document body
                    rv_node_remove input |> check "remove"
                    input)

                probe "image with a data source" cycleBefore (image gif false)
                probe "image with a data source, removed" cycleBefore (image gif true)
                probe "image with a missing file source" cycleBefore (image "file:///C:/ranvier-missing.png" false)
                probe "image with a missing file source, removed" cycleBefore (image "file:///C:/ranvier-missing.png" true)
        ]

    let json =
        JsonSerializer.Serialize (results, JsonSerializerOptions (WriteIndented = true))

    File.WriteAllText (Path.Combine (outDir, "teardown-probes.json"), json)
    printfn "RANVIER_TEARDOWN_PROBES %s" (JsonSerializer.Serialize results)
