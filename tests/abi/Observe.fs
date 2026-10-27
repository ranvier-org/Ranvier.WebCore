/// Checks ABI v15: resize and intersection observers delivering during rendering updates, and element
/// snapshots at device scales 1 and 2.
module RanvierWebCoreAbi.Observe

open System.IO
open System.Runtime.InteropServices
open System.Text.Json
open RanvierWebCoreAbi.Native

let private html =
    "<!doctype html><html><head><style>body{margin:0;background:white}#box{width:100px;height:50px;background:rgb(200,0,0)}#far{position:absolute;left:0;top:300px;width:50px;height:50px;background:blue}#spacer{height:1000px}</style></head><body><div id=box></div><div id=far></div><div id=spacer></div></body></html>"

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

let private snapshot (node: Node) =
    let mutable w = 0
    let mutable h = 0
    let status = rv_element_snapshot (node.Handle, null, 0, &w, &h)

    if status <> BufferTooSmall then
        failwith $"element_snapshot size returned {status}"

    let rgba = Array.zeroCreate<byte>(w * h * 4)

    rv_element_snapshot (node.Handle, rgba, rgba.Length, &w, &h)
    |> check "element_snapshot"

    w, h, rgba

let run (outDir: string) =
    for feature in [ "observers"; "snapshot" ] do
        require (rv_abi_has feature = 1) $"rv_abi_has {feature}"

    use host = new Host (200, 100)
    host.LoadHtml html
    use box = host.GetElementById "box"
    use far = host.GetElementById "far"

    // Resize: the first observation reports the size, a change reports the new one, unobserve stops it.
    let resizes = ResizeArray<string>()

    let onResize =
        ResizeCallback (fun _ target width height ->
            let retained = rv_node_retain target
            resizes.Add $"{retained = box.Handle}:{width}x{height}"
            rv_node_release retained)

    let resize =
        rv_host_observe_resize (host.Handle, Marshal.GetFunctionPointerForDelegate onResize, 0n)

    rv_observer_observe (resize, box.Handle)
    |> check "observe resize"

    host.Update ()

    rv_element_set_style (box.Handle, "width", "150px", 0)
    |> check "resize box"

    host.Update ()
    host.Update ()

    rv_observer_unobserve (resize, box.Handle)
    |> check "unobserve resize"

    rv_element_set_style (box.Handle, "width", "120px", 0)
    |> check "resize box again"

    host.Update ()

    // Intersection: far starts below the viewport and enters it after a scroll.
    let intersections = ResizeArray<string>()

    let onIntersection =
        IntersectionCallback (fun _ target intersecting ratio -> intersections.Add $"{target = far.Handle}:{intersecting}:{ratio}")

    let intersection =
        rv_host_observe_intersection (host.Handle, Marshal.GetFunctionPointerForDelegate onIntersection, 0n, "0px", [| 0.0; 1.0 |], 2)

    require (intersection <> 0n) "observe_intersection"

    rv_observer_observe (intersection, far.Handle)
    |> check "observe intersection"

    host.Update ()
    host.ScrollTo (0, 260)
    host.Update ()
    host.Update ()

    let badMargin =
        rv_host_observe_intersection (host.Handle, Marshal.GetFunctionPointerForDelegate onIntersection, 0n, "bogus", null, 0)

    rv_observer_release resize
    rv_observer_release intersection
    host.ScrollTo (0, 0)

    // Snapshots: the box alone, then at device scale 2.
    let w1, h1, rgba1 = snapshot box

    let centre1 =
        [
            int rgba1[(h1 / 2 * w1 + w1 / 2) * 4]
            int rgba1[(h1 / 2 * w1 + w1 / 2) * 4 + 1]
        ]

    host.SetDeviceScale 2.0f
    let w2, h2, _ = snapshot box
    host.SetDeviceScale 1.0f

    let summary =
        {|
            resizes = List.ofSeq resizes
            intersections = List.ofSeq intersections
            badMarginIsNull = (badMargin = 0n)
            snapshot = [ w1; h1 ]
            centre = centre1
            snapshot2x = [ w2; h2 ]
        |}

    File.WriteAllText (Path.Combine (outDir, "fsharp-observe.json"), JsonSerializer.Serialize (summary, JsonSerializerOptions (WriteIndented = true)))
    printfn "RANVIER_FSHARP_OBSERVE %s" (JsonSerializer.Serialize summary)
    System.GC.KeepAlive onResize
    System.GC.KeepAlive onIntersection

    require (List.ofSeq resizes = [ "True:100x50"; "True:150x50" ]) "resize observations: first size, change, none after unobserve"
    require (List.ofSeq intersections = [ "True:0:0"; "True:1:1" ]) "intersection: hidden, then fully visible after the scroll"
    require (badMargin = 0n) "an invalid root margin fails"
    require ([ w1; h1 ] = [ 120; 50 ] && centre1 = [ 200; 0 ]) "the snapshot holds the box alone"
    require ([ w2; h2 ] = [ 240; 100 ]) "the snapshot follows the device scale"
