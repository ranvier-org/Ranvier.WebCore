/// Checks the "accessibility-text" group: a node's text read as UTF-16 offsets, character, word, line,
/// sentence and paragraph units, the caret and selection, rectangles of text, the offset at a point, and the
/// text events of editing and selection.
module RanvierWebCoreAbi.AccessibilityText

open System.IO
open System.Runtime.InteropServices
open System.Text.Json
open RanvierWebCoreAbi.Native

let private html =
    "<!doctype html><html><head><style>body{margin:0;font:16px sans-serif}#p{position:absolute;left:10px;top:10px;width:120px;margin:0}#t{position:absolute;left:10px;top:120px;width:150px}#pw{position:absolute;left:10px;top:150px}</style></head><body><p id=p>One two three. Four five six.</p><input id=t value=\"abc def\"><input id=pw type=password value=\"pass\"></body></html>"

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

let private text (ax: nativeint) startOffset endOffset =
    readString "ax_text" (fun buffer capacity length ->
        rv_ax_text (ax, startOffset, endOffset, buffer, capacity, length))

let private boundary (ax: nativeint) offset unit =
    let mutable s = 0
    let mutable e = 0
    rv_ax_text_boundary (ax, offset, unit, &s, &e) |> check "ax_text_boundary"
    s, e

let private selection (ax: nativeint) =
    let mutable s = 0
    let mutable e = 0
    let result = rv_ax_text_selection (ax, &s, &e)
    result, s, e

let private rects (ax: nativeint) startOffset endOffset =
    let mutable count = 0
    let status = rv_ax_text_rects (ax, startOffset, endOffset, null, 0, &count)

    if status <> BufferTooSmall && status <> 0 then
        failwith $"ax_text_rects count returned {status}"

    let values = Array.zeroCreate<float> (count * 4)

    rv_ax_text_rects (ax, startOffset, endOffset, values, count, &count)
    |> check "ax_text_rects"

    values |> Array.chunkBySize 4 |> Array.map List.ofArray |> List.ofArray

let run (outDir: string) =
    require (rv_abi_has "accessibility-text" = 1) "rv_abi_has accessibility-text"
    let hasEvents = rv_abi_has "accessibility-events" = 1
    use host = new Host(300, 200)
    host.LoadHtml html
    let events = ResizeArray<nativeint * int>()
    let onEvent = AxCallback(fun _ node event -> events.Add(rv_ax_retain node, event))

    rv_host_set_accessibility (host.Handle, 1, Marshal.GetFunctionPointerForDelegate onEvent, 0n)
    |> check "host_set_accessibility"

    let ax (id: string) =
        use node = host.GetElementById id
        rv_node_ax node.Handle

    let p = ax "p"
    let t = ax "t"
    let pw = ax "pw"

    // The paragraph: its text, its units, and its lines, which wrap at 120px.
    let pLength = rv_ax_text_length p
    let pText = text p 0 pLength
    let character = boundary p 0 0
    let word = boundary p 4 1
    let wordText = text p (fst word) (snd word)
    let sentence = boundary p 0 3
    let sentenceText = text p (fst sentence) (snd sentence)
    let firstLine = boundary p 0 2
    let lastLine = boundary p pLength 2
    let paragraph = boundary p 5 4
    let lineRects = rects p 0 pLength
    let firstRect = rects p 0 1
    let offsetAtStart = rv_ax_text_offset_at (p, 11, 15)
    let badRange = rv_ax_text_length (rv_host_ax_root host.Handle)

    // The text field: its value as text, a selection set through the ABI, the caret, then typing.
    let tLength = rv_ax_text_length t
    let tText = text t 0 tLength
    let pwText = text pw 0 (rv_ax_text_length pw)
    let selectionBefore = selection t
    rv_ax_action (t, 1) |> ignore
    events.Clear()
    rv_ax_text_set_selection (t, 4, 7) |> check "ax_text_set_selection"
    let selected = selection t
    let caretAfterSelect = rv_ax_text_caret t
    let caretRect = rects t 2 2
    // WebCore reports a selection change in the rendering update after it.
    host.Update()
    host.CycleRunLoop 50
    let selectionEvent = events |> Seq.exists (fun (n, e) -> n = t && e = 14)
    events.Clear()
    rv_ax_text_set_selection (t, 7, 7) |> check "caret at the end"
    host.Type("x", "KeyX", "x")
    host.Update()
    host.CycleRunLoop 50
    let typedText = text t 0 (rv_ax_text_length t)
    let caretAfterTyping = rv_ax_text_caret t
    let pSelection = selection p

    let typingEvents =
        events |> Seq.map (fun (n, e) -> $"{rv_ax_role n}:{e}") |> List.ofSeq

    let textEvent = events |> Seq.exists (fun (n, e) -> n = t && e = 13)

    rv_host_set_accessibility (host.Handle, 0, 0n, 0n) |> check "accessibility off"

    for node, _ in events do
        rv_ax_release node

    for node in [ p; t; pw ] do
        rv_ax_release node

    System.GC.KeepAlive onEvent

    let summary =
        {| pLength = pLength
           pText = pText
           character = character
           word = word
           wordText = wordText
           sentence = sentence
           sentenceText = sentenceText
           firstLine = firstLine
           lastLine = lastLine
           paragraph = paragraph
           lineRects = lineRects
           firstRect = firstRect
           offsetAtStart = offsetAtStart
           rootLength = badRange
           tText = tText
           pwText = pwText
           selectionBefore = selectionBefore
           selected = selected
           caretAfterSelect = caretAfterSelect
           caretRect = caretRect
           selectionEvent = selectionEvent
           typedText = typedText
           caretAfterTyping = caretAfterTyping
           pSelection = pSelection
           typingEvents = typingEvents
           textEvent = textEvent
           hasEvents = hasEvents |}

    File.WriteAllText(
        Path.Combine(outDir, "fsharp-accessibility-text.json"),
        JsonSerializer.Serialize(summary, JsonSerializerOptions(WriteIndented = true))
    )

    printfn "RANVIER_FSHARP_ACCESSIBILITY_TEXT %s" (JsonSerializer.Serialize summary)

    require (pText = "One two three. Four five six." && pLength = pText.Length) "the paragraph's text and length"
    require (character = (0, 1)) "a character"
    require (wordText = "two") "the word at an offset"
    require (sentenceText.StartsWith "One two three." && snd sentence <= 15) "the first sentence"

    require
        (fst firstLine = 0
         && snd firstLine < pLength
         && snd lastLine = pLength
         && fst lastLine > 0)
        "lines wrap at the box's width"

    require (paragraph = (0, pLength)) "the paragraph is the whole text"
    require (lineRects.Length >= 2) "a rectangle per line"

    require
        (match firstRect with
         | [ [ x; y; w; h ] ] -> x >= 10.0 && x < 14.0 && y >= 10.0 && y < 16.0 && w > 0.0 && h > 0.0
         | _ -> false)
        "the first character's rectangle"

    require (offsetAtStart = 0) "the offset at the paragraph's first character"
    require (badRange = pLength) "the document's text holds its text runs, and not form fields' values"
    require (tText = "abc def" && pwText = "••••") "a text field's value; a password masked"
    require (selected = (1, 4, 7) && caretAfterSelect = 7) "the selection and caret set through the ABI"

    require
        (match caretRect with
         | [ [ _; _; w; h ] ] -> h > 0.0 && w >= 0.0
         | _ -> false)
        "a caret rectangle"

    require (typedText = "abc defx" && caretAfterTyping = 8) "typing moves the caret"
    require (pSelection = (0, -1, -1)) "the paragraph holds no selection"

    if hasEvents then
        require selectionEvent "a text selection event for the field"
        require textEvent "a text event for the field"
