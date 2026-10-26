#include "config.h"
#include "RanvierWebCoreAbi.h"
#include <JavaScriptCore/DisallowVMEntry.h>
#include <JavaScriptCore/InitializeThreading.h>
#include <WebCore/Document.h>
#include <WebCore/DocumentView.h>
#include <WebCore/AbortSignal.h>
#include <WebCore/AddEventListenerOptions.h>
#include <WebCore/CharacterData.h>
#include <WebCore/Comment.h>
#include <WebCore/DOMException.h>
#include <WebCore/DocumentFragment.h>
#include <WebCore/Element.h>
#include <WebCore/ElementInlines.h>
#include <WebCore/ElementTraversal.h>
#include <WebCore/FocusOptions.h>
#include <WebCore/Event.h>
#include <WebCore/EventInterfaces.h>
#include <WebCore/EventListener.h>
#include <WebCore/HTMLBodyElement.h>
#include <WebCore/HTMLHeadElement.h>
#include <WebCore/HTMLInputElement.h>
#include <WebCore/HTMLOptionElement.h>
#include <WebCore/HTMLSelectElement.h>
#include <WebCore/HTMLTextAreaElement.h>
#include <WebCore/ImageBuffer.h>
#include <WebCore/ImportNodeOptions.h>
#include <WebCore/KeyboardEvent.h>
#include <WebCore/LocalFrame.h>
#include <WebCore/LocalFrameView.h>
#include <JavaScriptCore/JSLock.h>
#include <WebCore/CommonVM.h>
#include <WebCore/GarbageCollectionController.h>
#include <WebCore/MemoryRelease.h>
#include <WebCore/ScriptWrappableInlines.h>
#include <WebCore/NodeDocument.h>
#include <WebCore/NodeInlines.h>
#include <WebCore/NodeList.h>
#include <WebCore/Page.h>
#include <WebCore/PixelBuffer.h>
#include <WebCore/Range.h>
#include <WebCore/Settings.h>
#include <WebCore/Text.h>
#include <WebCore/TrustedHTML.h>
#include <WebCore/DocumentLoader.h>
#include <WebCore/DocumentPage.h>
#include <WebCore/DocumentWriter.h>
#include <WebCore/EmptyClients.h>
#include <WebCore/FrameLoader.h>
#include <WebCore/LocalFrameInlines.h>
#include <WebCore/PageConfiguration.h>
#include <WebCore/ProcessWarming.h>
#include <WebCore/BlobRegistry.h>
#include <WebCore/CachedResource.h>
#include <WebCore/HTTPHeaderNames.h>
#include <WebCore/HTTPParsers.h>
#include <WebCore/HTTPStatusCodes.h>
#include <WebCore/LoaderStrategy.h>
#include <WebCore/MediaStrategy.h>
#include <WebCore/NetworkLoadMetrics.h>
#include <WebCore/PasteboardItemInfo.h>
#include <WebCore/PasteboardStrategy.h>
#include <WebCore/PlatformStrategies.h>
#include <WebCore/ResourceError.h>
#include <WebCore/ResourceLoaderTypes.h>
#include <WebCore/SharedBuffer.h>
#include <WebCore/SubresourceLoader.h>
#include <mutex>
#include <pal/SessionID.h>
#include <cstring>
#include <optional>
#include <utility>
#include <wtf/MainThread.h>
#include <wtf/ProcessID.h>
#include <wtf/RunLoop.h>
#include <wtf/text/MakeString.h>

#if PLATFORM(GTK) || PLATFORM(WPE)
#include <WebCore/PlatformDisplaySurfaceless.h>
#endif

using namespace WebCore;

// createPage and loadHTML follow WebCore's testing/TestPage.cpp (Copyright (C) 2026 Apple Inc., BSD-2-Clause).
static Ref<Page> createPage(IntSize viewportSize)
{
    static bool prewarmed = [] {
        ProcessWarming::prewarmGlobally();
        return true;
    }();
    UNUSED_VARIABLE(prewarmed);
    Ref page = Page::create(pageConfigurationWithEmptyClients(std::nullopt, PAL::SessionID::defaultSessionID()));
    page->settings().setScriptEnabled(false);
    page->settings().setAcceleratedCompositingEnabled(false);
    page->settings().setLoadsImagesAutomatically(true);
#if ENABLE(VIDEO)
    page->settings().setMediaEnabled(false);
#endif
    RefPtr frame = page->localMainFrame();
    RELEASE_ASSERT(frame);
    frame->setView(LocalFrameView::create(*frame, viewportSize));
    frame->init();
    return page;
}

static void loadHTML(LocalFrame& frame, const String& html)
{
    RefPtr activeDocumentLoader = frame.loader().activeDocumentLoader();
    ASSERT(activeDocumentLoader);
    auto& writer = activeDocumentLoader->writer();
    writer.setMIMEType("text/html"_s);
    writer.begin();
    writer.insertDataSynchronously(html);
    writer.end();
    if (RefPtr document = frame.document())
        document->updateLayoutIgnorePendingStylesheets();
}

struct RvHost {
    Ref<Page> page;
    IntSize size;
    std::optional<JSC::DisallowVMEntry> noScript;
    RvResourceHandler resourceHandler { nullptr };
    void* resourceContext { nullptr };

    Document& document() { return *page->localTopDocument(); }
    LocalFrame& frame() { return *page->localMainFrame(); }
};

static bool onOwningThread() { return isMainThread(); }

// The hosts alive on the owning thread, for routing a page's loads to its host.
static Vector<RvHost*> liveHosts;

static RvHost* hostForPage(const Page* page)
{
    for (auto* host : liveHosts) {
        if (host->page.ptr() == page)
            return host;
    }
    return nullptr;
}

// A load handed to the host. loader is null once WebCore removes the loader: on completion,
// cancellation or teardown of its document.
struct RvResourceLoad {
    RefPtr<SubresourceLoader> loader;
    bool inHandler { false };
};

static HashMap<const ResourceLoader*, RvResourceLoad*>& pendingLoads()
{
    static NeverDestroyed<HashMap<const ResourceLoader*, RvResourceLoad*>> loads;
    return loads;
}

static ResourceError hostLoadError(const URL& url, const String& description, ResourceError::Type type = ResourceError::Type::General)
{
    return ResourceError(errorDomainWebKitInternal, 0, url, description, type);
}

// Calls the loader through ResourceLoader's vtable: WebCore exports none of SubresourceLoader's overrides.
static void deliver(Ref<SubresourceLoader>&& subresourceLoader, RefPtr<SharedBuffer>&& data, const String& contentType)
{
    Ref<ResourceLoader> loader = WTF::move(subresourceLoader);
    if (loader->reachedTerminalState())
        return;
    URL url = loader->request().url();
    if (!data) {
        loader->didFail(hostLoadError(url, "The host failed the load"_s));
        return;
    }
    ResourceResponse response(WTF::move(url), extractMIMETypeFromMediaType(contentType), static_cast<long long>(data->size()), extractCharsetFromMediaType(contentType).toString());
    response.setHTTPStatusCode(httpStatus200OK);
    if (!contentType.isEmpty())
        response.setHTTPHeaderField(HTTPHeaderName::ContentType, contentType);
    response.setHTTPHeaderField(HTTPHeaderName::AccessControlAllowOrigin, "*"_s);
    loader->didReceiveResponse(WTF::move(response), [loader, data = data.releaseNonNull()] {
        if (loader->reachedTerminalState())
            return;
        loader->didReceiveBuffer(data, static_cast<long long>(data->size()), DataPayloadType::DataPayloadWholeResource);
        if (!loader->reachedTerminalState())
            loader->didFinishLoading(NetworkLoadMetrics { });
    });
}

// Frees the load, then delivers data, or a failure for null data, to its loader if WebCore still has it.
static int32_t complete(RvResourceLoad* load, RefPtr<SharedBuffer>&& data, String&& contentType)
{
    if (!load)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr loader = std::exchange(load->loader, nullptr);
    bool inHandler = load->inHandler;
    delete load;
    if (!loader)
        return RV_OK;
    pendingLoads().remove(loader.get());
    if (inHandler)
        deliver(loader.releaseNonNull(), WTF::move(data), contentType);
    else {
        RunLoop::mainSingleton().dispatch([loader = loader.releaseNonNull(), data = WTF::move(data), contentType = WTF::move(contentType)] mutable {
            deliver(WTF::move(loader), WTF::move(data), contentType);
        });
    }
    return RV_OK;
}

// Hands each load to its host's resource handler on a later run loop cycle; data: URLs load in WebCore.
class RvLoaderStrategy final : public LoaderStrategy {
public:
    void loadResource(LocalFrame& frame, CachedResource& resource, ResourceRequest&& request, const ResourceLoaderOptions& options, CompletionHandler<void(RefPtr<SubresourceLoader>&&)>&& completionHandler) final
    {
        SubresourceLoader::create(frame, resource, WTF::move(request), options, [completionHandler = WTF::move(completionHandler)](RefPtr<SubresourceLoader>&& loader) mutable {
            if (loader)
                schedule(*loader);
            completionHandler(WTF::move(loader));
        });
    }

    void loadResourceSynchronously(FrameLoader&, ResourceLoaderIdentifier, const ResourceRequest& request, ClientCredentialPolicy, const FetchOptions&, const HTTPHeaderMap&, ResourceError& error, ResourceResponse&, Vector<uint8_t>&) final
    {
        error = hostLoadError(request.url(), "Synchronous loads are unsupported"_s);
    }

    void remove(ResourceLoader* loader) final
    {
        if (auto* load = pendingLoads().take(loader))
            load->loader = nullptr;
    }

    void pageLoadCompleted(Page&) final { }
    void browsingContextRemoved(LocalFrame&) final { }
    void setDefersLoading(ResourceLoader&, bool) final { }
    void crossOriginRedirectReceived(ResourceLoader*, const URL&) final { }
    void servePendingRequests(ResourceLoadPriority) final { }
    void suspendPendingRequests() final { }
    void resumePendingRequests() final { }
    void startPingLoad(LocalFrame&, ResourceRequest& request, const HTTPHeaderMap&, const FetchOptions&, ContentSecurityPolicyImposition, PingLoadCompletionHandler&& completionHandler) final
    {
        if (completionHandler)
            completionHandler(hostLoadError(request.url(), "Ping loads are unsupported"_s), { });
    }
    void preconnectTo(FrameLoader&, ResourceRequest&& request, StoredCredentialsPolicy, ShouldPreconnectAsFirstParty, PreconnectCompletionHandler&& completionHandler) final
    {
        if (completionHandler)
            completionHandler(hostLoadError(request.url(), "Preconnection is unsupported"_s));
    }
    void setCaptureExtraNetworkLoadMetricsEnabled(bool) final { }
    bool isOnLine() const final { return true; }
    void addOnlineStateChangeListener(Function<void(bool)>&&) final { }
    void isResourceLoadFinished(CachedResource&, CompletionHandler<void(bool)>&& callback) final { callback(true); }

    ResourceError cancelledError(const ResourceRequest& request) const final { return hostLoadError(request.url(), "Cancelled"_s, ResourceError::Type::Cancellation); }
    ResourceError blockedError(const ResourceRequest& request) const final { return hostLoadError(request.url(), "Blocked"_s, ResourceError::Type::AccessControl); }
    bool isBlockedError(const ResourceError& error) const final { return error.type() == ResourceError::Type::AccessControl; }
    ResourceError blockedByContentBlockerError(const ResourceRequest& request) const final { return blockedError(request); }
    ResourceError cannotShowURLError(const ResourceRequest& request) const final { return hostLoadError(request.url(), "Cannot show URL"_s); }
    ResourceError interruptedForPolicyChangeError(const ResourceRequest& request) const final { return hostLoadError(request.url(), "Interrupted for policy change"_s); }
#if ENABLE(CONTENT_FILTERING)
    ResourceError blockedByContentFilterError(const ResourceRequest& request) const final { return blockedError(request); }
#endif
    ResourceError cannotShowMIMETypeError(const ResourceResponse& response) const final { return hostLoadError(response.url(), "Cannot show content with the MIME type"_s); }
    ResourceError fileDoesNotExistError(const ResourceResponse& response) const final { return hostLoadError(response.url(), "File does not exist"_s); }
    ResourceError httpsUpgradeRedirectLoopError(const ResourceRequest& request) const final { return hostLoadError(request.url(), "HTTPS upgrade redirect loop"_s); }
    ResourceError httpNavigationWithHTTPSOnlyError(const ResourceRequest& request) const final { return hostLoadError(request.url(), "HTTP navigation with HTTPS-only"_s); }
    bool isHttpNavigationWithHTTPSOnlyError(const ResourceError&) const final { return false; }
    ResourceError pluginWillHandleLoadError(const ResourceResponse& response) const final { return hostLoadError(response.url(), "Plug-in will handle load"_s); }

private:
    static void schedule(SubresourceLoader& loader)
    {
        if (loader.request().url().protocolIsData()) {
            loader.start();
            return;
        }
        auto* load = new RvResourceLoad { &loader };
        pendingLoads().set(&loader, load);
        RunLoop::mainSingleton().dispatch([load] {
            RefPtr loader = load->loader;
            if (!loader) {
                delete load;
                return;
            }
            RefPtr frame = loader->frame();
            auto* host = frame ? hostForPage(frame->page()) : nullptr;
            if (!host || !host->resourceHandler) {
                complete(load, nullptr, { });
                return;
            }
            load->inHandler = true;
            host->resourceHandler(host->resourceContext, load, loader->request().url().string().utf8().data());
            // load is freed when the host completed it inside the handler.
            if (pendingLoads().get(loader.get()) == load)
                load->inHandler = false;
        });
    }
};

// The pasteboard, blob registry and media strategies follow TestWebKitAPI's
// Tests/WebCore/TestPlatformStrategies.cpp (Copyright (C) 2026 Apple Inc., BSD-2-Clause): stubs that
// a document without scripts, media and editing commands leaves uncalled.
class RvPasteboardStrategy final : public PasteboardStrategy {
public:
#if PLATFORM(IOS_FAMILY)
    void writeToPasteboard(const PasteboardURL&, const String&, const PasteboardContext*) final { }
    void writeToPasteboard(const PasteboardWebContent&, const String&, const PasteboardContext*) final { }
    void writeToPasteboard(const PasteboardImage&, const String&, const PasteboardContext*) final { }
    void writeToPasteboard(const String&, const String&, const String&, const PasteboardContext*) final { }
    void updateSupportedTypeIdentifiers(const Vector<String>&, const String&, const PasteboardContext*) final { }
#endif
#if PLATFORM(COCOA)
    void getTypes(Vector<String>&, const String&, const PasteboardContext*) final { }
    RefPtr<SharedBuffer> bufferForType(const String&, const String&, const PasteboardContext*) final { return nullptr; }
    void getPathnamesForType(Vector<String>&, const String&, const String&, const PasteboardContext*) final { }
    String stringForType(const String&, const String&, const PasteboardContext*) final { return { }; }
    Vector<String> allStringsForType(const String&, const String&, const PasteboardContext*) final { return { }; }
    int64_t changeCount(const String&, const PasteboardContext*) final { return 0; }
    Color color(const String&, const PasteboardContext*) final { return { }; }
    URL url(const String&, const PasteboardContext*) final { return { }; }
    int getNumberOfFiles(const String&, const PasteboardContext*) final { return 0; }
    int64_t addTypes(const Vector<String>&, const String&, const PasteboardContext*) final { return 0; }
    int64_t setTypes(const Vector<String>&, const String&, const PasteboardContext*) final { return 0; }
    int64_t setBufferForType(SharedBuffer*, const String&, const String&, const PasteboardContext*) final { return 0; }
    int64_t setURL(const PasteboardURL&, const String&, const PasteboardContext*) final { return 0; }
    int64_t setColor(const Color&, const String&, const PasteboardContext*) final { return 0; }
    int64_t setStringForType(const String&, const String&, const String&, const PasteboardContext*) final { return 0; }
    int64_t writeWebArchive(LegacyWebArchive&, const String&) final { return 0; }
    bool containsURLStringSuitableForLoading(const String&, const PasteboardContext*) final { return false; }
    String urlStringSuitableForLoading(const String&, String&, const PasteboardContext*) final { return { }; }
#endif
    String readStringFromPasteboard(size_t, const String&, const String&, const PasteboardContext*) final { return { }; }
    RefPtr<SharedBuffer> readBufferFromPasteboard(std::optional<size_t>, const String&, const String&, const PasteboardContext*) final { return nullptr; }
    URL readURLFromPasteboard(size_t, const String&, String&, const PasteboardContext*) final { return { }; }
    std::optional<PasteboardItemInfo> informationForItemAtIndex(size_t, const String&, int64_t, const PasteboardContext*) final { return std::nullopt; }
    std::optional<Vector<PasteboardItemInfo>> allPasteboardItemInfo(const String&, int64_t, const PasteboardContext*) final { return std::nullopt; }
    int getPasteboardItemsCount(const String&, const PasteboardContext*) final { return 0; }
    Vector<String> typesSafeForDOMToReadAndWrite(const String&, const String&, const PasteboardContext*) final { return { }; }
    int64_t writeCustomData(const Vector<PasteboardCustomData>&, const String&, const PasteboardContext*) final { return 0; }
    bool containsStringSafeForDOMToReadForType(const String&, const String&, const PasteboardContext*) final { return false; }
#if PLATFORM(GTK) || PLATFORM(WPE)
    Vector<String> types(const String&) final { return { }; }
    String readTextFromClipboard(const String&, const String&) final { return { }; }
    Vector<String> readFilePathsFromClipboard(const String&) final { return { }; }
    RefPtr<SharedBuffer> readBufferFromClipboard(const String&, const String&) final { return nullptr; }
    void writeToClipboard(const String&, SelectionData&&) final { }
    void clearClipboard(const String&) final { }
    int64_t changeCount(const String&) final { return 0; }
#elif USE(LIBWPE)
    void getTypes(Vector<String>&) final { }
    void writeToPasteboard(const PasteboardWebContent&) final { }
    void writeToPasteboard(const String&, const String&) final { }
#endif
};

class RvBlobRegistry final : public BlobRegistry {
public:
    void registerInternalFileBlobURL(const URL&, Ref<BlobDataFileReference>&&, const String&, const String&) final { }
    void registerInternalBlobURL(const URL&, Vector<BlobPart>&&, const String&) final { }
    void registerBlobURL(const URL&, const URL&, const PolicyContainer&, const std::optional<SecurityOriginData>&) final { }
    void registerInternalBlobURLOptionallyFileBacked(const URL&, const URL&, RefPtr<BlobDataFileReference>&&, const String&) final { }
    void registerInternalBlobURLForSlice(const URL&, const URL&, long long, long long, const String&) final { }
    void unregisterBlobURL(const URL&, const std::optional<SecurityOriginData>&) final { }
    void registerBlobURLHandle(const URL&, const std::optional<SecurityOriginData>&) final { }
    void unregisterBlobURLHandle(const URL&, const std::optional<SecurityOriginData>&) final { }
    String blobType(const URL&) final { return emptyString(); }
    unsigned long long blobSize(const URL&) final { return 0; }
    void writeBlobsToTemporaryFilesForIndexedDB(const Vector<String>&, CompletionHandler<void(Vector<String>&&)>&&) final { }
};

class RvMediaStrategy final : public MediaStrategy {
public:
#if ENABLE(WEB_AUDIO)
    Ref<AudioDestination> createAudioDestination(const AudioDestinationCreationOptions&) final { RELEASE_ASSERT_NOT_REACHED(); }
#endif
};

class RvPlatformStrategies final : public PlatformStrategies {
private:
    LoaderStrategy* createLoaderStrategy() final { return new RvLoaderStrategy; }
    PasteboardStrategy* createPasteboardStrategy() final { return new RvPasteboardStrategy; }
    MediaStrategy* createMediaStrategy() final { return new RvMediaStrategy; }
    BlobRegistry* createBlobRegistry() final { return new RvBlobRegistry; }
#if ENABLE(DECLARATIVE_WEB_PUSH)
    PushStrategy* createPushStrategy() final { return nullptr; }
#endif
};

// Listener failures counted during the innermost dispatching ABI call.
static int failedListeners;

class RvEventListener final : public EventListener {
public:
    static Ref<RvEventListener> create(RvEventCallback callback, void* context)
    {
        return adoptRef(*new RvEventListener(callback, context));
    }

    void detach() { m_callback = nullptr; }

private:
    RvEventListener(RvEventCallback callback, void* context)
        : EventListener(CPPEventListenerType)
        , m_callback(callback)
        , m_context(context)
    {
    }

    void handleEvent(ScriptExecutionContext&, Event& event) final
    {
        if (m_callback && m_callback(m_context, reinterpret_cast<RvEvent*>(&event)))
            ++failedListeners;
    }

    RvEventCallback m_callback;
    void* m_context;
};

struct RvWatch {
    WeakPtr<Node, WeakPtrImplWithEventTargetData> node;
};

struct RvListener {
    Ref<RvEventListener> listener;
    Ref<Node> target;
    AtomString type;
    bool capture;
};

static Node* node(RvNode* handle) { return reinterpret_cast<Node*>(handle); }

static Event* event(RvEvent* handle) { return reinterpret_cast<Event*>(handle); }

template<typename Dispatch>
static int32_t dispatchCountingFailures(Dispatch&& dispatch)
{
    auto outer = std::exchange(failedListeners, 0);
    dispatch();
    auto failed = std::exchange(failedListeners, outer);
    return failed ? RV_ERR_LISTENER_FAILED : RV_OK;
}

static RvNode* handle(Ref<Node>&& node) { return reinterpret_cast<RvNode*>(&node.leakRef()); }

static String utf8(const char* text) { return String::fromUTF8(text); }

static RvNode* handleOrNull(Node* node) { return node ? handle(Ref { *node }) : nullptr; }

static RvEvent* eventHandle(Ref<Event>&& event) { return reinterpret_cast<RvEvent*>(&event.leakRef()); }

static int32_t copyString(const String& value, char* buffer, int32_t capacity, int32_t* length)
{
    if (!length)
        return RV_ERR_NULL_ARGUMENT;
    if (value.isNull()) {
        *length = -1;
        return RV_OK;
    }
    auto bytes = value.utf8();
    *length = static_cast<int32_t>(bytes.length());
    if (!buffer || capacity < *length)
        return RV_ERR_BUFFER_TOO_SMALL;
    std::memcpy(buffer, bytes.data(), bytes.length());
    return RV_OK;
}

// The exception of the latest call that returned RV_ERR_DOM_EXCEPTION, on the owning thread.
static std::optional<ExceptionCode> lastExceptionCode;
static String lastExceptionMessage;

static int32_t fail(const Exception& exception)
{
    lastExceptionCode = exception.code();
    lastExceptionMessage = exception.message();
    return RV_ERR_DOM_EXCEPTION;
}

template<typename T> static int32_t status(const ExceptionOr<T>& result) { return result.hasException() ? fail(result.exception()) : RV_OK; }

int32_t rv_abi_version(void) { return 11; }

int64_t rv_process_id(void) { return static_cast<int64_t>(getCurrentProcessID()); }

RvHost* rv_host_create(int32_t width, int32_t height)
{
    static bool initialized;
    if (!initialized) {
        JSC::initialize();
        WTF::initializeMainThread();
        setPlatformStrategies(new RvPlatformStrategies);
#if PLATFORM(GTK) || PLATFORM(WPE)
        if (!PlatformDisplay::sharedDisplayIfExists())
            PlatformDisplay::setSharedDisplay(PlatformDisplaySurfaceless::create());
#endif
        initialized = true;
    }
    if (!onOwningThread() || width <= 0 || height <= 0)
        return nullptr;
    auto* host = new RvHost { createPage({ width, height }), { width, height }, std::nullopt };
    host->noScript.emplace(host->document().vm());
    liveHosts.append(host);
    return host;
}

void rv_host_destroy(RvHost* host)
{
    if (!host || !onOwningThread())
        return;
    host->noScript.reset();
    liveHosts.removeFirst(host);
    delete host;
}

int32_t rv_host_load_html(RvHost* host, const char* html)
{
    if (!host || !html)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    loadHTML(host->frame(), utf8(html));
    return RV_OK;
}

int32_t rv_host_scripts_enabled(RvHost* host)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return host->page->settings().isScriptEnabled() ? 1 : 0;
}

int32_t rv_host_vm_entry_disallowed(RvHost* host)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return host->document().vm().disallowVMEntryCount ? 1 : 0;
}

RvNode* rv_document_body(RvHost* host)
{
    if (!host || !onOwningThread())
        return nullptr;
    RefPtr body = host->document().body();
    return body ? handle(body.releaseNonNull()) : nullptr;
}

RvNode* rv_document_active_element(RvHost* host)
{
    if (!host || !onOwningThread())
        return nullptr;
    RefPtr element = host->document().activeElement();
    return element ? handle(element.releaseNonNull()) : nullptr;
}

RvNode* rv_document_head(RvHost* host)
{
    if (!host || !onOwningThread())
        return nullptr;
    RefPtr head = host->document().head();
    return head ? handle(head.releaseNonNull()) : nullptr;
}

RvNode* rv_document_get_element_by_id(RvHost* host, const char* elementId)
{
    if (!host || !elementId || !onOwningThread())
        return nullptr;
    RefPtr element = host->document().getElementById(utf8(elementId));
    return element ? handle(element.releaseNonNull()) : nullptr;
}

RvNode* rv_document_create_element(RvHost* host, const char* tagName)
{
    if (!host || !tagName || !onOwningThread())
        return nullptr;
    auto element = host->document().createElementForBindings(AtomString::fromUTF8(tagName));
    if (element.hasException())
        return nullptr;
    return handle(element.releaseReturnValue());
}

RvNode* rv_document_create_text(RvHost* host, const char* data)
{
    if (!host || !data || !onOwningThread())
        return nullptr;
    return handle(host->document().createTextNode(utf8(data)));
}

int32_t rv_node_append_child(RvNode* parent, RvNode* child)
{
    if (!parent || !child)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return status(node(parent)->appendChild(*node(child)));
}

int32_t rv_node_set_text_content(RvNode* target, const char* text)
{
    if (!target || !text)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return status(node(target)->setTextContent(utf8(text)));
}

int32_t rv_element_set_attribute(RvNode* target, const char* name, const char* value)
{
    if (!target || !name || !value)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = dynamicDowncast<Element>(*node(target));
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    auto result = element->setAttribute(AtomString::fromUTF8(name), AtomString::fromUTF8(value));
    return status(result);
}

void rv_node_release(RvNode* target)
{
    if (target && onOwningThread())
        node(target)->deref();
}

int32_t rv_host_paint_rgba(RvHost* host, uint8_t* rgba, int32_t length)
{
    if (!host || !rgba)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto size = host->size;
    size_t required = static_cast<size_t>(size.width()) * size.height() * 4;
    if (length < 0 || static_cast<size_t>(length) < required)
        return RV_ERR_BUFFER_TOO_SMALL;
    host->document().updateLayoutIgnorePendingStylesheets();
    RefPtr view = host->frame().view();
    if (!view)
        return RV_ERR_PAINT_FAILED;
    view->updateLayoutAndStyleIfNeededRecursive();
    auto buffer = ImageBuffer::create(FloatSize { size }, RenderingMode::Unaccelerated,
        RenderingPurpose::Unspecified, 1.0f, DestinationColorSpace::SRGB(), PixelFormat::BGRA8);
    if (!buffer)
        return RV_ERR_PAINT_FAILED;
    view->paintContents(buffer->context(), IntRect { { }, size });
    buffer->flushDrawingContext();
    PixelBufferFormat format { AlphaPremultiplication::Unpremultiplied, PixelFormat::RGBA8, DestinationColorSpace::SRGB() };
    auto pixels = buffer->getPixelBuffer(format, IntRect { { }, size });
    if (!pixels || pixels->bytes().size() != required)
        return RV_ERR_PAINT_FAILED;
    std::memcpy(rgba, pixels->bytes().data(), required);
    return RV_OK;
}

RvListener* rv_node_add_event_listener(RvNode* target, const char* type, int32_t capture,
    RvEventCallback callback, void* context)
{
    if (!target || !type || !callback || !onOwningThread())
        return nullptr;
    auto* listener = new RvListener { RvEventListener::create(callback, context), *node(target),
        AtomString::fromUTF8(type), !!capture };
    AddEventListenerOptions options;
    options.capture = listener->capture;
    listener->target->addEventListener(listener->type, listener->listener.copyRef(), options);
    return listener;
}

int32_t rv_listener_remove(RvListener* listener)
{
    if (!listener)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    listener->target->removeEventListener(listener->type, listener->listener.get(), EventListenerOptions { listener->capture });
    listener->listener->detach();
    delete listener;
    return RV_OK;
}

int32_t rv_node_dispatch_event(RvNode* target, const char* type, int32_t bubbles, int32_t cancelable,
    int32_t* defaultPrevented)
{
    if (!target || !type)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    Ref protectedTarget = *node(target);
    Ref dispatched = Event::create(AtomString::fromUTF8(type), bubbles ? Event::CanBubble::Yes : Event::CanBubble::No,
        cancelable ? Event::IsCancelable::Yes : Event::IsCancelable::No);
    auto status = dispatchCountingFailures([&] { protectedTarget->dispatchEvent(dispatched); });
    if (defaultPrevented)
        *defaultPrevented = dispatched->defaultPrevented() ? 1 : 0;
    return status;
}

int32_t rv_element_click(RvNode* target)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = dynamicDowncast<HTMLElement>(*node(target));
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    return dispatchCountingFailures([&] { element->click(); });
}

int32_t rv_input_checked(RvNode* target)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr input = dynamicDowncast<HTMLInputElement>(*node(target));
    if (!input)
        return RV_ERR_NOT_INPUT;
    return input->checked() ? 1 : 0;
}

int32_t rv_event_phase(RvEvent* handle)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return event(handle)->eventPhase();
}

int32_t rv_event_default_prevented(RvEvent* handle)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return event(handle)->defaultPrevented() ? 1 : 0;
}

void rv_event_prevent_default(RvEvent* handle)
{
    if (handle && onOwningThread())
        event(handle)->preventDefault();
}

void rv_event_stop_propagation(RvEvent* handle)
{
    if (handle && onOwningThread())
        event(handle)->stopPropagation();
}

RvNode* rv_host_document(RvHost* host)
{
    if (!host || !onOwningThread())
        return nullptr;
    return handleOrNull(&host->document());
}

RvNode* rv_document_create_comment(RvHost* host, const char* data)
{
    if (!host || !data || !onOwningThread())
        return nullptr;
    return handle(host->document().createComment(utf8(data)));
}

RvNode* rv_document_create_fragment(RvHost* host)
{
    if (!host || !onOwningThread())
        return nullptr;
    return handle(host->document().createDocumentFragment());
}

RvNode* rv_document_import_node(RvHost* host, RvNode* source, int32_t deep)
{
    if (!host || !source || !onOwningThread())
        return nullptr;
    auto imported = host->document().importNode(*node(source), Variant<bool, ImportNodeOptions> { !!deep });
    return imported.hasException() ? nullptr : handle(imported.releaseReturnValue());
}

RvNode* rv_node_parse_fragment(RvNode* context, const char* markup)
{
    if (!context || !markup || !onOwningThread())
        return nullptr;
    Ref range = Range::create(node(context)->document());
    if (range->selectNodeContents(*node(context)).hasException())
        return nullptr;
    auto fragment = range->createContextualFragment(Variant<Ref<TrustedHTML>, String> { utf8(markup) });
    return fragment.hasException() ? nullptr : handle(fragment.releaseReturnValue());
}

int32_t rv_node_type(RvNode* target)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return static_cast<int32_t>(node(target)->nodeType());
}

RvNode* rv_node_relative(RvNode* target, int32_t relation)
{
    if (!target || !onOwningThread())
        return nullptr;
    auto& subject = *node(target);
    switch (relation) {
    case RV_RELATION_PARENT:
        return handleOrNull(subject.parentNode());
    case RV_RELATION_FIRST_CHILD:
        return handleOrNull(subject.firstChild());
    case RV_RELATION_LAST_CHILD:
        return handleOrNull(subject.lastChild());
    case RV_RELATION_NEXT_SIBLING:
        return handleOrNull(subject.nextSibling());
    case RV_RELATION_PREVIOUS_SIBLING:
        return handleOrNull(subject.previousSibling());
    case RV_RELATION_OWNER_DOCUMENT:
        return handleOrNull(subject.ownerDocument());
    }
    return nullptr;
}

int32_t rv_node_get_string(RvNode* target, int32_t property, char* buffer, int32_t capacity, int32_t* length)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto& subject = *node(target);
    switch (property) {
    case RV_STRING_NODE_NAME:
        return copyString(subject.nodeName(), buffer, capacity, length);
    case RV_STRING_TEXT_CONTENT:
        return copyString(subject.textContent(), buffer, capacity, length);
    case RV_STRING_LOCAL_NAME:
        return copyString(subject.localName(), buffer, capacity, length);
    case RV_STRING_NAMESPACE_URI:
        return copyString(subject.namespaceURI(), buffer, capacity, length);
    case RV_STRING_INNER_HTML:
        if (RefPtr element = dynamicDowncast<Element>(subject))
            return copyString(element->innerHTML(), buffer, capacity, length);
        return RV_ERR_NOT_ELEMENT;
    case RV_STRING_DATA:
        if (RefPtr data = dynamicDowncast<CharacterData>(subject))
            return copyString(data->data(), buffer, capacity, length);
        return RV_ERR_UNSUPPORTED;
    case RV_STRING_VALUE:
        if (RefPtr input = dynamicDowncast<HTMLInputElement>(subject))
            return copyString(input->value().get(), buffer, capacity, length);
        if (RefPtr area = dynamicDowncast<HTMLTextAreaElement>(subject))
            return copyString(area->value().get(), buffer, capacity, length);
        if (RefPtr select = dynamicDowncast<HTMLSelectElement>(subject))
            return copyString(select->value(), buffer, capacity, length);
        if (RefPtr option = dynamicDowncast<HTMLOptionElement>(subject))
            return copyString(option->value(), buffer, capacity, length);
        return RV_ERR_NOT_INPUT;
    case RV_STRING_PREFIX:
        if (RefPtr element = dynamicDowncast<Element>(subject))
            return copyString(element->prefix(), buffer, capacity, length);
        return RV_ERR_NOT_ELEMENT;
    case RV_STRING_TITLE:
        if (RefPtr document = dynamicDowncast<Document>(subject))
            return copyString(document->title(), buffer, capacity, length);
        if (RefPtr element = dynamicDowncast<HTMLElement>(subject))
            return copyString(element->title(), buffer, capacity, length);
        return RV_ERR_NOT_ELEMENT;
    }
    return RV_ERR_UNSUPPORTED;
}

int32_t rv_node_set_string(RvNode* target, int32_t property, const char* value)
{
    if (!target || !value)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto& subject = *node(target);
    switch (property) {
    case RV_STRING_TEXT_CONTENT:
        return status(subject.setTextContent(utf8(value)));
    case RV_STRING_INNER_HTML:
        if (RefPtr element = dynamicDowncast<Element>(subject))
            return status(element->setInnerHTML(Variant<Ref<TrustedHTML>, String> { utf8(value) }));
        return RV_ERR_NOT_ELEMENT;
    case RV_STRING_DATA:
        if (RefPtr data = dynamicDowncast<CharacterData>(subject)) {
            data->setData(utf8(value));
            return RV_OK;
        }
        return RV_ERR_UNSUPPORTED;
    case RV_STRING_VALUE:
        if (RefPtr input = dynamicDowncast<HTMLInputElement>(subject))
            return status(input->setValue(utf8(value)));
        if (RefPtr area = dynamicDowncast<HTMLTextAreaElement>(subject))
            return status(area->setValue(utf8(value)));
        if (RefPtr select = dynamicDowncast<HTMLSelectElement>(subject)) {
            select->setValue(utf8(value));
            return RV_OK;
        }
        if (RefPtr option = dynamicDowncast<HTMLOptionElement>(subject))
            return status(option->setAttribute(AtomString::fromUTF8("value"), AtomString::fromUTF8(value)));
        return RV_ERR_NOT_INPUT;
    case RV_STRING_TITLE:
        if (RefPtr document = dynamicDowncast<Document>(subject)) {
            document->setTitle(utf8(value));
            return RV_OK;
        }
        if (RefPtr element = dynamicDowncast<Element>(subject))
            return status(element->setAttribute(AtomString::fromUTF8("title"), AtomString::fromUTF8(value)));
        return RV_ERR_NOT_ELEMENT;
    }
    return RV_ERR_UNSUPPORTED;
}

int32_t rv_node_insert_before(RvNode* parent, RvNode* child, RvNode* reference)
{
    if (!parent || !child)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return status(node(parent)->insertBefore(*node(child), RefPtr { node(reference) }));
}

int32_t rv_node_remove_child(RvNode* parent, RvNode* child)
{
    if (!parent || !child)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return status(node(parent)->removeChild(*node(child)));
}

int32_t rv_node_replace_child(RvNode* parent, RvNode* newChild, RvNode* oldChild)
{
    if (!parent || !newChild || !oldChild)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return status(node(parent)->replaceChild(*node(newChild), *node(oldChild)));
}

int32_t rv_node_remove(RvNode* target)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return status(node(target)->remove());
}

RvNode* rv_node_clone(RvNode* target, int32_t deep)
{
    if (!target || !onOwningThread())
        return nullptr;
    auto clone = node(target)->cloneNodeForBindings(!!deep);
    return clone.hasException() ? nullptr : handle(clone.releaseReturnValue());
}

int32_t rv_node_contains(RvNode* target, RvNode* other)
{
    if (!target || !other)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return node(target)->contains(*node(other)) ? 1 : 0;
}

int32_t rv_node_is_connected(RvNode* target)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return node(target)->isConnected() ? 1 : 0;
}

int32_t rv_element_get_attribute(RvNode* target, const char* name, char* buffer, int32_t capacity, int32_t* length)
{
    if (!target || !name)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = dynamicDowncast<Element>(*node(target));
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    return copyString(element->getAttribute(AtomString::fromUTF8(name)), buffer, capacity, length);
}

int32_t rv_element_remove_attribute(RvNode* target, const char* name)
{
    if (!target || !name)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = dynamicDowncast<Element>(*node(target));
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    element->removeAttribute(AtomString::fromUTF8(name));
    return RV_OK;
}

int32_t rv_input_set_checked(RvNode* target, int32_t checked)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr input = dynamicDowncast<HTMLInputElement>(*node(target));
    if (!input)
        return RV_ERR_NOT_INPUT;
    input->setChecked(!!checked);
    return RV_OK;
}

RvEvent* rv_event_retain(RvEvent* handle)
{
    if (!handle || !onOwningThread())
        return nullptr;
    event(handle)->ref();
    return handle;
}

void rv_event_release(RvEvent* handle)
{
    if (handle && onOwningThread())
        event(handle)->deref();
}

RvEvent* rv_host_create_event(RvHost* host, int32_t eventInterface, const char* type, int32_t bubbles, int32_t cancelable)
{
    if (!host || !type || !onOwningThread())
        return nullptr;
    String name;
    switch (eventInterface) {
    case RV_EVENT_EVENT:
        name = "event"_s;
        break;
    case RV_EVENT_UI:
    case RV_EVENT_INPUT:
        name = "uievent"_s;
        break;
    case RV_EVENT_MOUSE:
    case RV_EVENT_POINTER:
        name = "mouseevent"_s;
        break;
    case RV_EVENT_KEYBOARD:
        name = "keyboardevent"_s;
        break;
    case RV_EVENT_FOCUS:
        name = "focusevent"_s;
        break;
    default:
        return nullptr;
    }
    auto created = host->document().createEvent(name);
    if (created.hasException())
        return nullptr;
    Ref result = created.releaseReturnValue();
    result->initEvent(AtomString::fromUTF8(type), !!bubbles, !!cancelable);
    return eventHandle(WTF::move(result));
}

int32_t rv_node_dispatch(RvNode* target, RvEvent* dispatched, int32_t* defaultPrevented)
{
    if (!target || !dispatched)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    Ref protectedTarget = *node(target);
    Ref protectedEvent = *event(dispatched);
    auto result = dispatchCountingFailures([&] { protectedTarget->dispatchEvent(protectedEvent); });
    if (defaultPrevented)
        *defaultPrevented = protectedEvent->defaultPrevented() ? 1 : 0;
    return result;
}

int32_t rv_event_interface(RvEvent* handle)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    switch (event(handle)->interfaceType()) {
    case EventInterfaceType::Event:
        return RV_EVENT_EVENT;
    case EventInterfaceType::UIEvent:
        return RV_EVENT_UI;
    case EventInterfaceType::MouseEvent:
        return RV_EVENT_MOUSE;
    case EventInterfaceType::PointerEvent:
        return RV_EVENT_POINTER;
    case EventInterfaceType::KeyboardEvent:
        return RV_EVENT_KEYBOARD;
    case EventInterfaceType::InputEvent:
        return RV_EVENT_INPUT;
    case EventInterfaceType::FocusEvent:
        return RV_EVENT_FOCUS;
    default:
        return RV_EVENT_OTHER;
    }
}

int32_t rv_event_flags(RvEvent* handle)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto& subject = *event(handle);
    return (subject.bubbles() ? RV_EVENT_BUBBLES : 0)
        | (subject.cancelable() ? RV_EVENT_CANCELABLE : 0)
        | (subject.propagationStopped() ? RV_EVENT_PROPAGATION_STOPPED : 0)
        | (subject.defaultPrevented() ? RV_EVENT_DEFAULT_PREVENTED : 0)
        | (subject.isTrusted() ? RV_EVENT_TRUSTED : 0);
}

int32_t rv_event_type(RvEvent* handle, char* buffer, int32_t capacity, int32_t* length)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return copyString(event(handle)->type(), buffer, capacity, length);
}

int32_t rv_event_key(RvEvent* handle, char* buffer, int32_t capacity, int32_t* length)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr keyboard = dynamicDowncast<KeyboardEvent>(*event(handle));
    if (!keyboard)
        return RV_ERR_UNSUPPORTED;
    return copyString(keyboard->key(), buffer, capacity, length);
}

RvNode* rv_event_target(RvEvent* subject, int32_t current)
{
    if (!subject || !onOwningThread())
        return nullptr;
    auto* target = current ? event(subject)->currentTarget() : event(subject)->target();
    return handleOrNull(dynamicDowncast<Node>(target));
}

int32_t rv_last_exception(int32_t part, char* buffer, int32_t capacity, int32_t* length)
{
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!lastExceptionCode)
        return copyString(String { }, buffer, capacity, length);
    switch (part) {
    case RV_EXCEPTION_NAME:
        return copyString(String { DOMException::name(*lastExceptionCode) }, buffer, capacity, length);
    case RV_EXCEPTION_MESSAGE:
        return copyString(lastExceptionMessage, buffer, capacity, length);
    }
    return RV_ERR_UNSUPPORTED;
}

RvNode* rv_node_query_selector(RvNode* scope, const char* selectors, int32_t* result)
{
    if (!scope || !selectors || !result) {
        if (result)
            *result = RV_ERR_NULL_ARGUMENT;
        return nullptr;
    }
    if (!onOwningThread()) {
        *result = RV_ERR_WRONG_THREAD;
        return nullptr;
    }
    RefPtr container = dynamicDowncast<ContainerNode>(*node(scope));
    if (!container) {
        *result = RV_ERR_UNSUPPORTED;
        return nullptr;
    }
    auto found = container->querySelector(utf8(selectors));
    *result = status(found);
    return found.hasException() ? nullptr : handleOrNull(found.releaseReturnValue());
}

int32_t rv_node_query_selector_all(RvNode* scope, const char* selectors, RvNode** nodes, int32_t capacity, int32_t* count)
{
    if (!scope || !selectors || !count)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr container = dynamicDowncast<ContainerNode>(*node(scope));
    if (!container)
        return RV_ERR_UNSUPPORTED;
    auto found = container->querySelectorAll(utf8(selectors));
    if (found.hasException())
        return fail(found.exception());
    Ref list = found.releaseReturnValue();
    *count = static_cast<int32_t>(list->length());
    if (!nodes || capacity < *count)
        return RV_ERR_BUFFER_TOO_SMALL;
    for (unsigned index = 0; index < list->length(); ++index)
        nodes[index] = handleOrNull(list->item(index));
    return RV_OK;
}

int32_t rv_node_query_selector_all_uncached(RvNode* scope, const char* selectors, RvNode** nodes, int32_t capacity, int32_t* count)
{
    if (!scope || !selectors || !count)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto text = utf8(selectors);
    // Element::matches scopes :scope to the tested element, where querySelectorAll scopes it to the query's root.
    if (text.containsIgnoringASCIICase(":scope"_s))
        return rv_node_query_selector_all(scope, selectors, nodes, capacity, count);
    RefPtr container = dynamicDowncast<ContainerNode>(*node(scope));
    if (!container)
        return RV_ERR_UNSUPPORTED;
    auto first = container->querySelector(text);
    if (first.hasException())
        return fail(first.exception());
    Vector<Ref<Element>> found;
    for (RefPtr element = first.returnValue(); element; element = ElementTraversal::next(*element, container.get())) {
        auto matched = element->matches(text);
        if (matched.hasException())
            return fail(matched.exception());
        if (matched.returnValue())
            found.append(*element);
    }
    *count = static_cast<int32_t>(found.size());
    if (!nodes || capacity < *count)
        return RV_ERR_BUFFER_TOO_SMALL;
    for (unsigned index = 0; index < found.size(); ++index)
        nodes[index] = handle(Ref<Node> { found[index].get() });
    return RV_OK;
}

int32_t rv_node_ref_count(RvNode* target)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return static_cast<int32_t>(node(target)->refCount());
}

RvWatch* rv_node_watch(RvNode* target)
{
    if (!target || !onOwningThread())
        return nullptr;
    return new RvWatch { *node(target) };
}

int32_t rv_watch_alive(RvWatch* watch)
{
    if (!watch)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return watch->node ? 1 : 0;
}

RvNode* rv_watch_node(RvWatch* watch)
{
    if (!watch || !onOwningThread())
        return nullptr;
    return handleOrNull(watch->node.get());
}

void rv_watch_release(RvWatch* watch)
{
    if (watch && onOwningThread())
        delete watch;
}

void rv_release_memory(void)
{
    if (onOwningThread())
        releaseMemory(Critical::Yes, Synchronous::Yes);
}

void rv_collect_garbage(void)
{
    if (onOwningThread())
        GarbageCollectionController::singleton().garbageCollectNow();
}

void rv_collect_garbage_eden(void)
{
    if (!onOwningThread())
        return;
    JSC::JSLockHolder lock(commonVM());
    if (!commonVM().heap.currentThreadIsDoingGCWork())
        commonVM().heap.collectNow(JSC::Sync, JSC::CollectionScope::Eden);
}

int32_t rv_run_loop_cycle(int32_t milliseconds)
{
    if (milliseconds < 0)
        return RV_ERR_UNSUPPORTED;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto deadline = MonotonicTime::now() + Seconds::fromMilliseconds(milliseconds);
    int32_t cycles = 0;
    do {
        RunLoop::cycle();
        ++cycles;
        if (MonotonicTime::now() < deadline)
            WTF::sleep(1_ms);
    } while (MonotonicTime::now() < deadline);
    return cycles;
}

int32_t rv_node_has_wrapper(RvNode* target)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return node(target)->wrapper() ? 1 : 0;
}

int32_t rv_element_attribute_count(RvNode* target)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = dynamicDowncast<Element>(*node(target));
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    if (!element->hasAttributes())
        return 0;
    return static_cast<int32_t>(element->attributeCount());
}

int32_t rv_element_attribute_at(RvNode* target, int32_t index, int32_t part, char* buffer, int32_t capacity, int32_t* length)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = dynamicDowncast<Element>(*node(target));
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    if (index < 0 || !element->hasAttributes() || static_cast<unsigned>(index) >= element->attributeCount())
        return RV_ERR_UNSUPPORTED;
    auto& attribute = element->attributeAt(static_cast<unsigned>(index));
    switch (part) {
    case RV_ATTRIBUTE_NAME:
        if (attribute.prefix().isEmpty())
            return copyString(attribute.localName(), buffer, capacity, length);
        return copyString(makeString(attribute.prefix(), ':', attribute.localName()), buffer, capacity, length);
    case RV_ATTRIBUTE_VALUE:
        return copyString(attribute.value(), buffer, capacity, length);
    }
    return RV_ERR_UNSUPPORTED;
}

int32_t rv_element_focus(RvNode* target)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = dynamicDowncast<Element>(*node(target));
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    return dispatchCountingFailures([&] { element->focus({ }); });
}

int32_t rv_host_set_resource_handler(RvHost* host, RvResourceHandler handler, void* context)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    host->resourceHandler = handler;
    host->resourceContext = handler ? context : nullptr;
    return RV_OK;
}

int32_t rv_resource_load_finish(RvResourceLoad* load, const uint8_t* data, int32_t length, const char* contentType)
{
    if (!load || (!data && length) || !contentType)
        return RV_ERR_NULL_ARGUMENT;
    if (length < 0)
        return RV_ERR_UNSUPPORTED;
    return complete(load, SharedBuffer::create(std::span { data, static_cast<size_t>(length) }), utf8(contentType));
}

int32_t rv_resource_load_fail(RvResourceLoad* load)
{
    return complete(load, nullptr, { });
}
