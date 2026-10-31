# The patch series

`patches/series` lists twenty-three patches, applied in order over the WebKit commit in `pins.json` by
`scripts/patches.py apply`. Each patch carries one concern and, except 0000, 0010, 0012 and 0014 through 0022, changes nothing unless
its CMake option is ON. Every option defaults to OFF, so the lean flavor, which sets none of them, compiles
WebKit's feature implementations. 0010 changes which symbols WebCore exports and which members the host may override,
and no behavior. 0012 adds the sources an embedder names to WebCore. 0013's option is set for macOS in every
flavor, because the package always loads WebCore outside its framework bundle (`config/mac.cmake`).
0014 through 0022 correct stylesheet mutation, typed lists, retained-object behavior and typed transform conversion in every flavor.

The patches add new files (under a `stub/` directory next to the code they stand in for) and CMake hunks.
They edit upstream C++ in these places: 0003 changes `CryptoDigestWin.cpp`, `CryptoKeyEC.h` and
`CryptoKeyRSA.h`; 0010 changes `EmptyClients.h`, `ChromeClient.h`, `WebAnimation.h`, `CSSTransition.h`, `Element.h`,
`Document.h` and `AXCoreObject.h`, and exports from `ResizeObserver.h`, `IntersectionObserver.h` and `Pasteboard.h`,
and also changes `PlatformCocoa.cmake`; 0011 changes `AXObjectCache.h`, `AXObjectCache.cpp`, `FrameSelection.h`,
`FrameSelection.cpp`, `ChromeClient.h` and `OptionsCommon.cmake`. 0012 adds a CMake hook to `Source/WebCore/CMakeLists.txt`. 0013 changes `LocalizedStrings.cpp` and
`OptionsMac.cmake`. 0014 changes `CSSStyleSheet.cpp`; 0015 changes `CSSKeyframeRule.h`, `CSSKeyframeRule.cpp`,
`CSSKeyframesRule.cpp` and `CSSStyleSheet.cpp`. 0016 changes `CSSCounterStyleRule.cpp` and
`CSSCounterStyleRule.h`. 0017 changes `CSSRule.h`, `CSSRule.cpp`, `CSSFontFaceRule.h`,
`PropertySetCSSDescriptors.h`, `PropertySetCSSDescriptors.cpp` and `CSSPositionTryDescriptors.cpp`.
0018 changes `css/parser/CSSParser.cpp` so an explicit custom-property CSSOM assignment can remove importance.
0019 changes `css/typedom/DeclaredStylePropertyMap.cpp`. 0020 changes `css/CSSProperties.json`.
0021 changes `css/typedom/DeclaredStylePropertyMap.cpp` and `dom/StyledElement.cpp`.
0022 changes `css/typedom/transform/CSSMatrixComponent.cpp` and `CSSPerspective.cpp`.
The patches touch 93 files in all.

The sizes are the reduction each patch measured when it was added, on Windows x64, in the slim flavor at
`/O2` (Ranvier's `evidence/ABI-EXPERIMENT.md`, gates 37 to 43).

| Patch | Option | Requires | Size removed |
|---|---|---|---|
| 0000-skia-strike-ref | none, always applies | | |
| 0001-angle-stub | `USE_ANGLE_STUB` | | 5.34 MB (two ANGLE DLLs) |
| 0002-network-stub | `USE_NETWORK_STUB` | | 3.26 MB with 0003 |
| 0003-crypto-stub | `USE_CRYPTO_STUB` | | (with 0002) |
| 0004-gpu-stub | `USE_GPU_STUB` | | 1.70 MB |
| 0005-web-api-stub | `USE_WEB_API_STUB` | | 4.90 MB with 0006 |
| 0006-sqlite-stub | `USE_SQLITE_STUB` | `USE_WEB_API_STUB` | (with 0005) |
| 0007-browser-api-stub | `USE_BROWSER_API_STUB` | `USE_WEB_API_STUB` | 1.44 MB |
| 0008-inspector-stub | `USE_INSPECTOR_STUB` | | 1.44 MB |
| 0009-jsc-inspector-stub | `USE_JSC_INSPECTOR_STUB` | `USE_INSPECTOR_STUB` | 0.98 MB |
| 0010-embedder-clients | none, always applies | | |
| 0011-ax-embedder-notifications | `USE_AX_EMBEDDER_NOTIFICATIONS` | | none: it adds code (see `docs/ACCESSIBILITY.md`) |
| 0012-embedder-sources | none, always applies; `WebCore_EMBEDDER_SOURCES` names the sources | | |
| 0013-unbundled-strings | `USE_UNBUNDLED_LOCALIZED_STRINGS` (macOS) | | none |
| 0014-constructed-sheet-replacement | none, always applies | | correctness repair |
| 0015-keyframe-offset-invalidation | none, always applies | | correctness repair |
| 0016-counter-style-name | none, always applies | | correctness repair |
| 0017-detached-cssom-context | none, always applies | | correctness repair |
| 0018-cssom-custom-property-priority | none, always applies | | correctness repair |
| 0019-declared-style-map-cow | none, always applies | | correctness repair |
| 0020-background-typed-list-separators | none, always applies | | correctness repair |
| 0021-typed-custom-property-priority | none, always applies | | correctness repair |

## Conventions

- **Release assertions mark what presentation never reaches.** A stub member that only a removed feature
  would call is `RELEASE_ASSERT_NOT_REACHED()`, so reaching it crashes at the call rather than misrendering.
  A member on a path the remaining code takes (page and worker lifecycles, queries) answers as WebKit does
  when the feature is absent or disconnected.
- **Stand-in IDL files** declare an interface with no members and no interface object where remaining
  code needs the type to exist. The script-visible result is that the API is `undefined`.
- **Generated stubs** come from upstream headers at build time where the set of members follows a header
  (0008's 163 inspector hooks and 48 canvas argument processors), or from a script kept in this
  repository (0001's EGL and GLES entry points, `scripts/angle_stub.py`).

## 0000-skia-strike-ref

Adds `src/core/SkStrikeRef.cpp` to Skia's source list in `Source/ThirdParty/skia/CMakeLists.txt`. The
pinned list omits the file, and `SkFont::makeStrikeRef` references its constructor, so linking
`WebCore.dll` as a DLL fails on one undefined symbol without it. This applies to every flavor.

## 0001-angle-stub

`Source/ThirdParty/ANGLE/Stub.cmake` defines `ANGLE::EGL` and `ANGLE::GLES` over a static library,
`stub/ANGLEStub.cpp`, compiled with `KHRONOS_STATIC`, and builds none of ANGLE. The library defines every
EGL and GLES 2 and 3 entry point that ANGLE's headers declare on Windows (1,072 functions, 181 of them EGL),
written by `scripts/angle_stub.py`. Every EGL call fails and every GL call does nothing.
`eglGetPlatformDisplayEXT` returns `EGL_NO_DISPLAY`, so `PlatformDisplay::sharedDisplay()` logs the EGL
error and crashes; with 0004 nothing calls it.

## 0002-network-stub

WebCore compiles the curl port's request, cookie, protection space and DNS sources, which use neither curl
nor OpenSSL, and `platform/network/stub/NetworkStub.cpp` in place of the other 17 sources of
`platform/Curl.cmake`. The stub's `NetworkStorageSession` holds no cookies, its public suffix list is
empty, and certificates have no summary. CMake no longer looks for curl or libpsl. The host serves every
resource itself through its resource handler.

## 0003-crypto-stub

Sets `USE(CRYPTO_STUB)` in place of `USE(OPENSSL)`. Web Crypto's registry holds only the SHA digests, so
every other `crypto.subtle` operation rejects with `NotSupportedError`; `crypto/stub/CryptoStub.cpp`
defines the backend's platform members. `CryptoKeyEC.h` and `CryptoKeyRSA.h` gain a branch for the
platform key type `PlatformKeyStub`. PAL computes digests with WebKit's own
`crypto/win/CryptoDigestWin.cpp` over the Windows CryptoAPI, which the patch brings up to the current API
(the `PAL::Crypto` namespace, the SHA-224 enumerator and `Vector::mutableSpan`). CMake looks for OpenSSL
only when 0002 or 0003 is off.

## 0004-gpu-stub

- **WebCore** (`platform/graphics/stub/GPUStub.cmake`) builds no source under `platform/graphics/texmap`,
  `egl` or `angle`, nor `PlatformDisplay.cpp` and `PlatformDisplayWin.cpp`. `GPUStub.cpp` defines the 14
  members of these types that the remaining code references. `GraphicsLayer::create`,
  `PlatformDisplay::sharedDisplay` and the GL context members are release assertions; `GLFence` reports
  itself unsupported.
- **Skia** (`Source/ThirdParty/skia/GPUStub.cmake`) builds without `src/gpu`, `src/text/gpu`, the SkSL code
  generators for GLSL, Metal, SPIR-V, WGSL and pipeline stages, and the EGL interface, and compiles
  without `SK_GL` and `SK_GANESH`. `stub/GaneshStub.cpp` defines the 27 Ganesh entry points WebCore
  references: the factories return null or an invalid texture, and members of a context abort.
- SkSL itself stays: Skia's raster blur and shadow filters compile SkSL effects at run time.
- `USE(TEXTURE_MAPPER)`, `USE(GRAPHICS_LAYER_WC)` and `USE(ANGLE)` stay set, so every remaining WebCore
  source compiles as upstream.

## 0005-web-api-stub

`Modules/stub/WebAPIStub.cmake` builds no source or IDL file under `Modules/cache`, `cookie-store`,
`indexeddb`, `push-api` and `websockets`, `workers/service` and `workers/shared`, nor their generated and
hand-written bindings and `NotificationEvent`.

- Eleven stand-in IDL files (`Modules/stub/idl`): the service and shared worker global scopes,
  `ServiceWorker`, `ExtendableEvent`, `ExtendableMessageEvent`, `PushEvent`, `PushSubscription`,
  `WebSocket`, `IDBFactory`, and the `NavigatorServiceWorker` and `WindowPush` mixins. Script sees
  `window.indexedDB`, `caches`, `navigator.serviceWorker`, `cookieStore`, `pushManager`, `WebSocket` and
  `SharedWorker` as `undefined`.
- `CMakeLists.txt` gains `WebCore_EVENT_INTERFACES_FILE` and `WebCore_EVENT_TARGET_FACTORY_FILE`, which
  default to the upstream inputs; the patch points the first at a copy of `dom/EventInterfaces.in` without
  the ten removed events. `JSEventTargetStub.h.in` writes the `toJS` declaration for each event target type
  whose binding is gone, because the event target factory still includes them.
- `WebAPIStub.cpp` defines the 84 members the remaining code references. Page and worker lifecycle members
  do nothing, IndexedDB connections report themselves invalid, and the rest are release assertions.
- Dedicated workers and worklets stay.

## 0006-sqlite-stub

`platform/sql/stub/SQLiteStub.cmake` builds without WebCore's SQLite wrappers (`platform/sql`), Web SQL
(`Modules/webdatabase`, apart from the `openDatabase` attribute and its callback), the curl cookie
database, the search field's recent-searches database and the resource monitor's persistence, and drops
`SQLite3::SQLite3` from WebCore's libraries. A stand-in `Database.idl` replaces the Web SQL interface.
`openDatabase` throws `NotSupportedError` when Web SQL is enabled; it is off by default, as upstream.

## 0007-browser-api-stub

`Modules/stub/BrowserAPIStub.cmake` builds no source or IDL file under `Modules/WebGPU`, `entriesapi`,
`filesystem`, `webtransport` and `webxr`, nor `GPUCanvasContext`, `GPUBasedCanvasRenderingContext`, the
WebXR bindings, and the bindings of those IDL files. `ENABLE_WEBGPU` and `ENABLE_WEBXR` are already off on
Windows, but upstream builds these sources regardless.

- Six stand-in IDL files: `FileSystemHandle`, `FileSystemFileHandle`, `FileSystemDirectoryHandle`,
  `FileSystemEntry`, `GPUCanvasContext` and the `NavigatorGPU` mixin. `navigator.gpu`, `WebTransport`, the
  File System handles, `navigator.storage.getDirectory` and `HTMLInputElement.webkitEntries` are
  `undefined`, and `getContext("webgpu")` returns null.
- `BrowserAPIStub.cpp` defines 18 members. `webkitGetAsEntry` reaches a release assertion only through
  `dataTransfer.items`, which `DataTransferItemsEnabled` gates; WebCore defaults it off and the host leaves
  it off.

## 0008-inspector-stub

`inspector/stub/InspectorStub.cmake` builds no source under WebCore's `inspector/` except four that the
remaining code calls directly (`InstrumentingAgents.cpp`, `InspectorIdentifierRegistry.cpp`,
`InspectorInstrumentationPublic.cpp`, `InspectorInstrumentationWebKit.cpp`), and no `CommandLineAPIHost`,
`InspectorAudit*` or `InspectorFrontendHost` bindings.

- `generate-inspector-stub.py` runs at build time over two upstream headers: it defines the 163 private
  `*Impl` hooks of `InspectorInstrumentation.h` as no-ops returning a value-initialized result, and the 48
  canvas argument processors of `InspectorCanvasArguments.h` as release assertions. An upstream change to
  either header changes the generated code with no edit to the patch.
- `InspectorStub.cpp` defines the page, frame and worker inspector controllers, which WebCore always
  constructs. They hold no agents, and queries answer as with no frontend connected. Console messages are
  not buffered for a frontend.

## 0009-jsc-inspector-stub

`JavaScriptCore/inspector/stub/InspectorStub.cmake` builds without JavaScriptCore's inspector agents,
injected scripts, generated dispatchers, agent registry, frontend router, inspector target, global object
inspector controller and JavaScript call frames. The console's arguments, call stacks and messages, async
stack traces, identifiers, `ScriptFunctionCall` and the generated protocol objects stay, because the
console clients and WebCore call them.

`InspectorStub.cpp` constructs and destroys the objects WebCore's inspector controllers hold (agent
registry, frontend router, backend dispatcher, injected script host and manager).
`InspectorDebuggerAgent::currentParentStackTrace` returns null. Members that serve a frontend or an
injected script are release assertions.

## 0010-embedder-clients

Makes WebCore's internals that the host uses reachable where WebCore is a shared library (Windows and
macOS). It changes symbol visibility and `final` keywords, and no behavior.

- `EmptyClients.h` exports `EmptyChromeClient`. Six of its members become `override` instead of `final`,
  so the host's chrome client can derive from it: `invalidateRootView`, `invalidateContentsForSlowScroll`,
  `setCursor`, `triggerRenderingUpdate`, `createPopupMenu` and `mouseDidMoveOverElement`.
- `ChromeClient.h` exports the six virtual members defined out of line that `EmptyChromeClient` does not
  override: the three shape detector factories, `getBarcodeDetectorSupportedFormats`,
  `enterFullScreenForElement` and `requestPointerLock` (macOS only).
- `WebAnimation.h`, `Element.h`, `Document.h` and `CSSTransition.h` export the animation members the host
  calls:
  - `WebAnimation`: `play`, `pause`, `reverse`, `finish`, `currentTime`, `setCurrentTime`, `playState` and
    `updatePlaybackRate`;
  - `getAnimations` on `Element` and `Document`;
  - `CSSTransition::transitionProperty`.
- `ResizeObserver.h` and `IntersectionObserver.h` export each observer's `create`, `observe`, `unobserve`,
  `disconnect` and destructor.
- `ClipboardEvent.h`, `DragEvent.h` and `StaticPasteboard.h` export their classes. `DataTransfer.h`
  exports nine members:
  - `createForCopyAndPaste` and `createForDrop`;
  - `types`, `getData` and `setData`;
  - `dropEffect`, `sourceOperationMask`, `destinationOperationMask` and `setSourceOperationMask`.

  With them the host fires `copy`, `cut`, `paste` and the drag events with a `clipboardData` or
  `dataTransfer` the page can read and set.
- `Pasteboard.h` declares `Pasteboard`'s allocator with `WTF_MAKE_TZONE_ALLOCATED_EXPORT(Pasteboard,
  WEBCORE_EXPORT)` in place of `WTF_MAKE_TZONE_ALLOCATED`. On macOS, where TZone allocation is on, this
  exports `Pasteboard::operatorNewSlow`, which the host's `makeUnique<StaticPasteboard>()` calls through the
  inherited `operator new`; without it `RanvierWebCoreHost` fails to link. Elsewhere the macro falls back to
  fast malloc either way.
- `Headers.cmake` forwards these headers:
  - `dom/InputEvent.h`, `dom/ShadowRootInit.h`, `dom/ClipboardEvent.h` and `dom/DragEvent.h`;
  - `platform/StaticPasteboard.h`;
  - `page/ScrollToOptions.h`;
  - the resize and intersection observer headers under `page/`, with their callbacks, entries and options;
  - `animation/CSSTransition.h`, `animation/GetAnimationsOptions.h` and `animation/BlendingKeyframes.h`;
  - `style/StyleExtractor.h` and `style/StyleExtractorState.h`, which `CSSComputedStyleDeclaration.h`
    includes.
- `PlatformCocoa.cmake` keeps `css/CSSComputedStyleDeclaration.h` and `animation/KeyframeEffect.h` among the
  forwarded headers. On macOS it removes both by default.
- `AXCoreObject.h` exports `headingLevel`, `hierarchicalLevel` and `invalidStatus`, which the host's
  accessibility functions call (`docs/ACCESSIBILITY.md`). The other members of `AXCoreObject` the host calls
  are virtual or inline.

## 0011-ax-embedder-notifications

`USE_AX_EMBEDDER_NOTIFICATIONS`, declared in `Source/cmake/OptionsCommon.cmake` so that every port has it,
hands each accessibility notification `AXObjectCache` delivers to the page's
`ChromeClient::postAccessibilityNotification` as well, before the port's platform layer posts it. The member is
the one WebCore's PlayStation and Haiku ports post through; `ChromeClient.h` declares it for the other ports
too, with an empty body, when the option is on. The Windows, macOS and AT-SPI layers post to the platform API
directly, and the Windows layer only for a page with an `HWND`, which an offscreen host has none of.

`AXObjectCache::postEmbedderNotification` is called from these places in `AXObjectCache.cpp`:

- for each notification of the queue, in `notificationPostTimerFired`;
- for each object of a children change, in `handleAllDeferredChildrenChanged`, also on Cocoa, whose
  platform layer does not post children changes;
- for the newly focused object, in `handleFocusedUIElementChanged`;
- for focus moving to an active descendant, an active descendant change, and a `<select>`'s value change,
  which `AXObjectCache` posts to the platform layer directly.
- for text edits (`TextChanged`), in `postTextStateChangeNotification`, `postTextReplacementNotification` and
  `postTextReplacementNotificationForTextControl`, and for selection changes (`SelectedTextChanged`) on Cocoa
  and AT-SPI, whose layers post them directly; Windows already queues them. `postEmbedderTextNotification`
  posts on the text field's object when the edit is inside one.

On Windows `FrameSelection` reports no selection change to accessibility (`notifyAccessibilityForSelectionChange`
is empty outside Cocoa and AT-SPI). With the option on, `FrameSelection.cpp` defines it as the AT-SPI port
does, so the cache queues `SelectedTextChanged` for the observable object.

With the option off, `postEmbedderNotification` and `postEmbedderTextNotification` are empty inline members, and `AXObjectCache` compiles to
what it was. The slim flavor turns the option on; the lean flavor keeps it off, and the host then reports
`rv_abi_has("accessibility-events")` as 0.

## 0012-embedder-sources

Adds the sources of the cache variable `WebCore_EMBEDDER_SOURCES` to WebCore's, outside the unified build, in
`Source/WebCore/CMakeLists.txt`. With the variable empty it adds none. `config/common.cmake` sets it to
`host/dom/RanvierDomGlue.cpp`, the glue of the generated DOM functions (`docs/GENERATOR.md`): compiled as part
of WebCore, the glue calls members WebCore does not export and exports plain C functions in their place. The
hunk stays the same as functions are added, so the generated surface grows without patch changes.

## 0013-unbundled-strings

On macOS WebCore reads each localized string of its user interface (`WEB_UI_STRING`: the default `<details>`
summary, form control labels, validation messages, accessibility role descriptions) from its framework
bundle, `com.apple.WebCore`, through `CFBundleCopyLocalizedString`. The package flattens
`WebCore.framework` into `libWebCore.dylib`, which is no bundle, so `CFBundleGetBundleWithIdentifier` returns
null and `CFBundleCopyLocalizedString` crashes reading it (`EXC_BAD_ACCESS` at address 8, CI run
40567133537, on loading a page with a `<details>` element).

`USE_UNBUNDLED_LOCALIZED_STRINGS`, declared in `OptionsMac.cmake`, makes `copyLocalizedString` answer with the
key when WebCore has no bundle. The keys are the English strings, so WebCore's text matches the Windows port,
whose `localizedString` returns the key. With a bundle, as in WebKit's own framework build, nothing changes.
`config/mac.cmake` turns it on in every flavor.

## 0014-constructed-sheet-replacement

Restricts detached constructed-sheet cache reuse to empty, uniquely owned contents outside the in-memory cache. Repeated replacement preserves the sheet wrapper and its current rules.

## 0015-keyframe-offset-invalidation

CSSKeyframeRule offset edits enter the parent CSSKeyframesRule mutation scope so existing CSS animations recompute their keyframes. Deleting a stylesheet rule uses the removed rule as its mutation target, preserving the name needed to invalidate a removed keyframes animation.

StyleRuleKeyframes copies its child offsets and declarations independently when stylesheet contents detach for mutation. Existing CSSKeyframeRule and style wrappers reattach to the copied children. Editing a retained keyframe after deletion also works when its parent is null.

`tests/abi/keyframe_rules.py` holds a CSS animation paused at 25% progress using a negative delay. It verifies computed effects, shared stylesheet isolation, retained wrappers, invalid/no-op input and checked ABI errors; CI runs it against each slim runtime and package audits run it against extracted payloads.

## 0016-counter-style-name

CSSCounterStyleRule name edits update both the style rule's public name and its counter-style descriptors under the existing mutation scope. Getters/serialization and the renderer's counter registry resolve the same name after copy-on-write.

`tests/abi/counter_style_rules.py` retains rules from two identical stylesheets, removes the second from the active cascade and renames the first. It checks public metadata, complete copy isolation, rendered old/new-name marker effects against literal and decimal controls, invalid/checked errors and detached-rule edits. Slim CI and extracted-package audits run the regression.

## 0017-detached-cssom-context

Retained CSSOM rules keep a weak original settings document and snapshot parser context before losing their parent. The binding helpers prefer live parent/stylesheet scope context while attached. Descriptor objects retain their own weak context so they survive their rule. Disabled or expired document contexts remain unsupported; no global raw-pointer registry or strong document reference is added.

Detached position-try/font-face descriptor edits copy shared backing rules/property sets before mutation and preserve existing descriptor identity. Attached mutations retain stylesheet notification and copy-on-write pairing. The CSSRule size assertion explicitly accounts for one context pointer; the parsed source rule layout is unchanged.

`tests/abi/detached_cssom_context.py` covers retained and late-acquired rules/descriptors, grouping-rule context, ownerless sheets, shared-sheet isolation with actual anchored layout, checked errors and weak owner expiry. Slim CI and extracted-package audits run it. A live settings-toggle scenario is not currently exercised by the public ABI test.

## 0018-cssom-custom-property-priority

The single-custom-property CSSOM parser replaces its parsed property directly, rather than applying the declaration-block cascade merge helper. Explicit assignments can therefore remove importance, including when the value is unchanged. Invalid parsing remains a no-op, and stylesheet declaration blocks keep their existing important-precedence rules.

`tests/abi/custom_properties.py` checks registered and unregistered property values, priority and computed dimensions, same-value importance removal, invalid-priority/token preservation, empty-value removal and duplicate stylesheet declarations.

## 0019-declared-style-map-cow

Declared typed style maps enter the rule mutation scope before acquiring the backing StyleRule. The scope can clone shared stylesheet contents and reattach the owning CSSStyleRule. All six mutation paths now use that current backing rule, preserving isolation of another cache-sharing stylesheet and ensuring edits affect the owning sheet and layout. An expired weak owner still takes the existing no-op/false path through the nullable rule mutation scope.

`tests/abi/style_property_maps.py` retains maps from identical sheets, edits one and verifies its current values, the other complete rule and actual geometry. `tests/abi/declared_style_maps.py` covers all six mutators with a fresh cache-sharing pair for each, complete-sheet isolation, wrapper identity, invalid-mutation preservation and expired weak owners.

## 0020-background-typed-list-separators

The metadata for background-image, background-clip, background-origin and background-size now declares a comma outer separator, matching their existing repeated-layer grammars. Typed OM set/append consume this generated separator. Inner background-size pairs keep their spaces; ordinary parser grammars and other legitimate space-separated properties are unchanged.

The focused typed-map fixture checks image set/append ordering, all four background properties, inner size pairs, animation-name comma lists and grid-auto-columns space lists. Private regeneration changes only the four separator returns in CSSPropertyNames.cpp and its gperf source; every generated header and other derived output is unchanged. Cached derived files are not overwritten.

## 0021-typed-custom-property-priority

Explicit typed custom-property assignment replaces the declaration directly instead of using the parser cascade merge helper, which preserved an old important value. This applies to declared maps and the CSSValue overload of StyledElement's inline custom setter; the unrelated string overload is unchanged. The changed inline overload is only called by Typed OM in this source pin.

`tests/abi/declared_style_maps.py` checks both changed-value and same-value importance removal in declared and inline maps, the complete cache-sharing copy and actual var-dependent geometry. The stylesheet parser's important-precedence semantics remain unchanged.

## 0022-css-transform-matrix-conversion

Typed transform conversion returns a new matrix whose is2D flag matches the component. A 3D matrix component now copies its internal transformation instead of exposing that internal mutable matrix, and forces the output's 3D flag even when the stored matrix is affine. A perspective-none component returns an identity matrix with a 3D flag, preserving that distinction when it appears inside a transform list.

`tests/abi/css_transforms.py` checks repeated conversion identity, mutation isolation, forced-3D options and perspective-none component/list flags. The initial native probe reproduces all these failures before the repair.

## 0033-image-loader-native-decode

ImageLoader keeps native decode waiters beside its decode promises and settles both at the same points, each with an `ImageDecodeResult` naming the reason: source change, access-control error, cancelled load, inactive document, missing source, load error, decode error or decoded. HTMLImageElement and SVGImageElement forward a `Function` waiter; the promise path is unchanged. An already complete image settles a waiter in a queued task instead of a microtask, because a host that disallows VM entry never performs a microtask checkpoint.

`tests/abi/image_decode.py` checks each outcome through `rv_image_decode`. Without the patch, a MutationObserver-based probe in the same host receives no terminal on a source change.

## 0034-svg-string-list-null-attribute

Removing `requiredExtensions` or `systemLanguage` empties the element's SVGStringList: both setters clear the list and return for a null attribute value, so the list reports `numberOfItems` 0, keeps its identity, and the element passes SVGTests conditional processing again, inside and outside `<switch>`, as in SVG 2 and Chromium. A present empty attribute keeps WebKit's single empty item.

`tests/abi/svg_tests_lists.py` compares removal, empty, restore, clear and append steps with the Chromium 156 oracle `tests/fixtures/svg-tests-lists-oracle.json` (`tests/abi/svg_tests_lists_browser.mjs`). Measured differences that remain: `clear()` leaves the attribute `""` where Chromium removes it, `systemLanguage` serialises with `", "`, and `requiredExtensions=""` holds one empty item. Evidence: `docs/mathml-evidence/source-0034/evidence.json`.

## 0035-caret-position-text-control-shadow-roots

`Document::caretPositionFromPoint` returns the text control element for a hit inside an `<input>` or `<textarea>`
that is outside any shadow tree, whatever `CaretPositionFromPointOptions.shadowRoots` lists, as Chromium does. Before
the patch a non-empty `shadowRoots` list returned a text node of the control's user-agent shadow root.

`tests/abi/caret_hit.py` replays the Chromium 156 oracle `tests/fixtures/caret-hit-oracle.json` with and without
`shadowRoots`; its text-control points give `INPUT@1` both ways at device scales 1, 1.5 and 2.

## Working on the series

```
python -I scripts/patches.py apply  --source <webkit>             # reset the series' files to the pin, apply all
python -I scripts/patches.py check  <commit> --source <webkit>    # dry-run the series against another commit
python -I scripts/patches.py export <name> <path>... --source <webkit>
```

`export` diffs the given paths against the pin with the earlier patches of the series applied, and
writes `patches/<name>.patch`; add a new name to `series` first. `.gitattributes` keeps the patches' line
endings LF, which `git apply` requires. `docs/UPDATING.md` covers moving to a new WebKit commit.
