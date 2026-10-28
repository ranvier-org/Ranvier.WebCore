/// <summary>Checks concrete implementations of an inherited zero-argument operation and an own overload.</summary>
module InheritedDomContracts

open Ranvier.Dom

/// <summary>Implements select-element indexed removal and the inherited child-node removal slot separately.</summary>
type Select() =
    let mutable removed = false
    let mutable removedIndex = -1

    /// <summary>Reports whether the inherited child-node removal implementation ran.</summary>
    member _.WasRemoved = removed

    /// <summary>Returns the index received by the select-element overload.</summary>
    member _.RemovedIndex = removedIndex

    interface HTMLSelectElement with
        member _.remove(index: int) = removedIndex <- index

    interface HTMLElement
    interface Element
    interface Node
    interface EventTarget

    interface ChildNode with
        member _.remove() = removed <- true

/// <summary>Returns zero after the inherited and own overloads dispatch to their distinct implementations.</summary>
[<EntryPoint>]
let main _ =
    let element = Select()
    (element :> HTMLSelectElement).remove(7)
    (element :> HTMLSelectElement).remove()
    (element :> ChildNode).remove()
    if not element.WasRemoved || element.RemovedIndex <> 7 then
        failwith "Inherited and own overloads did not retain distinct dispatch"
    printfn "INHERITED_DOM_IMPLEMENTATIONS PASS"
    0
