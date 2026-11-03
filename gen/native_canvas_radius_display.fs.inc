#if !FABLE_COMPILER
    member internal this.NativeDisplay(context: NativeDisplay.Context, depth: int, precedence: int) =
        NativeDisplay.union context depth precedence (box this) (fun nested ->
            match this with
            | UnrestrictedDoubleOrDOMPointInit.UnrestrictedDouble value ->
                "UnrestrictedDouble", [ Some (fun _ -> NativeDisplay.float64 context nested value) ]
            | UnrestrictedDoubleOrDOMPointInit.DOMPointInit value ->
                "DOMPointInit",
                [
                    Some (fun _ -> NativeDisplay.opaque context nested "Ranvier.Dom.DOMPointInit" (box value))
                ])

    override this.ToString() =
        if System.Runtime.CompilerServices.RuntimeFeature.IsDynamicCodeSupported then
            sprintf "%+A" this
        else
            NativeDisplay.format (fun context depth precedence -> this.NativeDisplay (context, depth, precedence))
#endif
