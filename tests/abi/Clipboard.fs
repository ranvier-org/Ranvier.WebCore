/// Checks ABI v18's clipboard in the App and DOM styles: copy, cut and paste through the app's callbacks,
/// the DOM events they fire, a page that cancels them, and the Control+C binding. The Native style is only
/// selected, not run: it would change the clipboard of the machine running the tests.
module RanvierWebCoreAbi.Clipboard

open System.IO
open System.Runtime.InteropServices
open System.Text.Json
open RanvierWebCoreAbi.Native

let private html =
    "<!doctype html><html><body><input id=src value=\"hello world\"><div id=ed contenteditable></div></body></html>"

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

let private innerHtml (node: Node) =
    readString "node_get_string" (fun buffer capacity length ->
        rv_node_get_string (node.Handle, 4, buffer, capacity, length))

let run (outDir: string) =
    require (rv_abi_has "clipboard" = 1) "rv_abi_has clipboard"
    use host = new Host(240, 120)
    host.LoadHtml html
    host.SetFocused true
    use src = host.GetElementById "src"
    use ed = host.GetElementById "ed"
    let events = ResizeArray<string>()

    for name in [ "copy"; "cut"; "paste" ] do
        // The listeners live as long as the host: the probe ends with it.
        src.Listen(name, false, (fun e -> events.Add $"src:{e.Type}:{e.Trusted}"))
        |> ignore

        ed.Listen(name, false, (fun e -> events.Add $"ed:{e.Type}:{e.Trusted}"))
        |> ignore

    let select (node: Node) start finish =
        rv_element_focus node.Handle |> check "focus"

        rv_text_set_selection (node.Handle, start, finish) |> check "select"

    // DOM style, the default: the event fires and no data leaves the page.
    select src 0 5
    let domCopy = rv_host_edit (host.Handle, 0)

    // App style.
    let written = ResizeArray<string>()
    let mutable offered: (string * string) list = []

    let write =
        ClipboardWrite(fun _ kind data first ->
            written.Add $"{first}:{Marshal.PtrToStringUTF8 kind}:{(Marshal.PtrToStringUTF8 data).Length}")

    let read =
        ClipboardRead(fun _ request ->
            for kind, data in offered do
                rv_clipboard_offer (request, kind, data) |> check "clipboard_offer")

    rv_host_set_clipboard (
        host.Handle,
        0,
        Marshal.GetFunctionPointerForDelegate write,
        Marshal.GetFunctionPointerForDelegate read,
        0n
    )
    |> check "set_clipboard app"

    select src 0 5
    let appCopy = rv_host_edit (host.Handle, 0)
    let copied = List.ofSeq written
    written.Clear()

    select src 0 6
    let appCut = rv_host_edit (host.Handle, 1)
    let afterCut = src.Value
    let cutWritten = List.ofSeq written
    written.Clear()

    // Control+C runs the same copy.
    select src 0 5
    host.Key(Input.KeyDown, "c", "KeyC", null, 2) |> ignore
    let keyWritten = List.ofSeq written

    // Pastes into the editable div: text, then HTML.
    rv_element_focus ed.Handle |> check "focus ed"
    offered <- [ "text/plain", "XYZ" ]
    let textPaste = rv_host_edit (host.Handle, 2)
    let afterText = innerHtml ed
    offered <- [ "text/plain", "bold"; "text/html", "<b>bold</b>" ]
    let htmlPaste = rv_host_edit (host.Handle, 2)
    let afterHtml = innerHtml ed

    // A page that cancels paste keeps the content.
    use _cancel = ed.Listen("paste", false, (fun e -> e.PreventDefault()))
    offered <- [ "text/plain", "NOPE" ]
    rv_host_edit (host.Handle, 2) |> ignore
    let afterCancelled = innerHtml ed

    let nativeStatus = rv_host_set_clipboard (host.Handle, 1, 0n, 0n, 0n)
    System.GC.KeepAlive write
    System.GC.KeepAlive read

    let summary =
        {|
            events = List.ofSeq events
            domCopy = domCopy
            appCopy = appCopy
            copied = copied
            appCut = appCut
            afterCut = afterCut
            cutWritten = cutWritten
            keyWritten = keyWritten
            textPaste = textPaste
            afterText = afterText
            htmlPaste = htmlPaste
            afterHtml = afterHtml
            afterCancelled = afterCancelled
            nativeStatus = nativeStatus
        |}

    File.WriteAllText(
        Path.Combine(outDir, "fsharp-clipboard.json"),
        JsonSerializer.Serialize(summary, JsonSerializerOptions(WriteIndented = true))
    )

    printfn "RANVIER_FSHARP_CLIPBOARD %s" (JsonSerializer.Serialize summary)

    require (domCopy = 1 && events[0] = "src:copy:True") "a DOM-style copy fires copy and writes nothing"

    require
        (appCopy = 1 && copied.Head = "1:text/plain:5" && copied.Length = 2)
        "an App-style copy writes text/plain then text/html"

    require
        (appCut = 1 && afterCut = "world" && cutWritten.Head = "1:text/plain:6")
        "a cut writes the selection and deletes it"

    require (keyWritten.Length = 2) "Control+C copies"
    require (textPaste = 1 && afterText = "XYZ") "a paste inserts the app's text"
    require (htmlPaste = 1 && afterHtml.Contains "<b>bold</b>") "a paste inserts the app's HTML"
    require (afterCancelled = afterHtml) "a page that cancels paste keeps its content"
    require (nativeStatus = 0) "the Native style can be selected on this platform"
