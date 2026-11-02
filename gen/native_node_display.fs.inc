#if !FABLE_COMPILER
    member internal this.NativeDisplay(context: NativeDisplay.Context, depth: int, precedence: int) =
        NativeDisplay.union context depth precedence (box (this)) (fun n0 ->
            match this with
            | NodeOrDOMString.Node (v0_0) ->
                "Node",
                [
                    Some (fun p -> NativeDisplay.opaque context n0 "<Ranvier.Dom.Node>" (box (v0_0)))
                ]
            | NodeOrDOMString.DOMString (v0_0) -> "DOMString", [ Some (fun p -> NativeDisplay.text context n0 (v0_0)) ])

    override this.ToString() =
        if System.Runtime.CompilerServices.RuntimeFeature.IsDynamicCodeSupported then
            sprintf "%+A" this
        else
            NativeDisplay.format (fun context depth precedence -> this.NativeDisplay (context, depth, precedence))
#endif
