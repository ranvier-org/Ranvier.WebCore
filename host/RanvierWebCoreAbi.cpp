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
#include <WebCore/Chrome.h>
#include <WebCore/DOMPasteAccess.h>
#include <WebCore/Editor.h>
#include <WebCore/EditorClient.h>
#include <WebCore/EventNames.h>
#include <WebCore/FrameDestructionObserverInlines.h>
#include <WebCore/StyleProperties.h>
#include <WebCore/TextCheckerClient.h>
#include <WebCore/TextChecking.h>
#include <WebCore/UndoStep.h>
#include <WebCore/VisibleSelection.h>
#include <WebCore/EventHandler.h>
#include <WebCore/FocusController.h>
#include <WebCore/HandleUserInputEventResult.h>
#include <WebCore/InputEvent.h>
#include <WebCore/MouseEvent.h>
#include <WebCore/MouseEventTypes.h>
#include <WebCore/PlatformKeyboardEvent.h>
#include <WebCore/PlatformMouseEvent.h>
#include <WebCore/PlatformWheelEvent.h>
#include <WebCore/ScrollingCoordinatorTypes.h>
#include <WebCore/WheelEvent.h>
#if PLATFORM(COCOA)
#include <WebCore/AttributedString.h>
#endif
#include <mutex>
#include <pal/SessionID.h>
#include <cstring>
#include <optional>
#include <utility>
#include <wtf/MainThread.h>
#include <wtf/ProcessID.h>
#include <wtf/RunLoop.h>
#include <wtf/HexNumber.h>
#include <wtf/text/MakeString.h>

#if PLATFORM(GTK) || PLATFORM(WPE)
#include <WebCore/PlatformDisplaySurfaceless.h>
#endif

using namespace WebCore;

struct RvHost;

// Reports the page's invalidations and rendering update requests to its host, which turns them into a dirty
// rectangle and a frame callback.
class RvChromeClient final : public EmptyChromeClient {
    WTF_MAKE_TZONE_ALLOCATED_INLINE(RvChromeClient);
public:
    RvHost* host { nullptr };

private:
    void invalidateRootView(const IntRect& rect) final { invalidate(rect); }
    void invalidateContentsAndRootView(const IntRect& rect) final { invalidate(rect); }
    void invalidateContentsForSlowScroll(const IntRect& rect) final { invalidate(rect); }
    void triggerRenderingUpdate() final { wantUpdate(); }
    bool scheduleRenderingUpdate() final
    {
        wantUpdate();
        return true;
    }
    void invalidate(const IntRect&);
    void wantUpdate();
};

// The editing command a key down runs, as Windows binds keys.
static String keyCommand(const String& key, bool shift, bool control)
{
    auto move = [&](ASCIILiteral command, ASCIILiteral withControl) {
        return makeString(control ? withControl : command, shift ? "AndModifySelection"_s : ""_s);
    };
    if (key == "ArrowLeft"_s)
        return move("MoveLeft"_s, "MoveWordLeft"_s);
    if (key == "ArrowRight"_s)
        return move("MoveRight"_s, "MoveWordRight"_s);
    if (key == "ArrowUp"_s)
        return move("MoveUp"_s, "MoveUp"_s);
    if (key == "ArrowDown"_s)
        return move("MoveDown"_s, "MoveDown"_s);
    if (key == "Home"_s)
        return move("MoveToBeginningOfLine"_s, "MoveToBeginningOfDocument"_s);
    if (key == "End"_s)
        return move("MoveToEndOfLine"_s, "MoveToEndOfDocument"_s);
    if (key == "Backspace"_s)
        return control ? "DeleteWordBackward"_s : "DeleteBackward"_s;
    if (key == "Delete"_s)
        return control ? "DeleteWordForward"_s : "DeleteForward"_s;
    if (key == "Enter"_s)
        return shift ? "InsertLineBreak"_s : "InsertNewline"_s;
    if (control && (key == "a"_s || key == "A"_s))
        return "SelectAll"_s;
    return { };
}

// An editor client that allows every edit and binds keys to editing commands, as WebKitLegacy's Windows client
// did. The rest follows EmptyEditorClient in WebCore's loader/EmptyClients.cpp (Copyright (C) 2006 Eric Seidel,
// 2008-2025 Apple Inc., Research In Motion Limited 2011; BSD-2-Clause).
class RvEditorClient final : public EditorClient {
    WTF_MAKE_TZONE_ALLOCATED_INLINE(RvEditorClient);
    WTF_OVERRIDE_DELETE_FOR_CHECKED_PTR(RvEditorClient);
private:
    // Key down runs the key's editing command; key press inserts the characters it produced.
    void handleKeyboardEvent(KeyboardEvent& event) final
    {
        RefPtr node = dynamicDowncast<Node>(event.target());
        RefPtr frame = node ? node->document().frame() : nullptr;
        auto* platformEvent = event.underlyingPlatformEvent();
        if (!frame || !platformEvent)
            return;
        auto& editor = frame->editor();
        if (event.type() == eventNames().keydownEvent) {
            auto command = keyCommand(event.key(), event.shiftKey(), event.ctrlKey());
            if (!command.isEmpty() && editor.command(command).execute(&event))
                event.setDefaultHandled();
            return;
        }
        auto text = platformEvent->text();
        if (event.type() == eventNames().keypressEvent && !event.ctrlKey() && !event.metaKey() && !text.isEmpty() && text[0] >= ' ' && editor.insertText(text, &event))
            event.setDefaultHandled();
    }
    void handleInputMethodKeydown(KeyboardEvent&) final { }

    bool shouldDeleteRange(const std::optional<SimpleRange>&) final { return true; }
    bool smartInsertDeleteEnabled() final { return false; }
    bool isSelectTrailingWhitespaceEnabled() const final { return false; }
    bool isContinuousSpellCheckingEnabled() final { return false; }
    void toggleContinuousSpellChecking() final { }
    bool isGrammarCheckingEnabled() final { return false; }
    void toggleGrammarChecking() final { }
    int spellCheckerDocumentTag() final { return -1; }

    bool shouldBeginEditing(const SimpleRange&) final { return true; }
    bool shouldEndEditing(const SimpleRange&) final { return true; }
    bool shouldInsertNode(Node&, const std::optional<SimpleRange>&, EditorInsertAction) final { return true; }
    bool shouldInsertText(const String&, const std::optional<SimpleRange>&, EditorInsertAction) final { return true; }
    bool shouldChangeSelectedRange(const std::optional<SimpleRange>&, const std::optional<SimpleRange>&, Affinity, bool) final { return true; }

    bool shouldApplyStyle(const StyleProperties&, const std::optional<SimpleRange>&) final { return true; }
    void didApplyStyle() final { }
    bool shouldMoveRangeAfterDelete(const SimpleRange&, const SimpleRange&) final { return true; }

    void didBeginEditing() final { }
    void respondToChangedContents() final { }
    void respondToChangedSelection(LocalFrame*) final { }
    void updateEditorStateAfterLayoutIfEditabilityChanged() final { }
    void discardedComposition(const Document&) final { }
    void canceledComposition() final { }
    void didUpdateComposition() final { }
    void didEndEditing() final { }
    void didEndUserTriggeredSelectionChanges() final { }
    void willWriteSelectionToPasteboard(const std::optional<SimpleRange>&) final { }
    void didWriteSelectionToPasteboard() final { }
    void getClientPasteboardData(const std::optional<SimpleRange>&, Vector<std::pair<String, RefPtr<SharedBuffer>>>&) final { }
    void requestCandidatesForSelection(const VisibleSelection&) final { }
    void handleAcceptedCandidateWithSoftSpaces(TextCheckingResult) final { }

    void registerUndoStep(UndoStep&) final { }
    void registerRedoStep(UndoStep&) final { }
    void clearUndoRedoOperations() final { }

    DOMPasteAccessResponse requestDOMPasteAccess(DOMPasteAccessCategory, FrameIdentifier, const String&) final { return DOMPasteAccessResponse::DeniedForGesture; }
#if PLATFORM(COCOA)
    HashMap<FrameIdentifier, AttributedString> collectAttributedStringsForRemoteFrames(FrameIdentifier, const Vector<FrameIdentifier>&) final { return { }; }
#endif

    bool canCopyCut(LocalFrame*, bool defaultValue) const final { return defaultValue; }
    bool canPaste(LocalFrame*, bool defaultValue) const final { return defaultValue; }
    bool canUndo() const final { return false; }
    bool canRedo() const final { return false; }

    void undo() final { }
    void redo() final { }

    void textFieldDidBeginEditing(Element&) final { }
    void textFieldDidEndEditing(Element&) final { }
    void textDidChangeInTextField(Element&) final { }
    bool doTextFieldCommandFromEvent(Element&, KeyboardEvent*) final { return false; }
    void textWillBeDeletedInTextField(Element&) final { }
    void textDidChangeInTextArea(Element&) final { }
    void overflowScrollPositionChanged() final { }
    void subFrameScrollPositionChanged() final { }

#if PLATFORM(IOS_FAMILY)
    void startDelayingAndCoalescingContentChangeNotifications() final { }
    void stopDelayingAndCoalescingContentChangeNotifications() final { }
    bool hasRichlyEditableSelection() final { return false; }
    int getPasteboardItemsCount() final { return 0; }
    RefPtr<DocumentFragment> documentFragmentFromDelegate(int) final { return nullptr; }
    bool performsTwoStepPaste(DocumentFragment*) final { return false; }
    void updateStringForFind(const String&) final { }
#endif

    bool performTwoStepDrop(DocumentFragment&, const SimpleRange&, bool) final { return false; }

#if PLATFORM(COCOA)
    void setInsertionPasteboard(const String&) final { };
#endif

#if USE(APPKIT)
    void uppercaseWord() final { }
    void lowercaseWord() final { }
    void capitalizeWord() final { }
    bool canApplyCaseTransformations(const String&) final { return true; }
    bool canConvertToTraditionalChinese(const String&) final { return false; }
    bool canConvertToSimplifiedChinese(const String&) final { return false; }
    void convertToTraditionalChinese() final { }
    void convertToSimplifiedChinese() final { }
#endif

#if USE(AUTOMATIC_TEXT_REPLACEMENT)
    void showSubstitutionsPanel(bool) final { }
    bool substitutionsPanelIsShowing() final { return false; }
    void toggleSmartInsertDelete() final { }
    bool isAutomaticQuoteSubstitutionEnabled() final { return false; }
    void toggleAutomaticQuoteSubstitution() final { }
    bool isAutomaticLinkDetectionEnabled() final { return false; }
    void toggleAutomaticLinkDetection() final { }
    bool isAutomaticDashSubstitutionEnabled() final { return false; }
    void toggleAutomaticDashSubstitution() final { }
    bool isAutomaticTextReplacementEnabled() final { return false; }
    void toggleAutomaticTextReplacement() final { }
    bool isAutomaticSpellingCorrectionEnabled() final { return false; }
    void toggleAutomaticSpellingCorrection() final { }
    bool isSmartListsEnabled() final { return false; }
    void toggleSmartLists() { }
#endif

#if PLATFORM(GTK)
    bool shouldShowUnicodeMenu() final { return false; }
#endif

    TextCheckerClient* textChecker() final { return &m_textCheckerClient; }

    void updateSpellingUIWithGrammarString(const String&, const GrammarDetail&) final { }
    void updateSpellingUIWithMisspelledWord(const String&) final { }
    void showSpellingUI(bool) final { }
    bool spellingUIIsShowing() final { return false; }

    void setInputMethodState(Element*) final { }

    class TextChecker final : public TextCheckerClient {
        bool shouldEraseMarkersAfterChangeSelection(TextCheckingType) const final { return true; }
        void ignoreWordInSpellDocument(const String&) final { }
        void learnWord(const String&) final { }
        void checkSpellingOfString(StringView, int*, int*) final { }
        void checkGrammarOfString(StringView, Vector<GrammarDetail>&, int*, int*) final { }
#if USE(UNIFIED_TEXT_CHECKING)
        Vector<TextCheckingResult> checkTextOfParagraph(StringView, OptionSet<TextCheckingType>, const VisibleSelection&) final { return { }; }
#endif
        void getGuessesForWord(const String&, const String&, const VisibleSelection&, Vector<String>&) final { }
        void requestCheckingOfString(TextCheckingRequest&, const VisibleSelection&) final { }
        void requestExtendedCheckingOfString(TextCheckingRequest&, const VisibleSelection&) final { }
    };

    TextChecker m_textCheckerClient;
};

// createPage and loadHTML follow WebCore's testing/TestPage.cpp (Copyright (C) 2026 Apple Inc., BSD-2-Clause).
static Ref<Page> createPage(IntSize viewportSize)
{
    static bool prewarmed = [] {
        ProcessWarming::prewarmGlobally();
        return true;
    }();
    UNUSED_VARIABLE(prewarmed);
    auto configuration = pageConfigurationWithEmptyClients(std::nullopt, PAL::SessionID::defaultSessionID());
    configuration.chromeClient = makeUniqueRef<RvChromeClient>();
    configuration.editorClient = makeUniqueRef<RvEditorClient>();
    Ref page = Page::create(WTF::move(configuration));
    page->settings().setScriptEnabled(false);
    page->settings().setScrollAnimatorEnabled(false);
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
    float deviceScale { 1 };
    // The viewport area invalidated since the last paint.
    IntRect dirty;
    RvFrameCallback frameCallback { nullptr };
    void* frameContext { nullptr };
    // The callback ran and no frame has started since.
    bool frameRequested { false };
    // Inside rv_host_update or rv_host_paint_rgba, which call no callback.
    bool inFrame { false };
    bool updateWanted { false };

    Document& document() { return *page->localTopDocument(); }
    LocalFrame& frame() { return *page->localMainFrame(); }

    void requestFrame()
    {
        if (inFrame || frameRequested || !frameCallback)
            return;
        frameRequested = true;
        frameCallback(frameContext);
    }
};

void RvChromeClient::invalidate(const IntRect& rect)
{
    if (!host)
        return;
    host->dirty.unite(intersection(rect, IntRect { { }, host->size }));
    host->requestFrame();
}

void RvChromeClient::wantUpdate()
{
    if (!host)
        return;
    host->updateWanted = true;
    host->requestFrame();
}

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

int32_t rv_abi_version(void) { return 12; }

// The device pixels of a paint: the viewport scaled and truncated, as ImageBuffer::getPixelBuffer scales it.
static IntSize paintSize(const RvHost& host)
{
    auto size = host.size;
    size.scale(host.deviceScale);
    return size;
}

int32_t rv_abi_has(const char* feature)
{
    if (!feature)
        return 0;
    for (auto* name : { "resize", "input", "frame", "event-details" }) {
        if (!std::strcmp(feature, name))
            return 1;
    }
    return 0;
}

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
    static_cast<RvChromeClient&>(host->page->chrome().client()).host = host;
    host->noScript.emplace(host->document().vm());
    liveHosts.append(host);
    return host;
}

void rv_host_destroy(RvHost* host)
{
    if (!host || !onOwningThread())
        return;
    host->noScript.reset();
    static_cast<RvChromeClient&>(host->page->chrome().client()).host = nullptr;
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
    auto pixelSize = paintSize(*host);
    size_t required = static_cast<size_t>(pixelSize.width()) * pixelSize.height() * 4;
    if (length < 0 || static_cast<size_t>(length) < required)
        return RV_ERR_BUFFER_TOO_SMALL;
    host->inFrame = true;
    host->frameRequested = false;
    host->document().updateLayoutIgnorePendingStylesheets();
    RefPtr view = host->frame().view();
    if (!view) {
        host->inFrame = false;
        return RV_ERR_PAINT_FAILED;
    }
    view->updateLayoutAndStyleIfNeededRecursive();
    auto buffer = ImageBuffer::create(FloatSize { size }, RenderingMode::Unaccelerated,
        RenderingPurpose::Unspecified, host->deviceScale, DestinationColorSpace::SRGB(), PixelFormat::BGRA8);
    if (buffer)
        view->paint(buffer->context(), IntRect { { }, size });
    host->dirty = { };
    host->inFrame = false;
    if (!buffer)
        return RV_ERR_PAINT_FAILED;
    buffer->flushDrawingContext();
    PixelBufferFormat format { AlphaPremultiplication::Unpremultiplied, PixelFormat::RGBA8, DestinationColorSpace::SRGB() };
    // getPixelBuffer takes CSS pixels and scales them as paintSize does.
    auto pixels = buffer->getPixelBuffer(format, IntRect { { }, size });
    if (!pixels || pixels->bytes().size() != required)
        return RV_ERR_PAINT_FAILED;
    std::memcpy(rgba, pixels->bytes().data(), required);
    // An update wanted during the paint, such as a layout that started an animation, needs another frame.
    if (host->updateWanted)
        host->requestFrame();
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

int32_t rv_host_resize(RvHost* host, int32_t width, int32_t height)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (width <= 0 || height <= 0)
        return RV_ERR_UNSUPPORTED;
    RefPtr view = host->frame().view();
    if (!view)
        return RV_ERR_PAINT_FAILED;
    host->size = { width, height };
    view->resize(host->size);
    host->dirty = { { }, host->size };
    host->requestFrame();
    return RV_OK;
}

int32_t rv_host_set_device_scale(RvHost* host, float scale)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!(scale >= 0.25f && scale <= 8))
        return RV_ERR_UNSUPPORTED;
    host->deviceScale = scale;
    host->page->setDeviceScaleFactor(scale);
    host->dirty = { { }, host->size };
    host->requestFrame();
    return RV_OK;
}

int32_t rv_host_paint_size(RvHost* host, int32_t* width, int32_t* height)
{
    if (!host || !width || !height)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto size = paintSize(*host);
    *width = size.width();
    *height = size.height();
    return RV_OK;
}

static OptionSet<PlatformEvent::Modifier> platformModifiers(int32_t bits)
{
    OptionSet<PlatformEvent::Modifier> modifiers;
    if (bits & RV_MODIFIER_SHIFT)
        modifiers.add(PlatformEvent::Modifier::ShiftKey);
    if (bits & RV_MODIFIER_CONTROL)
        modifiers.add(PlatformEvent::Modifier::ControlKey);
    if (bits & RV_MODIFIER_ALT)
        modifiers.add(PlatformEvent::Modifier::AltKey);
    if (bits & RV_MODIFIER_META)
        modifiers.add(PlatformEvent::Modifier::MetaKey);
    return modifiers;
}

// Runs an input function's WebCore call, which dispatches DOM events, and returns 1 or 0 for whether it was
// handled, or RV_ERR_LISTENER_FAILED. Styles the input changed, such as :hover and :focus, apply before it
// returns, so their invalidations and frame request do too.
template<typename Handle> static int32_t handleInput(RvHost& host, Handle&& handle)
{
    bool handled = false;
    auto status = dispatchCountingFailures([&] { handled = handle(); });
    host.document().updateStyleIfNeeded();
    if (RefPtr view = host.frame().view(); view && view->needsLayout())
        host.requestFrame();
    return status == RV_OK ? (handled ? 1 : 0) : status;
}

int32_t rv_host_mouse(RvHost* host, int32_t action, int32_t x, int32_t y, int32_t button, int32_t clickCount, int32_t modifiers)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (action < RV_MOUSE_MOVE || action > RV_MOUSE_UP || button < RV_BUTTON_NONE || button > RV_BUTTON_RIGHT || clickCount < 0)
        return RV_ERR_UNSUPPORTED;
    static constexpr PlatformEvent::Type types[] = { PlatformEvent::Type::MouseMoved, PlatformEvent::Type::MousePressed, PlatformEvent::Type::MouseReleased };
    DoublePoint position { static_cast<double>(x), static_cast<double>(y) };
    PlatformMouseEvent mouse(position, position, button == RV_BUTTON_NONE ? MouseButton::None : static_cast<MouseButton>(button),
        types[action], clickCount, platformModifiers(modifiers), MonotonicTime::now(), 0, SyntheticClickType::NoTap, MouseEventInputSource::UserDriven);
    Ref frame = host->frame();
    return handleInput(*host, [&] {
        auto& handler = frame->eventHandler();
        switch (action) {
        case RV_MOUSE_MOVE:
            return handler.mouseMoved(mouse).wasHandled();
        case RV_MOUSE_DOWN:
            return handler.handleMousePressEvent(mouse).wasHandled();
        default:
            return handler.handleMouseReleaseEvent(mouse).wasHandled();
        }
    });
}

int32_t rv_host_wheel(RvHost* host, int32_t x, int32_t y, float deltaX, float deltaY, int32_t modifiers)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    IntPoint position { x, y };
    // PlatformWheelEvent's deltas are positive towards the top left, and a tick is a 40-pixel line (E).
    PlatformWheelEvent wheel(position, position, -deltaX, -deltaY, -deltaX / 40, -deltaY / 40, PlatformWheelEventGranularity::ScrollByPixelWheelEvent,
        modifiers & RV_MODIFIER_SHIFT, modifiers & RV_MODIFIER_CONTROL, modifiers & RV_MODIFIER_ALT, modifiers & RV_MODIFIER_META);
    Ref frame = host->frame();
    return handleInput(*host, [&] {
        return frame->eventHandler().handleWheelEvent(wheel, { WheelEventProcessingSteps::SynchronousScrolling, WheelEventProcessingSteps::BlockingDOMEventDispatch }).first.wasHandled();
    });
}

// The keyIdentifier and Windows virtual key code WebCore's key handling reads, from the DOM key and code.
static std::pair<String, int> legacyKey(const String& key, const String& code)
{
    static constexpr std::tuple<ASCIILiteral, ASCIILiteral, int> named[] = {
        { "Tab"_s, "U+0009"_s, 0x09 }, { "Backspace"_s, "U+0008"_s, 0x08 }, { "Enter"_s, "Enter"_s, 0x0D },
        { "Escape"_s, "U+001B"_s, 0x1B }, { "Delete"_s, "U+007F"_s, 0x2E }, { "ArrowLeft"_s, "Left"_s, 0x25 },
        { "ArrowUp"_s, "Up"_s, 0x26 }, { "ArrowRight"_s, "Right"_s, 0x27 }, { "ArrowDown"_s, "Down"_s, 0x28 },
        { "PageUp"_s, "PageUp"_s, 0x21 }, { "PageDown"_s, "PageDown"_s, 0x22 }, { "End"_s, "End"_s, 0x23 },
        { "Home"_s, "Home"_s, 0x24 }, { "Shift"_s, "Shift"_s, 0x10 }, { "Control"_s, "Control"_s, 0x11 },
        { "Alt"_s, "Alt"_s, 0x12 },
    };
    for (auto& [name, identifier, virtualKey] : named) {
        if (key == name)
            return { identifier, virtualKey };
    }
    int virtualKey = 0;
    if (code.length() == 4 && code.startsWith("Key"_s) && isASCIIUpper(code[3]))
        virtualKey = code[3];
    else if (code.length() == 6 && code.startsWith("Digit"_s) && isASCIIDigit(code[5]))
        virtualKey = code[5];
    else if (code == "Space"_s)
        virtualKey = 0x20;
    if (key.length() == 1)
        return { makeString("U+"_s, hex(toASCIIUpper(key[0]), 4)), virtualKey };
    return { key, virtualKey };
}

int32_t rv_host_key(RvHost* host, int32_t action, const char* key, const char* code, const char* text, int32_t modifiers, int32_t repeat)
{
    if (!host || !key || !code)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (action < RV_KEY_DOWN || action > RV_KEY_CHAR)
        return RV_ERR_UNSUPPORTED;
    static constexpr PlatformEvent::Type types[] = { PlatformEvent::Type::RawKeyDown, PlatformEvent::Type::KeyUp, PlatformEvent::Type::Char };
    auto keyValue = utf8(key);
    auto codeValue = utf8(code);
    auto characters = action == RV_KEY_CHAR && text ? utf8(text) : String { emptyString() };
    auto [identifier, virtualKey] = legacyKey(keyValue, codeValue);
    PlatformKeyboardEvent keyboard(types[action], characters, characters, keyValue, codeValue, identifier, virtualKey,
        !!repeat, false, modifiers & RV_MODIFIER_ALT, platformModifiers(modifiers), MonotonicTime::now());
    Ref frame = host->frame();
    return handleInput(*host, [&] { return frame->eventHandler().keyEvent(keyboard); });
}

int32_t rv_host_set_focused(RvHost* host, int32_t focused)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto& focus = host->page->focusController();
    return dispatchCountingFailures([&] {
        focus.setActive(!!focused);
        focus.setFocused(!!focused);
    });
}

int32_t rv_host_set_frame_callback(RvHost* host, RvFrameCallback callback, void* context)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    host->frameCallback = callback;
    host->frameContext = callback ? context : nullptr;
    host->frameRequested = false;
    // A page that already wants a frame asks for it at once.
    if (host->updateWanted || !host->dirty.isEmpty())
        host->requestFrame();
    return RV_OK;
}

int32_t rv_host_update(RvHost* host)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    Ref page = host->page;
    host->inFrame = true;
    host->frameRequested = false;
    host->updateWanted = false;
    page->updateRendering();
    page->finalizeRenderingUpdate({ });
    host->inFrame = false;
    // A running animation asked for the next frame during this one.
    if (host->updateWanted)
        host->requestFrame();
    return RV_OK;
}

int32_t rv_host_dirty_rect(RvHost* host, int32_t* x, int32_t* y, int32_t* width, int32_t* height)
{
    if (!host || !x || !y || !width || !height)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto& dirty = host->dirty;
    *x = dirty.x();
    *y = dirty.y();
    *width = dirty.width();
    *height = dirty.height();
    return dirty.isEmpty() ? 0 : 1;
}

int32_t rv_event_number(RvEvent* handle, int32_t number, double* value)
{
    if (!handle || !value)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto& subject = *event(handle);
    RefPtr mouse = dynamicDowncast<MouseEvent>(subject);
    RefPtr keyboard = dynamicDowncast<KeyboardEvent>(subject);
    UIEventWithKeyState* keyState = mouse ? static_cast<UIEventWithKeyState*>(mouse.get()) : keyboard.get();
    std::optional<double> result;
    switch (number) {
    case RV_NUMBER_CLIENT_X:
        if (mouse)
            result = mouse->clientX();
        break;
    case RV_NUMBER_CLIENT_Y:
        if (mouse)
            result = mouse->clientY();
        break;
    case RV_NUMBER_BUTTON:
        if (mouse)
            result = mouse->buttonAsShort();
        break;
    case RV_NUMBER_BUTTONS:
        if (mouse)
            result = mouse->buttons();
        break;
    case RV_NUMBER_MODIFIERS:
        if (keyState) {
            result = (keyState->shiftKey() ? RV_MODIFIER_SHIFT : 0) | (keyState->ctrlKey() ? RV_MODIFIER_CONTROL : 0)
                | (keyState->altKey() ? RV_MODIFIER_ALT : 0) | (keyState->metaKey() ? RV_MODIFIER_META : 0);
        }
        break;
    case RV_NUMBER_DETAIL:
        if (RefPtr ui = dynamicDowncast<UIEvent>(subject))
            result = ui->detail();
        break;
    case RV_NUMBER_DELTA_X:
    case RV_NUMBER_DELTA_Y:
        if (RefPtr wheel = dynamicDowncast<WheelEvent>(subject))
            result = number == RV_NUMBER_DELTA_X ? wheel->deltaX() : wheel->deltaY();
        break;
    case RV_NUMBER_KEY_LOCATION:
        if (keyboard)
            result = keyboard->location();
        break;
    case RV_NUMBER_KEY_REPEAT:
        if (keyboard)
            result = keyboard->repeat() ? 1 : 0;
        break;
    }
    if (!result)
        return RV_ERR_UNSUPPORTED;
    *value = *result;
    return RV_OK;
}

int32_t rv_event_string(RvEvent* handle, int32_t property, char* buffer, int32_t capacity, int32_t* length)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto& subject = *event(handle);
    switch (property) {
    case RV_EVENT_STRING_CODE:
        if (RefPtr keyboard = dynamicDowncast<KeyboardEvent>(subject))
            return copyString(keyboard->code(), buffer, capacity, length);
        break;
    case RV_EVENT_STRING_DATA:
    case RV_EVENT_STRING_INPUT_TYPE:
        if (RefPtr input = dynamicDowncast<InputEvent>(subject))
            return copyString(property == RV_EVENT_STRING_DATA ? input->data() : input->inputType(), buffer, capacity, length);
        break;
    }
    return RV_ERR_UNSUPPORTED;
}

RvNode* rv_event_related_target(RvEvent* subject)
{
    if (!subject || !onOwningThread())
        return nullptr;
    return handleOrNull(dynamicDowncast<Node>(event(subject)->relatedTarget()));
}
