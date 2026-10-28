/// <summary>Runs generated browser adapters against observable JavaScript object members.</summary>
module GeneratorFableFixture

open Ranvier.Dom
open Fable.Core
open Fable.Core.JsInterop

[<Emit("({ append(...nodes) { this.received = nodes; }, checkOptions(options) { return options.enabled === true && options.label === undefined; }, state: true, mode: 'open' })")>]
let private createNode (): obj = jsNative

[<Emit("({ answer: 'seed' })")>]
let private createMap (): obj = jsNative

[<Emit("$0.received.length === 2 && $0.received[0] === $0 && $0.received[1] === 'tail'")>]
let private receivedOriginalValues (_: obj): bool = jsNative

/// <summary>Runs browser DOM adapter checks and returns zero when they pass.</summary>
[<EntryPoint>]
let main _ =
    let raw = createNode ()
    let node = unbox<Node> raw
    let properties = unbox<DOMStringMap> (createMap ())
    if properties.namedItem "answer" <> "seed" then failwith "Named DOM property getter lost the browser key"
    properties.setNamedItem("answer", "next")
    if properties.namedItem "answer" <> "next" then failwith "Named DOM property setter lost the browser key"
    if node.mode <> Mode.Open then failwith "A browser enumeration did not preserve its string value"
    if not (node.checkOptions(ProbeOptions())) then failwith "Dictionary defaults or absent fields differ from Web IDL"
    node.append(NodeOrDOMString.Node node, NodeOrDOMString.DOMString "tail")
    if not (receivedOriginalValues raw) then failwith "Variadic arguments lost their raw browser values or identity"
    match node.state with
    | BooleanOrDOMString.Boolean true -> ()
    | _ -> failwith "A browser boolean was not converted to a typed union result"
    node.state <- BooleanOrDOMString.DOMString "done"
    match node.state with
    | BooleanOrDOMString.DOMString "done" -> ()
    | _ -> failwith "A typed union setter did not preserve the raw browser string"
    printfn "FABLE_DOM_ADAPTERS PASS"
    0
