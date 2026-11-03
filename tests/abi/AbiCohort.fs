/// <summary>Selects the admitted ABI for the native test catalogue.</summary>
module internal RanvierWebCoreAbi.AbiCohort

/// <summary>Defaults an absent override to ABI63 and accepts only explicit ABI63 or ABI64.</summary>
let expectedVersion (value: string) =
    match value with
    | null -> 63
    | "63" -> 63
    | "64" -> 64
    | _ -> invalidOp "RANVIER_ABI_TEST_EXPECTED must be exactly 63 or 64"
