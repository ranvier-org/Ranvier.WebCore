module RanvierNativeMedia.ManagedChecks

open System
open System.Diagnostics
open System.IO
open System.Runtime.InteropServices
open System.Threading
open Ranvier.Examples.NativeMedia
open Ranvier.View.WebCore.Sdl

module private Support =
    [<DllImport("MediaManagedTestSupport", CallingConvention = CallingConvention.Cdecl)>]
    extern int media_test_identity()
    [<DllImport("MediaManagedTestSupport", CallingConvention = CallingConvention.Cdecl)>]
    extern int media_test_os_action(int action, double seconds)
    [<DllImport("MediaManagedTestSupport", CallingConvention = CallingConvention.Cdecl)>]
    extern int media_test_audio(float32& peak, int& active)
    [<DllImport("MediaManagedTestSupport", CallingConvention = CallingConvention.Cdecl)>]
    extern int media_test_render(nativeint host, nativeint inputTexture, byte[] output, uint32 capacity, int& width, int& height)

let private page =
    "<style>body{margin:0;background:white}#clip{position:absolute;left:20px;top:20px;width:90px;height:50px;overflow:hidden;will-change:transform}"
    + "#video{width:96px;height:64px;will-change:transform;transform:translateX(5px);opacity:.75}"
    + "#caption{position:absolute;left:20px;top:90px;font:20px sans-serif}</style>"
    + "<div id='clip'><div id='video'></div></div><div id='caption'></div>"

/// <summary>Runs actual managed playback, GPU composition, clock, OS actions and publication teardown.</summary>
[<EntryPoint>]
let main arguments =
    let mutable assertions = 0
    let check condition message =
        assertions <- assertions + 1
        if not condition then invalidOp message
    if arguments.Length = 1 && arguments[0] = "--unavailable" then
        try
            use unexpected = WindowsPlayback.Create()
            invalidOp "Absent optional DLL unexpectedly created a provider"
        with :? MediaProviderUnavailableException as error ->
            check (error.HResult < 0) "unavailable keeps actual HRESULT"
            Console.WriteLine "MEDIA_MANAGED_UNAVAILABLE_ASSERTIONS=1"
            0
    else
        if arguments.Length <> 2 then invalidArg "arguments" "Expected native directory and original media fixture"
        let native = Path.GetFullPath arguments[0]
        let library = NativeLibrary.Load(Path.Combine(native, "RanvierWebCoreHost.dll"))
        NativeLibrary.SetDllImportResolver(
            typeof<RanvierWebCoreAbi.Native.PrintOptions>.Assembly,
            DllImportResolver(fun name _ _ -> if name = "RanvierWebCoreHost" then library else 0n))
        check (Support.media_test_identity() = 0) "own process media identity"
        use window = Window.Create("Managed native media qualification", 320, 200, hidden = true, renderer = "direct3d11")
        check (Support.media_test_identity() = 0) "own identity retained after SDL initialization"
        let host = window.Host
        host.Document.body.innerHTML <- page
        let target = host.Document.getElementById "video"
        let caption = host.Document.getElementById "caption"
        host.Frame()
        use player = WindowsPlayback.Create()
        player.OpenFile(Path.GetFullPath arguments[1])
        player.AttachControls(window.NativeHandle, "Managed native media fixture")
        let phaseOf (frame: VideoFrameLease) =
            if frame.PresentationTime.Ticks < 6666666L then 0
            elif frame.PresentationTime.Ticks < 13333333L then 1
            else 2
        let mutable frames = 0
        let mutable presentations = 0
        let phases = Collections.Generic.HashSet<int>()
        let mutable peak = 0.0f
        let mutable clockAdvanced = false
        let render present (frame: VideoFrameLease) =
            let phase = phaseOf frame
            let cue = [| "red cue"; "green cue"; "blue cue" |][phase]
            caption.textContent <- cue
            check (caption.textContent = cue) "caption uses provider presentation time"
            check (frame.PixelWidth = 96 && frame.PixelHeight = 64) "decoded frame dimensions"
            host.Frame()
            if present then
                window.Present()
                presentations <- presentations + 1
            else
                let struct (width, height) = host.PaintSize
                let pixels = Array.zeroCreate<byte>(width * height * 4)
                let mutable actualWidth, actualHeight = 0, 0
                check (Support.media_test_render(host.Handle, frame.Texture, pixels, uint32 pixels.Length, &actualWidth, &actualHeight) = 0)
                    "actual GPU-only composition/readback"
                check (actualWidth = width && actualHeight = height) "physical dimensions"
                let scale = float width / 320.0
                let pixel x y =
                    let offset = (int (float y * scale) * width + int (float x * scale)) * 4
                    Array.sub pixels offset 4
                let center, clipped = pixel 40 35, pixel 115 35
                check (center[phase] > 200uy && ([0; 1; 2] |> List.filter ((<>) phase) |> List.forall (fun index -> center[index] > 45uy && center[index] < 100uy)))
                    "decoded pixels obey DOM transform and opacity"
                check (clipped = [|255uy; 255uy; 255uy; 255uy|]) "decoded pixels obey DOM clip"
                let mutable ink = 0
                for y in int (90.0 * scale) .. int (118.0 * scale) - 1 do
                    for x in int (20.0 * scale) .. int (190.0 * scale) - 1 do
                        let offset = (y * width + x) * 4
                        if pixels[offset] < 100uy && pixels[offset + 1] < 100uy && pixels[offset + 2] < 100uy then ink <- ink + 1
                check (ink > 20) "caption glyphs are painted in the actual frame"
                phases.Add phase |> ignore
                frames <- frames + 1
        let turn () =
            player.DrainControls()
            host.Cycle(milliseconds = 0)
            match player.TryPublishFrame(host, target) with
            | ValueNone -> ()
            | ValueSome frame ->
                do
                    use frame = frame
                    render true frame
                match player.TryRepublishFrame(host, target) with
                | ValueNone -> invalidOp "retained decoded frame disappeared"
                | ValueSome readback ->
                    use readback = readback
                    render false readback
            let snapshot = player.Snapshot()
            check (snapshot.HResult >= 0) "native errors remain visible"
            clockAdvanced <- clockAdvanced || snapshot.PositionSeconds > 0.15
            let mutable sample, active = 0.0f, 0
            check (Support.media_test_audio(&sample, &active) = 0) "own process audio-session measurement"
            if active <> 0 then peak <- max peak sample
            snapshot
        let wait label predicate =
            let watch = Stopwatch.StartNew()
            let mutable finished = false
            while not finished && watch.Elapsed.TotalSeconds < 6 do
                let snapshot = turn ()
                finished <- predicate snapshot
                if not finished then Thread.Sleep 5
            check finished label
        player.Play()
        wait "all decoded phases, caption frames and audible OS clock" (fun _ -> phases.Count = 3 && peak > 0.0001f && clockAdvanced)
        wait "OS end reaches managed provider state" (fun sample -> sample.State = PlaybackState.Ended)
        check (frames > 2) "multiple actual decoded frames"
        player.Pause()
        let paused = player.Snapshot().PositionSeconds
        Thread.Sleep 150
        check (abs (player.Snapshot().PositionSeconds - paused) < 0.03) "pause freezes OS clock"
        let mutable pausedPeak, pausedActive = 1.0f, 0
        check (Support.media_test_audio(&pausedPeak, &pausedActive) = 0 && pausedPeak < 0.0001f) "paused own audio sink is silent"
        player.Seek 0.25
        wait "seek completes on same native clock" (fun sample -> not sample.Seeking && abs (sample.PositionSeconds - 0.25) < 0.05)
        match player.TryRepublishFrame(host, target) with
        | ValueNone -> invalidOp "paused republish has no retained frame"
        | ValueSome frame ->
            use frame = frame
            render false frame
        let mutable wrong = 0
        let other = Thread(fun () -> try player.Play() with error -> wrong <- error.HResult)
        other.Start(); other.Join()
        check (wrong = int 0x8001010Eu) "managed wrong-thread call preserves native status"
        let osAction action seconds =
            let watch = Stopwatch.StartNew()
            let mutable result = -1
            while result <> 0 && watch.Elapsed.TotalSeconds < 5 do
                player.DrainControls()
                result <- Support.media_test_os_action(action, seconds)
                if result <> 0 then Thread.Sleep 20
            check (result = 0) "own real OS media-session action accepted"
        osAction 0 0.0
        wait "OS play reaches same managed provider" (fun sample -> sample.State = PlaybackState.Playing)
        osAction 1 0.0
        wait "OS pause reaches same managed provider" (fun sample -> sample.State = PlaybackState.Paused)
        osAction 3 1.0
        wait "OS seek reaches same managed provider" (fun sample -> not sample.Seeking && abs (sample.PositionSeconds - 1.0) < 0.05)
        osAction 2 0.0
        wait "OS stop reaches same managed provider" (fun sample -> sample.State = PlaybackState.Stopped && not sample.Seeking && sample.PositionSeconds < 0.05)
        player.DetachControls()
        player.Seek 1.5
        player.Play()
        let watch = Stopwatch.StartNew()
        let mutable held: VideoFrameLease option = None
        while Option.isNone held && watch.Elapsed.TotalSeconds < 5 do
            host.Cycle(milliseconds = 1)
            match player.TryPublishFrame(host, target) with
            | ValueSome frame -> held <- Some frame
            | ValueNone -> Thread.Sleep 5
        check (Option.isSome held) "publication held across player disposal"
        match held with
        | None -> ()
        | Some frame ->
            use frame = frame
            let mutable frameReleaseError = 0
            let releaseThread = Thread(fun () ->
                try (frame :> IDisposable).Dispose()
                with error -> frameReleaseError <- error.HResult)
            releaseThread.Start()
            releaseThread.Join()
            check (frameReleaseError = int 0x8001010Eu && frame.Texture <> 0n)
                "wrong-thread frame release preserves publication ownership"
            (player :> IDisposable).Dispose()
            render false frame
            let late = try player.Play(); false with :? ObjectDisposedException -> true
            check late "disposed player rejects restart while retained frame remains usable"
            (frame :> IDisposable).Dispose()
            let lateFrame = try frame.Texture |> ignore; false with :? ObjectDisposedException -> true
            check lateFrame "released frame rejects late texture access"
        (player :> IDisposable).Dispose()
        use missing = WindowsPlayback.Create()
        let mutable fileError = 0
        try missing.OpenFile(Path.Combine(Path.GetDirectoryName arguments[1], "absent-managed-media.mp4"))
        with :? ExternalException as error -> fileError <- error.HResult
        check (fileError = int 0x80070002u && missing.Snapshot().State = PlaybackState.Failed) "missing file exact error survives F# wrapper"
        use cancelled = WindowsPlayback.Create()
        cancelled.OpenFile(Path.GetFullPath arguments[1])
        cancelled.Play()
        cancelled.Cancel()
        check (cancelled.Snapshot().State = PlaybackState.Cancelled) "explicit cancellation retained"
        let mutable cancelledError = 0
        try cancelled.Play() with :? ExternalException as error -> cancelledError <- error.HResult
        check (cancelledError < 0) "cancelled provider cannot restart"
        Console.WriteLine("MEDIA_MANAGED_ASSERTIONS=" + assertions.ToString(Globalization.CultureInfo.InvariantCulture))
        Console.WriteLine("MEDIA_MANAGED_FRAMES=" + frames.ToString(Globalization.CultureInfo.InvariantCulture))
        Console.WriteLine("MEDIA_MANAGED_SDL_PRESENTATIONS=" + presentations.ToString(Globalization.CultureInfo.InvariantCulture))
        Console.WriteLine("MEDIA_MANAGED_AUDIO_PEAK=" + peak.ToString("R", Globalization.CultureInfo.InvariantCulture))
        Console.WriteLine("DYNAMIC_CODE_SUPPORTED=" + Runtime.CompilerServices.RuntimeFeature.IsDynamicCodeSupported.ToString())
        0
