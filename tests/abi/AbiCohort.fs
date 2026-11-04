/// <summary>Selects the admitted ABI for the native test catalogue.</summary>
module internal RanvierWebCoreAbi.AbiCohort

open System

/// <summary>The positive decimal version in RANVIER_ABI_TEST_EXPECTED, which the driver launcher always sets.</summary>
let expectedVersion (value: string) =
    let isDecimal =
        not (isNull value)
        && value.Length >= 1
        && value.Length <= 9
        && value.[0] >= '1'
        && value.[0] <= '9'
        && value |> Seq.forall Char.IsAsciiDigit
    if not isDecimal then
        invalidOp "RANVIER_ABI_TEST_EXPECTED must be a positive decimal ABI version"
    int value
