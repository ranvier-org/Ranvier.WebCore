/// Drives a page as a window would (ABI v12): resize and device scale, native mouse, wheel and keyboard input,
/// the frame callback, rendering updates and dirty rectangles, and the details of the trusted events.
module RanvierWebCoreAbi.Window

open System
open System.Diagnostics
open System.IO
open System.Text.Json
open RanvierWebCoreAbi.Native

let private html =
    "<!doctype html><html><head><style>body{margin:0;background:white}#field{position:absolute;left:10px;top:10px;width:150px;height:24px;font:16px sans-serif}#box{position:absolute;left:10px;top:60px;width:80px;height:30px;background:rgb(200,0,0);cursor:pointer}#box:hover{background:rgb(0,200,0)}#spacer{height:3000px}</style></head><body><input id=field><div id=box></div><div id=spacer></div></body></html>"

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

let private rgbAt (rgba: byte[]) width x y =
    let i = (y * width + x) * 4
    [ int rgba[i]; int rgba[i + 1]; int rgba[i + 2] ]

let run (outDir: string) =
    for feature in [ "resize"; "input"; "frame"; "event-details"; "cursor"; "scroll"; "ime" ] do
        require (rv_abi_has feature = 1) $"rv_abi_has {feature}"

    require (rv_abi_has "teleport" = 0) "rv_abi_has rejects an unknown feature"

    use host = new Host (200, 100)
    let mutable frames = 0
    host.OnFrame (fun () -> frames <- frames + 1)
    host.LoadHtml html
    let framesAfterLoad = frames
    let dirtyAfterLoad = host.DirtyRect
    let first = host.Paint ()
    let dirtyAfterPaint = host.DirtyRect

    // Resize and device scale.
    host.Resize (240, 120)
    let resized = host.PaintSize
    let dirtyAfterResize = host.DirtyRect
    host.Paint () |> ignore
    host.SetDeviceScale 2.0f
    let scaled = host.PaintSize
    let hiDpi = host.Paint ()
    let hiDpiBox = rgbAt hiDpi 480 100 150
    host.SetDeviceScale 1.5f
    let fractional = host.PaintSize
    host.Paint () |> ignore
    host.SetDeviceScale 1.0f
    host.Paint () |> ignore

    // Mouse: hover repaints the box; a click is trusted, with its coordinates, button and count.
    use box = host.GetElementById "box"
    let mouseLog = ResizeArray<string>()

    let record (event: Event) =
        let number n =
            event.Number n
            |> Option.map int
            |> Option.defaultValue -99

        mouseLog.Add $"{event.Type}:{event.Trusted}:{number Input.ClientX},{number Input.ClientY}:b{number Input.Button}:d{number Input.Detail}"

    use _down = box.Listen ("mousedown", false, record)
    use _up = box.Listen ("mouseup", false, record)
    use _click = box.Listen ("click", false, record)
    // A frame, as the app runs one: the update consumes the pending request.
    host.Update ()
    let beforeHover = rgbAt (host.Paint ()) 240 50 75
    let framesBeforeHover = frames

    host.Mouse (Input.MouseMove, 50, 75, Input.ButtonNone, 0, 0)
    |> ignore

    let hoverDirty = host.DirtyRect
    let framesAfterHover = frames
    let cursorOverBox = host.Cursor
    let hovered = rgbAt (host.Paint ()) 240 50 75

    host.Mouse (Input.MouseDown, 50, 75, Input.ButtonLeft, 1, 0)
    |> ignore

    host.Mouse (Input.MouseUp, 50, 75, Input.ButtonLeft, 1, 0)
    |> ignore

    // Keyboard: focus the field by clicking it, then type and delete.
    host.SetFocused true
    use field = host.GetElementById "field"
    let keyLog = ResizeArray<string>()

    use _keydown =
        field.Listen ("keydown", false, (fun e -> keyLog.Add $"keydown:{e.Trusted}:{e.String Input.Code}"))

    use _input =
        field.Listen ("input", false, (fun e -> keyLog.Add $"input:{e.String Input.Data}:{e.String Input.InputType}"))

    host.Mouse (Input.MouseMove, 20, 20, Input.ButtonNone, 0, 0)
    |> ignore

    host.Mouse (Input.MouseDown, 20, 20, Input.ButtonLeft, 1, 0)
    |> ignore

    host.Mouse (Input.MouseUp, 20, 20, Input.ButtonLeft, 1, 0)
    |> ignore

    let cursorOverField = host.Cursor

    let fieldFocused =
        match host.ActiveElement () with
        | Some active ->
            use active = active
            active.Handle = field.Handle
        | None -> false

    host.Type ("h", "KeyH", "h")
    host.Type ("i", "KeyI", "i")
    let typed = field.Value

    host.Key (Input.KeyDown, "Backspace", "Backspace", null, 0)
    |> ignore

    host.Key (Input.KeyUp, "Backspace", "Backspace", null, 0)
    |> ignore

    let afterBackspace = field.Value

    host.Key (Input.KeyDown, "ArrowLeft", "ArrowLeft", null, 0)
    |> ignore

    host.Type ("x", "KeyX", "x")
    let afterArrow = field.Value

    // An input method composes at the caret, after "x"; the commit replaces the composition.
    host.ImeSetComposition ("ni", 2, 2)
    let composing = field.Value
    let imeRect = host.ImeRect
    host.ImeCommit "你"
    let committed = field.Value
    host.ImeSetComposition ("ab", 2, 2)
    host.ImeCancel ()
    let cancelled = field.Value
    host.Paint () |> ignore

    // Wheel: scrolling moves the box out of the viewport and invalidates all of it.
    let wheelHandled = host.Wheel (50, 50, 0.0f, 100.0f)
    let wheelDirty = host.DirtyRect
    let wheelPosition = host.ScrollPosition
    let scrolled = rgbAt (host.Paint ()) 240 50 75
    host.ScrollTo (0, 0)
    let scrollToDirty = host.DirtyRect
    let scrollToPosition = host.ScrollPosition
    let scrolledBack = rgbAt (host.Paint ()) 240 50 75

    // A CSS animation asks for a frame each frame; each update and paint advances it.
    host.LoadHtml
        "<!doctype html><style>body{margin:0}@keyframes pulse{from{background:rgb(0,0,0)}to{background:rgb(250,250,250)}}#a{width:40px;height:40px;animation:pulse 300ms linear infinite alternate}</style><div id=a></div>"

    let colours = Collections.Generic.HashSet<int>()
    let framesBeforeAnimation = frames
    let clock = Stopwatch.StartNew ()
    let mutable pending = true

    host.OnFrame (fun () ->
        frames <- frames + 1
        pending <- true)

    while clock.ElapsedMilliseconds < 600L do
        host.CycleRunLoop 16

        if pending then
            pending <- false
            host.Update ()

            colours.Add (rgbAt (host.Paint ()) 240 20 20).Head
            |> ignore

    let animationFrames = frames - framesBeforeAnimation

    let summary =
        {|
            framesAfterLoad = framesAfterLoad
            dirtyAfterLoad = dirtyAfterLoad
            dirtyAfterPaint = dirtyAfterPaint
            firstPixelBox = rgbAt first 200 50 75
            resized = resized
            dirtyAfterResize = dirtyAfterResize
            scaled = scaled
            hiDpiBox = hiDpiBox
            fractional = fractional
            beforeHover = beforeHover
            hovered = hovered
            hoverDirty = hoverDirty
            hoverFrames = framesAfterHover - framesBeforeHover
            mouseLog = List.ofSeq mouseLog
            fieldFocused = fieldFocused
            typed = typed
            afterBackspace = afterBackspace
            afterArrow = afterArrow
            keyLog = List.ofSeq keyLog
            wheelHandled = wheelHandled
            wheelDirty = wheelDirty
            scrolled = scrolled
            cursorOverBox = cursorOverBox
            cursorOverField = cursorOverField
            composing = composing
            imeRect = imeRect
            committed = committed
            cancelled = cancelled
            wheelPosition = wheelPosition
            scrollToDirty = scrollToDirty
            scrollToPosition = scrollToPosition
            scrolledBack = scrolledBack
            animationFrames = animationFrames
            animationColours = colours.Count
        |}

    File.WriteAllText (Path.Combine (outDir, "fsharp-window.json"), JsonSerializer.Serialize (summary, JsonSerializerOptions (WriteIndented = true)))
    printfn "RANVIER_FSHARP_WINDOW %s" (JsonSerializer.Serialize summary)

    require (framesAfterLoad >= 1) "loading a page asks for a frame"
    require dirtyAfterLoad.IsSome "loading a page invalidates the viewport"
    require dirtyAfterPaint.IsNone "a paint clears the dirty rectangle"
    require (resized = (240, 120)) "resize sets the paint size"
    require (dirtyAfterResize = Some (0, 0, 240, 120)) "resize invalidates the viewport"
    require (scaled = (480, 240)) "device scale 2 doubles the paint size"
    require (hiDpiBox = [ 200; 0; 0 ]) "the box paints at twice its CSS position at scale 2"
    require (fractional = (360, 180)) "device scale 1.5"
    require (beforeHover = [ 200; 0; 0 ]) "box before hover"
    require (hovered = [ 0; 200; 0 ]) "a native mouse move applies :hover"
    require hoverDirty.IsSome "hover invalidates the box"
    require (framesAfterHover > framesBeforeHover) "hover asks for a frame"

    require
        (List.ofSeq mouseLog =
            [
                "mousedown:True:50,75:b0:d1"
                "mouseup:True:50,75:b0:d1"
                "click:True:50,75:b0:d1"
            ])
        "a native click dispatches trusted mousedown, mouseup and click with its details"

    require fieldFocused "clicking the field focuses it"
    require (typed = "hi") "typed characters reach the field"
    require (afterBackspace = "h") "Backspace deletes backward"
    require (afterArrow = "xh") "ArrowLeft moves the caret before typing"

    require
        (keyLog
         |> Seq.exists (fun l -> l = "keydown:True:Some(KeyH)"))
        "keydown is trusted with its code"

    require
        (keyLog
         |> Seq.exists (fun l -> l = "input:Some(h):Some(insertText)"))
        "input carries data and inputType"

    require (wheelDirty = Some (0, 0, 240, 120)) "a wheel scroll invalidates the viewport"
    require (scrolled = [ 255; 255; 255 ]) "the wheel scrolled the box away"
    require (cursorOverBox = 1) "cursor:pointer reports RV_CURSOR_POINTER"
    require (cursorOverField = 2) "a text field reports RV_CURSOR_TEXT"
    require (composing = "xnih") "a composition shows in the field at the caret"

    require
        (match imeRect with
         | Some (x, y, _, h) -> x >= 10 && x <= 160 && y >= 10 && y + h <= 40
         | None -> false)
        "the composition's rectangle lies in the field"

    require (committed = "x你h") "a commit replaces the composition"
    require (cancelled = "x你h") "a cancel removes the composition"
    require (wheelPosition = (0, 100)) "the wheel scroll position"
    require (scrollToPosition = (0, 0)) "scroll_to sets the position"
    require (scrollToDirty = Some (0, 0, 240, 120)) "scroll_to invalidates the viewport"
    require (scrolledBack = [ 200; 0; 0 ]) "scrolling back shows the box"
    require (animationFrames >= 10) "a running animation asks for frames"
    require (colours.Count >= 5) "updates advance the animation"
