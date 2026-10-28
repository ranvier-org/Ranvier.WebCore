/// <summary>Checks union-result conversion against real DOM objects from a same-origin iframe and a detached document.</summary>
module RealmBrowserContracts

open Ranvier.Dom
open Fable.Core

[<Emit("(() => { const frame = document.createElement('iframe'); document.body.append(frame); return frame.contentDocument; })()")>]
let private createForeignDocument (): obj = jsNative

[<Emit("document.implementation.createHTMLDocument('detached')")>]
let private createDetachedDocument (): obj = jsNative

[<Emit("$0.createElement('input')")>]
let private createInput (_: obj): obj = jsNative

[<Emit("$0.createElementNS('http://www.w3.org/2000/svg', 'svg')")>]
let private createSvg (_: obj): obj = jsNative

[<Emit("({ item: $0 })")>]
let private asFormResult (_: obj): HTMLFormElement = jsNative

[<Emit("(() => { const form = $0.createElement('form'); for(let i=0;i<2;i++) {const input = $0.createElement('input'); input.name='group'; form.append(input);} $0.body.append(form); return form; })()")>]
let private createRadioForm (_: obj): HTMLFormElement = jsNative

[<Emit("$0 !== null && !($0 instanceof globalThis.Element)")>]
let private isForeign (_: obj): bool = jsNative

[<Emit("$0.ownerDocument.defaultView === null")>]
let private isDetached (_: obj): bool = jsNative

[<Emit("$0 === $1")>]
let private identical (_: obj) (_: obj): bool = jsNative

[<Emit("Object.prototype.toString.call($0.group) === '[object RadioNodeList]' && !($0.group instanceof globalThis.RadioNodeList)")>]
let private hasForeignRadioList (_: HTMLFormElement): bool = jsNative

[<Emit("$0.group === $1")>]
let private isOriginalRadioList (_: HTMLFormElement) (_: RadioNodeList): bool = jsNative

[<Emit("document.body.dataset.result = 'REAL_BROWSER_REALMS_PASS'")>]
let private passed (): unit = jsNative

/// <summary>Returns zero after checking real iframe and detached-document union results.</summary>
[<EntryPoint>]
let main _ =
    let foreign = createForeignDocument ()
    let input = createInput foreign
    let svg = createSvg foreign
    if not (isForeign input && isForeign svg) then failwith "Expected iframe constructors to differ"
    let detached = createInput (createDetachedDocument ())
    if not (isDetached detached) then failwith "Expected a detached document without a window"
    for element in [| input; svg; detached |] do
        match (asFormResult element).namedItem "item" with
        | Some(RadioNodeListOrElement.Element returned) when identical (box returned) element -> ()
        | _ -> failwith "A real iframe/detached element was rejected or lost identity"
    let form = createRadioForm foreign
    if not (hasForeignRadioList form) then failwith "Expected a real RadioNodeList from the iframe"
    match form.namedItem "group" with
    | Some(RadioNodeListOrElement.RadioNodeList returned) when isOriginalRadioList form returned -> ()
    | _ -> failwith "A real iframe RadioNodeList was rejected or lost identity"
    passed ()
    0
