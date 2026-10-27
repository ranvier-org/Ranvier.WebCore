/// Checks ABI v19: a drag from outside the page in the App style, with dragenter, dragleave, dragover and
/// drop fired at the elements under the point, the operation a cancelled dragover accepts, and a drop
/// inserting text into editable content. The DOM style fires nothing.
module RanvierWebCoreAbi.Drop

open System.IO
open System.Text.Json
open RanvierWebCoreAbi.Native

let private html =
    "<!doctype html><html><head><style>body{margin:0}div{position:absolute;width:100px;height:40px}#plain{left:0;top:0}#zone{left:0;top:50px}#ed{left:0;top:100px}</style></head><body><div id=plain></div><div id=zone></div><div id=ed contenteditable></div></body></html>"

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

let private text (node: Node) =
    readString "node_get_string" (fun buffer capacity length ->
        rv_node_get_string (node.Handle, 1, buffer, capacity, length))

let run (outDir: string) =
    require (rv_abi_has "drop" = 1) "rv_abi_has drop"
    use host = new Host(200, 160)
    host.LoadHtml html
    use plain = host.GetElementById "plain"
    use zone = host.GetElementById "zone"
    use ed = host.GetElementById "ed"
    let events = ResizeArray<string>()

    for node, name in [ plain, "plain"; zone, "zone"; ed, "ed" ] do
        for kind in [ "dragenter"; "dragleave"; "dragover"; "drop" ] do
            node.Listen(kind, false, (fun e -> events.Add $"{name}:{e.Type}")) |> ignore

    // The zone accepts drops and handles them itself.
    zone.Listen("dragover", false, (fun e -> e.PreventDefault())) |> ignore
    zone.Listen("drop", false, (fun e -> e.PreventDefault())) |> ignore

    let data = rv_drag_data_create ()
    rv_drag_data_add (data, "text/plain", "dropped") |> check "drag_data_add"
    let all = 1 ||| 2 ||| 4

    let drag action x y =
        let op = rv_host_drag (host.Handle, action, x, y, all, data, 0)

        if op < 0 then
            failwith $"host_drag returned {op}"

        op

    // DOM style: nothing reaches the page.
    let domOp = drag 0 20 70
    let domEvents = events.Count

    rv_host_set_drag (host.Handle, 0) |> check "set_drag app"
    let overPlain = drag 0 20 20
    let overZone = drag 0 20 70
    let dropZone = drag 2 20 70
    let overEd = drag 0 20 120
    let dropEd = drag 2 20 120
    let edText = text ed
    let overPlainAgain = drag 0 20 20
    drag 1 20 20 |> ignore
    rv_drag_data_release data

    let summary =
        {|
            domOp = domOp
            domEvents = domEvents
            overPlain = overPlain
            overZone = overZone
            dropZone = dropZone
            overEd = overEd
            dropEd = dropEd
            edText = edText
            overPlainAgain = overPlainAgain
            events = List.ofSeq events
        |}

    File.WriteAllText(
        Path.Combine(outDir, "fsharp-drop.json"),
        JsonSerializer.Serialize(summary, JsonSerializerOptions(WriteIndented = true))
    )

    printfn "RANVIER_FSHARP_DROP %s" (JsonSerializer.Serialize summary)

    require (domOp = 0 && domEvents = 0) "the DOM style fires nothing"
    require (overPlain = 0) "an element without a dragover listener refuses the drop"
    require (overZone = 1 && dropZone = 1) "a cancelled dragover accepts a copy, and the drop reaches the page"
    require (overEd = 1 && dropEd = 1 && edText = "dropped") "text drops into editable content by default"

    require
        (List.ofSeq events =
            [
                "plain:dragenter"
                "plain:dragover"
                "plain:dragleave"
                "zone:dragenter"
                "zone:dragover"
                "zone:dragover"
                "zone:drop"
                "ed:dragenter"
                "ed:dragover"
                "ed:dragover"
                "ed:drop"
                "plain:dragenter"
                "plain:dragover"
                "plain:dragleave"
            ])
        "the drag events follow the element under the point"
