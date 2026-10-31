/// Probes what keeps a document and its nodes alive after the host's destruction. Each probe runs one action on a fresh
/// host, destroys the host, and reads the watched nodes before and after a run-loop cycle.
module RanvierWebCoreAbi.Teardown

open System.IO
open System.Text.Json
open RanvierWebCoreAbi.Native
open RanvierWebCoreAbi.NativeDom

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

/// Checks that run once the watched nodes are collected, then release the value handles they hold.
let private afterCollection = ResizeArray<unit -> unit> ()

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

    for check in afterCollection do
        check ()

    afterCollection.Clear ()
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

let private svgPaint =
    "<!doctype html><html><body><svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'><defs>"
    + "<linearGradient id='gradient' x1='1'/><pattern id='pattern' width='4' height='4'/>"
    + "<filter id='filter'><feGaussianBlur id='blur' stdDeviation='2'/></filter>"
    + "<clipPath id='clip'><rect width='5' height='5'/></clipPath><mask id='mask' x='3'/><marker id='marker' orient='30'/>"
    + "</defs><rect id='painted' width='20' height='20' fill='url(#gradient)' filter='url(#filter)' clip-path='url(#clip)' mask='url(#mask)'/>"
    + "<use id='use' href='#painted' x='5'/><image id='image' href='"
    + gif
    + "' width='4' height='4'/></svg></body></html>"

let private element (host: nativeint) (id: string) =
    let node = rv_document_get_element_by_id (host, id)

    if node = 0n then
        failwithf "missing SVG element %s" id

    node

let private handleOf (name: string) (getter: nativeint -> nativeint ref -> int) (target: nativeint) =
    let result = ref 0n

    if getter target result <> 0 || result.Value = 0n then
        failwithf "%s failed" name

    result.Value

/// Loads the SVG paint fixture, retains a typed value handle from each S08-S11 group, and, when <c>replace</c> is set,
/// replaces the document before the host is destroyed. The handles stay readable and writable after collection.
let private svgPaintHandles (replace: bool) (host: nativeint) (_: nativeint) (_: nativeint) =
    rv_host_load_html (host, svgPaint) |> check "load SVG paint"
    cycle ()
    let take id = element host id
    let gradient = take "gradient"
    let ids = [ "pattern"; "blur"; "clip"; "mask"; "marker"; "use"; "image" ]
    let nodes = ids |> List.map take
    let pattern, blur, clip, mask, marker, useNode, image =
        match nodes with
        | [ a; b; c; d; e; f; g ] -> a, b, c, d, e, f, g
        | _ -> failwith "SVG paint nodes"

    let x1 = handleOf "gradient x1" (fun t r -> rv_dom_svg_linear_gradient_element_get_x1 (t, &r.contents)) gradient
    let width = handleOf "pattern width" (fun t r -> rv_dom_svg_pattern_element_get_width (t, &r.contents)) pattern
    let deviation = handleOf "blur stdDeviationX" (fun t r -> rv_dom_svgfe_gaussian_blur_element_get_std_deviation_x (t, &r.contents)) blur
    let units = handleOf "clipPathUnits" (fun t r -> rv_dom_svg_clip_path_element_get_clip_path_units (t, &r.contents)) clip
    let maskX = handleOf "mask x" (fun t r -> rv_dom_svg_mask_element_get_x (t, &r.contents)) mask
    let angle = handleOf "marker orientAngle" (fun t r -> rv_dom_svg_marker_element_get_orient_angle (t, &r.contents)) marker
    let useX = handleOf "use x" (fun t r -> rv_dom_svg_use_element_get_x (t, &r.contents)) useNode
    let href = handleOf "image href" (fun t r -> rv_dom_svg_image_element_get_href (t, &r.contents)) image
    let x1Base = handleOf "gradient x1 baseVal" (fun t r -> rv_dom_svg_animated_length_get_base_val (t, &r.contents)) x1

    for node in nodes do
        rv_node_release node

    if replace then
        rv_host_load_html (host, html) |> check "replace SVG paint document"
        cycle ()

    afterCollection.Add (fun () ->
        rv_dom_svg_length_set_value (x1Base, 7.0f) |> check "retained gradient length write"
        let mutable value = 0.0f
        rv_dom_svg_length_get_value (x1Base, &value) |> check "retained gradient length read"

        if value <> 7.0f then
            failwithf "retained gradient length reads %f" value

        rv_dom_svg_animated_number_set_base_val (deviation, 3.0f) |> check "retained blur write"
        let mutable deviationValue = 0.0f
        rv_dom_svg_animated_number_get_base_val (deviation, &deviationValue) |> check "retained blur read"

        if deviationValue <> 3.0f then
            failwithf "retained blur reads %f" deviationValue

        let mutable unitValue = 0us
        rv_dom_svg_animated_enumeration_get_base_val (units, &unitValue) |> check "retained clip units read"
        rv_dom_svg_animated_string_set_base_val (href, "data:,") |> check "retained image href write"
        rv_dom_svg_length_release x1Base

        for animated in [ x1; width; maskX; useX ] do
            rv_dom_svg_animated_length_release animated

        rv_dom_svg_animated_number_release deviation
        rv_dom_svg_animated_enumeration_release units
        rv_dom_svg_animated_angle_release angle
        rv_dom_svg_animated_string_release href)

    gradient

/// Appends a div with a child span, takes one extra handle of the kind from the div (removing the div first when
/// <c>remove</c> is set), destroys the host, then releases that handle. The document and the div must be destroyed
/// after collection whatever the destroy order.
let private releaseAfterDestroy (kind: string) (remove: bool) =
    let host = rv_host_create (64, 64)
    rv_host_load_html (host, html) |> check "load_html"
    let document = rv_host_document host
    let body = rv_document_body host
    let div = rv_document_create_element (host, "div")
    let span = rv_document_create_element (host, "span")
    rv_node_append_child (div, span) |> check "append span"
    rv_node_append_child (body, div) |> check "append div"
    let held = ref 0n

    let release =
        match kind with
        | "node" ->
            held.Value <- rv_node_retain div
            fun () -> rv_node_release held.Value
        | "dataset" ->
            rv_dom_html_element_get_dataset (div, &held.contents) |> check "dataset"
            fun () -> rv_dom_dom_string_map_release held.Value
        | _ ->
            rv_dom_html_element_get_attribute_style_map (div, &held.contents) |> check "attributeStyleMap"
            fun () -> rv_dom_style_property_map_read_only_release held.Value

    if held.Value = 0n then
        failwithf "no %s handle" kind

    if remove then
        rv_node_remove div |> check "remove"

    let documentWatch = rv_node_watch document
    let divWatch = rv_node_watch div
    rv_node_release span
    rv_node_release div
    rv_node_release body
    rv_node_release document
    rv_host_destroy host
    cycle ()
    let documentAfterDisposal = refsOf documentWatch
    let divAfterDisposal = refsOf divWatch
    release ()
    cycle ()
    let documentAfterCycle = refsOf documentWatch
    let divAfterCycle = refsOf divWatch
    cycleFor longCycleMilliseconds
    let documentAfterLongCycle = refsOf documentWatch
    let divAfterLongCycle = refsOf divWatch
    rv_collect_garbage ()

    let result =
        {
            probe = (if remove then "removed div, " else "div, ") + kind + " released after host destroy"
            cycleBeforeDisposal = "none"
            documentRefsAfterDisposal = documentAfterDisposal
            targetRefsAfterDisposal = divAfterDisposal
            documentRefsAfterCycle = documentAfterCycle
            targetRefsAfterCycle = divAfterCycle
            documentRefsAfterLongCycle = documentAfterLongCycle
            targetRefsAfterLongCycle = divAfterLongCycle
            documentRefsAfterCollection = refsOf documentWatch
            targetRefsAfterCollection = refsOf divWatch
        }

    rv_watch_release documentWatch
    rv_watch_release divWatch
    result

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
                probe "SVG paint handles retained past host destroy" cycleBefore (svgPaintHandles false)
                probe "SVG paint handles retained past document replacement" cycleBefore (svgPaintHandles true)

            for kind in [ "node"; "dataset"; "style map" ] do
                for remove in [ false; true ] do
                    releaseAfterDestroy kind remove
        ]

    let json =
        JsonSerializer.Serialize (results, JsonSerializerOptions (WriteIndented = true))

    File.WriteAllText (Path.Combine (outDir, "teardown-probes.json"), json)
    printfn "RANVIER_TEARDOWN_PROBES %s" (JsonSerializer.Serialize results)
