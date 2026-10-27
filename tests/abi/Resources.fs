/// Loads a stylesheet, an image and a web font through the host resource handler (ABI v11), and the same page
/// without a handler, and checks the painted pixels of each.
module RanvierWebCoreAbi.Resources

open System
open System.Diagnostics
open System.IO
open System.IO.Compression
open System.Text
open System.Text.Json
open RanvierWebCoreAbi.Native

let private width, height = 640, 360

let private origin = "https://rv.test/"

let private html =
    $"<!doctype html><html><head><link rel=stylesheet href='{origin}style.css'></head><body><img src='{origin}green.png' width=40 height=40><div id=box></div><div id=text>XXXX</div></body></html>"

let private css =
    $"@font-face{{font-family:HostAhem;src:url({origin}ahem.ttf)}}body{{margin:0;background:white}}img{{position:absolute;left:400px;top:40px}}#box{{position:absolute;left:40px;top:40px;width:100px;height:60px;background:rgb(200,20,120)}}#text{{position:absolute;left:40px;top:160px;font:40px/40px HostAhem,serif;color:rgb(0,0,255)}}"

let private crc32 (bytes: byte[]) =
    let mutable crc = 0xFFFFFFFFu

    for b in bytes do
        crc <- crc ^^^ uint32 b

        for _ in 1..8 do
            crc <-
                if crc &&& 1u = 1u then
                    (crc >>> 1) ^^^ 0xEDB88320u
                else
                    crc >>> 1

    crc ^^^ 0xFFFFFFFFu

let private writePpm (path: string) (rgba: byte[]) =
    use output = File.Create path
    output.Write (Encoding.ASCII.GetBytes $"P6\n{width} {height}\n255\n")

    for i in 0..4 .. rgba.Length - 4 do
        output.Write (rgba, i, 3)

/// A truecolor PNG of the given size filled with one RGB colour.
let private solidPng (size: int) (r: byte, g: byte, b: byte) =
    let chunk (kind: string) (data: byte[]) (output: Stream) =
        let header = Encoding.ASCII.GetBytes kind

        let big (value: uint32) =
            [| byte (value >>> 24); byte (value >>> 16); byte (value >>> 8); byte value |]

        output.Write (big (uint32 data.Length))
        output.Write header
        output.Write data
        output.Write (big (crc32 (Array.append header data)))

    let rows =
        use compressed = new MemoryStream ()

        do
            use z = new ZLibStream (compressed, CompressionLevel.Optimal, true)

            for _ in 1..size do
                z.WriteByte 0uy

                for _ in 1..size do
                    z.Write ([| r; g; b |], 0, 3)

        compressed.ToArray ()

    let ihdr =
        Array.concat
            [
                [| 0uy; 0uy; 0uy; byte size |]
                [| 0uy; 0uy; 0uy; byte size |]
                [| 8uy; 2uy; 0uy; 0uy; 0uy |]
            ]

    use png = new MemoryStream ()
    png.Write [| 0x89uy; 0x50uy; 0x4Euy; 0x47uy; 0x0Duy; 0x0Auy; 0x1Auy; 0x0Auy |]
    chunk "IHDR" ihdr png
    chunk "IDAT" rows png
    chunk "IEND" [||] png
    png.ToArray ()

let private rgbAt (rgba: byte[]) x y =
    let i = (y * width + x) * 4
    [ int rgba[i]; int rgba[i + 1]; int rgba[i + 2] ]

let private countColour (rgba: byte[]) (x0, y0, x1, y1) colour =
    seq {
        for y in y0 .. y1 - 1 do
            for x in x0 .. x1 - 1 do
                if rgbAt rgba x y = colour then
                    yield 1
    }
    |> Seq.length

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

let private magenta, green, blue, white =
    [ 200; 20; 120 ], [ 10; 200; 30 ], [ 0; 0; 255 ], [ 255; 255; 255 ]

/// The pixels checked on a frame: the stylesheet's box, the image and the Ahem text's block of 160 by 40.
let private probe (frame: byte[]) =
    {|
        box = rgbAt frame 90 70
        image = rgbAt frame 420 60
        textRight = rgbAt frame 195 195
        textBlue = countColour frame (40, 160, 200, 200) blue
    |}

let private served (frame: byte[]) =
    let p = probe frame

    p.box = magenta
    && p.image = green
    && p.textRight = blue
    && p.textBlue = 6400

let run (outDir: string) =
    let source =
        match Environment.GetEnvironmentVariable "RANVIER_WEBKIT_SOURCE" with
        | null
        | "" -> @"C:\wk\src"
        | dir -> dir

    let resources =
        dict
            [
                $"{origin}style.css", (Encoding.UTF8.GetBytes css, "text/css; charset=utf-8")
                $"{origin}green.png", (solidPng 40 (10uy, 200uy, 30uy), "image/png")
                $"{origin}ahem.ttf", (File.ReadAllBytes (Path.Combine (source, "Tools/WebKitTestRunner/fonts/AHEM____.TTF")), "font/ttf")
            ]

    let requested = ResizeArray<string>()

    // Served: cycles the run loop in 10 ms steps until the frame shows all three resources, for at most 5 s.
    use host = new Host (width, height)

    host.ServeResources (fun url ->
        requested.Add url

        match resources.TryGetValue url with
        | true, resource -> Some resource
        | _ -> None)

    host.LoadHtml html
    let beforeCycle = probe (host.Paint ())
    let clock = Stopwatch.StartNew ()
    let mutable frame = host.Paint ()
    let mutable steps = 0

    while not (served frame)
          && clock.ElapsedMilliseconds < 5000L do
        host.CycleRunLoop 10
        steps <- steps + 1
        frame <- host.Paint ()

    let servedMs = clock.Elapsed.TotalMilliseconds
    let servedProbe = probe frame
    writePpm (Path.Combine (outDir, "fsharp-resources-served.ppm")) frame

    // Unserved: the same page and cycles without a handler.
    use bare = new Host (width, height)
    bare.LoadHtml html

    for _ in 1..steps do
        bare.CycleRunLoop 10

    let bareFrame = bare.Paint ()
    let bareProbe = probe bareFrame
    writePpm (Path.Combine (outDir, "fsharp-resources-unserved.ppm")) bareFrame

    let summary =
        {|
            requested = List.ofSeq requested
            beforeCycle = beforeCycle
            served = servedProbe
            servedSteps = steps
            servedMilliseconds = Math.Round (servedMs, 1)
            unserved = bareProbe
        |}

    File.WriteAllText (
        Path.Combine (outDir, "fsharp-resources.json"),
        JsonSerializer.Serialize (summary, JsonSerializerOptions (WriteIndented = true))
    )

    require (List.sort summary.requested = List.sort (List.ofSeq resources.Keys)) "the handler receives each resource URL once"

    require
        (beforeCycle.box <> magenta
         && beforeCycle.image <> green)
        "loads complete on a run loop cycle, after load_html returns"

    require (servedProbe.box = magenta) "a served stylesheet applies"
    require (servedProbe.image = green) "a served PNG image paints"

    require
        (servedProbe.textRight = blue
         && servedProbe.textBlue = 6400)
        "a served @font-face font renders the Ahem block"

    require
        (bareProbe.box = white
         && bareProbe.image <> green
         && bareProbe.textRight = white)
        "without a handler the loads fail"

    printfn "RANVIER_FSHARP_RESOURCES PASS %s" (JsonSerializer.Serialize summary)
