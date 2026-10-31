/// Checks the element surface of ABI v14: classes, inline and computed style, geometry and hit testing,
/// element scrolling, shadow roots, text selection, and control of CSS animations and transitions.
module RanvierWebCoreAbi.Surface

open System.IO
open System.Text.Json
open RanvierWebCoreAbi.Native

let private html =
    "<!doctype html><html><head><style>body{margin:0;background:white}#a{position:absolute;left:20px;top:30px;width:100px;height:50px;background:rgb(10,20,30)}#a.on{background:rgb(0,0,255)}#list{position:absolute;left:0;top:100px;width:100px;height:50px;overflow:auto}#list div{height:30px}@keyframes slide{from{left:0px}to{left:100px}}.anim{animation:slide 1000ms linear}#t{position:absolute;left:150px;top:0;width:10px;height:10px;opacity:1;transition:opacity 500ms linear}</style></head><body><div id=a></div><div id=list><div></div><div></div><div></div><div></div><div></div><div></div><div></div><div></div><div></div><div id=last></div></div><div id=shadowhost></div><input id=field><div id=t></div></body></html>"

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

let private rgbAt (rgba: byte[]) width x y =
    let i = (y * width + x) * 4
    [ int rgba[i]; int rgba[i + 1]; int rgba[i + 2] ]

let private style (node: Node) property =
    readString "element_get_style" (fun buffer capacity length -> rv_element_get_style (node.Handle, property, buffer, capacity, length))

let private computed (node: Node) property =
    readString "element_computed_style" (fun buffer capacity length -> rv_element_computed_style (node.Handle, property, buffer, capacity, length))

let private rect (node: Node) =
    let mutable x = 0.0
    let mutable y = 0.0
    let mutable w = 0.0
    let mutable h = 0.0

    rv_element_rect (node.Handle, &x, &y, &w, &h)
    |> check "element_rect"

    x, y, w, h

let private metric (node: Node) which =
    let mutable value = 0

    rv_element_scroll_metric (node.Handle, which, &value)
    |> check "element_scroll_metric"

    value

/// The animations of the element as (name, state, handle); the caller releases each handle.
let private animations (node: Node) =
    let mutable count = 0

    rv_element_animations (node.Handle, 0, null, 0, &count)
    |> ignore

    let handles = Array.zeroCreate<nativeint> count

    rv_element_animations (node.Handle, 0, handles, count, &count)
    |> check "element_animations"

    handles
    |> Array.map (fun animation ->
        let name =
            readString "animation_name" (fun buffer capacity length -> rv_animation_name (animation, buffer, capacity, length))

        name, rv_animation_state animation, animation)

let private time animation =
    let mutable ms = 0.0

    match rv_animation_time (animation, &ms) with
    | 1 -> Some ms
    | _ -> None

let run (outDir: string) =
    for feature in [ "style"; "geometry"; "animation"; "shadow"; "text-selection" ] do
        require (rv_abi_has feature = 1) $"rv_abi_has {feature}"

    use host = new Host (240, 160)
    host.LoadHtml html
    use a = host.GetElementById "a"

    // Classes.
    let added = rv_element_class (a.Handle, utf8 "on", utf8Length "on", 1)
    let contains = rv_element_class (a.Handle, utf8 "on", utf8Length "on", 0)
    let blue = rgbAt (host.Paint ()) 240 30 40
    let removed = rv_element_class (a.Handle, utf8 "on", utf8Length "on", 2)
    let toggled = rv_element_class (a.Handle, utf8 "on", utf8Length "on", 3)
    rv_element_class (a.Handle, utf8 "on", utf8Length "on", 2) |> ignore

    // Inline and computed style.
    rv_element_set_style (a.Handle, "width", utf8 "150px", utf8Length "150px", 0)
    |> check "set_style"

    let inlineWidth = style a "width"
    let computedWidth = computed a "width"
    let _, _, rectWidth, _ = rect a

    rv_element_set_style (a.Handle, "width", utf8 "bogus", utf8Length "bogus", 0)
    |> check "set_style invalid"

    let afterInvalid = style a "width"

    rv_element_set_style (a.Handle, "width", utf8 "", utf8Length "", 0)
    |> check "set_style remove"

    let afterRemove = computed a "width"
    let ax, ay, aw, ah = rect a

    // Hit testing.
    let hit = rv_host_element_at (host.Handle, 30, 40)
    let hitA = hit = a.Handle

    if hit <> 0n then
        rv_node_release hit

    // Element scrolling.
    use list = host.GetElementById "list"
    use last = host.GetElementById "last"
    let clientHeight = metric list 5
    let scrollHeight = metric list 3

    rv_element_scroll_to (list.Handle, 0, 120, 0)
    |> check "element_scroll_to"

    let scrolledTop = metric list 1

    rv_element_scroll_into_view (last.Handle, 0, 3, 0)
    |> check "scroll_into_view"

    let intoViewTop = metric list 1

    // Shadow root.
    use shadowHost = host.GetElementById "shadowhost"
    let mutable status = 0
    let root = rv_element_attach_shadow (shadowHost.Handle, &status)
    let rootType = rv_node_type root
    use inside = host.CreateElement "span"

    rv_node_append_child (root, inside.Handle)
    |> check "append into shadow root"

    let rootAgain = rv_element_shadow_root shadowHost.Handle
    let sameRoot = rootAgain = root
    let second = rv_element_attach_shadow (shadowHost.Handle, &status)
    let secondStatus = status
    rv_node_release rootAgain
    rv_node_release root

    // Text selection.
    use field = host.GetElementById "field"

    rv_node_set_string (field.Handle, 6, utf8 "hello", utf8Length "hello")
    |> check "set value"

    rv_text_set_selection (field.Handle, 1, 3)
    |> check "text_set_selection"

    let mutable selStart = 0
    let mutable selEnd = 0

    rv_text_selection (field.Handle, &selStart, &selEnd)
    |> check "text_selection"

    // A CSS animation: listed, named, seekable, pausable, retimed, finished and cancelled.
    rv_element_class (a.Handle, utf8 "anim", utf8Length "anim", 1) |> ignore
    host.Update ()
    let listed = animations a
    let name, initialState, anim = listed[0]

    // Paused first, so the seek holds while the update applies it.
    rv_animation_control (anim, 1) |> check "pause"

    let pausedState = rv_animation_state anim

    rv_animation_seek (anim, 500.0)
    |> check "animation_seek"

    let seekTime = time anim
    host.Update ()
    let leftAtHalf = computed a "left"

    rv_animation_set_rate (anim, 2.0)
    |> check "set_rate"

    let target = rv_animation_target anim
    let targetIsA = target = a.Handle

    if target <> 0n then
        rv_node_release target

    let mutable documentCount = 0

    rv_host_animations (host.Handle, null, 0, &documentCount)
    |> ignore

    rv_animation_control (anim, 3) |> check "finish"

    let finishedState = rv_animation_state anim

    rv_animation_control (anim, 4) |> check "cancel"

    let cancelledState = rv_animation_state anim

    for _, _, handle in listed do
        rv_animation_release handle

    // A CSS transition appears once its property changes.
    use t = host.GetElementById "t"
    host.Update ()

    rv_element_set_style (t.Handle, "opacity", utf8 "0", utf8Length "0", 0)
    |> check "start transition"

    host.Update ()
    let transitions = animations t

    let transitionNames =
        transitions
        |> Array.map (fun (n, _, _) -> n)
        |> List.ofArray

    for _, _, handle in transitions do
        rv_animation_release handle

    let summary =
        {|
            added = added
            contains = contains
            blue = blue
            removed = removed
            toggled = toggled
            inlineWidth = inlineWidth
            computedWidth = computedWidth
            rectWidth = rectWidth
            afterInvalid = afterInvalid
            afterRemove = afterRemove
            rect = [ ax; ay; aw; ah ]
            hitA = hitA
            clientHeight = clientHeight
            scrollHeight = scrollHeight
            scrolledTop = scrolledTop
            intoViewTop = intoViewTop
            rootType = rootType
            sameRoot = sameRoot
            secondIsNull = (second = 0n)
            secondStatus = secondStatus
            selection = [ selStart; selEnd ]
            animationCount = listed.Length
            name = name
            initialState = initialState
            seekTime = seekTime
            leftAtHalf = leftAtHalf
            pausedState = pausedState
            targetIsA = targetIsA
            documentCount = documentCount
            finishedState = finishedState
            cancelledState = cancelledState
            transitionNames = transitionNames
        |}

    File.WriteAllText (Path.Combine (outDir, "fsharp-surface.json"), JsonSerializer.Serialize (summary, JsonSerializerOptions (WriteIndented = true)))
    printfn "RANVIER_FSHARP_SURFACE %s" (JsonSerializer.Serialize summary)

    require
        (added = 1
         && contains = 1
         && removed = 0
         && toggled = 1)
        "classList add, contains, remove and toggle"

    require (blue = [ 0; 0; 255 ]) "an added class restyles the element"

    require
        (inlineWidth = "150px"
         && computedWidth = "150px"
         && rectWidth = 150.0)
        "inline style sets the width"

    require (afterInvalid = "150px") "an invalid value leaves the property unchanged"
    require (afterRemove = "100px") "an empty value removes the inline property"
    require ([ ax; ay; aw; ah ] = [ 20.0; 30.0; 100.0; 50.0 ]) "getBoundingClientRect"
    require hitA "elementFromPoint finds the element"
    require (clientHeight = 50 && scrollHeight = 300) "clientHeight and scrollHeight"
    require (scrolledTop = 120) "an element scrolls to a position"
    require (intoViewTop = 250) "scrollIntoView aligns the last child to the start, clamped"
    require (rootType = 11 && sameRoot) "attachShadow returns the open shadow root"
    require (second = 0n && secondStatus = DomException) "a second attachShadow fails with a DOMException"
    require ([ selStart; selEnd ] = [ 1; 3 ]) "text selection"

    require
        (listed.Length = 1
         && name = "slide"
         && initialState = 1)
        "the running CSS animation is listed by name"

    require (seekTime = Some 500.0) "seek sets the current time"
    require (leftAtHalf = "50px") "a seek to half applies the halfway value"
    require (pausedState = 2) "pause"
    require targetIsA "the animation targets the element"
    require (documentCount >= 1) "the document lists its animations"
    require (finishedState = 3) "finish"
    require (cancelledState = 0) "cancel"
    require (transitionNames = [ "opacity" ]) "a started transition is listed by property"
