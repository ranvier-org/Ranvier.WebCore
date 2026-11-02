module RanvierWebCoreAbi.PrintingTest

open System
open System.Runtime.InteropServices
open System.Text
open System.Threading
open RanvierWebCoreAbi.Native

let private options () =
    let mutable value = Unchecked.defaultof<PrintOptions>
    value.size <- uint32 (Marshal.SizeOf<PrintOptions>())
    value.max_pages <- 16u
    value.paper_width_points <- 576.0
    value.paper_height_points <- 720.0
    value.margin_top_points <- 36.0
    value.margin_right_points <- 36.0
    value.margin_bottom_points <- 36.0
    value.margin_left_points <- 36.0
    value.output_budget_bytes <- 8UL * 1024UL * 1024UL
    value.raster_dpi <- 144.0f
    value

/// <summary>Exercises the actual PDF P/Invoke, deferred completion and resource byte lifetime.</summary>
[<EntryPoint>]
let main arguments =
    let mutable assertions = 0

    let check condition message =
        assertions <- assertions + 1

        if not condition then
            invalidOp message

    let directory = IO.Path.GetFullPath(arguments.[0])

    let filename =
        if OperatingSystem.IsWindows() then
            "RanvierWebCoreHost.dll"
        elif OperatingSystem.IsMacOS() then
            "libRanvierWebCoreHost.dylib"
        else
            "libRanvierWebCoreHost.so"

    let library = NativeLibrary.Load(IO.Path.Combine(directory, filename))

    NativeLibrary.SetDllImportResolver(
        typeof<PrintOptions>.Assembly,
        DllImportResolver(fun name _ _ -> if name = "RanvierWebCoreHost" then library else 0n)
    )

    check (Marshal.SizeOf<PrintOptions>() = 72) "typed options layout"
    check (rv_abi_has "printing-pdf" = 1) "PDF capability"
    let mutable host = rv_host_create (500, 300)
    check (host <> 0n) "host creation"
    let tokens = ResizeArray<uint64>()
    use cancellation = new CancellationTokenSource()

    let poll =
        PrintCancelPoll(fun _ -> if cancellation.IsCancellationRequested then 1 else 0)

    let pollPointer = Marshal.GetFunctionPointerForDelegate(poll)
    let events = ResizeArray<struct (int * int * int)>()

    let completed =
        ResourceCompletion(fun _ outcome width height -> events.Add(struct (outcome, width, height)))

    let completedPointer = Marshal.GetFunctionPointerForDelegate(completed)

    let read token =
        let mutable length = -1L
        let sizeStatus = rv_print_pdf_result (token, Array.empty<byte>, 0L, &length)
        check (sizeStatus = (if length = 0L then 0 else -6)) "size query"
        let bytes = Array.zeroCreate<byte>(int length)
        check (rv_print_pdf_result (token, bytes, length, &length) = 0) "PDF bytes copy"
        bytes

    let request expected =
        events.Clear()
        let mutable selected = options ()
        let mutable pages = -1
        let mutable token = 0UL

        check
            (rv_host_print_pdf (host, &selected, pollPointer, 0n, completedPointer, 0n, &pages, &token) = 0)
            "print admission"

        check (events.Count = 0 && token <> 0UL) "completion is deferred"
        tokens.Add(token)
        let mutable turns = 0

        while events.Count = 0 && turns < 100 do
            rv_run_loop_cycle 1 |> ignore
            turns <- turns + 1

        check (events.Count = 1 && events.[0] = struct (expected, 0, 0)) "one terminal callback"
        token, pages, read token

    try
        let html =
            Encoding.UTF8.GetBytes(
                "<!doctype html><style>article{break-before:page}article:first-child{break-before:auto}</style>"
                + "<article>MANAGED PDF PAGE ONE</article><article>MANAGED PDF PAGE TWO</article><article>MANAGED PDF PAGE THREE</article>"
            )

        check (rv_host_load_html (host, html, html.Length) = 0) "load current document"
        check (rv_host_update host >= 0) "layout current document"
        let retained, pages, bytes = request 0
        check (pages = 3 && bytes.Length > 5 && Encoding.ASCII.GetString(bytes, 0, 5) = "%PDF-") "three-page PDF bytes"
        cancellation.Cancel()
        let _, _, empty = request 3
        check (empty.Length = 0) "cancelled print publishes no PDF"
        rv_host_destroy host
        host <- 0n
        check (read retained = bytes) "PDF bytes survive host destruction"

        Console.WriteLine(
            "PRINTING_MANAGED_ASSERTIONS="
            + assertions.ToString(Globalization.CultureInfo.InvariantCulture)
        )

        Console.WriteLine(
            "DYNAMIC_CODE_SUPPORTED="
            + Runtime.CompilerServices.RuntimeFeature.IsDynamicCodeSupported.ToString()
        )

        0
    finally
        for token in tokens do
            rv_resource_release token |> ignore

        if host <> 0n then
            rv_host_destroy host

        GC.KeepAlive(poll)
        GC.KeepAlive(completed)
