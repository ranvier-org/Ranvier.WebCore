# The patch series

`patches/series` is the authoritative list of patches, applied in order over the WebKit commit in `pins.json` by
`scripts/patches.py apply`. This file documents the patches whose rationale is not obvious from their names;
the others are described by their patch headers. Each patch carries one concern. Every CMake option a patch adds
defaults to OFF, so the lean flavor, which sets none of them, compiles WebKit's feature implementations. A patch
whose row names no option applies in every flavor. 0010 changes which symbols WebCore exports and which members the host may override, and no
behavior. 0012 adds the sources an embedder names to WebCore. 0013's option is set for macOS in every flavor,
because the package always loads WebCore outside its framework bundle (`config/mac.cmake`).

The patches add new files (under a `stub/` directory next to the code they stand in for) and CMake hunks. Each
patch section below names the upstream files it edits.

The sizes below are the reduction each stub patch measured when it was added, on Windows x64, in the slim flavor
at `/O2`. They are historical measurements, not a current package size (see `docs/SETTINGS.md`).

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

`tests/abi/svg_tests_lists.py` compares removal, empty, restore, clear and append steps with the Chromium 156 oracle `tests/fixtures/svg-tests-lists-oracle.json` (`tests/abi/svg_tests_lists_browser.mjs`). Measured differences that remain: `clear()` leaves the attribute `""` where Chromium removes it, `systemLanguage` serialises with `", "`, and `requiredExtensions=""` holds one empty item.

## 0035-caret-position-text-control-shadow-roots

`Document::caretPositionFromPoint` returns the text control element for a hit inside an `<input>` or `<textarea>`
that is outside any shadow tree, whatever `CaretPositionFromPointOptions.shadowRoots` lists, as Chromium does. Before
the patch a non-empty `shadowRoots` list returned a text node of the control's user-agent shadow root.

`tests/abi/caret_hit.py` replays the Chromium 156 oracle `tests/fixtures/caret-hit-oracle.json` with and without
`shadowRoots`; its text-control points give `INPUT@1` both ways at device scales 1, 1.5 and 2.

## 0043-media-capabilities-native-query

`MediaCapabilitiesNativeQuery.h` declares `queryMediaDecodingInfo` and `queryMediaEncodingInfo`, defined at the end
of `MediaCapabilities.cpp`: `decodingInfo()` and `encodingInfo()` for an embedder, without JavaScript or a promise.
They run the file's own configuration validation, completing with TypeError for an invalid configuration, and its
gather path: settings, allowed container and codec types, the VP9 gate, the WebRTC route and the media engine
configuration factories. The promise path, `MediaCapabilities.h`, the navigator and every setting are unchanged.
The new header is included only by `MediaCapabilities.cpp` and the host, so the patch recompiles one unified source.

`tests/abi/media_capabilities.py` checks each case of `tests/fixtures/media-capabilities-cases.json` through
`rv_media_decoding_info` and `rv_media_encoding_info`.

## 0049-image-bitmap-crop-completion-handler

`ImageBitmap::createCompletionHandler(context, source, options, sx, sy, sw, sh, handler)` is
`createImageBitmap(image, sx, sy, sw, sh, options)` for an embedder, without JavaScript or a promise. It completes
with RangeError for a zero `sw` or `sh`, normalises a negative rectangle as the promise path does, and runs the
existing per-source crop overloads, which stay private. The promise path is unchanged. The header gains one static
member function, so the eight unified sources that include `ImageBitmap.h` recompile with unchanged layouts.

`tests/abi/canvas_export.py` creates cropped bitmaps through `rv_image_bitmap_create`. Without the patch the host glue
has no public crop entry point.

## 0050-image-bitmap-unaccelerated-buffers

An ImageBitmap's buffer is accelerated only where a canvas's is: under `USE(CA)` or `USE(SKIA)`, `bufferRenderingMode`
returns Unaccelerated when `canvasUsesAcceleratedDrawing` is off, the setting `CanvasBase::shouldAccelerate()` reads.
The GTK and WPE `hardwareAccelerationEnabled` check stays. Cocoa enables the setting by default and keeps accelerated
bitmaps. The change is inside `ImageBitmap.cpp` and recompiles one unified source.

Without the patch every `createImageBitmap` on the slim Windows build creates an accelerated Skia buffer, whose
Ganesh stub aborts the process.

## 0051-web-animation-promise-observer

`WebAnimationPromiseObserver.h` declares `setWebAnimationPromiseObserver`, a process-wide function pointer that
`WebAnimation.cpp` calls each time a ready or finished promise settles: with no code when it resolves, and with
`AbortError` when `cancel()` or a reset of the pending tasks schedules its rejection. The engine rejects those promises
in a microtask, which a host that disallows VM entry never runs, so the observer reports the rejection when it is
scheduled. The pointer is a file static: no class layout changes, `WebAnimation.h` is untouched, and an unset observer
leaves the engine's behaviour unchanged. `Headers.cmake` lists the header among the private framework headers.

`tests/abi/animation_lifecycle.py` checks `rv_animation_ready` and `rv_animation_finished` against the Chromium 156
oracle `tests/fixtures/animation-lifecycle-oracle.json`.

## 0052-eventloop-checkpoint-microtasks

While the VM disallows entry, `EventLoopTaskGroup::queueMicrotask` queues a C++ microtask as a checkpoint task
(`runAtEndOfMicrotaskCheckpoint`) instead of wrapping it in a JavaScript microtask cell. A microtask checkpoint runs
checkpoint tasks in queueing order without entering the VM, so the engine's C++ microtasks (Web Animations AbortError
rejections and asynchronous finish, among others) run under a host that disallows VM entry. On the main thread a
`RunLoop` dispatch performs that checkpoint, once for every event loop that queued a checkpoint task before it ran; the
event loop's own timer and scheduled state are untouched, so task latency is the same as without the patch. Other
threads schedule their event loop. With VM entry allowed the function is unchanged. The change is one file,
`EventLoop.cpp`, with no class layout change, and recompiles one unified source.

The first revision scheduled the window event loop instead. Document::considerSpeculationRules then queued a C++
microtask from the style-recalc timer, inside the Windows shared-timer message, where `MainThreadSharedTimer` defers a
zero-delay timer through a timer queue; `ThreadTimers::updateSharedTimer` ignores a later zero-delay start while both
fire times are past, so every task queued afterwards waited milliseconds for that post. `tests/abi/event_loop_latency.py`
reproduces it (a denied pointer-lock request delivered after thousands of turns) and passes with this revision.

Without the patch, `cancel()` of an animation with a pending pause queues its rejection as a JavaScript microtask, and
the armed VM-entry crash (`crashOnDisallowedVMEntry`) aborts the host at the next checkpoint.

## 0074-texture-mapper-gpu-layer-painting

Upstream, `BitmapTexture::updateContents(GraphicsLayer*)` paints every TextureMapper tile into an unaccelerated
`ImageBuffer` and uploads it, because no port that uses `GraphicsLayerTextureMapper` respected the accelerated bit:
WPE and GTK rasterize on the GPU through coordinated graphics instead. The host composites with
`GraphicsLayerTextureMapper`, so every layer, its root layer included, was rasterized on the CPU, and a blurred
`box-shadow` (a Skia `DropShadowOnly` image filter) re-blurred on the CPU whenever a dirty rectangle crossed it.

The patch adds `BitmapTexture::setPaintsLayersOnGPU`, off by default. While it is set, a tile is painted straight into
its GL texture through `SkSurfaces::WrapBackendTexture` in the thread's Skia GL context, and the current context waits
on a fence for that work. A texture Skia cannot render to (BGRA layout, an external or memory-mapped buffer) and a
thread without a Skia context take the upstream path. `canPaintLayersOnGPU` creates the context: WPE creates it on
first use; on Windows, where upstream only WebKit's threaded compositor installs one, `PlatformDisplay::skiaGLContext`
returns the context the embedder installed, and that context has no `SkExecutor`, whose thread pool, joined from a
`thread_local` destructor under the loader lock, deadlocks the process's exit. `releaseLayerPaintingContext` destroys
it. The host turns painting on per composite (`rv_host_set_gpu_painting`, `docs/HOSTING.md`).

`GraphicsContextSkia::clip(FloatRect)` rounds a non-antialiased clip's device edges in a GPU layer paint as Skia's
raster backend does, `floor(x + 0.5)`, where Ganesh's pixel-centre rule would drop the column a half-pixel edge
crosses: a `background-clip: content-box` 100.5px wide lost its last column against the CPU paint and Chromium
(`tests/fixtures/background-content-clip-cases.json`).

## 0075-texture-mapper-scroll-backing-store

A viewport scroll takes WebKit's fast path, `LocalFrameView::scrollContentsFastPath`, which calls
`ChromeClient::scroll` for the embedder to move its backing store's pixels and then `invalidateRootView`, which asks
only for the view to be presented again. The host treated both as a repaint of the viewport, so each scroll frame
re-rasterized all of it. `EmptyChromeClient::scroll` is no longer `final`, so the host can implement it, and
`GraphicsLayerTextureMapper::scrollBackingStore` moves a one-tile layer's pixels by the scroll on the GPU
(`BitmapTexture::shiftContents`, two `glCopyTexSubImage2D` through a scratch texture). It returns false, and the host
repaints the layer, when the move is not a whole number of backing store pixels, a full repaint is pending, or the
store has several tiles.

`GraphicsLayerTextureMapper` kept a single rectangle to repaint and united every invalidation into it, so the strip a
scroll exposes at the bottom and a fixed element at the top repainted all the viewport between them. It keeps up to
eight rectangles now, merged past that.

## 0076-texture-mapper-gpu-paint-batch

0074 flushed, fenced and waited for every tile it painted on the GPU. Paints now only record their GL work in Skia's
context, and `setPaintsLayersOnGPU(false)`, which the host calls when a composite's layers have painted, submits them
and makes the compositing context wait once.

## 0077-adwaita-empty-scroll-corner

`ScrollView::paintScrollbars` paints the scroll corner whatever its rectangle, which is empty without both scrollbars,
and `ScrollbarThemeAdwaita::paintScrollCorner` drew its 1px border at the empty rectangle's origin: a grey pixel at the
top left of every scrollable page, which moved away with the content once scrolling moved pixels.

## 0078-viewport-constrained-movement-layout

A scroll moves the layout viewport (`LocalFrameView::setBaseLayoutViewportOrigin`), which marked every fixed and
sticky box as needing layout. `setNeedsLayout` also marks the box's layer for a full repaint, so after the layout
`RenderElement::repaintAfterLayoutIfNeeded` repainted a composited `position: fixed` layer whole on every scroll frame,
although only its position had changed. Fixed boxes now get an out-of-flow movement layout
(`setNeedsOutOfFlowMovementLayout`), whose repaint status `RenderLayer::shouldRepaintAfterLayout` skips for a
composited layer, and their layers a compositing geometry update. Sticky boxes keep the full layout. Safari never
reaches this path for a scroll, since it scrolls asynchronously.

## 0080-layout-boundary-simplified-ancestors

A layout boundary (an SVG root, a text control, a box with layout and size containment, a clipped box of fixed size)
lays out by itself as a subtree, because nothing in it can change the layout around it. When a second box needs
layout in the same frame, WebKit turns the subtree layout into one from the top
(`LocalFrameViewLayoutContext::scheduleSubtreeLayout`, `convertSubtreeLayoutToFullLayout`) and marked the boundary's
ancestors as having a child to lay out. A grid ancestor then ran its track sizing again, which lays a stretched item
out twice, at its content height and at its row's, and `RenderElement::repaintAfterLayoutIfNeeded` repainted the
item for the height that came and went.

A chart tooltip is the common case: the pointer moves an SVG shape (`cx`, `x1` are layout changes inside the SVG
root) and an absolutely positioned tooltip over it, and every frame repainted the whole grid card around the chart
(1068 by 619 px for a 2 px crosshair, a 14 px point and a 190 px tooltip in the Motion example).

`RenderObject::markContainingBlocksForLayout` now marks the ancestors of a boundary that joins a wider layout for a
simplified layout, the marking a positioned descendant already uses above its containing block: they reach the
boundary, lay it out and recompute their overflow, and do no layout of their own. An ancestor whose overflow can
change its layout (`overflowChangesMayAffectLayout`) still gets a normal layout, as before. A boundary that needs
layout itself marks its ancestors from `setNeedsLayout` as it always did. `tests/abi/boundary_repaint.py` holds the
invalidated area and compares the partial repaints with a full one.

## 0081-texture-mapper-merge-near-repaints

0075 keeps up to eight rectangles to repaint, and each is a paint pass of its own: a walk of the layer tree and, on
the GPU, a Skia surface, a context switch and a flush. The seven rectangles of the tooltip case above (28,000 px
together) took longer to paint than the whole card had. Two rectangles now merge when their union adds at most
256 by 256 px to their areas, so nearby damage paints in one pass and the far-apart rectangles 0075 was written for
stay separate.

## 0082-texture-mapper-angle-d3d11-paint-order

0076 makes the compositing context wait once for the layers Skia painted in its own context. Where the display has
no fence support, which is the case under ANGLE on Windows, `SkiaUtilities::flushAndSubmitWithFence` falls back to
`GrDirectContext::submit(GrSyncCpu::kYes)`, a `glFinish`: every frame that painted a layer blocked until the GPU
had finished all of its work. Each GPU paint also began with a `glFlush` of the compositing context.

ANGLE's D3D11 renderer issues the calls of every context of a display on one immediate device context, in the
order they are made, so the compositor already reads what Skia drew. On Windows the paints are now submitted
without the wait and without the flush before each one. Other platforms keep the fence.

## Working on the series

```
python -I scripts/patches.py apply  --source <webkit>             # reset the series' files to the pin, apply all
python -I scripts/patches.py check  <commit> --source <webkit>    # dry-run the series against another commit
python -I scripts/patches.py export <name> <path>... --source <webkit>
```

`export` diffs the given paths against the pin with the earlier patches of the series applied, and
writes `patches/<name>.patch`; add a new name to `series` first. `.gitattributes` keeps the patches' line
endings LF, which `git apply` requires. `docs/UPDATING.md` covers moving to a new WebKit commit.
