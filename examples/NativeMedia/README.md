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
The project targets the matching `Ranvier.View.WebCore` alpha.45 cohort.
Until that planned cohort is published, `RanvierViewRoot` must name its exact
owned View source checkout; private source qualification does not prove a public
package consumer. The matching package-only consumer remains a release gate.
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
The adapter also reserves each host/DOM-element across players: another player
cannot publish there until the current lease is consumed. Do not rebind or
unbind that leased element through other View/native APIs. Different elements
can carry independent players. Native DOM identity, rather than wrapper object
identity, determines whether targets are the same.
Dispose frame leases before destroying their View host. Player disposal revokes
controls and pauses immediately; an outstanding frame defers final provider
destruction. Wrong-thread calls and releases preserve ownership and fail with
the native wrong-thread HRESULT. Disposal is mandatory and idempotent.
If publication notification and rollback unbinding both fail, the original
publication error is reported and the player retains cleanup ownership. Its
next owner-thread call or `Dispose` retries unbinding before releasing the frame;
a failed retry remains retryable while the native frame pointer is still owned.
When native release consumes that pointer but reports a cleanup HRESULT, the
error is preserved and the frame is closed; it cannot expose a retired texture
or release it twice. A definitively disposed host has already released its
renderer bindings and permits provider cleanup.

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

The managed consumer also runs actual JIT and strict NativeAOT, each followed
by a copied application with the optional DLL physically absent:

```powershell
python -I -X utf8 tests/media/managed.py --native-stage PATH_TO_STAGE --view-root PATH_TO_VIEW --nuget-config PATH_TO_NUGET_CONFIG --output managed-media-proof
```

The stage is the parent of `runtimes/win-x64/native`. The explicit View source
graph supports qualification before the matching View package is published;
use a clean owned checkout and configuration retaining its feed mappings.
`--dotnet-sdk-driver` can select the exact installed SDK's `dotnet.dll`.
The runner builds only the optional SDK DLL and application, checks all source
and renderer hashes, retains command/log receipts, and removes disposable build
outputs. Its inspection-only SDK helper reads the composed GPU frame and the
process's own audio/OS session; the application adapter itself uses only public
View APIs. Run under the normal native-process and memory limits.
Call `--phase build` and then `--phase run` with the same arguments when build
and runtime grants are separate. The first retains its owned build directory;
the second verifies unchanged inputs and cleans it after execution.
