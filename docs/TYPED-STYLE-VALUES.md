# Typed CSS value bindings

The unpublished ABI22/Native preview.14 batch adds C14's engine typed-value foundation. The selected WebKit implementation at b95c91b1 already parses and reifies the values; the bindings call it directly and introduce no native JavaScript execution or new dependency.

## Scope

The canonical configuration selects CSSStyleValue.parse/parseAll and stringification, CSSOMKeywordValue/CSSKeywordValue, CSSStyleImageValue/CSSImageValue, CSSUnparsedValue, CSSOMVariableReferenceValue/CSSVariableReferenceValue, and the minimum CSSNumericValue/CSSUnitValue representation. Unit construction and value/unit access are included; numeric arithmetic/conversions and color operations remain deferred C15/C17 work. Unselected parsed math values retain their serializable numeric base instead of being rejected or flattened.

There are 136 native interfaces, 1,725 functions, 19 handle roots and zero stubs: 18 functions and two roots are added to the C12 cohort. All 1,707 existing function-model records, 16 dictionary schemas and old transport layouts remain unchanged. CSSStyleValue type dispatch checks the unit subtype before its numeric base. Browser public aliases and variable-reference union tags use the actual WebIDL interface names.

## Context, strings and ownership

Static parse calls validate a Document and owning engine thread. Selected factories likewise validate their context, while calling value factories that do not take a Document argument. New scalar strings use explicit UTF-8 byte lengths. Existing scalar and compound signatures retain their representation.

New unparsed-segment union fields use RvDomUtf8StringSpan (data and byte length). NUL bytes are preserved. Negative lengths, positive lengths with null data and invalid UTF-8 are rejected. The containing new compounds require present to be 0 or 1; mandatory inputs require 1. Result strings and object arms are owned until the matching union/sequence release, which frees bytes, drops retained references and clears the result. Inputs borrow their storage. Empty strings may have null data and length 0.

parse returns one owned value. parseAll returns an owned sequence whose retained elements are released with its matching release function unless ownership is explicitly transferred by retaining them first. Nullable indexed results distinguish missing segments from present empty strings. A returned variable-reference arm retains the actual engine object and its fallback identity.

The generated Fable setters normalize selected USVString input without evaluating the supplied expression more than once. Factories/static operations are exposed through the paired borrowed service in Core/Views; those providers must normalize every input too. A raw Chromium keyword constructor preserves lone surrogates despite the pinned WebKit USVString declaration, so direct raw engine behavior is not assumed to match automatically.

The reference-segment setter rejects null and validates the actual variable-reference brand through its intrinsic getter before WebIDL union coercion. The string overload still converts null to the text "null". The typed indexed setter rejects uint32.MaxValue with RangeError: JavaScript otherwise treats that key as an ordinary property, bypassing the engine's indexed setter. Append at the current length remains valid, matching CSSUnparsedValue::setItem in the pinned source.

CSSUnitValue's restricted WebIDL double constructor/setter reject NaN and infinities before allocation/mutation. This applies only to the newly selected type; unrestricted doubles and older binding behavior are unchanged.

## Exception names

The raw gate exposed an existing host defect: rv_last_exception used DOMException's name table for simple WebIDL exceptions, yielding a null name for TypeError and RangeError. The host now maps TypeError, RangeError and JSSyntaxError to their standard names, preserving the previous DOMException lookup and message behavior. Actual typed-value errors exercise TypeError/RangeError; the JSSyntaxError mapping is source-reviewed but has no selected throwing operation in this fixture.

## Evidence and remaining gates

- The old C12 runtime fails the new raw test at its missing parse export.
- Generator regressions were observed RED before static/stringifier/factory/span/alias/USV/finite/reference/index changes; all 45 tests pass.
- Local native and Fable Core contracts build all target frameworks with zero warnings/errors. Fresh FCS reports zero diagnostics; complete CSS public API records show 31 unchanged entities plus seven additions.
- Actual generated Fable interfaces pass 21 Chromium assertions, including subtype/union identity, fallback, NUL data, null/surrogate normalization, errors, once-only argument evaluation and rejection of null/forged reference arguments. The later maximum-index guard awaits the expanded shared fixture proof.
- The private Windows candidate passes 190 direct typed-value assertions with all retained handles released. It compiles fresh glue/host code and reuses the verified 45-object parent replacement set, including priority patch 0018; cached baseline and earlier candidate files are verified unchanged.
- The final combined raw batch passes 2,226 assertions: typed values 190, support 72, computed 93, rectangles 140, CSSOM 407, keyframes 93, counter 86, retained context 389, registration 231, tables 44, reflection 269, Area 117 and SVG/MathML 95.
- The complete compiled ABI driver passes its frames/resources/window/surface/observers/paint/popups/clipboard/drop/accessibility/DOM gate and separate teardown mode, both exit 0. Its stale ABI21 assertion was observed failing and updated to this ABI22 batch. Structured FCS checking could not load this standalone project's options; its CLI build passes with zero warnings/errors.

The broader driver initially crashed in Surface.load_html with the parent candidate too. The private staging helper had combined the cached WebCore import libraries with the official preview.11 JavaScriptCore DLL. Swapping only the matching cached JavaScriptCore DLL made the parent full driver pass. The new candidate now uses that coherent dependency and passes the entire driver, teardown and the combined 2,226-assertion raw batch. Cached build outputs and earlier candidates remain untouched. Exact new DLL hashes are in `artifacts/typed-values/coherent-runtime-sha256.json`; earlier private evidence is preserved and does not imply this broader-driver gate passed then.

Every slim platform CI job, the ABI driver harness and extracted-package audits run `tests/abi/typed_style_values.py`. Other-platform execution, the paired service/conformance proof, official normal/traced packages and final acceptance remain pending. These private results do not close C14.
