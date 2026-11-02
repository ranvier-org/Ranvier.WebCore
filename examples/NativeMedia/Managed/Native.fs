namespace Ranvier.Examples.NativeMedia

open System.Runtime.InteropServices

[<assembly: System.Runtime.CompilerServices.InternalsVisibleTo("Managed")>]
do ()

/// <summary>The application DLL's copied playback state.</summary>
[<Struct; StructLayout(LayoutKind.Sequential)>]
type internal NativeSnapshot =
    val mutable Size: uint32
    val mutable State: int
    val mutable Error: int
    val mutable Flags: uint32
    val mutable Position: double
    val mutable Duration: double

/// <summary>The texture and timestamp owned by a native publication lease.</summary>
[<Struct; StructLayout(LayoutKind.Sequential)>]
type internal NativeFrameInfo =
    val mutable Size: uint32
    val mutable Width: uint32
    val mutable Height: uint32
    val mutable Reserved: uint32
    val mutable Texture: nativeint
    val mutable Timestamp: int64

module internal Native =
    [<Literal>]
    let Library = "RanvierNativeMedia"

    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_create(nativeint& output, int& state)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Unicode, ExactSpelling = true)>]
    extern int ranvier_media_open(nativeint session, string localPath)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_play(nativeint session)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_pause(nativeint session)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_stop(nativeint session)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_seek(nativeint session, double seconds)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_cancel(nativeint session)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_snapshot(nativeint session, NativeSnapshot& output)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_next_frame(nativeint session, nativeint& output)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_republish(nativeint session, nativeint& output)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_frame_info(nativeint frame, NativeFrameInfo& output)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_frame_release(nativeint& frame)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Unicode, ExactSpelling = true)>]
    extern int ranvier_media_controls_attach(nativeint session, nativeint window, string title)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_controls_drain(nativeint session)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_controls_detach(nativeint session)
    [<DllImport(Library, CallingConvention = CallingConvention.Cdecl)>]
    extern int ranvier_media_release(nativeint& session)
