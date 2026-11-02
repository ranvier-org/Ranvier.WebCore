# Optional native Windows playback

This application-side adapter uses the Windows SDK Media Foundation/Media
Engine and OS transport controls. They are not loaded by the renderer and add
no WebCore feature flag, codec, network stack or package dependency. Windows
x64 is the qualified example; other platform provider adapters are not supplied.
No HTMLMediaElement, Web Audio, remote playback or browser activation behavior
is exposed.

## F# application use

Build the optional DLL with the installed Visual Studio C++ tools and Windows SDK:

```powershell
python examples/NativeMedia/build_windows.py --output media-provider
```

Reference `Managed/NativeMedia.fsproj` from the application and set
`NativeMediaDllPath` to the resulting absolute `RanvierNativeMedia.dll` path.
The project uses the existing `Ranvier.View.WebCore` package; `RanvierViewRoot`
can instead name an owned View source checkout for an unpublished cohort.
This example is not a new renderer package or automatically loaded dependency.

Create `Ranvier.Examples.NativeMedia.WindowsPlayback` on the View host thread,
open a local file and call `Play`. `AttachControls(window.NativeHandle, title)`
adds OS controls for that application's HWND; `DrainControls` applies queued
commands on the same thread. Snapshots preserve the provider's clock and HRESULT.
Known provider absence raises `MediaProviderUnavailableException`; unsupported
platforms fail before attempting to load the Windows DLL.

For a composited `Element` in the current host document:

```fsharp
match player.TryPublishFrame(window.Host, target) with
| ValueSome frame ->
    use frame = frame
    // Select ordinary DOM caption text from frame.PresentationTime.
    window.Present()
| ValueNone -> ()
```

The frame lease binds/notifies the existing View texture input and retains the
player/COM texture. Finish and release any native composition lease before
disposing the frame lease, which unbinds and releases the publication. Only one
publication may be outstanding. `TryRepublishFrame` handles paused redraws.
Dispose frame leases before destroying their View host. Player disposal revokes
controls and pauses immediately; an outstanding frame defers final provider
destruction. Wrong-thread calls and releases preserve ownership and fail with
the native wrong-thread HRESULT. Disposal is mandatory and idempotent.

`WindowsPlayback.h` owns one local source per initialized session. Call
`initialize()`, then `openFile(path)` on the owning application thread. A second
source is rejected until explicit reinitialization; this keeps late source
events attached to their original session. `play()`, `pause()`, `seek(seconds)`,
`stop()`, `snapshot()` and idempotent `close()` use the same OS player. `cancel()`
closes the session and discards late events. The snapshot preserves native
HRESULT failures; known missing-provider/unsupported-device outcomes are
explicitly `Unavailable`. Do not turn arbitrary failures into unavailable.

The OS player supplies both audio and the playback clock. The application
regularly calls `nextFrame(frame)` during its normal render turns, including
paused seeking. `S_FALSE` means no new frame. A successful frame is an RGBA8
shared D3D11 texture published under keyed-mutex key1. Pass it to the existing
`rv_host_bind_d3d11_texture` for a composited native DOM element, call
`rv_host_native_texture_changed`, update and acquire/present the native frame.
The renderer returns key0. Republish a retained paused texture under that same
protocol when another host frame is needed. Do not publish again while a
consumer owns the texture. A retained COM reference owns the resource, not an
immutable copy of its pixels.

Use the provider frame's presentation timestamp to select application-supplied
caption cues and update ordinary native DOM text. Keep decoding, local file
ownership and cue parsing in the application. Unbind the native texture before
closing the session; existing DOM clipping, transforms, opacity, DPI and stacking
remain renderer operations. The tests use an original two-second local H264/AAC
fixture; they make no complete format-support claim. OS codecs/endpoints remain
optional, and no codec or language component is installed by the example.

`WindowsMediaControls.h` binds to the application's own top-level HWND. Call
`initialize(window, title)` and regularly `drain(player)` on the same owner
thread. OS callbacks only enqueue bounded actions; they never call the renderer
or player from a worker thread. Publishing/draining reports actual playback
state and timeline. Close the controls before closing the player/window. Closing
revokes handlers, clears pending commands and disables that OS session. The OS
may acknowledge an already queued transport request after close; it cannot
restart playback through a revoked handler.

Only applications explicitly consuming these headers link their Windows SDK
libraries: Media Foundation, D3D11/DXGI, COM, and WinRT/window libraries for the
optional controls. Keep that adapter in the application's optional provider
module so a missing OS component can be reported without loading it into the
lean renderer. No user audio-volume setting, global media-key injection or
other application's media session is changed by the qualification tests.

The canonical native Windows GPU probe runs:

```powershell
python -I -X utf8 tests/media/windows.py --native-directory PATH_TO_NATIVE --output native-media-proof
```

It builds SDK-only disposable consumers, verifies actual playback/error/cancel
and sink lifetime, reads decoded and DOM-composited GPU frames, and uses the real
OS session manager to request actions on its own explicit application ID. Audio
output is measured on the test process's own audio-session meter; no system
audio recording is saved. Reports distinguish unavailable optional services from
actual failures, and the runner exits nonzero when an executed group fails.
Generated executables/objects are cleaned after execution. Renderer payload
hashes and consumer source hashes must remain unchanged.
