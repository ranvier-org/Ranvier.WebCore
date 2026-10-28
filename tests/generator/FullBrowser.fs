/// <summary>Checks the full generated browser surface, including interface union results and optional variadics.</summary>
module FullBrowserContracts

open Ranvier.Dom
open Fable.Core

[<Emit("(globalThis.Element = class Element {}, globalThis.RadioNodeList = class RadioNodeList {}, Object.assign(new globalThis.Element(), {append(...nodes) {this.received = nodes;}, hidden: false}))")>]
let private createElement (): obj = jsNative

[<Emit("({ item: $0 })")>]
let private createForm (_: obj): HTMLFormElement = jsNative

[<Emit("({ getComposedRanges(options, ...roots) { this.options = options; this.roots = roots; return []; } })")>]
let private createSelection (): DOMSelection = jsNative

[<Emit("({ answer: 'seed' })")>]
let private createMap (): DOMStringMap = jsNative

[<Emit("({})")>]
let private createRoot (): ShadowRoot = jsNative

[<Emit("$0.received.length === 2 && $0.received[0] === $0 && $0.received[1] === 'tail'")>]
let private receivedOriginalValues (_: obj): bool = jsNative

[<Emit("$0.roots.length === 1 && $0.roots[0] === $1")>]
let private receivedRoot (_: DOMSelection) (_: ShadowRoot): bool = jsNative

[<Emit("$0 === $1")>]
let private identical (_: obj) (_: obj): bool = jsNative

/// <summary>Returns zero after checking the compiled full browser surface.</summary>
[<EntryPoint>]
let main _ =
    let raw = createElement ()
    let element = unbox<HTMLElement> raw
    element.append(NodeOrDOMString.Node element, NodeOrDOMString.DOMString "tail")
    if not (receivedOriginalValues raw) then failwith "Full-surface mixed append changed raw browser arguments"
    element.hidden <- Some(BooleanOrUnrestrictedDoubleOrDOMString.DOMString "until-found")
    match element.hidden with
    | Some(BooleanOrUnrestrictedDoubleOrDOMString.DOMString "until-found") -> ()
    | _ -> failwith "Full-surface nullable union result was not reboxed"
    match (createForm raw).namedItem "item" with
    | Some(RadioNodeListOrElement.Element returned) when identical (box returned) raw -> ()
    | _ -> failwith "An interface union result lost browser object identity"
    let selection = createSelection ()
    let root = createRoot ()
    selection.getComposedRanges(shadowRoots = [| root |]) |> ignore
    if not (receivedRoot selection root) then failwith "Omitted optional argument changed variadic roots"
    selection.getComposedRanges(GetComposedRangesOptions(), root) |> ignore
    if not (receivedRoot selection root) then failwith "Explicit optional argument changed variadic roots"
    let properties = createMap ()
    properties.setNamedItem("answer", "next")
    if properties.namedItem "answer" <> "next" then failwith "Full-surface named property adapter failed"
    printfn "FULL_FABLE_DOM_CONTRACTS PASS"
    0
