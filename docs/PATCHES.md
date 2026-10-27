# The patch series

`patches/series` lists eleven patches, applied in order over the WebKit commit in `pins.json` by
`scripts/patches.py apply`. Each patch carries one concern and, except 0000 and 0010, changes nothing unless
its CMake option is ON. Every option defaults to OFF, so the lean flavor, which sets none of them, compiles
WebKit's own sources. 0010 changes which symbols WebCore exports and which members the host may override,
and no behavior.

The patches add new files (under a `stub/` directory next to the code they stand in for) and CMake hunks.
They edit upstream C++ in two places: 0003 changes `CryptoDigestWin.cpp`, `CryptoKeyEC.h` and
`CryptoKeyRSA.h`, and 0010 changes `EmptyClients.h`, `ChromeClient.h`, `WebAnimation.h`, `CSSTransition.h`, `Element.h` and
`Document.h`, and exports from `ResizeObserver.h` and `IntersectionObserver.h`. It also changes `PlatformCocoa.cmake`. The patches touch 62 files in all.

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
- `ClipboardEvent.h` and `StaticPasteboard.h` export their classes, and `DataTransfer.h` exports
  `createForCopyAndPaste`, `types`, `getData` and `setData`. With them the host fires `copy`, `cut` and
  `paste` with a `clipboardData` the page can read and set.
- `Headers.cmake` forwards these headers:
  - `dom/InputEvent.h`, `dom/ShadowRootInit.h` and `dom/ClipboardEvent.h`;
  - `platform/StaticPasteboard.h`;
  - `page/ScrollToOptions.h`;
  - the resize and intersection observer headers under `page/`, with their callbacks, entries and options;
  - `animation/CSSTransition.h`, `animation/GetAnimationsOptions.h` and `animation/BlendingKeyframes.h`;
  - `style/StyleExtractor.h` and `style/StyleExtractorState.h`, which `CSSComputedStyleDeclaration.h`
    includes.
- `PlatformCocoa.cmake` keeps `css/CSSComputedStyleDeclaration.h` and `animation/KeyframeEffect.h` among the
  forwarded headers. On macOS it removes both by default.

## Working on the series

```
python -I scripts/patches.py apply  --source <webkit>             # reset the series' files to the pin, apply all
python -I scripts/patches.py check  <commit> --source <webkit>    # dry-run the series against another commit
python -I scripts/patches.py export <name> <path>... --source <webkit>
```

`export` diffs the given paths against the pin with the earlier patches of the series applied, and
writes `patches/<name>.patch`; add a new name to `series` first. `.gitattributes` keeps the patches' line
endings LF, which `git apply` requires. `docs/UPDATING.md` covers moving to a new WebKit commit.
