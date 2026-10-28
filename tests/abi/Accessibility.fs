/// Checks the "accessibility" group: the tree WebCore builds for a page, read through the ABI as a platform
/// bridge would read it (roles, names, descriptions, values, states, bounds, children, hit testing, focus), the
/// actions an assistive technology performs, and the events WebCore posts as the page changes.
module RanvierWebCoreAbi.Accessibility

open System.IO
open System.Runtime.InteropServices
open System.Text.Json
open RanvierWebCoreAbi.Native

let private html =
    "<!doctype html><html><head><title>Accessibility</title><style>body{margin:0;font:16px sans-serif}button{position:absolute;left:10px;top:10px;width:100px;height:30px}#c{position:absolute;left:10px;top:50px}#t{position:absolute;left:10px;top:80px;width:150px}#s{position:absolute;left:10px;top:110px;width:150px}#far{position:absolute;left:0;top:900px}</style></head><body><main><h1 id=h>Settings</h1><button id=b aria-describedby=d>Save</button><span id=d>Writes the file</span><input id=c type=checkbox aria-label=\"Dark mode\"><label for=t>Name</label><input id=t type=text placeholder=\"Your name\" value=\"Ann\"><input id=s type=range min=0 max=10 value=4 aria-label=Volume><div id=hidden style=\"display:none\"><button>Hidden</button></div><div id=live aria-live=polite></div><ul id=list><li>One</li><li>Two</li></ul><a id=link href=\"https://example.com/\">Example</a><details id=det><summary>More</summary><p>Inside</p></details><p id=far>Far</p></main></body></html>"

let private require condition (message: string) =
    if not condition then
        failwith $"ASSERTION FAILED: {message}"

let private axString (ax: nativeint) property =
    readString "ax_string" (fun buffer capacity length -> rv_ax_string (ax, property, buffer, capacity, length))

let private axNumber (ax: nativeint) property =
    let mutable value = 0.0
    let status = rv_ax_number (ax, property, &value)
    if status = 0 then Some value else None

let private children (ax: nativeint) =
    let mutable count = 0
    let status = rv_ax_children (ax, null, 0, &count)

    if status <> BufferTooSmall && status <> 0 then
        failwith $"ax_children count returned {status}"

    let nodes = Array.zeroCreate<nativeint> count
    rv_ax_children (ax, nodes, nodes.Length, &count) |> check "ax_children"
    nodes

let private rect (ax: nativeint) =
    let mutable x = 0.0
    let mutable y = 0.0
    let mutable w = 0.0
    let mutable h = 0.0
    rv_ax_rect (ax, &x, &y, &w, &h) |> check "ax_rect"
    [ x; y; w; h ]

let private elementRect (node: Node) =
    let mutable x = 0.0
    let mutable y = 0.0
    let mutable w = 0.0
    let mutable h = 0.0
    rv_element_rect (node.Handle, &x, &y, &w, &h) |> check "element_rect"
    [ x; y; w; h ]

// Bits of rv_ax_states.
let private focusable, focused, checkable, isChecked, expandable, expanded, editable, offscreen, liveRegion =
    1, 2, 8, 16, 128, 256, 4096, 1 <<< 21, 1 <<< 22

let private has bit states = states &&& bit <> 0

// RANVIER_TRACE=1 prints each step to stderr before it runs, so a native crash names the call that made it.
let private tracing = System.Environment.GetEnvironmentVariable "RANVIER_TRACE" = "1"

let private step (name: string) =
    if tracing then
        eprintfn "RANVIER_STEP %s" name
        stderr.Flush()

let run (outDir: string) =
    require (rv_abi_has "accessibility" = 1) "rv_abi_has accessibility"
    // The lean flavor builds WebCore without patch 0011's notifications: the tree, and no events.
    step "Accessibility: let hasEvents = rv_abi_has 'accessibility-events' = 1"
    let hasEvents = rv_abi_has "accessibility-events" = 1
    use host = new Host(300, 200)
    step "Accessibility: host.LoadHtml html"
    host.LoadHtml html

    let ax (id: string) =
        use node = host.GetElementById id
        rv_node_ax node.Handle

    step "Accessibility: let rootBefore = rv_host_ax_root host.Handle"
    let rootBefore = rv_host_ax_root host.Handle

    let events = ResizeArray<nativeint * int>()

    let onEvent =
        AxCallback(fun _ node event ->
            // Kept until the end of the test; each is released there.
            events.Add(rv_ax_retain node, event))

    step "Accessibility: rv_host_set_accessibility (host.Handle, 1, Marshal.GetFunctionPointerForDelegate onEvent, "
    rv_host_set_accessibility (host.Handle, 1, Marshal.GetFunctionPointerForDelegate onEvent, 0n)
    |> check "host_set_accessibility"

    step "Accessibility: let root = rv_host_ax_root host.Handle"
    let root = rv_host_ax_root host.Handle
    require (root <> 0n) "a root once accessibility is on"
    step "Accessibility: let rootRole = rv_ax_role root"
    let rootRole = rv_ax_role root
    step "Accessibility: let rootParent = rv_ax_parent root"
    let rootParent = rv_ax_parent root
    let rootRect = rect root

    // The tree, depth first, as role:name.
    let rec walk (node: nativeint) depth =
        [ let indent = String.replicate depth " "
          let role = rv_ax_role node

          if role = -10 then
              yield $"{indent}detached"
          else
              yield $"{indent}{role}:{axString node 0}"

              for child in children node do
                  yield! walk child (depth + 1)
                  rv_ax_release child ]

    let tree = walk root 0

    step "Accessibility: let h = ax 'h'"
    let h = ax "h"
    step "Accessibility: let b = ax 'b'"
    let b = ax "b"
    step "Accessibility: let c = ax 'c'"
    let c = ax "c"
    step "Accessibility: let t = ax 't'"
    let t = ax "t"
    step "Accessibility: let s = ax 's'"
    let s = ax "s"
    step "Accessibility: let link = ax 'link'"
    let link = ax "link"
    step "Accessibility: let list = ax 'list'"
    let list = ax "list"
    step "Accessibility: let live = ax 'live'"
    let live = ax "live"
    step "Accessibility: let det = ax 'det'"
    let det = ax "det"
    step "Accessibility: let far = ax 'far'"
    let far = ax "far"
    step "Accessibility: use hiddenDiv = host.GetElementById 'hidden'"
    use hiddenDiv = host.GetElementById "hidden"
    step "Accessibility: use hiddenButton = new Node(rv_node_relative (hiddenDiv.Handle, 1))"
    use hiddenButton = new Node(rv_node_relative (hiddenDiv.Handle, 1))
    step "Accessibility: let hidden = rv_node_ax hiddenButton.Handle"
    let hidden = rv_node_ax hiddenButton.Handle

    step "Accessibility: use bNode = host.GetElementById 'b'"
    use bNode = host.GetElementById "b"
    step "Accessibility: let bDom = rv_ax_dom_node b"
    let bDom = rv_ax_dom_node b
    let bDomSame = (bDom = bNode.Handle)
    step "Accessibility: rv_node_release bDom"
    rv_node_release bDom
    step "Accessibility: let bParent = rv_ax_parent b"
    let bParent = rv_ax_parent b
    step "Accessibility: let bParentRole = rv_ax_role bParent"
    let bParentRole = rv_ax_role bParent
    step "Accessibility: rv_ax_release bParent"
    rv_ax_release bParent
    let bRect = rect b
    let bElementRect = elementRect bNode

    // Hit testing the button's centre finds the button, or the text inside it.
    step "Accessibility: let hit = rv_host_ax_hit_test (host.Handle, 60, 25)"
    let hit = rv_host_ax_hit_test (host.Handle, 60, 25)
    step "Accessibility: let hitParent = rv_ax_parent hit"
    let hitParent = rv_ax_parent hit
    let hitIsButton = hit = b || hitParent = b
    step "Accessibility: rv_ax_release hitParent"
    rv_ax_release hitParent
    step "Accessibility: rv_ax_release hit"
    rv_ax_release hit

    let summaryBefore =
        {| heading = [ string (rv_ax_role h); axString h 0 ], axNumber h 3
           button = rv_ax_role b, axString b 0, axString b 1, rv_ax_states b
           checkbox = rv_ax_role c, axString c 0, rv_ax_states c
           text = rv_ax_role t, axString t 0, axString t 2, axString t 5, rv_ax_states t
           slider = rv_ax_role s, axString s 0, axNumber s 0, axNumber s 1, axNumber s 2
           link = rv_ax_role link, axString link 7
           list = rv_ax_role list, (children list).Length
           details = rv_ax_role det, rv_ax_states det
           live = axString live 8, rv_ax_states live
           farStates = rv_ax_states far |}

    let listChildren = children list
    step "Accessibility: let listItemRoles = listChildren |> Array.map rv_ax_role |> List.ofArray"
    let listItemRoles = listChildren |> Array.map rv_ax_role |> List.ofArray
    listChildren |> Array.iter rv_ax_release

    // Actions.
    step "Accessibility: let pressChecked = rv_ax_action (c, 0)"
    let pressChecked = rv_ax_action (c, 0)
    step "Accessibility: let checkedAfterPress = rv_ax_states c"
    let checkedAfterPress = rv_ax_states c
    let input = ResizeArray<string>()
    step "Accessibility: use tNode = host.GetElementById 't'"
    use tNode = host.GetElementById "t"
    tNode.Listen("input", false, (fun e -> input.Add e.Type)) |> ignore
    step "Accessibility: let focusResult = rv_ax_action (t, 1)"
    let focusResult = rv_ax_action (t, 1)
    step "Accessibility: let focusNode = rv_host_ax_focus host.Handle"
    let focusNode = rv_host_ax_focus host.Handle
    let focusIsText = focusNode = t
    step "Accessibility: rv_ax_release focusNode"
    rv_ax_release focusNode
    step "Accessibility: let setValue = rv_ax_set_value (t, 'Bob')"
    let setValue = rv_ax_set_value (t, "Bob")
    let valueAfter = axString t 2
    step "Accessibility: let setNumber = rv_ax_set_number (s, 7.0)"
    let setNumber = rv_ax_set_number (s, 7.0)
    let sliderAfterSet = axNumber s 0
    step "Accessibility: let increment = rv_ax_action (s, 3)"
    let increment = rv_ax_action (s, 3)
    let sliderAfterIncrement = axNumber s 0
    step "Accessibility: let expandResult = rv_ax_action (det, 5)"
    let expandResult = rv_ax_action (det, 5)
    step "Accessibility: let detailsAfterExpand = rv_ax_states det"
    let detailsAfterExpand = rv_ax_states det
    step "Accessibility: let notRange = rv_ax_action (b, 3)"
    let notRange = rv_ax_action (b, 3)
    events.Clear()
    step "Accessibility: host.CycleRunLoop 50"
    host.CycleRunLoop 50

    let eventsAfterActions =
        events |> Seq.map (fun (node, event) -> node, event) |> List.ofSeq

    let eventOn node kind =
        eventsAfterActions |> List.exists (fun (n, e) -> n = node && e = kind)

    let checkboxStateEvent = eventOn c 3
    let focusEvent = eventOn t 0
    let valueEvent = eventOn t 2

    // Page changes: a list item added, live region text, the button removed.
    events.Clear()
    step "Accessibility: use listNode = host.GetElementById 'list'"
    use listNode = host.GetElementById "list"
    step "Accessibility: use item = host.CreateElement 'li'"
    use item = host.CreateElement "li"
    item.SetText "Three"
    listNode.Append item
    step "Accessibility: use liveNode = host.GetElementById 'live'"
    use liveNode = host.GetElementById "live"
    liveNode.SetText "Saved"
    // WebCore updates its tree during the rendering update the app runs for the frame the change requested.
    step "Accessibility: host.Update()"
    host.Update()
    step "Accessibility: host.CycleRunLoop 50"
    host.CycleRunLoop 50
    let changed () =
        events |> Seq.exists (fun (n, e) -> n = list && e = 1)
        && events |> Seq.exists (fun (n, e) -> n = live && e = 8)

    // Events arrive asynchronously; a loaded runner can take more than one cycle to deliver them.
    let mutable cycles = 0

    while hasEvents && not (changed ()) && cycles < 40 do
        host.Update()
        host.CycleRunLoop 50
        cycles <- cycles + 1

    let changeEvents =
        events |> Seq.map (fun (n, e) -> $"{rv_ax_role n}:{e}") |> List.ofSeq

    let childrenEvent = events |> Seq.exists (fun (n, e) -> n = list && e = 1)
    let liveEvent = events |> Seq.exists (fun (n, e) -> n = live && e = 8)
    let listCountAfter = (children list).Length
    let liveText = axString live 9

    step "Accessibility: rv_node_remove bNode.Handle |> check 'remove button'"
    rv_node_remove bNode.Handle |> check "remove button"
    step "Accessibility: host.CycleRunLoop 50"
    host.CycleRunLoop 50
    step "Accessibility: let detachedRole = rv_ax_role b"
    let detachedRole = rv_ax_role b

    step "Accessibility: rv_host_set_accessibility (host.Handle, 0, 0n, 0n) |> check 'accessibility off'"
    rv_host_set_accessibility (host.Handle, 0, 0n, 0n) |> check "accessibility off"
    step "Accessibility: let rootAfterOff = rv_host_ax_root host.Handle"
    let rootAfterOff = rv_host_ax_root host.Handle

    for node, _ in events do
        rv_ax_release node

    for node in [ root; h; b; c; t; s; link; list; live; det; far ] do
        rv_ax_release node

    System.GC.KeepAlive onEvent

    let summary =
        {| rootBeforeIsNull = (rootBefore = 0n)
           rootRole = rootRole
           rootParentIsNull = (rootParent = 0n)
           rootRect = rootRect
           tree = tree
           before = summaryBefore
           hiddenIsNull = (hidden = 0n)
           bDomSame = bDomSame
           bParentRole = bParentRole
           bRect = bRect
           bElementRect = bElementRect
           hitIsButton = hitIsButton
           listItemRoles = listItemRoles
           pressChecked = pressChecked
           checkedAfterPress = checkedAfterPress
           focusResult = focusResult
           focusIsText = focusIsText
           setValue = setValue
           valueAfter = valueAfter
           input = List.ofSeq input
           setNumber = setNumber
           sliderAfterSet = sliderAfterSet
           increment = increment
           sliderAfterIncrement = sliderAfterIncrement
           expandResult = expandResult
           detailsAfterExpand = detailsAfterExpand
           notRange = notRange
           eventsAfterActions = eventsAfterActions |> List.map snd
           checkboxStateEvent = checkboxStateEvent
           focusEvent = focusEvent
           valueEvent = valueEvent
           childrenEvent = childrenEvent
           liveEvent = liveEvent
           listCountAfter = listCountAfter
           liveText = liveText
           detachedRole = detachedRole
           rootAfterOffIsNull = (rootAfterOff = 0n)
           hasEvents = hasEvents
           changeEvents = changeEvents |}

    File.WriteAllText(
        Path.Combine(outDir, "fsharp-accessibility.json"),
        JsonSerializer.Serialize(summary, JsonSerializerOptions(WriteIndented = true))
    )

    printfn "RANVIER_FSHARP_ACCESSIBILITY %s" (JsonSerializer.Serialize summary)

    let role (r, _, _, _, _) = r
    require (rootBefore = 0n) "no root while accessibility is off"
    require (rootRole = 1 && rootParent = 0n) "the root is the document, with no parent"
    require (rootRect = [ 0.0; 0.0; 300.0; 200.0 ]) "the root's bounds are the viewport"
    require (summaryBefore.heading = ([ "7"; "Settings" ], Some 1.0)) "a heading: role, name, level"

    let bRole, bName, bDescription, bStates = summaryBefore.button
    require (bRole = 9 && bName = "Save" && bDescription = "Writes the file") "a button: role, name, description"
    require (has focusable bStates) "a button is focusable"

    let cRole, cName, cStates = summaryBefore.checkbox

    require
        (cRole = 11
         && cName = "Dark mode"
         && has checkable cStates
         && not (has isChecked cStates))
        "an unchecked checkbox"

    let tRole, tName, tValue, tPlaceholder, tStates = summaryBefore.text

    require
        (tRole = 15 && tName = "Name" && tValue = "Ann" && tPlaceholder = "Your name")
        "a labelled text field with its value"

    require (has editable tStates) "a text field is editable"

    let sRole, sName, sValue, sMin, sMax = summaryBefore.slider

    require
        (sRole = 25
         && sName = "Volume"
         && sValue = Some 4.0
         && sMin = Some 0.0
         && sMax = Some 10.0)
        "a slider and its range"

    require (summaryBefore.link = (8, "https://example.com/")) "a link and its URL"
    require (summaryBefore.list = (31, 2) && listItemRoles = [ 32; 32 ]) "a list of two items"
    require (fst summaryBefore.details = 4 || has expandable (snd summaryBefore.details)) "details expands"
    require (has offscreen summaryBefore.farStates) "a paragraph below the viewport is offscreen"
    require (hidden = 0n) "a display:none element has no node"
    require (bDomSame) "the button's DOM node"
    require (bParentRole = 59) "the button's parent is the main landmark"
    require (bRect = bElementRect) "node bounds match the element's bounding rectangle"
    require hitIsButton "hit testing finds the button"
    require (pressChecked = 1 && has isChecked checkedAfterPress) "pressing checks the checkbox"
    require (focusResult = 1 && focusIsText) "focusing the text field"

    require
        (setValue = 1 && valueAfter = "Bob" && List.ofSeq input = [ "input" ])
        "setting the text field's value fires input"

    require (setNumber = 1 && sliderAfterSet = Some 7.0) "setting the slider's value"
    require (increment = 1 && sliderAfterIncrement = Some 8.0) "incrementing the slider"
    require (expandResult = 1 && has expanded detailsAfterExpand) "expanding details"
    require (notRange = 0) "a button does not increment"
    require (fst summaryBefore.live = "polite" && has liveRegion (snd summaryBefore.live)) "a polite live region"
    require (listCountAfter = 3 && liveText = "Saved") "the tree follows DOM changes"

    if hasEvents then
        require checkboxStateEvent "a state event for the checkbox"
        require focusEvent "a focus event for the text field"
        require valueEvent "a value event for the text field"
        require childrenEvent "a children event for the list"
        require liveEvent "a live region event"
    else
        require (eventsAfterActions.IsEmpty) "no events without patch 0011"

    require (detachedRole = -10) "a removed node is detached"
    require (rootAfterOff = 0n) "no root once accessibility is off"
