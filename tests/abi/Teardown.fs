/// Probes what keeps a document and its nodes alive after the host's destruction. Each probe runs one action on a fresh
/// host, destroys the host, and reads the watched nodes before and after a run-loop cycle. An image probe takes the
/// after-cycle read once the image's load has settled.
module RanvierWebCoreAbi.Teardown

open System
open System.IO
open System.Text.Json
open RanvierWebCoreAbi.Native
open RanvierWebCoreAbi.NativeDom

/// The UTF-8 bytes of a generated string input, passed with utf8Length of the same value.
let private utf8 (value: string) = System.Text.Encoding.UTF8.GetBytes value

let private utf8Length (value: string) = System.Text.Encoding.UTF8.GetByteCount value

let private html = "<!doctype html><html><head></head><body></body></html>"

/// A present dictionary string over pinned UTF-8 bytes, valid until the handle is freed.
let private stringInput (value: string) =
    let bytes = utf8 value
    let pin = Runtime.InteropServices.GCHandle.Alloc(bytes, Runtime.InteropServices.GCHandleType.Pinned)
    let mutable input = RvDomUtf8StringInput()
    input.present <- 1
    input.data <- pin.AddrOfPinnedObject()
    input.length <- bytes.Length
    input, pin

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

let private cycle () = cycleFor cycleMilliseconds

/// Checks that run once the watched nodes are collected, then release the value handles they hold.
let private afterCollection = ResizeArray<unit -> unit>()

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

/// The probe-name substring set by RANVIER_TEARDOWN_ONLY; unset or empty selects every probe.
let private only = Environment.GetEnvironmentVariable "RANVIER_TEARDOWN_ONLY"

let private selected (name: string) =
    String.IsNullOrEmpty only || name.Contains(only, StringComparison.Ordinal)

/// Cycles the run loop until WebCore destroys the watched image, which ends its load. The image's loader holds the image
/// until its pending load or error event and the zero-delay timer that releases the image have both run.
let private settleImageLoad (imageWatch: nativeint) =
    cycle ()
    let elapsed = Diagnostics.Stopwatch.StartNew()

    while refsOf imageWatch <> -1 do
        if elapsed.Elapsed > TimeSpan.FromSeconds 10.0 then
            failwith "image load still pending 10 s after host destroy"

        cycleFor 0

/// Runs the action on a fresh host, with the host, its document and its body; the action returns the node it targets,
/// or 0. After the host is destroyed, afterDestroy runs with the target's watch before the after-cycle read. A node
/// reads -1 once WebCore destroyed it.
let private probeWith
    (afterDestroy: nativeint -> unit)
    (name: string)
    (cycleBefore: string)
    (action: nativeint -> nativeint -> nativeint -> nativeint)
    =
    let host = rv_host_create (64, 64)

    rv_host_load_html (host, html) |> check "load_html"

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
    afterDestroy targetWatch

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

    afterCollection.Clear()
    rv_watch_release documentWatch

    if targetWatch <> 0n then
        rv_watch_release targetWatch

    result

/// Runs probeWith with a 20 ms cycle after host destroy, for a selected probe.
let private probe (name: string) (cycleBefore: string) action =
    if selected name then
        Some(probeWith (fun _ -> cycle ()) name cycleBefore action)
    else
        None

/// Runs probeWith on an image action; the after-cycle read follows the settled load.
let private imageProbe (name: string) (cycleBefore: string) action =
    if selected name then
        Some(probeWith settleImageLoad name cycleBefore action)
    else
        None

/// Appends a new element of the tag to the body and focuses it.
let private focused (tag: string) (host: nativeint) (_: nativeint) (body: nativeint) =
    let element = rv_document_create_element (host, tag)

    rv_node_append_child (body, element) |> check "append_child"

    rv_element_focus element |> check "focus"
    element

/// Focuses an input inside a container under the body, then removes the container from the document.
let rec private inRemovedContainer (valueAttribute: bool) (host: nativeint) (document: nativeint) (body: nativeint) =
    removedFrom true valueAttribute host document body

/// Appends an input inside a container under the body, focuses it when <c>focus</c> is set, then removes the
/// container from the document.
and private removedFrom (focus: bool) (valueAttribute: bool) (host: nativeint) (_: nativeint) (body: nativeint) =
    let container = rv_document_create_element (host, "div")

    rv_node_append_child (body, container) |> check "append_child"

    let input = rv_document_create_element (host, "input")

    if valueAttribute then
        rv_element_set_attribute (input, "value", "x") |> check "set_attribute"

    rv_node_append_child (container, input) |> check "append_child"

    if focus then
        rv_element_focus input |> check "focus"

    rv_node_remove container |> check "remove"
    rv_node_release container
    input

/// Appends an image with the source to the body, and removes it from the document when <c>remove</c> is set.
let private image (source: string) (remove: bool) (host: nativeint) (_: nativeint) (body: nativeint) =
    let element = rv_document_create_element (host, "img")

    rv_element_set_attribute (element, "src", source) |> check "set_attribute"

    rv_node_append_child (body, element) |> check "append_child"

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

    let x1 =
        handleOf "gradient x1" (fun t r -> rv_dom_svg_linear_gradient_element_get_x1 (t, &r.contents)) gradient

    let width =
        handleOf "pattern width" (fun t r -> rv_dom_svg_pattern_element_get_width (t, &r.contents)) pattern

    let deviation =
        handleOf
            "blur stdDeviationX"
            (fun t r -> rv_dom_svgfe_gaussian_blur_element_get_std_deviation_x (t, &r.contents))
            blur

    let units =
        handleOf "clipPathUnits" (fun t r -> rv_dom_svg_clip_path_element_get_clip_path_units (t, &r.contents)) clip

    let maskX =
        handleOf "mask x" (fun t r -> rv_dom_svg_mask_element_get_x (t, &r.contents)) mask

    let angle =
        handleOf "marker orientAngle" (fun t r -> rv_dom_svg_marker_element_get_orient_angle (t, &r.contents)) marker

    let useX =
        handleOf "use x" (fun t r -> rv_dom_svg_use_element_get_x (t, &r.contents)) useNode

    let href =
        handleOf "image href" (fun t r -> rv_dom_svg_image_element_get_href (t, &r.contents)) image

    let x1Base =
        handleOf "gradient x1 baseVal" (fun t r -> rv_dom_svg_animated_length_get_base_val (t, &r.contents)) x1

    for node in nodes do
        rv_node_release node

    if replace then
        rv_host_load_html (host, html) |> check "replace SVG paint document"
        cycle ()

    afterCollection.Add(fun () ->
        rv_dom_svg_length_set_value (x1Base, 7.0f)
        |> check "retained gradient length write"

        let mutable value = 0.0f

        rv_dom_svg_length_get_value (x1Base, &value)
        |> check "retained gradient length read"

        if value <> 7.0f then
            failwithf "retained gradient length reads %f" value

        rv_dom_svg_animated_number_set_base_val (deviation, 3.0f)
        |> check "retained blur write"

        let mutable deviationValue = 0.0f

        rv_dom_svg_animated_number_get_base_val (deviation, &deviationValue)
        |> check "retained blur read"

        if deviationValue <> 3.0f then
            failwithf "retained blur reads %f" deviationValue

        let mutable unitValue = 0us

        rv_dom_svg_animated_enumeration_get_base_val (units, &unitValue)
        |> check "retained clip units read"

        rv_dom_svg_animated_string_set_base_val (href, utf8 "data:,", utf8Length "data:,")
        |> check "retained image href write"

        rv_dom_svg_length_release x1Base

        for animated in [ x1; width; maskX; useX ] do
            rv_dom_svg_animated_length_release animated

        rv_dom_svg_animated_number_release deviation
        rv_dom_svg_animated_enumeration_release units
        rv_dom_svg_animated_angle_release angle
        rv_dom_svg_animated_string_release href)

    gradient

/// Creates a tree walker or node iterator over target with a host NodeFilter, and returns it with a weak reference
/// to the filter's managed function. The function lives only in the native filter, outside the caller's frame.
[<System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)>]
let private hostFilterTraversal (kind: string) (document: nativeint) (target: nativeint) =
    let owner = obj ()

    let filter =
        fun (_: nativeint) ->
            (if isNull owner then
                 Traversal.FilterResult.Skip
             else
                 Traversal.FilterResult.Accept)

    use handle = Traversal.NodeFilter.Create(target, filter)
    let mutable traversal = 0n

    if kind = "tree walker" then
        rv_dom_document_create_tree_walker (document, target, 0xFFFFFFFFu, handle.Handle, &traversal)
        |> check "create_tree_walker"
    else
        rv_dom_document_create_node_iterator (document, target, 0xFFFFFFFFu, handle.Handle, &traversal)
        |> check "create_node_iterator"

    traversal, WeakReference filter

let mutable private viewportCalls = 0

let private viewportDelegate =
    EventCallback(fun _ _ ->
        viewportCalls <- viewportCalls + 1
        0)

let private viewportCallback =
    System.Runtime.InteropServices.Marshal.GetFunctionPointerForDelegate viewportDelegate

/// Appends a div with a child span, takes one extra handle of the kind from the div (removing the div first when
/// <c>remove</c> is set), destroys the host, then releases that handle. The document and the div must be destroyed
/// after collection whatever the destroy order.
let private releaseName (kind: string) (remove: bool) =
    (if remove then "removed div, " else "div, ")
    + kind
    + " released after host destroy"

let private runReleaseAfterDestroy (kind: string) (remove: bool) =
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
        | "tree walker"
        | "node iterator" ->
            let traversal, weak = hostFilterTraversal kind document div
            held.Value <- traversal

            fun () ->
                if kind = "tree walker" then
                    rv_dom_tree_walker_release held.Value
                else
                    rv_dom_node_iterator_release held.Value

                GC.Collect()
                GC.WaitForPendingFinalizers()

                if weak.IsAlive then
                    failwithf "%s filter function alive after the traversal was released" kind
        | "window target"
        | "media query list" ->
            held.Value <-
                if kind = "window target" then
                    rv_host_window_event_target host
                else
                    rv_host_match_media (host, "(min-width: 10px)")

            let listener =
                rv_event_target_add_listener (
                    held.Value,
                    (if kind = "window target" then "resize" else "change"),
                    0,
                    viewportCallback,
                    0n
                )

            if listener = 0n then
                failwithf "no %s listener" kind

            fun () ->
                rv_listener_remove listener |> check "listener removal after destroy"
                rv_event_target_release held.Value

                if viewportCalls <> 0 then
                    failwithf "%s listener ran after host destroy" kind
        | "scrolled document" ->
            held.Value <- rv_node_retain document
            rv_element_set_style (body, "height", "2000px", 0) |> check "tall body"
            let window = rv_host_window_event_target host

            let listener =
                rv_event_target_add_listener (window, "scroll", 0, viewportCallback, 0n)

            if listener = 0n then
                failwith "no scroll listener"

            rv_dom_window_scroll_to_2 (held.Value, 0.0, 10.5) |> check "Window.scrollTo"
            let mutable y = -1.0
            rv_dom_window_get_scroll_y (held.Value, &y) |> check "Window.scrollY"

            if y <> 10.0 then
                failwithf "scrollY %f before destroy" y

            fun () ->
                let status = rv_dom_window_get_scroll_y (held.Value, &y)

                if not (status = -9 || (status = 0 && y = 0.0)) then
                    failwithf "Window.scrollY after destroy: %d %f" status y

                let scrolled = rv_dom_window_scroll_by_2 (held.Value, 0.0, 5.5)

                if scrolled <> 0 && scrolled <> -9 then
                    failwithf "Window.scrollBy after destroy: %d" scrolled

                rv_listener_remove listener |> check "scroll listener removal after destroy"
                rv_event_target_release window
                rv_node_release held.Value

                if viewportCalls <> 0 then
                    failwith "scroll listener ran after host destroy"
        | "coordinate spaces" ->
            rv_element_set_style (div, "width", "40px", 0) |> check "div width"
            rv_element_set_style (div, "height", "20px", 0) |> check "div height"

            rv_element_set_style (div, "transform", "rotate(30deg)", 0)
            |> check "div transform"

            held.Value <- rv_node_retain div
            let points = [| 0.0; 0.0 |]

            rv_node_convert_points (held.Value, 0, 0n, 1, &points[0], 1)
            |> check "node to page before destroy"

            let quad = Array.zeroCreate<float> 8

            rv_node_box_quad (held.Value, 0, 0n, 3, &quad[0])
            |> check "box quad before destroy"

            fun () ->
                let after = [| 1.0; 2.0 |]
                let status = rv_node_convert_points (held.Value, 0, 0n, 1, &after[0], 1)

                if status <> -10 || after <> [| 1.0; 2.0 |] then
                    failwithf "rv_node_convert_points after destroy: %d" status

                let quadStatus = rv_node_box_quad (held.Value, 0, 0n, 3, &quad[0])

                if quadStatus <> -10 then
                    failwithf "rv_node_box_quad after destroy: %d" quadStatus

                rv_node_release held.Value
        | "aria relations" ->
            rv_element_set_attribute (div, "id", "label") |> check "label id"
            rv_dom_node_set_text_content (div, utf8 "Label", utf8Length "Label") |> check "label text"
            let button = rv_document_create_element (host, "button")
            rv_node_append_child (body, button) |> check "append button"
            held.Value <- button
            let mutable value = RvDomSequenceElementNullable()

            let items =
                System.Runtime.InteropServices.GCHandle.Alloc(
                    [| div |],
                    System.Runtime.InteropServices.GCHandleType.Pinned
                )

            value.present <- 1
            value.count <- 1
            value.items <- items.AddrOfPinnedObject()

            rv_dom_element_set_aria_labelled_by_elements (button, [| value |])
            |> check "ariaLabelledByElements"

            items.Free()
            let mutable read = RvDomSequenceElementNullable()

            rv_dom_element_get_aria_labelled_by_elements (button, &read)
            |> check "ariaLabelledByElements read"

            if read.present <> 1 || read.count <> 1 then
                failwithf "ariaLabelledByElements %d %d before destroy" read.present read.count

            fun () ->
                let mutable after = RvDomSequenceElementNullable()
                let status = rv_dom_element_get_aria_labelled_by_elements (held.Value, &after)

                if status <> 0 then
                    failwithf "ariaLabelledByElements after destroy: %d" status

                rv_dom_sequence_element_nullable_release &after
                rv_dom_sequence_element_nullable_release &read
                rv_node_release held.Value
        | "visual viewport" ->
            rv_dom_window_get_visual_viewport (document, &held.contents)
            |> check "Window.visualViewport"

            let listener =
                rv_event_target_add_listener (held.Value, "resize", 0, viewportCallback, 0n)

            if listener = 0n then
                failwith "no visualViewport resize listener"

            rv_host_set_page_scale (host, 2.0, 0, 0) |> check "page scale 2"
            let mutable width = -1.0

            rv_dom_visual_viewport_get_width (held.Value, &width)
            |> check "VisualViewport.width"

            if width <> 32.0 then
                failwithf "VisualViewport.width %f at page scale 2" width

            fun () ->
                let status = rv_dom_visual_viewport_get_width (held.Value, &width)

                if status <> -10 then
                    failwithf "VisualViewport.width after destroy: %d" status

                rv_listener_remove listener
                |> check "visualViewport listener removal after destroy"

                rv_event_target_release held.Value

                if viewportCalls <> 0 then
                    failwith "visualViewport listener ran after host destroy"
        | "form controls collection"
        | "options collection"
        | "form data"
        | "submit event" ->
            let form = rv_document_create_element (host, "form")
            let select = rv_document_create_element (host, "select")
            let button = rv_document_create_element (host, "button")
            rv_node_append_child (form, select) |> check "append select"
            rv_node_append_child (form, button) |> check "append button"
            rv_node_append_child (div, form) |> check "append form"

            let releaseHeld =
                match kind with
                | "form controls collection" ->
                    rv_dom_html_form_element_get_elements (form, &held.contents) |> check "elements"
                    fun () -> rv_dom_html_collection_release held.Value
                | "options collection" ->
                    rv_dom_html_select_element_get_options (select, &held.contents)
                    |> check "options"

                    fun () -> rv_dom_html_collection_release held.Value
                | "form data" ->
                    rv_dom_dom_form_data_create (document, form, button, &held.contents)
                    |> check "FormData"

                    fun () -> rv_dom_dom_form_data_release held.Value
                | _ ->
                    let mutable init = RvDomSubmitEventInit()
                    init.size <- uint32 (Runtime.InteropServices.Marshal.SizeOf<RvDomSubmitEventInit>())
                    init.submitter <- button
                    let name = Text.Encoding.UTF8.GetBytes "submit"

                    rv_dom_submit_event_create (document, name, name.Length, [| init |], &held.contents)
                    |> check "SubmitEvent"

                    fun () -> rv_event_release held.Value

            rv_node_release button
            rv_node_release select
            rv_node_release form
            releaseHeld
        | "open modal dialog" ->
            let dialog = rv_document_create_element (host, "dialog")
            rv_node_append_child (div, dialog) |> check "append dialog"
            rv_dom_html_dialog_element_show_modal dialog |> check "showModal"
            held.Value <- dialog

            fun () ->
                let mutable isOpen = -1
                let status = rv_dom_html_dialog_element_get_open (held.Value, &isOpen)

                if status <> 0 && status <> -9 then
                    failwithf "HTMLDialogElement.open after destroy: %d" status

                let closed = rv_dom_html_dialog_element_close (held.Value, utf8 "late", utf8Length "late")

                if closed <> 0 && closed <> -9 && closed <> -3 then
                    failwithf "HTMLDialogElement.close after destroy: %d" closed

                rv_node_release held.Value
        | "blob slice" ->
            let data = Text.Encoding.UTF8.GetBytes "kept"

            let handle =
                Runtime.InteropServices.GCHandle.Alloc(data, Runtime.InteropServices.GCHandleType.Pinned)

            let mutable part = RvDomUnionBufferSourceOrBlobOrUSVString()
            part.present <- 1
            part.tag <- RV_DOM_UNION_BUFFER_SOURCE_OR_BLOB_OR_USV_STRING_BUFFER_SOURCE
            let mutable span = RvDomByteSpan()
            span.data <- handle.AddrOfPinnedObject()
            span.length <- data.Length
            part.arm0 <- span

            let parts =
                Runtime.InteropServices.GCHandle.Alloc([| part |], Runtime.InteropServices.GCHandleType.Pinned)

            let mutable sequence = RvDomSequenceBufferSourceOrBlobOrUSVString()
            sequence.present <- 1
            sequence.count <- 1
            sequence.items <- parts.AddrOfPinnedObject()
            let mutable options = RvDomFilePropertyBag()
            options.size <- uint32 (Runtime.InteropServices.Marshal.SizeOf<RvDomFilePropertyBag>())
            let name = Text.Encoding.UTF8.GetBytes "kept.txt"
            let mutable file = 0n

            rv_dom_file_create (document, [| sequence |], name, name.Length, [| options |], &file)
            |> check "File"

            parts.Free()
            handle.Free()
            let empty = [||]: byte array
            rv_dom_blob_slice (file, 1L, 3L, empty, 0, &held.contents) |> check "Blob.slice"
            let input = rv_document_create_element (host, "input")
            rv_element_set_attribute (input, "type", "file") |> check "type=file"
            rv_node_append_child (div, input) |> check "append input"
            let list = [| 0n |]
            rv_file_list_create ([| file |], 1, list) |> check "FileList"
            rv_dom_html_input_element_set_files (input, list[0]) |> check "input.files"
            rv_node_release input

            fun () ->
                let bytes = Array.zeroCreate<byte> 4
                let mutable length = 0L

                rv_blob_read_bytes (held.Value, bytes, 4L, &length)
                |> check "slice bytes after destroy"

                if Text.Encoding.UTF8.GetString(bytes, 0, int length) <> "ep" then
                    failwith "Blob.slice bytes changed after destroy"

                let mutable count = 0u

                rv_dom_file_list_get_length (list[0], &count)
                |> check "FileList.length after destroy"

                if count <> 1u then
                    failwith "FileList.length changed after destroy"

                rv_dom_file_list_release list[0]
                rv_dom_blob_release file
                rv_dom_blob_release held.Value
        | "blob reads" ->
            // A FileReader and an engine read in flight, and a revoked object URL, when the host is destroyed.
            let data = Array.zeroCreate<byte> (1 <<< 20)

            let handle =
                Runtime.InteropServices.GCHandle.Alloc(data, Runtime.InteropServices.GCHandleType.Pinned)

            let mutable part = RvDomUnionBufferSourceOrBlobOrUSVString()
            part.present <- 1
            part.tag <- RV_DOM_UNION_BUFFER_SOURCE_OR_BLOB_OR_USV_STRING_BUFFER_SOURCE
            let mutable span = RvDomByteSpan()
            span.data <- handle.AddrOfPinnedObject()
            span.length <- data.Length
            part.arm0 <- span

            let parts =
                Runtime.InteropServices.GCHandle.Alloc([| part |], Runtime.InteropServices.GCHandleType.Pinned)

            let mutable sequence = RvDomSequenceBufferSourceOrBlobOrUSVString()
            sequence.present <- 1
            sequence.count <- 1
            sequence.items <- parts.AddrOfPinnedObject()
            let mutable blob = 0n
            rv_dom_blob_create (document, [| sequence |], null, &blob) |> check "Blob"
            parts.Free()
            handle.Free()
            let buffer = Array.zeroCreate<byte> 256
            let length = [| 0 |]

            rv_dom_domurl_create_object_url (document, blob, buffer, buffer.Length, length)
            |> check "URL.createObjectURL"

            let url = buffer[0 .. length[0] - 1]
            rv_dom_domurl_revoke_object_url (document, url, url.Length) |> check "URL.revokeObjectURL"
            rv_dom_file_reader_create (document, &held.contents) |> check "FileReader"
            rv_dom_file_reader_read_as_array_buffer (held.Value, blob) |> check "readAsArrayBuffer"
            let outcomes = Collections.Generic.List<int>()
            let completion = ResourceCompletion(fun _ outcome _ _ -> outcomes.Add outcome)
            let pointer = Runtime.InteropServices.Marshal.GetFunctionPointerForDelegate completion
            let mutable pending = 0UL
            rv_blob_read (host, blob, 1, pointer, 0n, &pending) |> check "rv_blob_read"
            let mutable revoked = 0UL
            rv_blob_url_read (host, url, url.Length, pointer, 0n, &revoked) |> check "rv_blob_url_read"

            fun () ->
                // INVALIDATED for the read in flight; LOAD_FAILED for the revoked URL, at most once each.
                if outcomes.Count > 2 || not (outcomes.Contains 4) then
                    failwithf "reads at destroy: %A" (List.ofSeq outcomes)

                let mutable state = 0us
                let status = rv_dom_file_reader_get_ready_state (held.Value, &state)

                if status <> 0 && status <> -10 then
                    failwithf "FileReader.readyState after destroy: %d" status

                let mutable kind = 0
                let mutable bytes = 0L

                rv_file_reader_result (held.Value, &kind, null, 0L, &bytes)
                |> check "FileReader.result after destroy"

                if kind <> 0 then
                    failwithf "FileReader.result after destroy: kind %d" kind

                rv_resource_release pending |> check "release read"
                rv_resource_release revoked |> check "release URL read"
                GC.KeepAlive completion
                rv_event_target_release held.Value
                rv_dom_blob_release blob
        | "url values" ->
            let text = Text.Encoding.UTF8.GetBytes "https://held.test/a?b=c"

            rv_dom_domurl_create (document, text, text.Length, null, -1, &held.contents)
            |> check "URL"

            let mutable parameters = 0n

            rv_dom_domurl_get_search_params (held.Value, &parameters)
            |> check "URL.searchParams"

            fun () ->
                let mutable size = 0u

                rv_dom_url_search_params_get_size (parameters, &size)
                |> check "URLSearchParams.size after destroy"

                if size <> 1u then
                    failwith "URLSearchParams.size changed after destroy"

                let buffer = Array.zeroCreate<byte> 64
                let length = [| 0 |]

                rv_dom_domurl_get_href (held.Value, buffer, buffer.Length, length)
                |> check "URL.href after destroy"

                if Text.Encoding.UTF8.GetString(buffer, 0, length[0]) <> "https://held.test/a?b=c" then
                    failwith "URL.href changed after destroy"

                rv_dom_url_search_params_release parameters
                rv_dom_domurl_release held.Value
        | "url pattern result" ->
            let pattern = Text.Encoding.UTF8.GetBytes "https://h.test/held/:id"
            let target = Text.Encoding.UTF8.GetBytes "https://h.test/held/7"

            let memory =
                Runtime.InteropServices.Marshal.AllocHGlobal(pattern.Length + target.Length)

            Runtime.InteropServices.Marshal.Copy(pattern, 0, memory, pattern.Length)
            Runtime.InteropServices.Marshal.Copy(target, 0, memory + nativeint pattern.Length, target.Length)

            let input (offset: int) (length: int) =
                let mutable span = RvDomUtf8StringSpan()
                span.data <- memory + nativeint offset
                span.length <- length
                let mutable value = RvDomUnionUSVStringOrURLPatternInit()
                value.present <- 1
                value.tag <- 1
                value.arm0 <- span
                value

            rv_dom_url_pattern_create_2 (document, [| input 0 pattern.Length |], null, &held.contents)
            |> check "URLPattern"

            let mutable result = 0n

            rv_dom_url_pattern_exec (held.Value, [| input pattern.Length target.Length |], null, -1, &result)
            |> check "URLPattern.exec"

            Runtime.InteropServices.Marshal.FreeHGlobal memory

            fun () ->
                if result = 0n then
                    failwith "URLPattern.exec matched nothing"

                rv_dom_url_pattern_result_release result
                rv_dom_url_pattern_release held.Value
        | "toggle event" ->
            let button = rv_document_create_element (host, "button")
            rv_node_append_child (div, button) |> check "append button"
            let mutable init = RvDomToggleEventInit()
            init.size <- uint32 (Runtime.InteropServices.Marshal.SizeOf<RvDomToggleEventInit>())
            let oldState, oldPin = stringInput "closed"
            let newState, newPin = stringInput "open"
            init.old_state <- oldState
            init.new_state <- newState
            init.source <- button
            let name = Text.Encoding.UTF8.GetBytes "toggle"

            rv_dom_toggle_event_create (document, name, name.Length, [| init |], &held.contents)
            |> check "ToggleEvent"

            oldPin.Free()
            newPin.Free()

            rv_node_release button

            fun () ->
                let buffer = Array.zeroCreate<byte> 16
                let length = [| 0 |]

                rv_dom_toggle_event_get_new_state (held.Value, buffer, buffer.Length, length)
                |> check "ToggleEvent.newState after destroy"

                if Text.Encoding.UTF8.GetString(buffer, 0, length[0]) <> "open" then
                    failwith "ToggleEvent.newState changed after destroy"

                rv_event_release held.Value
        | "error event" ->
            let mutable init = RvDomErrorEventInit()
            init.size <- uint32 (Runtime.InteropServices.Marshal.SizeOf<RvDomErrorEventInit>())
            let message, messagePin = stringInput "boom"
            init.message <- message
            init.lineno <- 3u
            let name = Text.Encoding.UTF8.GetBytes "error"

            rv_dom_error_event_create (document, name, name.Length, [| init |], &held.contents)
            |> check "ErrorEvent"

            messagePin.Free()

            fun () ->
                let buffer = Array.zeroCreate<byte> 32
                let length = [| 0 |]

                rv_dom_error_event_get_message (held.Value, buffer, buffer.Length, length)
                |> check "ErrorEvent.message after destroy"

                if Text.Encoding.UTF8.GetString(buffer, 0, length[0]) <> "boom" then
                    failwith "ErrorEvent.message changed after destroy"

                rv_dom_event_get_interface_name (held.Value, buffer, buffer.Length, length)
                |> check "Event interface name after destroy"

                if Text.Encoding.UTF8.GetString(buffer, 0, length[0]) <> "ErrorEvent" then
                    failwith "ErrorEvent interface name changed after destroy"

                rv_event_release held.Value
        | "screen" ->
            let metrics = Runtime.InteropServices.Marshal.AllocHGlobal 36
            let values = [| 36; 1080; 1920; 0; 40; 1080; 1880; 30; 0 |]

            values
            |> Array.iteri (fun index value -> Runtime.InteropServices.Marshal.WriteInt32(metrics, index * 4, value))

            rv_host_set_screen (host, metrics) |> check "rv_host_set_screen"
            Runtime.InteropServices.Marshal.FreeHGlobal metrics
            let mutable width = 0
            rv_dom_screen_get_width (document, &width) |> check "screen.width"

            if width <> 1080 then
                failwithf "screen.width %d" width

            held.Value <- rv_node_retain document

            fun () ->
                let mutable kept = 0

                rv_dom_screen_get_width (held.Value, &kept)
                |> check "screen.width after destroy"

                // The document has no frame after destroy, and WebKit's Screen reports 0 without one.
                if kept <> 0 then
                    failwithf "screen.width after destroy %d" kept

                let mutable kind = -1

                rv_dom_screen_orientation_get_type (held.Value, &kind)
                |> check "orientation.type after destroy"

                rv_node_release held.Value
        | "diagnostics" ->
            let live = rv_diagnostic_live_count ()
            rv_host_set_diagnostics (host, 1) |> check "rv_host_set_diagnostics"
            let tree = [| 0n |]
            rv_host_inspect_render_tree (host, div, 0, tree) |> check "rv_host_inspect_render_tree"
            let rules = [| 0n |]
            rv_host_inspect_matched_rules (host, div, rules) |> check "rv_host_inspect_matched_rules"
            let length = [| 0 |]
            rv_diagnostic_text (tree[0], null, 0, length) |> ignore
            let size = length[0]

            if size <= 0 || rv_diagnostic_count rules[0] < 1 || rv_diagnostic_live_count () <> live + 2 then
                failwith "diagnostic snapshots before destroy"

            held.Value <- tree[0]

            fun () ->
                let buffer = Array.zeroCreate<byte> size
                rv_diagnostic_text (held.Value, buffer, buffer.Length, length) |> check "render tree text after destroy"

                if length[0] <> size || not (Text.Encoding.UTF8.GetString(buffer).StartsWith "RenderBlock {DIV}") then
                    failwith "render tree snapshot changed after destroy"

                if rv_diagnostic_count rules[0] < 1 || rv_diagnostic_kind rules[0] <> 2 then
                    failwith "matched-rules snapshot changed after destroy"

                rv_diagnostic_release held.Value
                rv_diagnostic_release rules[0]

                if rv_diagnostic_live_count () <> live then
                    failwith "diagnostic snapshots leaked"
        | "cascade diagnostics" ->
            let live = rv_diagnostic_live_count ()
            rv_host_set_diagnostics (host, 1) |> check "rv_host_set_diagnostics"
            let name = Text.Encoding.UTF8.GetBytes "display"
            let cascade = [| 0n |]

            rv_host_inspect_cascade (host, div, name, name.Length, cascade)
            |> check "rv_host_inspect_cascade"

            let count = rv_diagnostic_count cascade[0]

            if count < 1 || rv_diagnostic_kind cascade[0] <> 3 || rv_diagnostic_live_count () <> live + 1 then
                failwith "cascade snapshot before destroy"

            held.Value <- cascade[0]

            fun () ->
                let buffer = Array.zeroCreate<byte> 16
                let length = [| 0 |]
                rv_diagnostic_text (held.Value, buffer, buffer.Length, length) |> check "cascade text after destroy"

                if Text.Encoding.UTF8.GetString(buffer, 0, length[0]) <> "display"
                   || rv_diagnostic_count held.Value <> count
                   || rv_diagnostic_kind held.Value <> 3 then
                    failwith "cascade snapshot changed after destroy"

                let mutable winners = 0.0

                for index in 0 .. count - 1 do
                    let mutable winner = 0.0
                    rv_diagnostic_entry_number (held.Value, index, 6, &winner) |> check "cascade winner after destroy"
                    winners <- winners + winner

                if winners <> 1.0 then
                    failwithf "cascade winners after destroy %f" winners

                rv_diagnostic_release held.Value

                if rv_diagnostic_live_count () <> live then
                    failwith "cascade snapshot leaked"
        | "crypto" ->
            let filled = Array.zeroCreate<byte> 16

            rv_dom_crypto_get_random_values (document, RV_DOM_ARRAY_BUFFER_VIEW_UINT8, filled, filled.Length)
            |> check "crypto.getRandomValues"

            if filled = Array.zeroCreate<byte> 16 then
                failwith "crypto.getRandomValues left the bytes zero"

            held.Value <- rv_node_retain document

            fun () ->
                let bytes = Array.zeroCreate<byte> 16

                let random =
                    rv_dom_crypto_get_random_values (held.Value, RV_DOM_ARRAY_BUFFER_VIEW_UINT8, bytes, bytes.Length)

                if random <> 0 || bytes = Array.zeroCreate<byte> 16 then
                    failwithf "crypto.getRandomValues after destroy: %d" random

                let buffer = Array.zeroCreate<byte> 64
                let length = [| 0 |]
                let uuid = rv_dom_crypto_random_uuid (held.Value, buffer, buffer.Length, length)

                if uuid <> 0 || length[0] <> 36 then
                    failwithf "crypto.randomUUID after destroy: %d" uuid

                rv_node_release held.Value
        | "string results" ->
            // The container results that carry owned UTF-8 spans, read and released past host destroy.
            held.Value <- rv_node_retain div
            rv_element_set_attribute (div, "data-held", "1") |> check "data-held"
            rv_element_set_attribute (div, "hidden", "until-found") |> check "hidden"
            let mutable sheet = 0n
            rv_dom_css_style_sheet_create (document, null, &sheet) |> check "CSSStyleSheet"
            let css = "@layer first, second; @view-transition { navigation: auto; types: one two; }"
            rv_dom_css_style_sheet_replace_sync (sheet, utf8 css, utf8Length css) |> check "replaceSync"
            let mutable rules = 0n
            rv_dom_css_style_sheet_get_css_rules (sheet, &rules) |> check "cssRules"
            let mutable layer = 0n
            let mutable transition = 0n
            rv_dom_css_rule_list_item (rules, 0u, &layer) |> check "layer statement rule"
            rv_dom_css_rule_list_item (rules, 1u, &transition) |> check "view transition rule"
            rv_dom_css_rule_list_release rules
            rv_dom_style_sheet_release sheet
            let layer, transition = layer, transition

            let text (span: RvDomUtf8StringSpan) =
                if span.length <= 0 then
                    ""
                else
                    let bytes = Array.zeroCreate<byte> span.length
                    Runtime.InteropServices.Marshal.Copy(span.data, bytes, 0, span.length)
                    Text.Encoding.UTF8.GetString bytes

            let spans (items: nativeint) (count: int) =
                let size = Runtime.InteropServices.Marshal.SizeOf<RvDomUtf8StringSpan>()

                [ for index in 0 .. count - 1 ->
                      text (Runtime.InteropServices.Marshal.PtrToStructure<RvDomUtf8StringSpan>(items + nativeint (index * size))) ]

            fun () ->
                for rule, expected in [ layer, [ "first"; "second" ]; transition, [ "one"; "two" ] ] do
                    let mutable values = RvDomSequenceUSVString()

                    if rule = layer then
                        rv_dom_css_layer_statement_rule_get_name_list (rule, &values)
                        |> check "CSSLayerStatementRule.nameList after destroy"
                    else
                        rv_dom_css_view_transition_rule_get_types (rule, &values)
                        |> check "CSSViewTransitionRule.types after destroy"

                    if spans values.items values.count <> expected then
                        failwithf "USVString sequence after destroy: %A" (spans values.items values.count)

                    rv_dom_sequence_usv_string_release (&values)

                    if values.present <> 0 || values.count <> 0 || values.items <> 0n then
                        failwith "USVString sequence release left contents"

                    rv_dom_css_rule_release rule

                let mutable names = RvDomSequenceDOMString()
                rv_dom_element_get_attribute_names (held.Value, &names) |> check "getAttributeNames after destroy"

                if spans names.items names.count <> [ "data-held"; "hidden" ] then
                    failwithf "getAttributeNames after destroy: %A" (spans names.items names.count)

                rv_dom_sequence_dom_string_release (&names)

                if names.present <> 0 || names.count <> 0 || names.items <> 0n then
                    failwith "getAttributeNames release left contents"

                let mutable hidden = RvDomUnionBooleanOrUnrestrictedDoubleOrDOMStringNullable()
                rv_dom_html_element_get_hidden (held.Value, &hidden) |> check "hidden after destroy"

                if hidden.present <> 1 || hidden.tag <> 3 || text hidden.arm2 <> "until-found" then
                    failwith "hidden after destroy is not the until-found string"

                rv_dom_union_boolean_or_unrestricted_double_or_dom_string_nullable_release (&hidden)

                if hidden.present <> 0 || hidden.arm2.data <> 0n then
                    failwith "hidden release left contents"

                rv_node_release held.Value
        | "caret position" ->
            rv_dom_node_set_text_content (span, utf8 "AAAA", utf8Length "AAAA") |> check "caret text"
            rv_dom_document_caret_position_from_point (document, 2.0, 2.0, null, &held.contents)
            |> check "caretPositionFromPoint"

            let mutable node = 0n

            rv_dom_caret_position_get_offset_node (held.Value, &node)
            |> check "CaretPosition.offsetNode"

            if node = 0n then
                failwith "no CaretPosition.offsetNode"

            rv_node_release node

            fun () ->
                let mutable offset = 99u

                rv_dom_caret_position_get_offset (held.Value, &offset)
                |> check "CaretPosition.offset after destroy"

                if offset > 4u then
                    failwithf "CaretPosition.offset %d after destroy" offset

                rv_dom_caret_position_get_offset_node (held.Value, &node)
                |> check "CaretPosition.offsetNode after destroy"

                if node = 0n then
                    failwith "CaretPosition.offsetNode lost after destroy"

                rv_node_release node
                let mutable rect = 0n
                let status = rv_dom_caret_position_get_client_rect (held.Value, &rect)

                if status <> 0 && status <> -9 then
                    failwithf "CaretPosition.getClientRect after destroy: %d" status

                if rect <> 0n then
                    rv_dom_dom_rect_read_only_release rect

                rv_dom_caret_position_release held.Value
        | _ ->
            rv_dom_html_element_get_attribute_style_map (div, &held.contents)
            |> check "attributeStyleMap"

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
            probe = releaseName kind remove
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

let private releaseAfterDestroy (kind: string) (remove: bool) =
    if selected (releaseName kind remove) then
        Some(runReleaseAfterDestroy kind remove)
    else
        None

/// Runs each probe without a run-loop cycle before disposal, with a single cycle and with a 20 ms cycle, and writes
/// teardown-probes.json.
let run (outDir: string) =
    let results =
        [
            for cycleBefore in [ "none"; "single"; "20 ms" ] do
                probe "control" cycleBefore (fun _ _ _ -> 0n)

                probe "document title" cycleBefore (fun _ document _ ->
                    rv_node_set_string (document, titleProperty, "Probe") |> check "set title"

                    0n)

                probe "focused input" cycleBefore (focused "input")
                probe "focused textarea" cycleBefore (focused "textarea")
                probe "focused button" cycleBefore (focused "button")

                probe "focused input, value written" cycleBefore (fun host document body ->
                    let input = focused "input" host document body

                    rv_node_set_string (input, valueProperty, "x") |> check "set value"

                    input)

                probe "focused input, container removed" cycleBefore (inRemovedContainer false)
                probe "focused input with a value attribute, container removed" cycleBefore (inRemovedContainer true)
                probe "unfocused input, container removed" cycleBefore (removedFrom false false)

                probe "focused input removed" cycleBefore (fun host document body ->
                    let input = focused "input" host document body
                    rv_node_remove input |> check "remove"
                    input)

                imageProbe "image with a data source" cycleBefore (image gif false)
                imageProbe "image with a data source, removed" cycleBefore (image gif true)
                imageProbe "image with a missing file source" cycleBefore (image "file:///C:/ranvier-missing.png" false)

                imageProbe
                    "image with a missing file source, removed"
                    cycleBefore
                    (image "file:///C:/ranvier-missing.png" true)

                probe "SVG paint handles retained past host destroy" cycleBefore (svgPaintHandles false)
                probe "SVG paint handles retained past document replacement" cycleBefore (svgPaintHandles true)

            for kind in
                [
                    "node"
                    "dataset"
                    "style map"
                    "tree walker"
                    "node iterator"
                    "window target"
                    "media query list"
                    "scrolled document"
                    "form controls collection"
                    "options collection"
                    "form data"
                    "submit event"
                    "open modal dialog"
                    "toggle event"
                    "error event"
                    "blob slice"
                    "blob reads"
                    "caret position"
                    "crypto"
                    "diagnostics"
                    "cascade diagnostics"
                    "screen"
                    "url values"
                    "url pattern result"
                    "visual viewport"
                    "string results"
                    "aria relations"
                    "coordinate spaces"
                ] do
                for remove in [ false; true ] do
                    releaseAfterDestroy kind remove
        ]
        |> List.choose id

    let json =
        JsonSerializer.Serialize(results, JsonSerializerOptions(WriteIndented = true))

    File.WriteAllText(Path.Combine(outDir, "teardown-probes.json"), json)
    printfn "RANVIER_TEARDOWN_PROBES %s" (JsonSerializer.Serialize results)
