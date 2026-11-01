macOS SDK global-name clash scan of the batch-6 host sources (mac3).
- Failure: native run 41272153655 (codex/batch-6 at 7a1ad465), osx-arm64 Build: RanvierDomGlue.cpp:7128:53 "reference to
  'Comment' is ambiguous" between CarbonCore AIFF.h's global `typedef struct Comment Comment` and WebCore::Comment, under
  the glue's `using namespace WebCore`.
- Fix: gen/domgen.py emits no `using namespace WebCore` and writes every WebCore name of the glue as WebCore::<name>
  (qualify_webcore over the emitted text; the names are the IDL interfaces, namespaces, callbacks, dictionaries,
  enumerations and typedefs, RUNTIME_WEBCORE_NAMES and gen/dom.json webcoreNames). host/RanvierWebCoreAbi.cpp
  qualifies its four uses of WebCore::Cursor (QuickDraw declares a global Cursor).
- Stand-in: carbon-globals.h declares at global scope, as `typedef struct X X;`, the MacTypes, QuickdrawTypes and
  CarbonCore (AIFF, Components, Files, OSUtils, ...) type names, Comment, Rect, Point, Size, Style, Handle, Ptr, Region,
  Cursor, Pattern, Picture, Fixed, Boolean, Byte among them. Polygon is left out: wingdi.h declares a function of that name.
  compile.py compiles a host unit with the batch6-candidate-2 flags (artifacts/batch6-candidate-2/*.rsp; no PCH,
  -ferror-limit=0) and /FI carbon-globals.h; --overlay C:/wk/int7-tools/macsim/include adds int7's macOS-off cmakeconfig.h.
  scan.py runs it over the 16 host units built on every platform (the D3D11 and UIA units are Windows-only).
- Results (logs/):
  RanvierDomGlue-old.log    9c37e764 glue: 2 errors, the CI pair (7128:53 Comment ambiguous, 484:16 deliver lambda).
  RanvierDomGlue.log        regenerated glue: 0 errors.
  RanvierDomGlue-macoff.log regenerated glue with the macOS-off overlay: 0 errors.
  RanvierWebCoreAbi-old.log 9c37e764 RanvierWebCoreAbi.cpp: 51 errors (4 Cursor ambiguous, 47 follow-on).
  RanvierWebCoreAbi.log     qualified RanvierWebCoreAbi.cpp: 0 errors.
  the other 14 units: 0 errors at 9c37e764 sources (warnings only, as in the candidate build).
