/// Checks ABI v16: repainting the dirty rectangle into the previous frame gives the same image as a full
/// paint, at device scales 1 and 2, and measures both paints.
module RanvierWebCoreAbi.Paint

open System.Diagnostics
open System.IO
open System.Text.Json
open RanvierWebCoreAbi.Native

let private html =
    "<!doctype html><html><head><style>body{margin:0;background:linear-gradient(90deg,#fff,#cde);font:16px sans-serif}p{margin:8px}#box{position:absolute;left:300px;top:200px;width:40px;height:40px;background:rgb(200,0,0)}</style></head><body>"
    + String.replicate 60 "<p>Native WebCore paints only what changed, row by row, into the image the app keeps.</p>"
    + "<div id=box></div></body></html>"

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

/// The mean milliseconds of a paint call over runs.
let private timed runs (paint: unit -> unit) =
    paint ()
    let clock = Stopwatch.StartNew ()

    for _ in 1..runs do
        paint ()

    clock.Elapsed.TotalMilliseconds / float runs

let private check' (host: Host) (box: Node) colour =
    let w, h = host.PaintSize
    let image = host.Paint ()

    rv_element_set_style (box.Handle, "background", utf8 colour, utf8Length colour, 0)
    |> check "restyle box"

    host.Update ()
    let dirty = host.DirtyRect
    let x, y, dw, dh = defaultArg dirty (0, 0, 0, 0)

    rv_host_paint_rgba_rect (host.Handle, image, image.Length, x, y, dw, dh)
    |> check "paint_rgba_rect"

    let afterPartial = host.DirtyRect
    let full = host.Paint ()
    dirty, afterPartial, (image = full), w, h

let run (outDir: string) =
    require (rv_abi_has "partial-paint" = 1) "rv_abi_has partial-paint"
    use host = new Host (1280, 720)
    host.LoadHtml html
    use box = host.GetElementById "box"

    let dirty1, after1, equal1, _, _ = check' host box "rgb(0,0,200)"
    host.SetDeviceScale 2.0f
    let dirty2, after2, equal2, w2, h2 = check' host box "rgb(0,200,0)"
    host.SetDeviceScale 1.0f

    let image = host.Paint ()
    let fullMs = timed 20 (fun () -> host.Paint () |> ignore)

    let rectMs =
        timed 20 (fun () ->
            rv_host_paint_rgba_rect (host.Handle, image, image.Length, 300, 200, 40, 40)
            |> check "timed rect")

    let summary =
        {|
            dirty1 = dirty1
            equal1 = equal1
            after1 = after1
            dirty2 = dirty2
            equal2 = equal2
            after2 = after2
            size2 = [ w2; h2 ]
            fullMs = fullMs
            rectMs = rectMs
        |}

    File.WriteAllText (Path.Combine (outDir, "fsharp-paint.json"), JsonSerializer.Serialize (summary, JsonSerializerOptions (WriteIndented = true)))
    printfn "RANVIER_FSHARP_PAINT %s" (JsonSerializer.Serialize summary)

    require (dirty1 = Some (300, 200, 40, 40)) "restyling the box invalidates the box"
    require equal1 "the dirty repaint matches a full paint at scale 1"
    require after1.IsNone "a paint that covers the dirty rectangle clears it"
    require equal2 "the dirty repaint matches a full paint at scale 2"
    require (rectMs < fullMs) "a 40 by 40 repaint is faster than a full 1280 by 720 paint"
