# H13 URL parsing and patterns plan

## Core and view state

- **Core primitives used:** none inside the native exports or the shared URL contracts. A view that derives a URL
  from state computes it in a memo (`createMemoWithComparer` with string equality on `href` skips unchanged
  results), and a route match in a memo over the pattern and the current URL. The memo's owner releases the
  native handles it created through `onCleanup`.
- **View-owned state:** none. The engine holds each URL, its search parameters and each compiled pattern. A
  wrapper holds only the native handle of its engine object, which the core cannot hold.

**Goal:** expose WebKit's own `URL`, `URLSearchParams` and `URLPattern` (WTF `URLParser` and the WebCore
URLPattern compiler, which interprets its expressions with JSC's Yarr interpreter and runs no script) through
the shared browser/native contract, and compare relative resolution, normalization, encoding, query handling
and URLPattern matching against Chromium and the web-platform-tests corpus (Ranvier.WebCore #115).

**Trees:** native `C:/wk/native-url`, branch `codex/native-api-url`, from G05's `dc0951a` with D16 (`2fc30ea`)
merged; H11 and G09 merge before allocation. Reservation Native33/ABI41, DOM alpha.36, Views 0.1.26, backend
alpha.26. `URL.createObjectURL` and `URL.revokeObjectURL` stay excluded: they belong to a later blob-URL group.

## Route

The engine's parser is the conformance reference, so the exports call it; no managed parser is written.
`System.Uri` agrees with Chromium on `href` for 30 of 40 measured cases: it keeps out-of-range IPv4 parts,
skips IDNA, lowercases a `mailto:` host, encodes `data:` spaces, keeps tab and newline, rejects `http:/\\host`,
decodes `%7E` and writes `foo:///` for `foo://`. .NET has no URLPattern.

## Native surface

`gen/dom.json` selects `DOMURL` (public name `URL`), `URLSearchParams` and `URLPattern` as value-object roots
with Document-receiver constructors, `URL.parse` and `URL.canParse` as static bindings, the
`URLSearchParams` entries snapshot and stringifier, and `URLPatternResult`, `URLPatternComponentResult` and
`URLPatternInit` as result dictionaries. Every string is UTF-8 with a byte length, including the strings
inside the URLPattern input union, the group values and the URLSearchParams init union.

The generator gains three transports, committed separately (`67709dc`, `bf39f91`): an optional string without a
default as length -1, `record<K, V>` as the entry sequence of its `Vector<KeyValuePair<K, V>>`, and owned
dictionary results (docs/GENERATOR.md, "Dictionary results").

## Proof

1. **RED:** `tests/abi/url_values.py` fails on Native30 because the URL exports are absent.
2. **Native GREEN** on `artifacts/native33-candidate-N`: `tests/abi/url_values.py` replays
   `tests/fixtures/url-cases.json` (parsing and relative resolution, setters, URLSearchParams operations,
   `URL.searchParams` identity and liveness, URLPattern construction, `test` and `exec`) against the Chromium
   oracle `tests/fixtures/url-oracle.json`, and checks argument, interface and thread errors and handles held
   past `rv_host_destroy`. `tests/abi/url_wpt.py` runs the pinned WPT corpus (`tests/fixtures/wpt/url`) and
   scores both engines with the WPT harness rules.
3. **Managed GREEN:** the shared conformance fixture runs on native JIT, NativeAOT and Chromium, with teardown
   cases and an evidence JSON.

## Qualifications (measured)

- Own cases: 6 of 142 URL cases differ from Chromium 156.0.8078.4, each where the engine follows the WHATWG URL
  standard: a space in a host fails, `|` stays unencoded in a path, `file:c:` keeps its drive-letter case,
  `file://localhost/` loses the host, the protocol setter keeps `mailto:` non-special, and `search = "?"`
  keeps the `?`. URLSearchParams and URLPattern cases agree.
- WPT `15b31607`: the engine passes urltestdata 896/896, setters 278/278 and urlpattern 369/369; Chromium
  passes 787, 238 and 369. All 150 disagreements are listed with both outcomes in
  `tests/fixtures/url-wpt-qualified.json`; no case fails on both engines.
- Every URL, URLSearchParams and URLPattern string is length-delimited, so U+0000 survives every member
  (URLSearchParams is in `sequenceStringSpans`).
- The JavaScript overload `new URLPattern(input, options, baseURL)` throws a TypeError in binding conversion;
  the C ABI has no such call.
