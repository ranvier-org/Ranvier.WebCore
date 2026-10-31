/// Drives native WebCore DOM mutation and repaint from F# through the C ABI. The page HTML, nodes and
/// first mutation match NativeHost.cpp, so frames 0 and 1 are directly comparable with the C++ fixture.
module RanvierWebCoreAbi.Program

open System
open System.IO
open System.Text.Json
open System.Threading
open RanvierWebCoreAbi.Native

let width, height = 640, 360

let html =
    "<!doctype html><html><head><style>body{margin:0;background:white;font:20px sans-serif}#panel{margin:32px;padding:24px;background:rgb(20,60,80);color:white;width:500px}button{font:20px sans-serif}</style></head><body></body></html>"

let writePpm (path: string) (rgba: byte[]) =
    use output = File.Create path
    let header = Text.Encoding.ASCII.GetBytes $"P6\n{width} {height}\n255\n"
    output.Write(header, 0, header.Length)

    for i in 0..4 .. rgba.Length - 4 do
        output.Write(rgba, i, 3)

let rgbAt (rgba: byte[]) x y =
    let i = (y * width + x) * 4
    [ int rgba[i]; int rgba[i + 1]; int rgba[i + 2] ]

let changedPixels (a: byte[]) (b: byte[]) =
    seq { 0..4 .. a.Length - 4 }
    |> Seq.filter (fun i -> a[i] <> b[i] || a[i + 1] <> b[i + 1] || a[i + 2] <> b[i + 2])
    |> Seq.length

let opaquePixels (rgba: byte[]) =
    seq { 3..4 .. rgba.Length - 1 }
    |> Seq.filter (fun i -> rgba[i] = 255uy)
    |> Seq.length

let require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

[<EntryPoint>]
let main _ =
    let outDir =
        match Environment.GetEnvironmentVariable "RANVIER_WEBCORE_OUT" with
        | null
        | "" -> "fsharp-run"
        | dir -> dir

    Directory.CreateDirectory outDir |> ignore
    require (rv_abi_version () = 54) "ABI version 54"

    // RANVIER_WEBCORE_PROBE=teardown runs the teardown probes instead of the frames.
    if Environment.GetEnvironmentVariable "RANVIER_WEBCORE_PROBE" = "teardown" then
        Teardown.run outDir
        exit 0

    use host = new Host(width, height)
    host.LoadHtml html
    require (host.ScriptsEnabled = 0) "page scripts disabled after load"
    require (host.VmEntryDisallowed = 1) "JSC VM entry disallowed after load"

    use body = host.Body()
    use panel = host.CreateElement "div"
    panel.SetAttribute("id", "panel")
    use text = host.CreateText "Native WebCore document - before mutation"
    panel.Append text
    use button = host.CreateElement "button"
    button.SetText "Native button"
    panel.Append button
    body.Append panel

    let frame0 = host.Paint()
    writePpm (Path.Combine(outDir, "fsharp-frame0.ppm")) frame0

    text.SetText "Direct native DOM mutation - after"
    panel.SetAttribute("style", "background:rgb(160,40,30)")
    let frame1 = host.Paint()
    writePpm (Path.Combine(outDir, "fsharp-frame1.ppm")) frame1

    let items =
        [ 1..3 ] |> List.map (fun n -> n * n) |> List.map string |> String.concat ", "

    use appended = host.CreateElement "div"
    appended.SetAttribute("style", "margin:0 32px;padding:12px;background:rgb(30,120,60);color:white;width:300px")
    use appendedText = host.CreateText $"Appended from F#: squares {items}"
    appended.Append appendedText
    body.Append appended
    let frame2 = host.Paint()
    writePpm (Path.Combine(outDir, "fsharp-frame2.ppm")) frame2

    let mutable wrongThreadStatus = 0

    let worker =
        Thread(fun () -> wrongThreadStatus <- rv_node_set_text_content (text.Handle, "from another thread"))

    worker.Start()
    worker.Join()

    // Native WebCore EventListeners calling F# handlers.
    let log = ResizeArray<string>()
    let handlerThreads = Collections.Generic.HashSet<int>()
    let vmGuardInHandlers = ResizeArray<int>()

    let record label (event: Event) =
        log.Add $"{label}:{event.Phase}"

        handlerThreads.Add Thread.CurrentThread.ManagedThreadId |> ignore

        vmGuardInHandlers.Add host.VmEntryDisallowed

    let take () =
        let entries = List.ofSeq log
        log.Clear()
        entries

    let propagation =
        use _ = panel.Listen("probe", true, record "panel-capture")
        use _ = button.Listen("probe", false, record "button")
        use _ = panel.Listen("probe", false, record "panel-bubble")
        use _ = body.Listen("probe", false, record "body-bubble")
        GC.Collect()
        GC.WaitForPendingFinalizers()
        GC.Collect()
        let prevented = button.Dispatch("probe", true, true)

        {|
            log = take ()
            prevented = prevented
        |}

    button.Dispatch("probe", true, true) |> ignore
    let afterRemoval = take ()

    let cancellation =
        use _ =
            button.Listen(
                "cancel",
                false,
                fun event ->
                    record "button" event
                    event.PreventDefault()
            )

        use _ =
            panel.Listen("cancel", false, (fun event -> log.Add $"panel-sees-prevented:{event.DefaultPrevented}"))

        let cancelable = button.Dispatch("cancel", true, true)
        let notCancelable = button.Dispatch("cancel", true, false)

        {|
            cancelable = cancelable
            notCancelable = notCancelable
            log = take ()
        |}

    let stopped =
        use _ =
            button.Listen(
                "stop",
                false,
                fun event ->
                    record "button" event
                    event.StopPropagation()
            )

        use _ = button.Listen("stop", false, record "button-second")
        use _ = panel.Listen("stop", false, record "panel-bubble")
        button.Dispatch("stop", true, true) |> ignore
        take ()

    use checkbox = host.CreateElement "input"
    checkbox.SetAttribute("type", "checkbox")
    appended.Append checkbox

    let checkboxClicks =
        let initial = checkbox.Checked

        let clicked =
            use _ = checkbox.Listen("change", false, record "checkbox-change")
            checkbox.Click()
            checkbox.Checked

        let clickedLog = take ()

        let cancelledClick =
            use _ =
                checkbox.Listen(
                    "click",
                    false,
                    fun event ->
                        record "checkbox-click" event
                        event.PreventDefault()
                )

            use _ = checkbox.Listen("change", false, record "checkbox-change")
            checkbox.Click()
            checkbox.Checked

        let cancelledLog = take ()
        checkbox.Click()

        {|
            initial = initial
            clicked = clicked
            clickedLog = clickedLog
            cancelledClick = cancelledClick
            cancelledLog = cancelledLog
            clickedAfterRemoval = checkbox.Checked
        |}

    let failure =
        use _ =
            button.Listen("throw", false, (fun _ -> raise (InvalidOperationException "handler failure from F#")))

        use _ = panel.Listen("throw", false, record "panel-after-throw")

        let error =
            try
                button.Dispatch("throw", true, true) |> ignore
                None
            with :? AggregateException as error ->
                Some error

        {|
            raised =
                error
                |> Option.map (fun error -> error.InnerExceptions |> Seq.map _.Message |> List.ofSeq)
            log = take ()
        |}

    let removalDuringDispatch =
        let second = ref None

        use _ =
            button.Listen(
                "remove",
                false,
                fun event ->
                    record "first" event

                    second.Value
                    |> Option.iter (fun (listener: Listener) -> (listener :> IDisposable).Dispose())
            )

        second.Value <- Some(button.Listen("remove", false, record "second"))
        button.Dispatch("remove", true, true) |> ignore
        let first = take ()
        button.Dispatch("remove", true, true) |> ignore
        {| first = first; second = take () |}

    let beforeReentry = host.Paint()

    let reentry =
        use _ = body.Listen("inner", false, record "inner-body")

        use _ =
            panel.Listen(
                "outer",
                false,
                fun event ->
                    record "outer-start" event
                    text.SetText "Text set inside a native event callback"
                    body.Dispatch("inner", false, false) |> ignore
                    log.Add "outer-end"
            )

        button.Dispatch("outer", true, false) |> ignore
        take ()

    let frame3 = host.Paint()
    writePpm (Path.Combine(outDir, "fsharp-frame3.ppm")) frame3

    let nestedFailure =
        use _ =
            body.Listen("inner-throw", false, (fun _ -> failwith "nested handler failure"))

        use _ =
            panel.Listen(
                "outer-catch",
                false,
                fun event ->
                    record "outer" event

                    try
                        body.Dispatch("inner-throw", false, false) |> ignore
                    with :? AggregateException ->
                        log.Add "caught-nested"
            )

        let outerSucceeded =
            try
                button.Dispatch("outer-catch", true, false) |> ignore

                true
            with _ ->
                false

        {|
            outerSucceeded = outerSucceeded
            log = take ()
        |}

    use guarded = button.Listen("guarded", false, record "guarded")
    let offThread = ref (0, 0)

    let guardWorker =
        Thread(fun () ->
            let mutable prevented = 0
            let removeStatus = rv_listener_remove guarded.Handle

            let dispatchStatus =
                rv_node_dispatch_event (button.Handle, "guarded", 1, 1, &prevented)

            offThread.Value <- (removeStatus, dispatchStatus))

    guardWorker.Start()
    guardWorker.Join()
    button.Dispatch("guarded", true, true) |> ignore
    let guardedLog = take ()

    let greenPixels =
        seq { 0..4 .. frame2.Length - 4 }
        |> Seq.filter (fun i -> frame2[i] = 30uy && frame2[i + 1] = 120uy && frame2[i + 2] = 60uy)
        |> Seq.length

    let summary =
        {|
            managedPid = int64 Environment.ProcessId
            nativePid = rv_process_id ()
            os = Runtime.InteropServices.RuntimeInformation.OSDescription
            runtime = Runtime.InteropServices.RuntimeInformation.FrameworkDescription
            managedThread = Thread.CurrentThread.ManagedThreadId
            pixel40_40 =
                {|
                    frame0 = rgbAt frame0 40 40
                    frame1 = rgbAt frame1 40 40
                |}
            opaque =
                {|
                    frame0 = opaquePixels frame0
                    frame1 = opaquePixels frame1
                    frame2 = opaquePixels frame2
                |}
            changed =
                {|
                    frame0to1 = changedPixels frame0 frame1
                    frame1to2 = changedPixels frame1 frame2
                |}
            frame2GreenPixels = greenPixels
            wrongThreadStatus = wrongThreadStatus
            scriptsEnabled = host.ScriptsEnabled
            vmEntryDisallowed = host.VmEntryDisallowed
            events =
                {|
                    propagation = propagation
                    afterRemoval = afterRemoval
                    cancellation = cancellation
                    stopPropagation = stopped
                    checkbox = checkboxClicks
                    failure = failure
                    removalDuringDispatch = removalDuringDispatch
                    reentry = reentry
                    changedByReentry = changedPixels beforeReentry frame3
                    nestedFailure = nestedFailure
                    offThread =
                        {|
                            removeStatus = fst offThread.Value
                            dispatchStatus = snd offThread.Value
                            guardedLog = guardedLog
                        |}
                    handlerThreads = List.ofSeq handlerThreads
                    vmGuardInHandlers = List.distinct (List.ofSeq vmGuardInHandlers)
                |}
        |}

    require (summary.managedPid = summary.nativePid) "native WebCore runs in the managed process"
    require (summary.pixel40_40.frame0 = [ 20; 60; 80 ]) "frame0 panel background"
    require (summary.pixel40_40.frame1 = [ 160; 40; 30 ]) "frame1 panel background after F# style mutation"
    require (summary.opaque.frame0 > 10000) "frame0 opaque"
    require (summary.changed.frame0to1 > 1000) "frame0->1 repaint changed pixels"
    require (summary.changed.frame1to2 > 1000) "frame1->2 repaint changed pixels"
    require (greenPixels > 1000) "frame2 contains the appended element's background"
    require (wrongThreadStatus = WrongThread) "off-thread call rejected"

    require (summary.scriptsEnabled = 0 && summary.vmEntryDisallowed = 1) "scripts disabled and VM guard held"

    let events = summary.events

    require
        (events.propagation.log = [ "panel-capture:1"; "button:2"; "panel-bubble:3"; "body-bubble:3" ])
        "capture, target and bubble handlers run in DOM order"

    require (not events.propagation.prevented) "uncancelled dispatch reports not prevented"
    require (events.afterRemoval.IsEmpty) "disposed listeners stay silent"
    require (events.cancellation.cancelable) "preventDefault cancels a cancelable event"
    require (not events.cancellation.notCancelable) "preventDefault leaves a non-cancelable event uncancelled"

    require
        (events.cancellation.log =
            [
                "button:2"
                "panel-sees-prevented:True"
                "button:2"
                "panel-sees-prevented:False"
            ])
        "later handlers observe the cancellation"

    require
        (events.stopPropagation = [ "button:2"; "button-second:2" ])
        "stopPropagation ends propagation after the target"

    require
        (not events.checkbox.initial
         && events.checkbox.clicked
         && events.checkbox.clickedLog = [ "checkbox-change:2" ])
        "click toggles the checkbox and fires change synchronously"

    require
        (events.checkbox.cancelledClick
         && events.checkbox.cancelledLog = [ "checkbox-click:2" ])
        "a cancelled click reverts the checkbox default action"

    require (not events.checkbox.clickedAfterRemoval) "click toggles again once the cancelling listener is removed"
    require (events.failure.raised = Some [ "handler failure from F#" ]) "handler exception is rethrown after dispatch"
    require (events.failure.log = [ "panel-after-throw:3" ]) "dispatch continues past a failed handler"

    require
        (events.removalDuringDispatch.first = [ "first:2" ]
         && events.removalDuringDispatch.second = [ "first:2" ])
        "a listener removed during dispatch stays silent"

    require
        (events.reentry = [ "outer-start:3"; "inner-body:2"; "outer-end" ])
        "a handler mutates the DOM and dispatches"

    require (events.changedByReentry > 100) "a DOM mutation made in a handler repaints"

    require
        (events.nestedFailure.outerSucceeded
         && events.nestedFailure.log = [ "outer:3"; "caught-nested" ])
        "a nested dispatch failure stays inside the nested call"

    require
        (events.offThread.removeStatus = WrongThread
         && events.offThread.dispatchStatus = WrongThread
         && events.offThread.guardedLog = [ "guarded:2" ])
        "off-thread remove and dispatch are rejected and leave the listener registered"

    require (events.handlerThreads = [ summary.managedThread ]) "handlers run on the host thread"
    require (events.vmGuardInHandlers = [ 1 ]) "JSC VM entry stays disallowed inside handlers"

    let json =
        JsonSerializer.Serialize(summary, JsonSerializerOptions(WriteIndented = true))

    File.WriteAllText(Path.Combine(outDir, "fsharp-summary.json"), json)
    Resources.run outDir
    Window.run outDir
    Surface.run outDir
    Observe.run outDir
    Paint.run outDir
    Popup.run outDir
    Clipboard.run outDir
    Drop.run outDir
    DragOut.run outDir
    Accessibility.run outDir
    AccessibilityText.run outDir
    Dom.run outDir
    TraversalProbe.run outDir
    printfn "RANVIER_FSHARP_ABI PASS %s" (JsonSerializer.Serialize summary)
    0
