namespace Ranvier.Examples.NativeMedia

open System
open System.Runtime.InteropServices
open Ranvier.Dom
open Ranvier.View.WebCore

/// <summary>The OS playback session's reported state.</summary>
type PlaybackState =
    | Closed = 0
    | Ready = 1
    | Loading = 2
    | Playing = 3
    | Paused = 4
    | Ended = 5
    | Cancelled = 6
    | Failed = 7
    | Unavailable = 8
    | Stopped = 9

/// <summary>An unavailable optional application DLL, OS player or graphics provider, preserving its HRESULT.</summary>
type MediaProviderUnavailableException(errorCode: int) =
    inherit ExternalException("The optional Windows playback provider is unavailable", errorCode)

/// <summary>A copied playback-clock and readiness sample that owns no native resource.</summary>
[<Sealed>]
type PlaybackSnapshot internal (value: NativeSnapshot) =
    /// <summary>The OS player's state.</summary>
    member _.State = enum<PlaybackState> value.State
    /// <summary>The exact native failure code; nonnegative values indicate success.</summary>
    member _.HResult = value.Error
    /// <summary>The OS audio/video clock in seconds.</summary>
    member _.PositionSeconds = value.Position
    /// <summary>The duration in seconds, possibly NaN before source readiness.</summary>
    member _.DurationSeconds = value.Duration
    /// <summary>Whether current media data is ready.</summary>
    member _.Ready = value.Flags &&& 1u <> 0u
    /// <summary>Whether an asynchronous seek is pending.</summary>
    member _.Seeking = value.Flags &&& 2u <> 0u
    /// <summary>Whether the source contains audio.</summary>
    member _.HasAudio = value.Flags &&& 4u <> 0u
    /// <summary>Whether the source contains video.</summary>
    member _.HasVideo = value.Flags &&& 8u <> 0u

module private Ownership =
    let thread owner =
        if Environment.CurrentManagedThreadId <> owner then
            raise (ExternalException("Native media calls require the creating thread", int 0x8001010Eu))

    let check operation status =
        if status < 0 then
            raise (ExternalException(operation + " failed", status))

/// <summary>A bound video publication retaining its provider and texture until disposal.</summary>
/// <remarks>Finish and release the native composition lease before disposing this lease on the creating thread.</remarks>
[<Sealed>]
type VideoFrameLease internal (owner: int, info: NativeFrameInfo, release: unit -> unit) =
    let mutable disposed = false
    let ensure () =
        Ownership.thread owner
        if disposed then raise (ObjectDisposedException "VideoFrameLease")

    /// <summary>The provider presentation timestamp used to select application caption cues.</summary>
    member _.PresentationTime = ensure (); TimeSpan.FromTicks info.Timestamp
    /// <summary>The decoded frame width in pixels.</summary>
    member _.PixelWidth = ensure (); int info.Width
    /// <summary>The decoded frame height in pixels.</summary>
    member _.PixelHeight = ensure (); int info.Height
    /// <summary>The borrowed D3D11 texture, valid only while this lease remains live.</summary>
    member _.Texture = ensure (); info.Texture

    interface IDisposable with
        member _.Dispose() =
            if not disposed then
                Ownership.thread owner
                try release ()
                finally disposed <- true

/// <summary>An optional Windows Media Foundation player with explicit owner-thread and video-publication lifetime.</summary>
/// <remarks>Dispose every frame lease before destroying its View host. Disposing the player pauses/revokes actions immediately; live frames defer provider teardown.</remarks>
[<Sealed>]
type WindowsPlayback private (initial: nativeint) =
    let owner = Environment.CurrentManagedThreadId
    let mutable handle = initial

    let ensure () =
        Ownership.thread owner
        if handle = 0n then raise (ObjectDisposedException "WindowsPlayback")

    let command name call =
        ensure ()
        call handle |> Ownership.check name

    let publish repeat (host: WebCoreHost) (target: Element) =
        ensure ()
        if isNull (box host) then nullArg (nameof host)
        if isNull (box target) then nullArg (nameof target)
        if not (WebCoreHost.Has "texture-input-d3d11") then
            raise (NotSupportedException "This native renderer has no D3D11 texture input")
        let mutable frame = 0n
        let status =
            if repeat then Native.ranvier_media_republish(handle, &frame)
            else Native.ranvier_media_next_frame(handle, &frame)
        Ownership.check "media frame publication" status
        if status = 1 then ValueNone
        else
            let mutable bound = false
            try
                let mutable info = Unchecked.defaultof<NativeFrameInfo>
                info.Size <- uint32 (Marshal.SizeOf<NativeFrameInfo>())
                Native.ranvier_media_frame_info(frame, &info) |> Ownership.check "media frame metadata"
                host.BindD3D11Texture(target, info.Texture)
                bound <- true
                host.NativeTextureChanged target
                let mutable held = frame
                let release () =
                    let mutable failure: exn = null
                    try host.BindD3D11Texture(target, 0n)
                    with
                    | :? ObjectDisposedException -> ()
                    | error -> failure <- error
                    let status = Native.ranvier_media_frame_release(&held)
                    if not (isNull failure) then raise failure
                    Ownership.check "media frame release" status
                ValueSome (new VideoFrameLease(owner, info, release))
            with error ->
                if bound then
                    try host.BindD3D11Texture(target, 0n) with _ -> ()
                Native.ranvier_media_frame_release(&frame) |> ignore
                raise error

    /// <summary>Creates an OS player on the calling thread; no file or media session controls are opened.</summary>
    /// <exception cref="T:System.PlatformNotSupportedException">The application is not running on Windows.</exception>
    /// <exception cref="T:Ranvier.Examples.NativeMedia.MediaProviderUnavailableException">The optional DLL or OS provider is unavailable.</exception>
    static member Create() =
        if not (OperatingSystem.IsWindows()) then
            raise (PlatformNotSupportedException "Windows Media Foundation playback requires Windows")
        let mutable result = 0n
        let mutable state = 0
        let status =
            try Native.ranvier_media_create(&result, &state)
            with :? DllNotFoundException as error -> raise (MediaProviderUnavailableException error.HResult)
        if status < 0 && state = int PlaybackState.Unavailable then
            raise (MediaProviderUnavailableException status)
        Ownership.check "media create" status
        new WindowsPlayback(result)

    /// <summary>Opens one local media file; create another player to use another source.</summary>
    member _.OpenFile(path: string) = command "media open" (fun session -> Native.ranvier_media_open(session, path))
    /// <summary>Starts or resumes the OS audio/video clock.</summary>
    member _.Play() = command "media play" Native.ranvier_media_play
    /// <summary>Pauses the OS audio/video clock.</summary>
    member _.Pause() = command "media pause" Native.ranvier_media_pause
    /// <summary>Pauses and seeks the source to zero.</summary>
    member _.Stop() = command "media stop" Native.ranvier_media_stop
    /// <summary>Requests a nonnegative finite position in seconds.</summary>
    member _.Seek(seconds: float) = command "media seek" (fun session -> Native.ranvier_media_seek(session, seconds))
    /// <summary>Revokes controls and cancels playback; an outstanding frame retains the provider until released.</summary>
    member _.Cancel() = command "media cancel" Native.ranvier_media_cancel
    /// <summary>Copies current playback state, preserving native error and clock values.</summary>
    member _.Snapshot() =
        ensure ()
        let mutable value = Unchecked.defaultof<NativeSnapshot>
        value.Size <- uint32 (Marshal.SizeOf<NativeSnapshot>())
        Native.ranvier_media_snapshot(handle, &value) |> Ownership.check "media snapshot"
        PlaybackSnapshot value
    /// <summary>Publishes a decoded frame into a composited element, or returns ValueNone when no frame is ready.</summary>
    /// <remarks>Release the previous frame and composition leases before requesting another publication.</remarks>
    member _.TryPublishFrame(host: WebCoreHost, target: Element) = publish false host target
    /// <summary>Republishes the retained paused frame for a new View presentation.</summary>
    /// <remarks>Release the previous frame and composition leases first; ValueNone means no frame was decoded yet.</remarks>
    member _.TryRepublishFrame(host: WebCoreHost, target: Element) = publish true host target
    /// <summary>Attaches OS transport controls to the application's own top-level HWND.</summary>
    member _.AttachControls(window: nativeint, title: string) =
        command "media controls attach" (fun session -> Native.ranvier_media_controls_attach(session, window, title))
    /// <summary>Applies queued OS actions to this player and publishes its state/timeline on the owner thread.</summary>
    member _.DrainControls() = command "media controls drain" Native.ranvier_media_controls_drain
    /// <summary>Revokes OS callbacks and disables this player's session controls.</summary>
    member _.DetachControls() = command "media controls detach" Native.ranvier_media_controls_detach

    interface IDisposable with
        member _.Dispose() =
            if handle <> 0n then
                Ownership.thread owner
                Native.ranvier_media_release(&handle) |> Ownership.check "media release"
