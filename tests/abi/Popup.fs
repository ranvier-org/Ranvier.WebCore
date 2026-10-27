/// Checks ABI v17: a <select> menu shown through the app's popup handler, its items and a choice, a select
/// with no handler, and the tooltip under the mouse.
module RanvierWebCoreAbi.Popup

open System.IO
open System.Runtime.InteropServices
open System.Text.Json
open RanvierWebCoreAbi.Native

let private html =
    "<!doctype html><html><head><style>body{margin:0}#s{position:absolute;left:10px;top:10px;width:120px;height:24px}#tip{position:absolute;left:10px;top:60px;width:50px;height:20px;background:#ccc}</style></head><body><select id=s><option>One</option><optgroup label=More><option>Two</option><option disabled>Three</option></optgroup><option>Four</option></select><div id=tip title=\"A native tooltip\"></div></body></html>"

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

let private item popup index =
    let mutable kind = 0
    let mutable enabled = 0

    let text =
        readString "popup_item" (fun buffer capacity length -> rv_popup_item (popup, index, &kind, &enabled, buffer, capacity, length))

    $"{kind}:{enabled}:{text}"

let private tooltip (host: Host) =
    readString "host_tooltip" (fun buffer capacity length -> rv_host_tooltip (host.Handle, buffer, capacity, length))

let private press (host: Host) x y =
    host.Mouse (Input.MouseMove, x, y, Input.ButtonNone, 0, 0)
    |> ignore

    host.Mouse (Input.MouseDown, x, y, Input.ButtonLeft, 1, 0)
    |> ignore

    host.Mouse (Input.MouseUp, x, y, Input.ButtonLeft, 1, 0)
    |> ignore

let run (outDir: string) =
    for feature in [ "popups"; "tooltip" ] do
        require (rv_abi_has feature = 1) $"rv_abi_has {feature}"

    use host = new Host (240, 120)
    host.LoadHtml html
    host.SetFocused true
    use select = host.GetElementById "s"
    let changes = ResizeArray<string>()

    use _change =
        select.Listen ("change", false, (fun e -> changes.Add (if e.Trusted then "trusted" else "untrusted")))

    // With a handler: the menu opens at the select's box with its items, and a choice changes the value.
    let shown = ResizeArray<string>()
    let mutable opened = 0n

    let onPopup =
        PopupCallback (fun _ popup action x y width height selected ->
            shown.Add $"{action}:{x},{y},{width},{height}:{selected}"

            if action = 0 then
                opened <- popup)

    rv_host_set_popup_handler (host.Handle, Marshal.GetFunctionPointerForDelegate onPopup, 0n)
    |> check "set_popup_handler"

    press host 50 20
    let count = if opened <> 0n then rv_popup_item_count opened else -1

    let items =
        if opened <> 0n then
            [ for i in 0 .. count - 1 -> item opened i ]
        else
            []

    if opened <> 0n then
        rv_popup_choose (opened, 4)
        |> check "popup_choose"

    let chosen = select.Value

    // Without a handler: pressing the select opens no menu.
    rv_host_set_popup_handler (host.Handle, 0n, 0n)
    |> check "remove popup handler"

    let shownBefore = shown.Count
    press host 50 20
    let shownWithout = shown.Count - shownBefore

    // Tooltips follow the mouse.
    host.Mouse (Input.MouseMove, 30, 70, Input.ButtonNone, 0, 0)
    |> ignore

    let overTip = tooltip host

    host.Mouse (Input.MouseMove, 200, 100, Input.ButtonNone, 0, 0)
    |> ignore

    let overBody = tooltip host
    System.GC.KeepAlive onPopup

    let summary =
        {|
            shown = List.ofSeq shown
            count = count
            items = items
            chosen = chosen
            changes = List.ofSeq changes
            shownWithout = shownWithout
            overTip = overTip
            overBody = overBody
        |}

    File.WriteAllText (Path.Combine (outDir, "fsharp-popup.json"), JsonSerializer.Serialize (summary, JsonSerializerOptions (WriteIndented = true)))
    printfn "RANVIER_FSHARP_POPUP %s" (JsonSerializer.Serialize summary)

    require
        (shown.Count >= 1
         && shown[0].StartsWith "0:10,10,120,24:0")
        "the menu opens at the select's box with the first item selected"

    // WebCore indents the options of a group by four spaces and reports the group label as disabled.
    require
        (items = [ "0:1:One"; "2:0:More"; "0:1:    Two"; "0:0:    Three"; "0:1:Four" ])
        "the menu lists options, the group label and the disabled option"

    require (chosen = "Four") "choosing an item selects it"
    require (List.ofSeq changes = [ "trusted" ]) "a choice fires one trusted change event"
    require (shownWithout = 0) "without a handler no menu opens"
    require (overTip = "A native tooltip" && overBody = "") "the tooltip follows the title under the mouse"
