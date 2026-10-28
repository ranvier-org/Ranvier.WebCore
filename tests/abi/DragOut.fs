/// Checks ABI v20: a mouse drag of a link and of a draggable element starts a drag through the app's callback
/// with its data and image, the drag is fed back into the page as a drop, and rv_drag_end fires dragend.
module RanvierWebCoreAbi.DragOut

open System.IO
open System.Runtime.InteropServices
open System.Text.Json
open RanvierWebCoreAbi.Native

let private html =
    "<!doctype html><html><head><style>body{margin:0;font:16px sans-serif}#box{position:absolute;left:0;top:0;width:100px;height:40px;background:rgb(200,0,0)}#link{position:absolute;left:0;top:50px}#ed{position:absolute;left:0;top:100px;width:200px;height:40px}</style></head><body><div id=box draggable=true></div><a id=link href=\"https://example.test/page\">link</a><div id=ed contenteditable></div></body></html>"

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

let private items drag =
    [
        for i in 0 .. rv_drag_item_count drag - 1 ->
            let kind =
                readString "drag_item_type" (fun b c l -> rv_drag_item_type (drag, i, b, c, l))

            let value =
                readString "drag_item_value" (fun b c l -> rv_drag_item_value (drag, i, b, c, l))

            kind, value
    ]

let run (outDir: string) =
    require (rv_abi_has "drag-out" = 1) "rv_abi_has drag-out"
    use host = new Host(240, 160)
    host.LoadHtml html
    use box = host.GetElementById "box"
    use ed = host.GetElementById "ed"
    let events = ResizeArray<string>()
    box.Listen("dragstart", false, (fun e -> events.Add e.Type)) |> ignore
    box.Listen("dragend", false, (fun e -> events.Add e.Type)) |> ignore
    let mutable started: (nativeint * int * int * int) list = []

    let onStart =
        DragStartCallback(fun _ drag x y allowed -> started <- started @ [ drag, x, y, allowed ])

    let gesture (x0, y0) (x1, y1) =
        host.Mouse(Input.MouseMove, x0, y0, Input.ButtonNone, 0, 0) |> ignore
        host.Mouse(Input.MouseDown, x0, y0, Input.ButtonLeft, 1, 0) |> ignore
        host.Mouse(Input.MouseMove, x0 + 5, y0 + 5, Input.ButtonLeft, 0, 0) |> ignore
        host.Mouse(Input.MouseMove, x1, y1, Input.ButtonLeft, 0, 0) |> ignore

    // Without the App style no drag starts.
    gesture (10, 10) (60, 30)
    host.Mouse(Input.MouseUp, 60, 30, Input.ButtonLeft, 1, 0) |> ignore
    let startedInDom = started.Length

    rv_host_set_drag (host.Handle, 0) |> check "set_drag app"

    rv_host_set_drag_start (host.Handle, Marshal.GetFunctionPointerForDelegate onStart, 0n)
    |> check "set_drag_start"

    // The draggable box: an image, offset where the press was.
    gesture (10, 10) (60, 30)

    let boxDrag, boxX, boxY, boxAllowed =
        if started.IsEmpty then (0n, 0, 0, 0) else started.Head

    let mutable w, h, ox, oy = 0, 0, 0, 0

    let sized =
        if boxDrag <> 0n then
            rv_drag_image (boxDrag, null, 0, &w, &h, &ox, &oy)
        else
            0

    if boxDrag <> 0n then
        rv_drag_end (boxDrag, 60, 30, 0) |> check "drag_end box"

    host.Mouse(Input.MouseUp, 60, 30, Input.ButtonLeft, 1, 0) |> ignore

    // The link: its URL, dropped into the editable div through rv_host_drag.
    gesture (10, 58) (60, 110)

    let linkDrag =
        if started.Length >= 2 then
            (let d, _, _, _ = started[1] in d)
        else
            0n

    let linkItems = if linkDrag <> 0n then items linkDrag else []
    let mutable dropped = -1

    if linkDrag <> 0n then
        let data = rv_drag_data linkDrag
        rv_host_drag (host.Handle, 0, 20, 120, 7, data, 0) |> ignore
        dropped <- rv_host_drag (host.Handle, 2, 20, 120, 7, data, 0)
        rv_drag_data_release data
        rv_drag_end (linkDrag, 20, 120, dropped) |> check "drag_end link"

    host.Mouse(Input.MouseUp, 20, 120, Input.ButtonLeft, 1, 0) |> ignore

    let edText =
        readString "ed text" (fun b c l -> rv_node_get_string (ed.Handle, 1, b, c, l))

    System.GC.KeepAlive onStart

    let summary =
        {|
            startedInDom = startedInDom
            starts = started.Length
            box = [ boxX; boxY; boxAllowed ]
            image = [ sized; w; h; ox; oy ]
            linkItems = linkItems |> List.map (fun (k, v) -> $"{k}={v}")
            dropped = dropped
            edText = edText
            events = List.ofSeq events
        |}

    File.WriteAllText(
        Path.Combine(outDir, "fsharp-dragout.json"),
        JsonSerializer.Serialize(summary, JsonSerializerOptions(WriteIndented = true))
    )

    printfn "RANVIER_FSHARP_DRAGOUT %s" (JsonSerializer.Serialize summary)

    require (startedInDom = 0) "the DOM style starts no drag"
    require (started.Length = 2) "dragging the box and the link each start a drag"
    require ([ boxX; boxY ] = [ 10; 10 ] && boxAllowed <> 0) "the drag starts at the press, with allowed operations"

    require
        ([ sized; w; h; ox; oy ] = [ BufferTooSmall; 100; 40; 10; 10 ])
        "the drag image is the box, offset where the press was"

    require
        (linkItems |> List.exists (fun (_, v) -> v.Contains "https://example.test/page"))
        "the link drag carries its URL"

    require
        (dropped = 1 && edText.Contains "https://example.test/page")
        "the drag drops into the page through rv_host_drag"

    require (List.ofSeq events = [ "dragstart"; "dragend" ]) "the box gets dragstart, then dragend at rv_drag_end"
