#if !FABLE_COMPILER
    member internal this.NativeDisplay(context: NativeDisplay.Context, depth: int, precedence: int) =
        NativeDisplay.union context depth precedence (box (this)) (fun n0 ->
            match this with
            | DOMStringOrCanvasGradientOrCanvasPattern.DOMString (v0_0) -> "DOMString", [ Some (fun p -> NativeDisplay.text context n0 (v0_0)) ]
            | DOMStringOrCanvasGradientOrCanvasPattern.CanvasGradient (v0_0) ->
                "CanvasGradient",
                [
                    Some (fun p -> NativeDisplay.opaque context n0 "<Ranvier.Dom.CanvasGradient>" (box (v0_0)))
                ]
            | DOMStringOrCanvasGradientOrCanvasPattern.CanvasPattern (v0_0) ->
                "CanvasPattern",
                [
                    Some (fun p -> NativeDisplay.opaque context n0 "<Ranvier.Dom.CanvasPattern>" (box (v0_0)))
                ])

    override this.ToString() =
        if System.Runtime.CompilerServices.RuntimeFeature.IsDynamicCodeSupported then
            sprintf "%+A" this
        else
            NativeDisplay.format (fun context depth precedence -> this.NativeDisplay (context, depth, precedence))
#endif
