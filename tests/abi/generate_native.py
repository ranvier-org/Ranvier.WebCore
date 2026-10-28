"""Generates the P/Invoke declarations of tests/abi/Native.fs from host/RanvierWebCoreAbi.h: the declarations in the module
Raw, and a function of the same name and parameters for each, which counts and times the call while Calls.On.

Usage:
  python generate_native.py compare   compares the header's functions with the externs in Native.fs, by name and
                                      parameter types, and exits 1 on any difference
  python generate_native.py write     replaces Native.fs's declarations with the generated ones, between the
                                      generated-section markers (the first write replaces the hand-written section)
  python generate_native.py check     exits 1 when the externs of Native.fs's generated section differ from the
                                      header's functions, by name, order and parameter types; the section's layout
                                      is Fantomas's
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEADER = HERE.parents[1] / "host" / "RanvierWebCoreAbi.h"
NATIVE = HERE / "Native.fs"

BEGIN = "// BEGIN GENERATED from host/RanvierWebCoreAbi.h by tests/abi/generate_native.py; edit the header, then run it."
END = "// END GENERATED"

# The hand-written section that the first write replaces: from the library literal to the last extern.
HAND_START = "[<Literal>]\nlet private Lib"
HAND_END = "let WrongThread = -2"

# F# keywords and reserved identifiers that a C parameter name can take.
KEYWORDS = set(
    """abstract and as assert base begin class default delegate do done downcast downto elif else end exception extern
    false finally fixed for fun function global if in inherit inline interface internal lazy let match member module
    mutable namespace new not null of open or override private public rec return select sig static struct then to
    true try type upcast use val void when while with yield break checked component const constraint continue event
    external include mixin parallel process protected pure sealed tailcall trait virtual""".split()
)

# The parameter name for an unnamed handle, by its pointee type.
HANDLE_NAMES = {"RvHost": "host", "RvNode": "node", "RvEvent": "event", "RvWatch": "watch", "RvListener": "listener", "RvAnimation": "animation", "RvAxNode": "ax"}


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def declarations(header: str):
    """Each exported function as (name, return type, [(C type, name)])."""
    body = strip_comments(header)
    found = []

    for match in re.finditer(r"RV_EXPORT\s+([^;{]*?)\b(rv_\w+)\s*\(([^)]*)\)\s*;", body, flags=re.S):
        returns = " ".join(match.group(1).split())
        params = []
        text = " ".join(match.group(3).split())

        if text and text != "void":
            for part in text.split(","):
                part = part.strip()
                named = re.match(r"^(.*?[\s*])(\w+)$", part)

                if named and named.group(2) not in ("int32_t", "int64_t", "void") and not named.group(2).startswith("Rv"):
                    params.append((" ".join(named.group(1).split()).replace(" *", "*"), named.group(2)))
                else:
                    ctype = part.replace(" *", "*")
                    params.append((ctype, HANDLE_NAMES.get(ctype.rstrip("*"), "value")))

        found.append((match.group(2), returns.replace(" *", "*"), params))

    return found


def return_type(ctype: str) -> str:
    if ctype == "void":
        return "void"
    if ctype == "int32_t":
        return "int"
    if ctype == "int64_t":
        return "int64"
    if re.fullmatch(r"Rv\w+\*", ctype):
        return "nativeint"
    raise ValueError(f"unmapped return type {ctype}")


def parameter(ctype: str, name: str) -> tuple[str, str]:
    """The F# parameter type, with its marshalling attribute, for the C parameter."""
    if ctype == "int32_t":
        return "int", ""
    if ctype == "float":
        return "float32", ""
    if ctype == "double":
        return "float", ""
    if ctype == "double*":
        # An array the function fills, such as rv_ax_text_rects's rectangles; else one value.
        return ("float[]", "[<In; Out>] ") if name == "rects" else ("double&", "")
    if ctype == "const char*":
        return "string", "[<MarshalAs(UnmanagedType.LPUTF8Str)>] "
    if ctype == "char*":
        return "byte[]", ""
    if ctype == "uint8_t*":
        return "byte[]", "[<In; Out>] "
    if ctype == "const uint8_t*":
        return "byte[]", "[<In>] "
    if ctype == "const double*":
        return "float[]", "[<In>] "
    if ctype == "int32_t*":
        # A string getter's length is passed as a one-element array, as readString passes it.
        return ("int[]", "") if name == "length" else ("int&", "")
    if re.fullmatch(r"Rv\w+\*\*", ctype):
        return "nativeint[]", ""
    # An Rv type without a pointer is a function pointer typedef; the header passes every struct by pointer.
    if re.fullmatch(r"Rv\w+\*?", ctype) or ctype == "void*":
        return "nativeint", ""
    raise ValueError(f"unmapped parameter type {ctype} {name}")


def fsharp_name(name: str) -> str:
    return f"``{name}``" if name in KEYWORDS else name


def generated(header: str) -> str:
    lines = [
        BEGIN,
        "",
        "[<Literal>]",
        'let private Lib = "RanvierWebCoreHost"',
        "",
        "/// <summary>The <c>RvEventCallback</c> of the header.</summary>",
        "[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]",
        "type EventCallback = delegate of context: nativeint * event: nativeint -> int",
        "",
        "/// <summary>The <c>RvResourceHandler</c> of the header; <c>url</c> is a NUL-terminated UTF-8 string.</summary>",
        "[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]",
        "type ResourceHandler = delegate of context: nativeint * load: nativeint * url: nativeint -> unit",
        "",
        "/// <summary>The <c>RvFrameCallback</c> of the header.</summary>",
        "[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]",
        "type FrameCallback = delegate of context: nativeint -> unit",
        "",
        "/// <summary>The <c>RvResizeCallback</c> of the header.</summary>",
        "[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]",
        "type ResizeCallback = delegate of context: nativeint * target: nativeint * width: float * height: float -> unit",
        "",
        "/// <summary>The <c>RvIntersectionCallback</c> of the header.</summary>",
        "[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]",
        "type IntersectionCallback = delegate of context: nativeint * target: nativeint * intersecting: int * ratio: float -> unit",
        "",
        "/// <summary>The <c>RvPopupCallback</c> of the header.</summary>",
        "[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]",
        "type PopupCallback =",
        "    delegate of context: nativeint * popup: nativeint * action: int * x: int * y: int * width: int * height: int * selected: int -> unit",
        "",
        "/// <summary>The <c>RvClipboardWrite</c> of the header; <c>type</c> and <c>data</c> are NUL-terminated UTF-8.</summary>",
        "[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]",
        "type ClipboardWrite = delegate of context: nativeint * ``type``: nativeint * data: nativeint * first: int -> unit",
        "",
        "/// <summary>The <c>RvClipboardRead</c> of the header.</summary>",
        "[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]",
        "type ClipboardRead = delegate of context: nativeint * request: nativeint -> unit",
        "",
        "/// <summary>The <c>RvDragStartCallback</c> of the header.</summary>",
        "[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]",
        "type DragStartCallback = delegate of context: nativeint * drag: nativeint * x: int * y: int * allowed: int -> unit",
        "/// <summary>The <c>RvAxCallback</c> of the header.</summary>",
        "[<UnmanagedFunctionPointer(CallingConvention.Cdecl)>]",
        "type AxCallback = delegate of context: nativeint * node: nativeint * event: int -> unit",
    ]

    found = declarations(header)
    lines += [
        "",
        "/// <summary>",
        "/// Per-function counts and Stopwatch ticks of the calls made while <c>On</c>, indexed as <c>Names</c>. The ticks of a",
        "/// call span its P/Invoke transition, marshalling and native work.",
        "/// </summary>",
        "module Calls =",
        "    let Names = [| " + "; ".join(f'"{name}"' for name, _, _ in found) + " |]",
        "    let Counts: int64 array = Array.zeroCreate Names.Length",
        "    let Ticks: int64 array = Array.zeroCreate Names.Length",
        "    let mutable On = false",
        "    /// <summary>The sum of <c>Ticks</c>.</summary>",
        "    let mutable Elapsed = 0L",
        "",
        "/// <summary>The header's functions as P/Invoke declarations.</summary>",
        "module Raw =",
    ]

    for name, returns, params in found:
        rendered = []

        for ctype, pname in params:
            ftype, attribute = parameter(ctype, pname)
            rendered.append(f"{attribute}{ftype} {fsharp_name(pname)}")

        lines += ["", "    [<DllImport(Lib)>]", f"    extern {return_type(returns)} {name}({', '.join(rendered)})"]

    for index, (name, returns, params) in enumerate(found):
        typed, passed = [], []

        for ctype, pname in params:
            ftype, _ = parameter(ctype, pname)
            pname = fsharp_name(pname)
            byref = ftype.endswith("&")
            typed.append(f"{pname}: byref<{ftype[:-1]}>" if byref else f"{pname}: {ftype}")
            passed.append(f"&{pname}" if byref else pname)

        fsharp_return = "unit" if return_type(returns) == "void" else return_type(returns)
        call = f"Raw.{name} ({', '.join(passed)})"
        lines += [
            "",
            f"let {name} ({', '.join(typed)}) : {fsharp_return} =",
            "    if Calls.On then",
            "        let started = System.Diagnostics.Stopwatch.GetTimestamp ()",
            f"        let result = {call}",
            "        let spent = System.Diagnostics.Stopwatch.GetTimestamp () - started",
            f"        Calls.Counts[{index}] <- Calls.Counts[{index}] + 1L",
            f"        Calls.Ticks[{index}] <- Calls.Ticks[{index}] + spent",
            "        Calls.Elapsed <- Calls.Elapsed + spent",
            "        result",
            "    else",
            f"        {call}",
        ]

    lines += ["", END]
    return "\n".join(lines) + "\n"


def externs(fsharp: str):
    """Each extern in the F# source as (name, return type, [parameter type with attribute])."""
    found = []

    for match in re.finditer(r"extern\s+(\S+)\s+(rv_\w+)\s*\((.*?)\)\s*\n", fsharp, flags=re.S):
        params = []
        text = " ".join(match.group(3).split())

        if text:
            for part in re.split(r",(?![^\[]*\])", text):
                part = part.strip()
                attribute = re.match(r"^(\[<.*?>\])\s*", part)
                rest = part[attribute.end():] if attribute else part
                ftype = rest.rsplit(" ", 1)[0]
                params.append(((attribute.group(1) + " ") if attribute else "") + ftype)

        found.append((match.group(2), match.group(1), params))

    return found


def compare(native: str, header: str) -> int:
    expected = {
        name: (return_type(r), [parameter(c, n)[1] + parameter(c, n)[0] for c, n in params])
        for name, r, params in declarations(header)
    }
    actual = {name: (r, params) for name, r, params in externs(native)}
    differences = 0

    for name in sorted(set(expected) | set(actual)):
        if name not in actual:
            print(f"missing from Native.fs: {name}")
            differences += 1
        elif name not in expected:
            print(f"not in the header: {name}")
            differences += 1
        elif expected[name] != actual[name]:
            print(f"differs: {name}\n  header:    {expected[name]}\n  Native.fs: {actual[name]}")
            differences += 1

    print(f"header functions {len(expected)}, Native.fs externs {len(actual)}, differences {differences}")
    return 1 if differences else 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    header = HEADER.read_text(encoding="utf-8")
    raw = NATIVE.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    native = raw.replace("\r\n", "\n")
    section = generated(header)

    if mode == "compare":
        return compare(native, header)

    if BEGIN in native:
        start = native.index(BEGIN)
        stop = native.index(END) + len(END) + 1
    else:
        start = native.index(HAND_START)
        stop = native.index(HAND_END)

    current = native[start:stop]

    if mode == "check":
        names = [name for name, _, _ in declarations(header)]
        ordered = [name for name, _, _ in externs(current)] == names
        status = compare(current, header)

        if not ordered:
            print("the generated section's externs are out of the header's order; run write")

        return 1 if status or not ordered or BEGIN not in native else 0

    if mode == "write":
        tail = native[stop:]
        result = native[:start] + section + ("" if BEGIN in native else "\n") + tail
        NATIVE.write_bytes(result.replace("\n", newline).encode("utf-8"))
        print(f"wrote {len(declarations(header))} externs")
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
