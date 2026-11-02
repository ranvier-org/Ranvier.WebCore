// Copyright (c) Microsoft Corporation.
// Portions licensed under the MIT license in NativeDisplay.LICENSE.txt.

#if !FABLE_COMPILER
open System
open System.Collections.Generic
open System.Globalization

/// <summary>Typed diagnostic documents and their bounded F# text layout.</summary>
module internal NativeDisplay =
    /// <summary>A spacing or indentation boundary between documents.</summary>
    [<NoEquality; NoComparison; Diagnostics.DebuggerDisplay("{ToString(),nq}")>]
    type Joint =
        | Unbreakable
        | Breakable of int
        | Broken of int

        /// <summary>Returns the internal layout category.</summary>
        override _.ToString() =
            "Layout joint"

    /// <summary>A document whose leaves already contain typed text.</summary>
    [<NoEquality; NoComparison; Diagnostics.DebuggerDisplay("{ToString(),nq}")>]
    type Doc =
        | Leaf of bool * string * bool
        | Node of Doc * Doc * Joint

        /// <summary>Returns the internal document category.</summary>
        override _.ToString() =
            "Typed layout"

    let rec private left =
        function
        | Leaf (jl, _, _) -> jl
        | Node (l, _, _) -> left l

    let rec private right =
        function
        | Leaf (_, _, jr) -> jr
        | Node (_, r, _) -> right r

    let private middle l r =
        right l || left r

    let private empty = Leaf (true, "", true)

    let private word text =
        Leaf (false, text, false)

    let private leftWord text =
        Leaf (false, text, true)

    let private rightWord text =
        Leaf (true, text, false)

    let private isEmpty =
        function
        | Leaf (true, "", true) -> true
        | _ -> false

    let private join joint l r =
        if isEmpty l then r
        elif isEmpty r then l
        else Node (l, r, joint)

    let private beside l r =
        join Unbreakable l r

    let private breakable indent l r =
        join (Breakable indent) l r

    let private above l r =
        join (Broken 0) l r

    let private bracket l r value =
        beside (beside (leftWord l) value) (rightWord r)

    let private separated separator values =
        match values with
        | [] -> empty
        | head :: tail -> List.fold (fun state item -> breakable 0 (beside state (rightWord separator)) item) head tail

    let private recordLayout fields =
        fields
        |> List.map (fun (name, value) -> breakable 1 (beside (word name) (word "=")) value)
        |> function
            | [] -> empty
            | head :: tail -> List.fold above head tail
        |> fun body -> beside (beside (word "{") body) (word "}")

    let private tupleLayout values =
        bracket "(" ")" (separated "," values)

    let private arrayLayout values =
        bracket "[|" "|]" (separated ";" values)

    let private unionLayout precedence name values =
        match values with
        | [] -> word name
        | values ->
            let payload =
                match values with
                | [ value ] -> value
                | values -> tupleLayout values

            let body = breakable 2 (word name) payload
            if precedence <= 2 then bracket "(" ")" body else body

    /// <summary>Fits a typed document into the requested column width.</summary>
    let render maxWidth layout =
        let mutable stack = Array.zeroCreate<int> 400
        let mutable next = 0
        let mutable outer = 0

        let push saving =
            if next = stack.Length then
                Array.Resize (&stack, next + 400)

            stack[next] <- saving
            next <- next + 1

        let pop () =
            let broken = stack[next - 1] < 0

            if outer = next then
                outer <- outer - 1

            next <- next - 1
            broken

        let force () =
            if outer = next then
                None
            else
                let saving = stack[outer]
                stack[outer] <- -saving
                outer <- outer + 1
                Some saving

        let rec fit pos layout =
            match layout with
            | Leaf (_, text, _) ->
                let rec fitLeaf pos =
                    if pos + text.Length <= maxWidth then
                        pos
                    else
                        match force () with
                        | None -> pos
                        | Some saving -> fitLeaf (pos - saving)

                layout, fitLeaf pos + text.Length, text.Length
            | Node (l, r, joint) ->
                let mid = if middle l r then 0 else 1
                let l, pos, offsetl = fit pos l

                match joint with
                | Unbreakable ->
                    let r, pos, offsetr = fit (pos + mid) r
                    Node (l, r, Unbreakable), pos, offsetl + mid + offsetr
                | Broken indent ->
                    let r, pos, offsetr = fit (pos - offsetl + indent) r
                    Node (l, r, Broken indent), pos, indent + offsetr
                | Breakable indent ->
                    let saving = offsetl + mid - indent

                    if saving > 0 then
                        push saving
                        let r, pos, offsetr = fit (pos + mid) r

                        if pop () then
                            Node (l, r, Broken indent), pos, indent + offsetr
                        else
                            Node (l, r, Breakable indent), pos, offsetl + mid + offsetr
                    else
                        let r, pos, offsetr = fit (pos + mid) r
                        Node (l, r, Breakable indent), pos, offsetl + mid + offsetr

        let fitted =
            if maxWidth <= 0 then
                layout
            else
                let doc, _, _ = fit 0 layout in doc

        let text = Text.StringBuilder ()
        let mutable index = 0

        let append (value: string) =
            text.Append (value) |> ignore
            index <- index + value.Length

        let rec write pos =
            function
            | Leaf (_, value, _) -> append value
            | Node (l, r, Broken indent) when maxWidth <> 0 ->
                write pos l
                append "\n"
                append (String (' ', pos + indent))
                index <- pos + indent
                write (pos + indent) r
            | Node (l, r, _) ->
                write pos l

                if not (middle l r) then
                    append " "

                write index r

        write 0 fitted
        text.ToString ()

    /// <summary>Tracks the active reference path and the 10000-node display budget.</summary>
    type Context() =
        let active = HashSet<obj>(HashIdentity.Reference)
        let mutable remaining = 10000
        /// <summary>The remaining visible-node budget.</summary>
        member _.Remaining = remaining

        /// <summary>Charges one visible node while the budget is positive.</summary>
        member _.Count() =
            if remaining > 0 then
                remaining <- remaining - 1

        /// <summary>Bounds depth and cycles before evaluating a value's typed fields.</summary>
        member _.Guard(depth, value: obj, build: int -> Doc) =
            if depth <= 0 || remaining <= 0 then
                word "..."
            elif isNull value then
                remaining <- remaining - 1
                word (if depth = 100 then "<null>" else "null")
            elif not (active.Add value) then
                word "..."
            else
                try
                    build (depth - 1)
                finally
                    active.Remove value |> ignore

    let private atom (context: Context) depth text =
        if depth <= 0 || context.Remaining <= 0 then
            word "..."
        else
            context.Count ()
            word text

    /// <summary>Formats with the shared width, depth, item and node limits.</summary>
    let format build =
        build (Context ()) 100 3 |> render 80

    /// <summary>Formats a record's known fields in declaration order.</summary>
    let record (context: Context) depth (value: obj) fields =
        context.Guard (
            depth,
            value,
            fun nestedDepth ->
                fields nestedDepth
                |> List.map (fun (name, renderField) ->
                    context.Count ()
                    name, renderField ())
                |> recordLayout
        )

    /// <summary>Formats a case and its retained typed arguments with F# precedence.</summary>
    let union (context: Context) depth precedence (value: obj) cases =
        context.Guard (
            depth,
            value,
            fun nestedDepth ->
                context.Count ()
                let name, arguments = cases nestedDepth
                let retained = List.choose id arguments
                let childPrecedence = if retained.Length = 1 then 2 else 3

                unionLayout
                    precedence
                    name
                    (retained
                     |> List.map (fun renderArgument -> renderArgument childPrecedence))
        )

    /// <summary>Formats a tuple's typed elements.</summary>
    let tuple (context: Context) depth (value: obj) fields =
        context.Guard (depth, value, fun nestedDepth -> fields nestedDepth |> tupleLayout)

    /// <summary>Formats at most 100 array elements, preserving null and cycle boundaries.</summary>
    let array (context: Context) depth renderItem (values: 'T array) =
        context.Guard (
            depth,
            box values,
            fun nestedDepth ->
                let rec items index =
                    if context.Remaining <= 0 then
                        [ word "..." ]
                    elif index = values.Length then
                        []
                    elif index >= 100 then
                        [ word "..." ]
                    else
                        renderItem context nestedDepth 3 values[index]
                        :: items (index + 1)

                items 0 |> arrayLayout
        )

    /// <summary>Formats an option using its statically typed payload renderer.</summary>
    let option (context: Context) depth precedence renderItem value =
        match value with
        | None -> atom context depth "None"
        | Some item ->
            union context depth precedence (box value) (fun nestedDepth ->
                "Some",
                [
                    Some (fun childPrecedence -> renderItem context nestedDepth childPrecedence item)
                ])

    /// <summary>Formats a result using statically typed payload renderers.</summary>
    let result (context: Context) depth precedence renderOk renderError value =
        match value with
        | Ok item ->
            union context depth precedence (box value) (fun nestedDepth ->
                "Ok",
                [
                    Some (fun childPrecedence -> renderOk context nestedDepth childPrecedence item)
                ])
        | Error item ->
            union context depth precedence (box value) (fun nestedDepth ->
                "Error",
                [
                    Some (fun childPrecedence -> renderError context nestedDepth childPrecedence item)
                ])

    /// <summary>Formats a nonnull opaque value with its declared marker and no user code.</summary>
    let opaque (context: Context) depth marker (value: obj) =
        context.Guard (
            depth,
            value,
            fun _ ->
                context.Count ()
                word marker
        )

    let known (context: Context) depth value renderValue =
        if isNull (box value) then
            opaque context depth "" null
        else
            renderValue value

    /// <summary>Uses a known library renderer while preserving its redaction and exception behavior.</summary>
    let manual (context: Context) depth (value: obj) renderValue =
        context.Guard (
            depth,
            value,
            fun _ ->
                context.Count ()

                let text =
                    try
                        renderValue ()
                    with error ->
                        "<ToString exception: " + error.Message + ">"

                word (if isNull text then "" else text)
        )

    /// <summary>Formats a string with the structured formatter's quotes.</summary>
    let text (context: Context) depth (value: string) =
        context.Guard (
            depth,
            box value,
            fun _ ->
                context.Count ()
                word ("\"" + value + "\"")
        )

    /// <summary>Formats a Boolean literal.</summary>
    let boolean context depth value =
        atom context depth (if value then "true" else "false")

    /// <summary>Formats the unit literal.</summary>
    let unit context depth () =
        atom context depth "()"


    let int32 context depth (value: int) =
        atom context depth (value.ToString (CultureInfo.InvariantCulture))

    /// <summary>Formats a double as an F# structured numeric literal.</summary>
    let float64 context depth (value: float) =
        let text =
            if Double.IsNaN value then
                "nan"
            elif Double.IsPositiveInfinity value then
                "infinity"
            elif Double.IsNegativeInfinity value then
                "-infinity"
            else
                let number = value.ToString("G10", CultureInfo.InvariantCulture).ToLowerInvariant()

                if number.Contains "." || number.Contains "e" then
                    number
                else
                    number + ".0"

        atom context depth text

    /// <summary>Formats a byte as an F# structured numeric literal.</summary>
    let uint8 context depth (value: byte) =
        atom
            context
            depth
            (value.ToString (CultureInfo.InvariantCulture)
             + "uy")

    let int64 context depth (value: int64) =
        atom
            context
            depth
            (value.ToString (CultureInfo.InvariantCulture)
             + "L")

    let uint32 context depth (value: uint32) =
        atom
            context
            depth
            (value.ToString (CultureInfo.InvariantCulture)
             + "u")

    let uint64 context depth (value: uint64) =
        atom
            context
            depth
            (value.ToString (CultureInfo.InvariantCulture)
             + "UL")

    let list (context: Context) depth renderItem (values: 'T list) =
        context.Guard (
            depth,
            box values,
            fun nestedDepth ->
                let rec items count remaining =
                    match remaining with
                    | [] -> []
                    | _ when count >= 100 || context.Remaining <= 0 -> [ word "..." ]
                    | head :: tail ->
                        renderItem context nestedDepth 3 head
                        :: items (count + 1) tail

                bracket "[" "]" (separated ";" (items 0 values))
        )

    let stringSet (context: Context) depth renderItem (values: HashSet<string>) =
        context.Guard (
            depth,
            box values,
            fun nestedDepth ->
                let docs = ResizeArray<Doc>()
                let mutable iterator = values.GetEnumerator ()
                let mutable count = 0

                while count < 100
                      && context.Remaining > 0
                      && iterator.MoveNext () do
                    docs.Add (renderItem context nestedDepth 3 iterator.Current)
                    count <- count + 1

                if count < values.Count then
                    docs.Add (word "...")

                beside (word "seq") (bracket "[" "]" (separated ";" (List.ofSeq docs)))
        )

    let rec exceptionValue (context: Context) depth (error: exn) =
        context.Guard (
            depth,
            box error,
            fun nestedDepth ->
                let message =
                    try
                        error.Message
                    with _ ->
                        "<message unavailable>"

                recordLayout
                    [
                        "Type", text context nestedDepth (error.GetType().FullName)
                        "Message", text context nestedDepth message
                        "HResult", int32 context nestedDepth error.HResult
                        "InnerException", exceptionValue context nestedDepth error.InnerException
                    ]
        )
#endif
