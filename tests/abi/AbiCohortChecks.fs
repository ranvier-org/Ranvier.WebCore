module RanvierWebCoreAbi.AbiCohortChecks

open System

[<EntryPoint>]
let main _ =
    for input, expected in [ "63", 63; "64", 64; "65", 65; "999999999", 999999999 ] do
        if AbiCohort.expectedVersion input <> expected then
            failwith "ABI cohort did not select the exact admitted version"

    for input in [ null; ""; "0"; "064"; " 64"; "64 "; "64.0"; "-1"; "1000000000" ] do
        let mutable rejected = false
        try
            AbiCohort.expectedVersion input |> ignore
        with :? InvalidOperationException -> rejected <- true
        if not rejected then
            failwith "Unsupported ABI cohort was admitted"

    if 63 = AbiCohort.expectedVersion "64" then
        failwith "The selected catalogue expectation lost exact version matching"
    printfn "ABI_COHORT_CONTROLS_PASS=13"
    0
