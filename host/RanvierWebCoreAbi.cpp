#include "config.h"
#include "RanvierWebCoreAbi.h"
#include "dom/RanvierDomGlue.h"
#include "RanvierSvgViewGlue.h"
#include "RanvierResourceGlue.h"
#include "RanvierEventGlue.h"
#include "RanvierViewportGlue.h"
#include "RanvierInspectGlue.h"
#include <atomic>
#include <string>
#include <vector>
#include <JavaScriptCore/DisallowVMEntry.h>
#include <JavaScriptCore/InitializeThreading.h>
#include <WebCore/Document.h>
#include <WebCore/DocumentParser.h>
#include <WebCore/AXCoreObject.h>
#include <WebCore/AXNotifications.h>
#include <WebCore/AXObjectCache.h>
#include <WebCore/AccessibilityObject.h>
#include <WebCore/BoundaryPoint.h>
#include <WebCore/RenderObject.h>
#include <WebCore/TextControlInnerElements.h>
#include <WebCore/TextIterator.h>
#include <WebCore/VisibleUnits.h>
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
#include <WebCore/NodeFilter.h>
#include <WebCore/NodeInlines.h>
#include <WebCore/NodeList.h>
#include <WebCore/Page.h>
#include <WebCore/PixelBuffer.h>
#include <WebCore/Range.h>
#include <WebCore/Settings.h>
#include <WebCore/MIMETypeRegistry.h>
#include <WebCore/Text.h>
#include <WebCore/TrustedHTML.h>
#include <WebCore/DocumentLoader.h>
#include <WebCore/DocumentPage.h>
#include <WebCore/DocumentWriter.h>
#include <WebCore/EmptyClients.h>
#include <WebCore/FrameLoader.h>
#include <WebCore/LocalFrameInlines.h>
#include <WebCore/PageConfiguration.h>
#include <WebCore/PlatformScreen.h>
#include <WebCore/ScreenOrientationManager.h>
#include <WebCore/ScreenOrientationType.h>
#include <WebCore/ScreenProperties.h>
#include <WebCore/EmptyFrameLoaderClient.h>
#include <WebCore/FormData.h>
#include <WebCore/FormState.h>
#include <WebCore/FormSubmission.h>
#include <WebCore/HTMLFormElement.h>
#include <WebCore/ProcessWarming.h>
#include <WebCore/Blob.h>
#include <WebCore/BlobData.h>
#include <WebCore/BlobRegistry.h>
#include <WebCore/BlobRegistryImpl.h>
#include <WebCore/File.h>
#include <WebCore/FileList.h>
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
#include <WebCore/ClipboardEvent.h>
#include <WebCore/DragActions.h>
#include <WebCore/DragClient.h>
#include <WebCore/DragController.h>
#include <WebCore/DragItem.h>
#include <WebCore/HTMLNames.h>
#include <wtf/SetForScope.h>
#include <wtf/HashMap.h>
#include <WebCore/DragEvent.h>
#include <WebCore/VisiblePosition.h>
#include <WebCore/DataTransfer.h>
#include <WebCore/StaticPasteboard.h>
#include <WebCore/markup.h>
#include <WebCore/HitTestResult.h>
#include <WebCore/PopupMenu.h>
#include <WebCore/PopupMenuClient.h>
#include <WebCore/DOMRectReadOnly.h>
#include <WebCore/FrameSnapshotting.h>
#include <WebCore/IntersectionObserver.h>
#include <WebCore/IntersectionObserverCallback.h>
#include <WebCore/IntersectionObserverEntry.h>
#include <WebCore/ResizeObserver.h>
#include <WebCore/ResizeObserverCallback.h>
#include <WebCore/ResizeObserverEntry.h>
#include <WebCore/CSSAnimation.h>
#include <WebCore/CSSComputedStyleDeclaration.h>
#include <WebCore/CSSStyleDeclaration.h>
#include <WebCore/CSSTransition.h>
#include <WebCore/DOMTokenList.h>
#include <WebCore/GetAnimationsOptions.h>
#include <WebCore/HTMLTextFormControlElement.h>
#include <WebCore/KeyframeEffect.h>
#include <WebCore/ScrollIntoViewOptions.h>
#include <WebCore/ScrollToOptions.h>
#include <WebCore/ShadowRoot.h>
#include <WebCore/ShadowRootInit.h>
#include <WebCore/StyledElement.h>
#include <WebCore/WebAnimation.h>
#include <WebCore/WebAnimationTime.h>
#include <WebCore/CompositionHighlight.h>
#include <WebCore/CompositionUnderline.h>
#include <WebCore/Cursor.h>
#include <WebCore/FrameSelection.h>
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
#include <WebCore/EventTargetInlines.h>
#include <WebCore/MouseEventTypes.h>
#include <WebCore/PlatformKeyboardEvent.h>
#include <WebCore/PlatformMouseEvent.h>
#include <WebCore/PlatformWheelEvent.h>
#include <WebCore/ScrollingCoordinatorTypes.h>
#include <WebCore/WheelEvent.h>
#if PLATFORM(COCOA)
#include <WebCore/AttributedString.h>
#endif
#if PLATFORM(MAC)
#include <WebCore/DeprecatedGlobalSettings.h>
#endif
#include <cmath>
#include <mutex>
#include <pal/SessionID.h>
#include <cstring>
#include <filesystem>
#include <optional>
#include <utility>
#include <wtf/MainThread.h>
#include <wtf/ProcessID.h>
#include <wtf/RunLoop.h>
#include <wtf/HexNumber.h>
#include <wtf/text/MakeString.h>
#include <wtf/text/TextBreakIterator.h>
#include <unicode/ubrk.h>
#include <unicode/uloc.h>
#include <unicode/uchar.h>
#include <unicode/uversion.h>

#if PLATFORM(GTK) || PLATFORM(WPE)
#include <WebCore/PlatformDisplaySurfaceless.h>
#endif

// RANVIER_COMPOSITING: RanvierWebCoreHost.cmake defines it when WebCore has GraphicsLayerTextureMapper and the
// GPU code (USE_GPU_STUB off).
#if RANVIER_COMPOSITING
#include <GLES2/gl2.h>
#include <WebCore/GLContext.h>
#include <WebCore/GraphicsLayerTextureMapper.h>
#include <WebCore/PlatformDisplay.h>
#include <WebCore/TextureMapper.h>
#include <WebCore/TextureMapperLayer.h>
#if defined(_WIN32)
#include "RanvierWebCoreD3D11.h"
#endif
#endif

using namespace WebCore;

struct RvHost;

// Reports the page's invalidations and rendering update requests to its host, which turns them into a dirty
// rectangle and a frame callback.
class RvChromeClient final : public EmptyChromeClient {
    WTF_MAKE_TZONE_ALLOCATED_INLINE(RvChromeClient);
public:
    RvHost* host { nullptr };
    bool isEmptyChromeClient() const final { return false; }

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
    void setCursor(const Cursor&) final;
    void mouseDidMoveOverElement(const HitTestResult&, OptionSet<PlatformEventModifier>, const String& toolTip, TextDirection) final;
    RefPtr<PopupMenu> createPopupMenu(PopupMenuClient&) const final;
#if USE(AX_EMBEDDER_NOTIFICATIONS)
    void postAccessibilityNotification(AccessibilityObject&, AXNotification) final;
#endif
    void invalidate(const IntRect&);
    void wantUpdate();
};

// The RV_CURSOR_* value of a WebCore cursor.
static int32_t cursorValue(Cursor::Type type)
{
    using enum Cursor::Type;
    switch (type) {
    case Hand: return RV_CURSOR_POINTER;
    case IBeam: return RV_CURSOR_TEXT;
    case VerticalText: return RV_CURSOR_VERTICAL_TEXT;
    case Cross: return RV_CURSOR_CROSSHAIR;
    case Move: return RV_CURSOR_MOVE;
    case MiddlePanning:
    case EastPanning:
    case NorthPanning:
    case NorthEastPanning:
    case NorthWestPanning:
    case SouthPanning:
    case SouthEastPanning:
    case SouthWestPanning:
    case WestPanning: return RV_CURSOR_ALL_SCROLL;
    case Wait: return RV_CURSOR_WAIT;
    case Progress: return RV_CURSOR_PROGRESS;
    case Help: return RV_CURSOR_HELP;
    case ContextMenu: return RV_CURSOR_CONTEXT_MENU;
    case Cell: return RV_CURSOR_CELL;
    case Alias: return RV_CURSOR_ALIAS;
    case Copy: return RV_CURSOR_COPY;
    case NoDrop: return RV_CURSOR_NO_DROP;
    case NotAllowed: return RV_CURSOR_NOT_ALLOWED;
    case Grab: return RV_CURSOR_GRAB;
    case Grabbing: return RV_CURSOR_GRABBING;
    case ZoomIn: return RV_CURSOR_ZOOM_IN;
    case ZoomOut: return RV_CURSOR_ZOOM_OUT;
    case None: return RV_CURSOR_NONE;
    case ColumnResize: return RV_CURSOR_COL_RESIZE;
    case RowResize: return RV_CURSOR_ROW_RESIZE;
    case NorthResize: return RV_CURSOR_N_RESIZE;
    case EastResize: return RV_CURSOR_E_RESIZE;
    case SouthResize: return RV_CURSOR_S_RESIZE;
    case WestResize: return RV_CURSOR_W_RESIZE;
    case NorthEastResize: return RV_CURSOR_NE_RESIZE;
    case NorthWestResize: return RV_CURSOR_NW_RESIZE;
    case SouthEastResize: return RV_CURSOR_SE_RESIZE;
    case SouthWestResize: return RV_CURSOR_SW_RESIZE;
    case EastWestResize: return RV_CURSOR_EW_RESIZE;
    case NorthSouthResize: return RV_CURSOR_NS_RESIZE;
    case NorthEastSouthWestResize: return RV_CURSOR_NESW_RESIZE;
    case NorthWestSouthEastResize: return RV_CURSOR_NWSE_RESIZE;
    case Custom: return RV_CURSOR_CUSTOM;
    case Invalid:
    case Pointer: return RV_CURSOR_DEFAULT;
    }
    return RV_CURSOR_DEFAULT;
}

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
// Runs an RV_EDIT_* command for the page's host; defined with rv_host_edit.
static int32_t runEdit(Page*, int32_t command);

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
            // Control+C, X and V run the host's clipboard commands, in the host's clipboard style.
            if (event.ctrlKey() && event.key().length() == 1) {
                auto letter = toASCIILower(event.key()[0]);
                auto clipboard = letter == 'c' ? RV_EDIT_COPY : letter == 'x' ? RV_EDIT_CUT : letter == 'v' ? (event.shiftKey() ? RV_EDIT_PASTE_PLAIN : RV_EDIT_PASTE) : -1;
                if (clipboard >= 0) {
                    if (runEdit(frame->page(), clipboard) > 0)
                        event.setDefaultHandled();
                    return;
                }
            }
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

// The host whose rv_host_mouse call is running; the drag client reads it, having no page of its own.
static RvHost* inputHost;

// Hands drags out of the page to the app's drag start callback, in the App drag style.
class RvDragClient final : public DragClient {
    void willPerformDragDestinationAction(DragDestinationAction, const DragData&) final { }
    void willPerformDragSourceAction(DragSourceAction, const IntPoint&, DataTransfer&) final { }
    OptionSet<DragSourceAction> dragSourceActionMaskForPoint(const IntPoint&) final;
    void startDrag(DragItem, DataTransfer&, Frame&, const std::optional<NodeIdentifier>&) final;
};

// Hands each form submission to the host's form submission handler instead of scheduling it, so the document is never
// navigated or unloaded; every other navigation keeps the empty client's behaviour.
class RvFrameLoaderClient final : public EmptyFrameLoaderClient {
public:
    explicit RvFrameLoaderClient(FrameLoader& loader)
        : EmptyFrameLoaderClient(loader)
    {
    }

private:
    bool shouldScheduleFormSubmission(FormSubmission&) final;
};

// createPage and loadHTML follow WebCore's testing/TestPage.cpp (Copyright (C) 2026 Apple Inc., BSD-2-Clause).
// The orientation a host's screen reports, which rv_host_set_screen sets. Locking is not supported: the page's
// ScreenOrientationLockingAPIEnabled setting stays off, and a lock that reaches the manager fails.
class RvScreenOrientationManager final : public ScreenOrientationManager, public RefCounted<RvScreenOrientationManager> {
    WTF_MAKE_TZONE_ALLOCATED_INLINE(RvScreenOrientationManager);
public:
    static Ref<RvScreenOrientationManager> create() { return adoptRef(*new RvScreenOrientationManager); }
    void ref() const final { RefCounted::ref(); }
    void deref() const final { RefCounted::deref(); }

    void setOrientation(ScreenOrientationType orientation)
    {
        if (orientation == m_orientation)
            return;
        m_orientation = orientation;
        for (auto& weakObserver : copyToVector(m_observers)) {
            if (RefPtr observer = weakObserver.get())
                observer->screenOrientationDidChange(orientation);
        }
    }

private:
    ScreenOrientationType currentOrientation() final { return m_orientation; }
    void lock(ScreenOrientationLockType, CompletionHandler<void(std::optional<Exception>&&)>&& completion) final
    {
        completion(Exception { ExceptionCode::NotSupportedError, "Screen orientation locking is not supported."_s });
    }
    void unlock() final { }
    void addObserver(ScreenOrientationManagerObserver& observer) final { m_observers.add(observer); }
    void removeObserver(ScreenOrientationManagerObserver& observer) final { m_observers.remove(observer); }

    ScreenOrientationType m_orientation { ScreenOrientationType::LandscapePrimary };
    WeakHashSet<ScreenOrientationManagerObserver> m_observers;
};

static Ref<Page> createPage(IntSize viewportSize, RvScreenOrientationManager& orientation)
{
    static bool prewarmed = [] {
        ProcessWarming::prewarmGlobally();
        return true;
    }();
    UNUSED_VARIABLE(prewarmed);
    auto configuration = pageConfigurationWithEmptyClients(std::nullopt, PAL::SessionID::defaultSessionID());
    // The empty clients' sandbox, except that forms may submit: a submission reaches RvFrameLoaderClient.
    configuration.mainFrameCreationParameters = PageConfiguration::LocalMainFrameCreationParameters { CompletionHandler<UniqueRef<LocalFrameLoaderClient>(LocalFrame&, FrameLoader&)> { [](auto&, auto& loader) -> UniqueRef<LocalFrameLoaderClient> {
        return makeUniqueRefWithoutRefCountedCheck<RvFrameLoaderClient>(loader);
    } }, SandboxFlags::all() - SandboxFlag::Forms, ReferrerPolicy::EmptyString };
    configuration.chromeClient = makeUniqueRef<RvChromeClient>();
    configuration.editorClient = makeUniqueRef<RvEditorClient>();
    configuration.dragClient = makeUnique<RvDragClient>();
    configuration.screenOrientationManager = orientation;
    Ref page = Page::create(WTF::move(configuration));
    page->settings().setScriptEnabled(false);
    page->settings().setScrollAnimatorEnabled(false);
    page->settings().setAcceleratedCompositingEnabled(false);
    page->settings().setLoadsImagesAutomatically(true);
    page->settings().setDataListElementEnabled(true);
    page->settings().setDownloadAttributeEnabled(true);
    page->settings().setCSSFontFaceMetricOverrideDescriptorsEnabled(true);
    page->settings().setCSSAnchorPositioningEnabled(true);
    page->settings().setPopoverHintEnabled(true);
    page->settings().setScreenOrientationAPIEnabled(true);
    page->settings().setVisualViewportAPIEnabled(true);
    page->settings().setInteractiveFormValidationEnabled(true);
    // Markup arrives decoded, so the document's encoding, which form submission and URL query encoding use, is UTF-8.
    page->settings().setDefaultTextEncodingName("UTF-8"_s);
#if ENABLE(VIDEO)
    page->settings().setMediaEnabled(false);
#endif
    RefPtr frame = page->localMainFrame();
    RELEASE_ASSERT(frame);
    frame->setView(LocalFrameView::create(*frame, viewportSize));
    frame->init();
    return page;
}

static void loadDocument(LocalFrame& frame, const String& markup, const String& mimeType)
{
    RefPtr activeDocumentLoader = frame.loader().activeDocumentLoader();
    ASSERT(activeDocumentLoader);
    auto& writer = activeDocumentLoader->writer();
    writer.setMIMEType(mimeType);
    writer.begin();
    if (mimeType == "text/html"_s)
        writer.insertDataSynchronously(markup);
    else {
        Ref parser = *frame.document()->parser();
        parser->appendSynchronously(RefPtr { markup.impl() });
    }
    writer.end();
    if (RefPtr document = frame.document())
        document->updateLayoutIgnorePendingStylesheets();
}

static void loadHTML(LocalFrame& frame, const String& html)
{
    loadDocument(frame, html, "text/html"_s);
}

#if RANVIER_COMPOSITING
// The GL context every host composites in, created on first use and kept for the process's lifetime. WebKit
// has one per compositing thread, and BitmapTexturePool, which is process-wide, hands a texture made in one
// context to whichever context paints next.
static GLContext* compositingContext()
{
    static GLContext* context = GLContext::create(PlatformDisplay::sharedDisplay().glDisplay(), GLContext::Target::Default).release();
    return context;
}

// Composites the page's GraphicsLayerTextureMapper tree in this process, the way WebKit's
// LayerTreeHostTextureMapper does, but into an offscreen framebuffer that paint reads back.
//
// As there, a root layer of the host's own paints the frame's content that has no layer of its own, under
// the compositor's tree: on the Windows port the frame's root layer paints into the window, not into a
// layer (RenderLayerBacking::paintsIntoWindow).
struct RvCompositor final : GraphicsLayerClient {
    GLContext* context { nullptr };
    std::unique_ptr<TextureMapper> textureMapper;
    RefPtr<GraphicsLayer> root;
    // The compositor's root layer, a child of root; and the view root paints, during composite.
    GraphicsLayer* attached { nullptr };
    LocalFrameView* view { nullptr };
    IntSize size;
    GLuint texture { 0 };
    GLuint depthStencil { 0 };
    GLuint framebuffer { 0 };

    static std::unique_ptr<RvCompositor> create(IntSize size)
    {
        auto compositor = std::make_unique<RvCompositor>();
        compositor->size = size;
        compositor->context = compositingContext();
        if (!compositor->context || !compositor->context->makeContextCurrent())
            return nullptr;
        // The TextureMapper takes its shaders and limits from the current context.
        compositor->textureMapper = TextureMapper::create();
        compositor->root = GraphicsLayer::create(nullptr, *compositor);
        compositor->root->setDrawsContent(true);
        compositor->root->setContentsOpaque(true);
        compositor->root->setSize(FloatSize { size });
        glGenTextures(1, &compositor->texture);
        glBindTexture(GL_TEXTURE_2D, compositor->texture);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size.width(), size.height(), 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glBindTexture(GL_TEXTURE_2D, 0);
        // TextureMapper clips with the stencil buffer and sorts 3D planes with the depth buffer.
        glGenRenderbuffers(1, &compositor->depthStencil);
        glBindRenderbuffer(GL_RENDERBUFFER, compositor->depthStencil);
        glRenderbufferStorage(GL_RENDERBUFFER, 0x88F0 /* GL_DEPTH24_STENCIL8_OES */, size.width(), size.height());
        glGenFramebuffers(1, &compositor->framebuffer);
        glBindFramebuffer(GL_FRAMEBUFFER, compositor->framebuffer);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, compositor->texture, 0);
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, compositor->depthStencil);
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_STENCIL_ATTACHMENT, GL_RENDERBUFFER, compositor->depthStencil);
        bool complete = glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE;
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        return complete ? WTF::move(compositor) : nullptr;
    }

    void paintContents(const GraphicsLayer&, GraphicsContext& context, const FloatRect& clip, OptionSet<GraphicsLayerPaintBehavior>) final
    {
        if (!view)
            return;
        context.save();
        context.clip(clip);
        view->paint(context, enclosingIntRect(clip));
        context.restore();
    }

    ~RvCompositor()
    {
        if (!context || !context->makeContextCurrent())
            return;
        if (root)
            root->removeAllChildren();
        root = nullptr;
        textureMapper = nullptr;
        glDeleteFramebuffers(1, &framebuffer);
        glDeleteRenderbuffers(1, &depthStencil);
        glDeleteTextures(1, &texture);
    }
};
#endif

struct RvHost {
    Ref<Page> page;
    IntSize size;
    std::optional<JSC::DisallowVMEntry> noScript;
    RvResourceHandler resourceHandler { nullptr };
    void* resourceContext { nullptr };
    RvFormSubmissionHandler formSubmissionHandler { nullptr };
    void* formSubmissionContext { nullptr };
#if RANVIER_COMPOSITING
    // rv_host_create sets RV_COMPOSITING_WHEN_NEEDED.
    int32_t compositingMode { RV_COMPOSITING_OFF };
    // Created on the first frame that composites, so a page that never needs a layer never creates a GL context.
    std::unique_ptr<RvCompositor> compositor;
#if defined(_WIN32)
    std::shared_ptr<RvD3D11Surface> presentationSurface;
#endif
#endif
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
    int32_t cursor { RV_CURSOR_DEFAULT };
    String tooltip;
    RvPopupCallback popupCallback { nullptr };
    void* popupContext { nullptr };
    int32_t clipboardStyle { RV_CLIPBOARD_DOM };
    RvClipboardWrite clipboardWrite { nullptr };
    RvClipboardRead clipboardRead { nullptr };
    void* clipboardContext { nullptr };
    int32_t dragStyle { RV_DRAG_DOM };
    // The element under a drag from outside, which received dragenter.
    RefPtr<Element> dragTarget;
    // Where the last mouse press was, in CSS pixels of the viewport: where a drag out of the page starts.
    IntPoint pressPoint;
    RvDragStartCallback dragStartCallback { nullptr };
    void* dragStartContext { nullptr };
    bool accessibility { false };
    // rv_host_set_diagnostics: the rv_host_inspect_* calls read the document only while set.
    bool diagnostics { false };
    RvAxCallback axCallback { nullptr };
    void* axContext { nullptr };
    // Accessibility events posted since the last delivery, and whether a delivery is scheduled.
    Vector<std::pair<Ref<AXCoreObject>, int32_t>> axPending;
    bool axDeliveryScheduled { false };

    Document& document() { return *page->localTopDocument(); }
    LocalFrame& frame() { return *page->localMainFrame(); }

    RefPtr<RvScreenOrientationManager> orientation;
    // The display the page's screen data belongs to, unique to the host.
    PlatformDisplayID displayID { 0 };
    // The app's screen, from rv_host_set_screen; until then the screen follows the host size.
    std::optional<ScreenData> screen;

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

void RvChromeClient::setCursor(const Cursor& cursor)
{
    if (host)
        host->cursor = cursorValue(cursor.type());
}

void RvChromeClient::mouseDidMoveOverElement(const HitTestResult&, OptionSet<PlatformEventModifier>, const String& toolTip, TextDirection)
{
    if (host)
        host->tooltip = toolTip;
}

// A <select>'s menu, shown by the app's popup handler. It holds a reference to itself while shown, which
// rv_popup_choose or a hide releases.
class RvPopupMenu final : public PopupMenu {
public:
    RvPopupMenu(RvHost* host, PopupMenuClient& client)
        : host(host)
        , client(&client)
    {
    }

    RvHost* host;
    PopupMenuClient* client;
    bool shown { false };

    void end()
    {
        if (!shown)
            return;
        shown = false;
        deref();
    }

private:
    void show(const IntRect& rect, LocalFrameView& view, int selectedIndex) final
    {
        if (shown || !host || !host->popupCallback)
            return;
        auto box = view.contentsToRootView(rect);
        shown = true;
        ref();
        host->popupCallback(host->popupContext, reinterpret_cast<RvPopup*>(this), RV_POPUP_SHOW, box.x(), box.y(), box.width(), box.height(), selectedIndex);
    }

    void hide() final
    {
        if (!shown)
            return;
        Ref protectedThis { *this };
        if (host && host->popupCallback)
            host->popupCallback(host->popupContext, reinterpret_cast<RvPopup*>(this), RV_POPUP_HIDE, 0, 0, 0, 0, -1);
        if (client)
            client->popupDidHide();
        end();
    }

    void updateFromElement() final { }
    void disconnectClient() final { client = nullptr; }
};

// Without a popup handler, or a host, the menu shows nothing, as WebCore's empty popup menu.
RefPtr<PopupMenu> RvChromeClient::createPopupMenu(PopupMenuClient& client) const
{
    return adoptRef(*new RvPopupMenu(host, client));
}

void RvChromeClient::wantUpdate()
{
    if (!host)
        return;
    host->updateWanted = true;
    host->requestFrame();
}

static bool onOwningThread() { return isMainThread(); }

static bool segmentationInitialized;

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

// Each form's planned submission: a later submission of the form replaces a pending one, as a later planned navigation
// replaces an earlier one. A pending task holds its form, so the address identifies the form until the task runs.
static HashMap<const HTMLFormElement*, uint64_t>& plannedSubmissions()
{
    static NeverDestroyed<HashMap<const HTMLFormElement*, uint64_t>> planned;
    return planned;
}

// Copies the submission and posts it to the host's handler, so the submitting call returns before any app code runs.
bool RvFrameLoaderClient::shouldScheduleFormSubmission(FormSubmission& submission)
{
    RefPtr state = submission.state();
    if (!state)
        return false;
    static uint64_t lastPlan;
    uint64_t plan = ++lastPlan;
    plannedSubmissions().set(&state->form(), plan);
    bool post = submission.method() == FormSubmission::Method::Post;
    auto contentType = !post ? String { } : submission.boundary().isEmpty() ? submission.contentType() : makeString(submission.contentType(), "; boundary="_s, submission.boundary());
    // FormSubmission::requestURL, which WebCore does not export; a GET entry list is ASCII.
    URL url = submission.action();
    if (!post && !url.protocolIsJavaScript())
        url.setQuery(String { byteCast<Latin1Character>(submission.data().flatten().span()) });
    RunLoop::mainSingleton().dispatch([document = Ref { state->sourceDocument() }, form = Ref { state->form() }, submitter = RefPtr<Element> { state->submitter() },
        method = CString { post ? "POST" : "GET" }, url = url.string().utf8(), target = submission.target().string().utf8(),
        contentType = contentType.utf8(), hasContentType = post, bytes = post ? submission.data().flatten() : Vector<uint8_t> { }, plan] {
        auto planned = plannedSubmissions().find(form.ptr());
        if (planned == plannedSubmissions().end() || planned->value != plan)
            return;
        plannedSubmissions().remove(planned);
        auto* host = hostForPage(document->page());
        if (!host || !host->formSubmissionHandler || &host->document() != document.ptr())
            return;
        RvFormSubmission copy { sizeof(RvFormSubmission), method.data(), url.data(), target.data(), hasContentType ? contentType.data() : nullptr,
            bytes.span().data(), static_cast<int32_t>(bytes.size()), reinterpret_cast<RvNode*>(form.ptr()), reinterpret_cast<RvNode*>(submitter.get()) };
        host->formSubmissionHandler(host->formSubmissionContext, &copy);
    });
    return false;
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

// Hands each load to its host's resource handler on a later run loop cycle; data: and blob: URLs load in WebCore.
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
    // data: and blob: URLs load in WebCore: blob: through the blob registry's BlobResourceHandle.
    static void schedule(SubresourceLoader& loader)
    {
        if (loader.request().url().protocolIsData() || loader.request().url().protocolIsBlob()) {
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

// The blob registry follows WebKitLegacy's WebBlobRegistry (Source/WebKitLegacy/mac/WebCoreSupport/
// WebPlatformStrategies.mm, Copyright (C) 2010-2026 Apple Inc., BSD-2-Clause): the in-process BlobRegistryImpl
// holds every blob's data on the main thread.
class RvBlobRegistry final : public BlobRegistry {
    WTF_MAKE_TZONE_ALLOCATED(RvBlobRegistry);
    WTF_OVERRIDE_DELETE_FOR_CHECKED_PTR(RvBlobRegistry);
public:
    void registerInternalFileBlobURL(const URL& url, Ref<BlobDataFileReference>&& reference, const String&, const String& contentType) final { m_registry.registerInternalFileBlobURL(url, WTF::move(reference), contentType); }
    void registerInternalBlobURL(const URL& url, Vector<BlobPart>&& parts, const String& contentType) final { m_registry.registerInternalBlobURL(url, WTF::move(parts), contentType); }
    void registerBlobURL(const URL& url, const URL& source, const PolicyContainer& policy, const std::optional<SecurityOriginData>& topOrigin) final { m_registry.registerBlobURL(url, source, policy, topOrigin); }
    void registerInternalBlobURLOptionallyFileBacked(const URL& url, const URL& source, RefPtr<BlobDataFileReference>&& reference, const String& contentType) final { m_registry.registerInternalBlobURLOptionallyFileBacked(url, source, WTF::move(reference), contentType, { }); }
    void registerInternalBlobURLForSlice(const URL& url, const URL& source, long long start, long long end, const String& contentType) final { m_registry.registerInternalBlobURLForSlice(url, source, start, end, contentType); }
    void unregisterBlobURL(const URL& url, const std::optional<SecurityOriginData>& topOrigin) final { m_registry.unregisterBlobURL(url, topOrigin); }
    void registerBlobURLHandle(const URL& url, const std::optional<SecurityOriginData>& topOrigin) final { m_registry.registerBlobURLHandle(url, topOrigin); }
    void unregisterBlobURLHandle(const URL& url, const std::optional<SecurityOriginData>& topOrigin) final { m_registry.unregisterBlobURLHandle(url, topOrigin); }
    String blobType(const URL& url) final { return m_registry.blobType(url); }
    unsigned long long blobSize(const URL& url) final { return m_registry.blobSize(url); }
    void writeBlobsToTemporaryFilesForIndexedDB(const Vector<String>& urls, CompletionHandler<void(Vector<String>&&)>&& completion) final { m_registry.writeBlobsToTemporaryFilesForIndexedDB(urls, WTF::move(completion)); }
    BlobRegistryImpl* blobRegistryImpl() final { return &m_registry; }

private:
    BlobRegistryImpl m_registry;
};

WTF_MAKE_TZONE_ALLOCATED_IMPL(RvBlobRegistry);

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

// The NodeFilters rv_node_filter_create made that are still alive.
static HashSet<const NodeFilter*>& hostNodeFilters()
{
    static NeverDestroyed<HashSet<const NodeFilter*>> filters;
    return filters;
}

class RvHostNodeFilter final : public NodeFilter {
public:
    static Ref<RvHostNodeFilter> create(Document& document, RvNodeFilterCallback callback, void* context, RvNodeFilterRelease release)
    {
        return adoptRef(*new RvHostNodeFilter(document, callback, context, release));
    }

    ~RvHostNodeFilter()
    {
        hostNodeFilters().remove(this);
        if (m_release)
            m_release(m_context);
    }

    void* context() const { return m_context; }

private:
    RvHostNodeFilter(Document& document, RvNodeFilterCallback callback, void* context, RvNodeFilterRelease release)
        : NodeFilter(&document)
        , m_callback(callback)
        , m_context(context)
        , m_release(release)
    {
        hostNodeFilters().add(this);
    }

    CallbackResult<unsigned short> acceptNode(Node& node) final { return acceptNodeRethrowingException(node); }

    CallbackResult<unsigned short> acceptNodeRethrowingException(Node& node) final
    {
        if (!canInvokeCallback())
            return CallbackResultType::ExceptionThrown;
        Ref protectedNode { node };
        auto result = m_callback(m_context, reinterpret_cast<RvNode*>(&node));
        if (result < FILTER_ACCEPT || result > FILTER_SKIP)
            return CallbackResultType::ExceptionThrown;
        return static_cast<unsigned short>(result);
    }

    bool hasCallback() const final { return true; }

    RvNodeFilterCallback m_callback;
    void* m_context;
    RvNodeFilterRelease m_release;
};

struct RvListener {
    Ref<RvEventListener> listener;
    Ref<EventTarget> target;
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

// The exception of the latest call that returned RV_ERR_DOM_EXCEPTION, on the owning thread, is kept in WebCore
// with the generated functions' (host/dom/RanvierDomGlue.h), so rv_last_exception reports either.
static int32_t fail(const Exception& exception) { return Ranvier::recordException(exception); }

template<typename T> static int32_t status(const ExceptionOr<T>& result) { return result.hasException() ? fail(result.exception()) : RV_OK; }

// The layouts tests/abi/abi_layouts.py checks from ctypes and the F# interop declares.
static_assert(sizeof(void*) != 8 || (sizeof(RvFormSubmission) == 72 && offsetof(RvFormSubmission, method) == 8 && offsetof(RvFormSubmission, content_type) == 32
    && offsetof(RvFormSubmission, body_length) == 48 && offsetof(RvFormSubmission, form) == 56 && offsetof(RvFormSubmission, submitter) == 64));
static_assert(sizeof(void*) != 8 || (sizeof(RvTextSegments) == 32 && offsetof(RvTextSegments, starts) == 8 && offsetof(RvTextSegments, locale) == 24));
static_assert(sizeof(void*) != 8 || (sizeof(RvEventInit) == 112 && offsetof(RvEventInit, screenX) == 24 && offsetof(RvEventInit, key) == 64
    && offsetof(RvEventInit, relatedTarget) == 96 && offsetof(RvEventInit, customDetailJson) == 104));
static_assert(sizeof(RvScreenMetrics) == 36 && offsetof(RvScreenMetrics, avail_left) == 12 && offsetof(RvScreenMetrics, orientation) == 32);


static_assert(sizeof(RvWindowMetrics) == 32 && offsetof(RvWindowMetrics, outerHeight) == 16 && offsetof(RvWindowMetrics, devicePixelRatio) == 24);

int32_t rv_abi_version(void) { return 54; }

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
    if (!std::strcmp(feature, "screen"))
        return 1;
    if (!std::strcmp(feature, "capabilities"))
        return 1;
    if (!std::strcmp(feature, "svg-view-selection"))
        return 1;
    if (!std::strcmp(feature, "image-decode"))
        return 1;
    if (!std::strcmp(feature, "font-load"))
        return 1;
    if (!std::strcmp(feature, "event-construction"))
        return 1;
    if (!std::strcmp(feature, "input-state"))
        return 1;
    if (!std::strcmp(feature, "viewport"))
        return 1;
    if (!std::strcmp(feature, "dom-binary-values"))
        return 1;
    if (!std::strcmp(feature, "accessibility-relations"))
        return 1;
    if (!std::strcmp(feature, "coordinate-spaces"))
        return 1;
    if (!std::strcmp(feature, "page-scale"))
        return 1;
    if (!std::strcmp(feature, "obscured-insets"))
        return 1;
    if (!std::strcmp(feature, "form-submission"))
        return 1;
    if (!std::strcmp(feature, "text-segmentation"))
        return 1;
    if (!std::strcmp(feature, "diagnostics"))
        return 1;
    if (!std::strcmp(feature, "cascade-diagnostics"))
        return 1;
#if defined(_WIN32)
    if (!std::strcmp(feature, "accessibility-uia"))
        return 1;
#endif
    for (auto* name : { "resize", "input", "frame", "event-details", "cursor", "scroll", "ime", "style", "geometry", "animation", "shadow", "text-selection", "observers", "snapshot", "partial-paint", "popups", "tooltip", "clipboard", "drop", "drag-out", "accessibility", "accessibility-text", "svg-document" }) {
        if (!std::strcmp(feature, name))
            return 1;
    }
#if RANVIER_COMPOSITING
    if (!std::strcmp(feature, "compositing"))
        return 1;
#if defined(_WIN32)
    if (!std::strcmp(feature, "presentation-d3d11"))
        return 1;
#endif
#endif
    // "dom-generated" and "dom:<Interface>": the generated functions of RanvierWebCoreDom.h.
    if (ranvier_dom_has(feature))
        return 1;
#if USE(AX_EMBEDDER_NOTIFICATIONS)
    // WebCore hands its accessibility notifications to the host (patch 0011).
    if (!std::strcmp(feature, "accessibility-events"))
        return 1;
#endif
    return 0;
}

#include "RanvierCapabilities.inc"

int64_t rv_process_id(void) { return static_cast<int64_t>(getCurrentProcessID()); }

#if RANVIER_COMPOSITING
static void applyCompositingMode(RvHost& host, int32_t mode)
{
    // Without ForceCompositingMode, WebCore enters compositing mode only while some element needs a layer of its
    // own (RenderLayerCompositor), and the frame then has a clip layer.
    host.compositingMode = mode;
    host.page->settings().setAcceleratedCompositingEnabled(mode != RV_COMPOSITING_OFF);
    host.page->settings().setForceCompositingMode(mode == RV_COMPOSITING_ALWAYS);
}
#endif

// The screen of a host without one from rv_host_set_screen: the host's size in CSS pixels, all of it available,
// 24 bits deep, landscape-primary unless taller than wide.
static ScreenData defaultScreen(const RvHost& host)
{
    ScreenData data;
    data.screenRect = FloatRect { { }, host.size };
    data.screenAvailableRect = data.screenRect;
    data.screenDepth = 24;
    data.screenDepthPerComponent = 8;
    return data;
}

// Sets the screen data of every live host's display, which WebCore's PlatformScreen reports.
static void publishScreens()
{
    ScreenProperties properties;
    for (auto* live : liveHosts) {
        auto data = live->screen.value_or(defaultScreen(*live));
        if (!live->screen)
            live->orientation->setOrientation(data.screenRect.height() > data.screenRect.width()
                ? ScreenOrientationType::PortraitPrimary : ScreenOrientationType::LandscapePrimary);
        properties.screenDataMap.set(live->displayID, WTF::move(data));
        if (!properties.primaryDisplayID)
            properties.primaryDisplayID = live->displayID;
    }
    PlatformScreen::updateSingletonProperties(WTF::move(properties));
}

int32_t rv_host_set_screen(RvHost* host, const RvScreenMetrics* metrics)
{
    if (!host || !metrics)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (metrics->size < sizeof(RvScreenMetrics) || metrics->width <= 0 || metrics->height <= 0 || metrics->avail_width < 0
        || metrics->avail_height < 0 || metrics->color_depth <= 0 || metrics->color_depth > 64
        || metrics->orientation < RV_SCREEN_PORTRAIT_PRIMARY || metrics->orientation > RV_SCREEN_LANDSCAPE_SECONDARY)
        return RV_ERR_UNSUPPORTED;
    ScreenData data;
    data.screenRect = FloatRect { 0, 0, static_cast<float>(metrics->width), static_cast<float>(metrics->height) };
    data.screenAvailableRect = FloatRect { static_cast<float>(metrics->avail_left), static_cast<float>(metrics->avail_top),
        static_cast<float>(metrics->avail_width), static_cast<float>(metrics->avail_height) };
    data.screenDepth = metrics->color_depth;
    data.screenDepthPerComponent = metrics->color_depth / 3;
    host->screen = WTF::move(data);
    publishScreens();
    host->page->screenPropertiesDidChange();
    host->orientation->setOrientation(static_cast<ScreenOrientationType>(metrics->orientation));
    return RV_OK;
}

struct RvDiagnosticEntry {
    double numbers[RV_CASCADE_NUMBER_FIELDS] { };
    std::string strings[RV_CASCADE_STRING_FIELDS];
};

struct RvDiagnostic {
    int32_t kind;
    std::string text;
    std::vector<RvDiagnosticEntry> entries;
};

static std::atomic<int32_t> liveDiagnostics;

static int32_t copyBytes(const std::string& value, char* buffer, int32_t capacity, int32_t* length)
{
    if (!length)
        return RV_ERR_NULL_ARGUMENT;
    *length = static_cast<int32_t>(value.size());
    if (!buffer || capacity < *length)
        return RV_ERR_BUFFER_TOO_SMALL;
    std::memcpy(buffer, value.data(), value.size());
    return RV_OK;
}

// RV_OK when the host is live, on its thread and has diagnostics enabled.
static int32_t diagnosticsAllowed(RvHost* host)
{
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host) || !host->diagnostics)
        return RV_ERR_UNSUPPORTED;
    return RV_OK;
}

static RvDiagnostic* newDiagnostic(int32_t kind)
{
    auto* diagnostic = new RvDiagnostic { kind, { }, { } };
    ++liveDiagnostics;
    return diagnostic;
}

int32_t rv_host_set_diagnostics(RvHost* host, int32_t enabled)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host) || (enabled != 0 && enabled != 1))
        return RV_ERR_UNSUPPORTED;
    host->diagnostics = enabled;
    return RV_OK;
}

int32_t rv_host_inspect_render_tree(RvHost* host, RvNode* target, int32_t flags, RvDiagnostic** diagnostic)
{
    if (!host || !diagnostic)
        return RV_ERR_NULL_ARGUMENT;
    if (auto allowed = diagnosticsAllowed(host))
        return allowed;
    constexpr int32_t known = RV_RENDER_TREE_ALL_LAYERS | RV_RENDER_TREE_LAYER_NESTING | RV_RENDER_TREE_OVERFLOW
        | RV_RENDER_TREE_SVG_GEOMETRY | RV_RENDER_TREE_ID_AND_CLASS | RV_RENDER_TREE_LAYOUT_STATE;
    constexpr int32_t layers = RV_RENDER_TREE_ALL_LAYERS | RV_RENDER_TREE_LAYER_NESTING;
    auto* document = reinterpret_cast<RvNode*>(&host->document());
    bool element = target && target != document;
    if (flags & ~known || (element && (flags & layers)))
        return RV_ERR_UNSUPPORTED;
    std::string text;
    auto status = ranvier_inspect_render_tree(document, target, flags, [](void* context, const char* bytes, int32_t length) {
        static_cast<std::string*>(context)->assign(bytes, length);
    }, &text);
    if (status)
        return status;
    auto* result = newDiagnostic(RV_DIAGNOSTIC_RENDER_TREE);
    result->text = WTF::move(text);
    *diagnostic = result;
    return RV_OK;
}

int32_t rv_host_inspect_matched_rules(RvHost* host, RvNode* element, RvDiagnostic** diagnostic)
{
    if (!host || !element || !diagnostic)
        return RV_ERR_NULL_ARGUMENT;
    if (auto allowed = diagnosticsAllowed(host))
        return allowed;
    std::vector<RvDiagnosticEntry> entries;
    auto status = ranvier_inspect_matched_rules(reinterpret_cast<RvNode*>(&host->document()), element, [](void* context, const RanvierInspectRule* rule) {
        RvDiagnosticEntry entry;
        entry.numbers[RV_RULE_ORIGIN] = rule->origin;
        entry.numbers[RV_RULE_SPECIFICITY_A] = rule->specificity[0];
        entry.numbers[RV_RULE_SPECIFICITY_B] = rule->specificity[1];
        entry.numbers[RV_RULE_SPECIFICITY_C] = rule->specificity[2];
        entry.numbers[RV_RULE_SELECTOR_COUNT] = rule->selectorCount;
        entry.numbers[RV_RULE_MATCHED_SELECTOR_COUNT] = rule->matchedSelectorCount;
        entry.strings[RV_RULE_SELECTOR_TEXT].assign(rule->selectorText ? rule->selectorText : "", rule->selectorTextLength);
        entry.strings[RV_RULE_MATCHED_SELECTOR].assign(rule->matchedSelector ? rule->matchedSelector : "", rule->matchedSelectorLength);
        entry.strings[RV_RULE_DECLARATIONS].assign(rule->declarations ? rule->declarations : "", rule->declarationsLength);
        static_cast<std::vector<RvDiagnosticEntry>*>(context)->push_back(WTF::move(entry));
    }, &entries);
    if (status)
        return status;
    auto* result = newDiagnostic(RV_DIAGNOSTIC_MATCHED_RULES);
    result->entries = WTF::move(entries);
    *diagnostic = result;
    return RV_OK;
}

int32_t rv_host_inspect_cascade(RvHost* host, RvNode* element, const uint8_t* property, int32_t property_length, RvDiagnostic** diagnostic)
{
    if (!host || !element || !property || !diagnostic)
        return RV_ERR_NULL_ARGUMENT;
    if (auto allowed = diagnosticsAllowed(host))
        return allowed;
    struct Collected {
        std::string text;
        std::vector<RvDiagnosticEntry> entries;
    } collected;
    auto status = ranvier_inspect_cascade(reinterpret_cast<RvNode*>(&host->document()), element, property, property_length,
        [](void* context, const char* bytes, int32_t length) {
            static_cast<Collected*>(context)->text.assign(bytes, length);
        },
        [](void* context, const RanvierCascadeEntry* source) {
            RvDiagnosticEntry entry;
            std::copy(std::begin(source->numbers), std::end(source->numbers), entry.numbers);
            for (int field = 0; field < RV_CASCADE_STRING_FIELDS; ++field)
                entry.strings[field].assign(source->strings[field] ? source->strings[field] : "", source->lengths[field]);
            static_cast<Collected*>(context)->entries.push_back(WTF::move(entry));
        }, &collected);
    if (status)
        return status;
    auto* result = newDiagnostic(RV_DIAGNOSTIC_CASCADE);
    result->text = WTF::move(collected.text);
    result->entries = WTF::move(collected.entries);
    *diagnostic = result;
    return RV_OK;
}

int32_t rv_host_inspect_box_model(RvHost* host, RvNode* element, double* values)
{
    if (!host || !element || !values)
        return RV_ERR_NULL_ARGUMENT;
    if (auto allowed = diagnosticsAllowed(host))
        return allowed;
    return ranvier_inspect_box_model(reinterpret_cast<RvNode*>(&host->document()), element, values);
}

int32_t rv_diagnostic_kind(RvDiagnostic* diagnostic)
{
    return diagnostic ? diagnostic->kind : RV_ERR_NULL_ARGUMENT;
}

int32_t rv_diagnostic_text(RvDiagnostic* diagnostic, char* buffer, int32_t capacity, int32_t* length)
{
    if (!diagnostic)
        return RV_ERR_NULL_ARGUMENT;
    return copyBytes(diagnostic->text, buffer, capacity, length);
}

int32_t rv_diagnostic_count(RvDiagnostic* diagnostic)
{
    return diagnostic ? static_cast<int32_t>(diagnostic->entries.size()) : RV_ERR_NULL_ARGUMENT;
}

int32_t rv_diagnostic_entry_string(RvDiagnostic* diagnostic, int32_t index, int32_t field, char* buffer, int32_t capacity, int32_t* length)
{
    if (!diagnostic || !length)
        return RV_ERR_NULL_ARGUMENT;
    int32_t fields = diagnostic->kind == RV_DIAGNOSTIC_CASCADE ? RV_CASCADE_STRING_FIELDS : RV_RULE_DECLARATIONS + 1;
    if (index < 0 || static_cast<size_t>(index) >= diagnostic->entries.size() || field < 0 || field >= fields)
        return RV_ERR_UNSUPPORTED;
    return copyBytes(diagnostic->entries[index].strings[field], buffer, capacity, length);
}

int32_t rv_diagnostic_entry_number(RvDiagnostic* diagnostic, int32_t index, int32_t field, double* value)
{
    if (!diagnostic || !value)
        return RV_ERR_NULL_ARGUMENT;
    int32_t fields = diagnostic->kind == RV_DIAGNOSTIC_CASCADE ? RV_CASCADE_NUMBER_FIELDS : RV_RULE_MATCHED_SELECTOR_COUNT + 1;
    if (index < 0 || static_cast<size_t>(index) >= diagnostic->entries.size() || field < 0 || field >= fields)
        return RV_ERR_UNSUPPORTED;
    *value = diagnostic->entries[index].numbers[field];
    return RV_OK;
}

void rv_diagnostic_release(RvDiagnostic* diagnostic)
{
    if (!diagnostic)
        return;
    delete diagnostic;
    --liveDiagnostics;
}

int32_t rv_diagnostic_live_count(void)
{
    return liveDiagnostics.load();
}

RvHost* rv_host_create(int32_t width, int32_t height)
{
    static bool initialized;
    if (!initialized) {
        JSC::initialize();
        WTF::initializeMainThread();
        setPlatformStrategies(new RvPlatformStrategies);
#if PLATFORM(MAC)
        // Overlay scrollbars take no layout width, as on the Adwaita ports and in Chromium.
        DeprecatedGlobalSettings::setUsesOverlayScrollbars(true);
#endif
#if PLATFORM(GTK) || PLATFORM(WPE)
        if (!PlatformDisplay::sharedDisplayIfExists())
            PlatformDisplay::setSharedDisplay(PlatformDisplaySurfaceless::create());
#endif
        initialized = true;
        segmentationInitialized = true;
    }
    if (!onOwningThread() || width <= 0 || height <= 0)
        return nullptr;
    Ref orientation = RvScreenOrientationManager::create();
    auto* host = new RvHost { createPage({ width, height }, orientation), { width, height }, std::nullopt };
    host->orientation = WTF::move(orientation);
    static_cast<RvChromeClient&>(host->page->chrome().client()).host = host;
    static PlatformDisplayID nextDisplayID = 0x52560000;
    host->displayID = ++nextDisplayID;
    ranvier_page_set_display(reinterpret_cast<RvNode*>(&host->document()), host->displayID);
    host->noScript.emplace(host->document().vm());
#if RANVIER_COMPOSITING
    applyCompositingMode(*host, RV_COMPOSITING_WHEN_NEEDED);
#endif
    liveHosts.append(host);
    publishScreens();
    return host;
}

#if RANVIER_COMPOSITING
static void setCompositing(RvHost& host, int32_t mode)
{
    applyCompositingMode(host, mode);
    host.document().updateLayoutIgnorePendingStylesheets();
    if (RefPtr view = host.frame().view())
        view->updateLayoutAndStyleIfNeededRecursive();
}
#endif

int32_t rv_host_set_accelerated_compositing(RvHost* host, int32_t mode)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (mode != RV_COMPOSITING_OFF && mode != RV_COMPOSITING_ALWAYS && mode != RV_COMPOSITING_WHEN_NEEDED)
        return RV_ERR_UNSUPPORTED;
#if RANVIER_COMPOSITING
    if (mode == RV_COMPOSITING_OFF) {
        if (host->compositor) {
            // The layers free their textures in the compositor's context.
            host->compositor->context->makeContextCurrent();
            setCompositing(*host, mode);
            host->compositor = nullptr;
        } else if (host->compositingMode != RV_COMPOSITING_OFF)
            setCompositing(*host, mode);
        return RV_OK;
    }
    if (mode == RV_COMPOSITING_ALWAYS && !host->compositor) {
        auto compositor = RvCompositor::create(host->size);
        if (!compositor)
            return RV_ERR_UNSUPPORTED;
        host->compositor = WTF::move(compositor);
    }
    setCompositing(*host, mode);
    return RV_OK;
#else
    return mode == RV_COMPOSITING_OFF ? RV_OK : RV_ERR_UNSUPPORTED;
#endif
}

void rv_host_destroy(RvHost* host)
{
    if (!host || !onOwningThread())
        return;
    ranvier_resource_invalidate_document(reinterpret_cast<RvNode*>(&host->document()));
    ranvier_event_glue_invalidate_document(reinterpret_cast<RvNode*>(&host->document()));
    rv_host_detach_uia(host);
    rv_host_set_accelerated_compositing(host, RV_COMPOSITING_OFF);
    host->noScript.reset();
    rv_host_set_accessibility(host, 0, nullptr, nullptr);
    static_cast<RvChromeClient&>(host->page->chrome().client()).host = nullptr;
    liveHosts.removeFirst(host);
    delete host;
    publishScreens();
}

int32_t rv_host_load_html(RvHost* host, const char* html)
{
    if (!host || !html)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    ranvier_resource_invalidate_document(reinterpret_cast<RvNode*>(&host->document()));
    ranvier_event_glue_invalidate_document(reinterpret_cast<RvNode*>(&host->document()));
    loadHTML(host->frame(), utf8(html));
    // The new document posts accessibility notifications once its cache exists.
    if (host->accessibility)
        host->document().axObjectCache();
    return RV_OK;
}

int32_t rv_host_load_svg(RvHost* host, const char* svg)
{
    if (!host || !svg)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    ranvier_resource_invalidate_document(reinterpret_cast<RvNode*>(&host->document()));
    ranvier_event_glue_invalidate_document(reinterpret_cast<RvNode*>(&host->document()));
    loadDocument(host->frame(), utf8(svg), "image/svg+xml"_s);
    if (host->accessibility)
        host->document().axObjectCache();
    return RV_OK;
}

int32_t rv_host_select_svg_view(RvHost* host, const char* fragment, int32_t* selected)
{
    if (!host || !fragment || !selected)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host))
        return RV_ERR_UNSUPPORTED;
    return ranvier_host_select_svg_view(reinterpret_cast<RvNode*>(&host->document()), fragment, selected);
}

int32_t rv_image_decode(RvHost* host, RvNode* image, RvResourceCompletion completion, void* context, uint64_t* operation)
{
    if (!host || !image || !completion || !operation)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host))
        return RV_ERR_UNSUPPORTED;
    return ranvier_resource_decode_image(reinterpret_cast<RvNode*>(&host->document()), image, completion, context, operation);
}

int32_t rv_font_load(RvHost* host, const char* family, const uint8_t* data, int32_t length, RvResourceCompletion completion, void* context, uint64_t* operation)
{
    if (!host || !family || (!data && length) || length < 0 || !completion || !operation)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host))
        return RV_ERR_UNSUPPORTED;
    return ranvier_resource_load_font(reinterpret_cast<RvNode*>(&host->document()), family, data, length, completion, context, operation);
}

int32_t rv_resource_cancel(uint64_t operation)
{
    return ranvier_resource_cancel(operation);
}

int32_t rv_resource_release(uint64_t operation)
{
    return ranvier_resource_release(operation);
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

#if RANVIER_COMPOSITING
static int32_t composite(RvCompositor& compositor, LocalFrameView& view, uint8_t* rgba, GLuint targetFramebuffer = 0)
{
    if (!compositor.context->makeContextCurrent())
        return RV_ERR_PAINT_FAILED;
    // The root of the frame's layer tree: RenderLayerCompositor::rootGraphicsLayer is not exported, and the
    // frame's clip layer, which a view without a platform widget always has, is one of its descendants.
    RefPtr<GraphicsLayer> frameRoot = view.clipLayer();
    if (!frameRoot)
        return RV_ERR_PAINT_FAILED;
    while (frameRoot->parent() && frameRoot->parent() != compositor.root.get())
        frameRoot = frameRoot->parent();
    if (compositor.attached != frameRoot.get()) {
        compositor.root->removeAllChildren();
        compositor.root->addChild(*frameRoot);
        compositor.attached = frameRoot.get();
    }
    // The content under the layers is repainted whole each frame.
    compositor.view = &view;
    compositor.root->setNeedsDisplay();
    compositor.root->flushCompositingStateForThisLayerOnly();
    view.flushCompositingStateIncludingSubframes();
    auto& rootLayer = downcast<GraphicsLayerTextureMapper>(*compositor.root);
    rootLayer.updateBackingStoreIncludingSubLayers(*compositor.textureMapper);
    compositor.view = nullptr;

    auto size = compositor.size;
    glBindFramebuffer(GL_FRAMEBUFFER, targetFramebuffer ? targetFramebuffer : compositor.framebuffer);
    glViewport(0, 0, size.width(), size.height());
    glClearColor(0, 0, 0, 0);
    glClearStencil(0);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);
    // FlipY::Yes puts the page's first row at the framebuffer's first row, which glReadPixels returns first.
    compositor.textureMapper->beginPainting(TextureMapper::FlipY::Yes);
    rootLayer.layer().paint(*compositor.textureMapper);
    compositor.textureMapper->endPainting();
    if (!rgba) {
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        return glGetError() == GL_NO_ERROR ? RV_OK : RV_ERR_PAINT_FAILED;
    }
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(0, 0, size.width(), size.height(), GL_RGBA, GL_UNSIGNED_BYTE, rgba);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    if (glGetError() != GL_NO_ERROR)
        return RV_ERR_PAINT_FAILED;
    // The framebuffer holds premultiplied alpha; the ABI returns unpremultiplied.
    size_t count = static_cast<size_t>(size.width()) * size.height();
    for (size_t i = 0; i < count; ++i) {
        uint8_t* pixel = rgba + i * 4;
        uint8_t alpha = pixel[3];
        if (alpha && alpha != 255) {
            for (int c = 0; c < 3; ++c)
                pixel[c] = static_cast<uint8_t>(std::min(255, (pixel[c] * 255 + alpha / 2) / alpha));
        }
    }
    return RV_OK;
}
#endif

struct RvGpuFrame {
#if defined(_WIN32) && RANVIER_COMPOSITING
    std::shared_ptr<RvD3D11Surface> surface;
#endif
};

int32_t rv_host_acquire_d3d11_frame(RvHost* host, void* consumerDevice, RvGpuFrame** frame)
{
    if (!frame)
        return RV_ERR_NULL_ARGUMENT;
    *frame = nullptr;
    if (!host || !consumerDevice)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
#if defined(_WIN32) && RANVIER_COMPOSITING
    if (host->deviceScale != 1 || host->compositingMode == RV_COMPOSITING_OFF || host->inFrame)
        return RV_ERR_UNSUPPORTED;
    if (host->presentationSurface && host->presentationSurface->matches(consumerDevice, host->size.width(), host->size.height())
        && !host->presentationSurface->available())
        return RV_ERR_UNSUPPORTED;
    auto result = [&]() -> int32_t {
        SetForScope inFrame(host->inFrame, true);
        host->frameRequested = false;
        host->document().updateLayoutIgnorePendingStylesheets();
        RefPtr view = host->frame().view();
        if (!view)
            return RV_ERR_PAINT_FAILED;
        view->updateLayoutAndStyleIfNeededRecursive();
        if (!view->clipLayer())
            return RV_ERR_UNSUPPORTED;
        if (host->compositor && host->compositor->size != host->size)
            host->compositor = nullptr;
        if (!host->compositor)
            host->compositor = RvCompositor::create(host->size);
        if (!host->compositor)
            return RV_ERR_UNSUPPORTED;
        if (!host->presentationSurface || !host->presentationSurface->matches(consumerDevice, host->size.width(), host->size.height())) {
            host->presentationSurface = RvD3D11Surface::create(consumerDevice, host->size.width(), host->size.height(), [] {
                auto* context = compositingContext();
                return context && context->makeContextCurrent();
            });
        }
        auto surface = host->presentationSurface;
        if (!surface || !surface->beginProducer()) {
            host->presentationSurface = nullptr;
            return RV_ERR_UNSUPPORTED;
        }
        auto paintResult = composite(*host->compositor, *view, nullptr, surface->framebuffer());
        bool transferred = paintResult == RV_OK && surface->finishProducer();
        if (!transferred) {
            surface->cancelProducer();
            host->presentationSurface = nullptr;
        } else {
            host->dirty = { };
            *frame = new RvGpuFrame { WTF::move(surface) };
        }
        return transferred ? RV_OK : RV_ERR_PAINT_FAILED;
    }();
    if (host->updateWanted)
        host->requestFrame();
    return result;
#else
    return RV_ERR_UNSUPPORTED;
#endif
}

int32_t rv_gpu_frame_info(RvGpuFrame* frame, void** texture, int32_t* width, int32_t* height, int32_t* format)
{
    if (!frame || !texture || !width || !height || !format)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
#if defined(_WIN32) && RANVIER_COMPOSITING
    *texture = frame->surface->texture();
    *width = frame->surface->width();
    *height = frame->surface->height();
    *format = RV_GPU_RGBA8_PREMULTIPLIED;
    return RV_OK;
#else
    return RV_ERR_UNSUPPORTED;
#endif
}

int32_t rv_gpu_frame_release(RvGpuFrame* frame)
{
    if (!frame)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
#if defined(_WIN32) && RANVIER_COMPOSITING
    bool released = frame->surface->releaseConsumer();
    delete frame;
    return released ? RV_OK : RV_ERR_PAINT_FAILED;
#else
    return RV_ERR_UNSUPPORTED;
#endif
}

// Paints area, in CSS pixels of the viewport, into its place in rgba, an image of paintSize.
static int32_t paintArea(RvHost& host, uint8_t* rgba, int32_t length, IntRect area)
{
    auto pixelSize = paintSize(host);
    size_t required = static_cast<size_t>(pixelSize.width()) * pixelSize.height() * 4;
    if (length < 0 || static_cast<size_t>(length) < required)
        return RV_ERR_BUFFER_TOO_SMALL;
    area.intersect({ { }, host.size });
    host.inFrame = true;
    host.frameRequested = false;
    host.document().updateLayoutIgnorePendingStylesheets();
    RefPtr view = host.frame().view();
    if (!view) {
        host.inFrame = false;
        return RV_ERR_PAINT_FAILED;
    }
    view->updateLayoutAndStyleIfNeededRecursive();
#if RANVIER_COMPOSITING
    // A paint of the whole viewport composites when the host is in compositing mode. In
    // RV_COMPOSITING_WHEN_NEEDED a frame without a clip layer is not in compositing mode and takes the CPU path.
    // The compositor paints CSS pixels one to one, so a device scale other than 1 takes the CPU path too, as
    // does a paint of part of the viewport.
    if (area == IntRect { { }, host.size } && host.compositingMode != RV_COMPOSITING_OFF && view->clipLayer() && host.deviceScale == 1) {
        // A resize since the compositor was made needs a framebuffer of the new size.
        if (host.compositor && host.compositor->size != host.size)
            host.compositor = nullptr;
        if (!host.compositor)
            host.compositor = RvCompositor::create(host.size);
        if (host.compositor) {
            auto result = composite(*host.compositor, *view, rgba);
            host.dirty = { };
            host.inFrame = false;
            if (host.updateWanted)
                host.requestFrame();
            return result;
        }
        // No GL: the host stays on the CPU path, as with RV_COMPOSITING_OFF.
        setCompositing(host, RV_COMPOSITING_OFF);
    }
#endif
    RefPtr<ImageBuffer> buffer;
    if (!area.isEmpty()) {
        buffer = ImageBuffer::create(FloatSize { area.size() }, RenderingMode::Unaccelerated,
            RenderingPurpose::Unspecified, host.deviceScale, DestinationColorSpace::SRGB(), PixelFormat::BGRA8);
        if (buffer) {
            buffer->context().translate(-area.x(), -area.y());
            auto behavior = view->paintBehavior();
            view->setPaintBehavior(behavior | PaintBehavior::FlattenCompositingLayers);
            view->paint(buffer->context(), area);
            view->setPaintBehavior(behavior);
        }
    }
    // A paint of part of the viewport leaves invalidations outside it for a later paint.
    if (area.contains(host.dirty))
        host.dirty = { };
    host.inFrame = false;
    if (area.isEmpty())
        return RV_OK;
    if (!buffer)
        return RV_ERR_PAINT_FAILED;
    buffer->flushDrawingContext();
    PixelBufferFormat format { AlphaPremultiplication::Unpremultiplied, PixelFormat::RGBA8, DestinationColorSpace::SRGB() };
    // getPixelBuffer takes CSS pixels and scales them as paintSize does.
    auto pixels = buffer->getPixelBuffer(format, IntRect { { }, area.size() });
    if (!pixels)
        return RV_ERR_PAINT_FAILED;
    auto origin = area.location();
    origin.scale(host.deviceScale);
    auto columns = std::min(pixels->size().width(), pixelSize.width() - origin.x());
    auto rows = std::min(pixels->size().height(), pixelSize.height() - origin.y());
    auto source = pixels->bytes();
    for (int row = 0; row < rows; ++row) {
        std::memcpy(rgba + (static_cast<size_t>(origin.y() + row) * pixelSize.width() + origin.x()) * 4,
            source.data() + static_cast<size_t>(row) * pixels->size().width() * 4, static_cast<size_t>(columns) * 4);
    }
    // An update wanted during the paint, such as a layout that started an animation, needs another frame.
    if (host.updateWanted)
        host.requestFrame();
    return RV_OK;
}

int32_t rv_host_paint_rgba(RvHost* host, uint8_t* rgba, int32_t length)
{
    if (!host || !rgba)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return paintArea(*host, rgba, length, { { }, host->size });
}

int32_t rv_host_paint_rgba_rect(RvHost* host, uint8_t* rgba, int32_t length, int32_t x, int32_t y, int32_t width, int32_t height)
{
    if (!host || !rgba)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (width < 0 || height < 0)
        return RV_ERR_UNSUPPORTED;
    return paintArea(*host, rgba, length, { x, y, width, height });
}

RvListener* rv_node_add_event_listener(RvNode* target, const char* type, int32_t capture,
    RvEventCallback callback, void* context)
{
    if (!target || !type || !callback || !onOwningThread())
        return nullptr;
    auto* listener = new RvListener { RvEventListener::create(callback, context), *node(target),
        AtomString::fromUTF8(type), !!(capture & RV_LISTENER_CAPTURE) };
    AddEventListenerOptions options;
    options.capture = listener->capture;
    if (capture & RV_LISTENER_PASSIVE_SPECIFIED)
        options.passive = !!(capture & RV_LISTENER_PASSIVE);
    listener->target->addEventListener(listener->type, listener->listener.copyRef(), options);
    return listener;
}

RvNodeFilter* rv_node_filter_create(RvNode* target, RvNodeFilterCallback callback, void* context, RvNodeFilterRelease release)
{
    if (!target || !callback || !onOwningThread())
        return nullptr;
    NodeFilter* filter = &RvHostNodeFilter::create(node(target)->document(), callback, context, release).leakRef();
    return reinterpret_cast<RvNodeFilter*>(filter);
}

int32_t rv_node_filter_context(RvNodeFilter* filter, void** context)
{
    if (!filter || !context)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto* engine = reinterpret_cast<NodeFilter*>(filter);
    *context = hostNodeFilters().contains(engine) ? static_cast<RvHostNodeFilter*>(engine)->context() : nullptr;
    return RV_OK;
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
    Ref range = WebCore::Range::create(node(context)->document());
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

static EventTarget* eventTarget(RvEventTarget* handle) { return reinterpret_cast<EventTarget*>(handle); }

static RvEventTarget* targetHandleOrNull(EventTarget* target)
{
    if (!target)
        return nullptr;
    target->ref();
    return reinterpret_cast<RvEventTarget*>(target);
}

RvEvent* rv_host_construct_event(RvHost* host, int32_t kind, const char* type, const RvEventInit* init)
{
    if (!host || !type || !init || !onOwningThread())
        return nullptr;
    return ranvier_event_construct(reinterpret_cast<RvNode*>(&host->document()), kind, type, init);
}

int32_t rv_custom_event_detail_json(RvEvent* handle, char* buffer, int32_t capacity, int32_t* length)
{
    return ranvier_custom_event_detail_json(handle, buffer, capacity, length);
}

RvEventTarget* rv_host_create_event_target(RvHost* host)
{
    if (!host || !onOwningThread())
        return nullptr;
    return ranvier_event_target_create(reinterpret_cast<RvNode*>(&host->document()));
}

RvEventTarget* rv_host_window_event_target(RvHost* host)
{
    if (!host || !onOwningThread())
        return nullptr;
    return ranvier_window_event_target(reinterpret_cast<RvNode*>(&host->document()));
}

int32_t rv_host_max_touch_points(RvHost* host, int32_t* value)
{
    if (!host || !value)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return ranvier_window_max_touch_points(reinterpret_cast<RvNode*>(&host->document()), value);
}

RvEventTarget* rv_event_target_retain(RvEventTarget* handle)
{
    if (!handle || !onOwningThread())
        return nullptr;
    eventTarget(handle)->ref();
    return handle;
}

void rv_event_target_release(RvEventTarget* handle)
{
    if (handle && onOwningThread())
        eventTarget(handle)->deref();
}

RvEventTarget* rv_node_as_event_target(RvNode* handle)
{
    if (!handle || !onOwningThread())
        return nullptr;
    return targetHandleOrNull(static_cast<EventTarget*>(node(handle)));
}

RvNode* rv_event_target_as_node(RvEventTarget* handle)
{
    if (!handle || !onOwningThread())
        return nullptr;
    return handleOrNull(dynamicDowncast<Node>(eventTarget(handle)));
}

int32_t rv_event_target_equals(RvEventTarget* left, RvEventTarget* right)
{
    return left && right && eventTarget(left) == eventTarget(right) ? 1 : 0;
}

RvListener* rv_event_target_add_listener(RvEventTarget* target, const char* type, int32_t flags, RvEventCallback callback, void* context)
{
    if (!target || !type || !callback || !onOwningThread())
        return nullptr;
    auto* listener = new RvListener { RvEventListener::create(callback, context), *eventTarget(target),
        AtomString::fromUTF8(type), !!(flags & RV_LISTENER_CAPTURE) };
    AddEventListenerOptions options;
    options.capture = listener->capture;
    if (flags & RV_LISTENER_PASSIVE_SPECIFIED)
        options.passive = !!(flags & RV_LISTENER_PASSIVE);
    listener->target->addEventListener(listener->type, listener->listener.copyRef(), options);
    return listener;
}

int32_t rv_event_target_dispatch(RvEventTarget* target, RvEvent* dispatched, int32_t* defaultPrevented)
{
    if (!target || !dispatched)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    Ref protectedTarget = *eventTarget(target);
    Ref protectedEvent = *event(dispatched);
    auto result = dispatchCountingFailures([&] { protectedTarget->dispatchEvent(protectedEvent); });
    if (defaultPrevented)
        *defaultPrevented = protectedEvent->defaultPrevented() ? 1 : 0;
    return result;
}

RvEventTarget* rv_event_get_target(RvEvent* subject, int32_t current)
{
    if (!subject || !onOwningThread())
        return nullptr;
    return targetHandleOrNull(current ? event(subject)->currentTarget() : event(subject)->target());
}

RvEventTarget* rv_event_get_related_target(RvEvent* subject)
{
    if (!subject || !onOwningThread())
        return nullptr;
    return targetHandleOrNull(event(subject)->relatedTarget());
}

int32_t rv_host_window_metrics(RvHost* host, RvWindowMetrics* metrics)
{
    if (!host || !metrics)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (metrics->size < static_cast<int32_t>(sizeof(RvWindowMetrics)))
        return RV_ERR_UNSUPPORTED;
    auto status = ranvier_window_metrics(reinterpret_cast<RvNode*>(&host->document()), metrics);
    if (status != RV_OK)
        return status;
    // The window of a host is its viewport: the chrome client has no window rectangle of its own.
    metrics->outerWidth = host->size.width();
    metrics->outerHeight = host->size.height();
    return RV_OK;
}

int32_t rv_host_set_visible(RvHost* host, int32_t visible)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    host->page->setIsVisible(!!visible);
    return RV_OK;
}

RvEventTarget* rv_host_match_media(RvHost* host, const char* query)
{
    if (!host || !query || !onOwningThread())
        return nullptr;
    return ranvier_match_media(reinterpret_cast<RvNode*>(&host->document()), query);
}

int32_t rv_media_query_matches(RvEventTarget* target, int32_t* matches)
{
    if (!target || !matches)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return ranvier_media_query_matches(target, matches);
}

int32_t rv_media_query_media(RvEventTarget* target, char* buffer, int32_t capacity, int32_t* length)
{
    if (!target || !length)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return ranvier_media_query_media(target, buffer, capacity, length);
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
    case EventInterfaceType::CustomEvent:
        return RV_EVENT_CUSTOM;
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
    auto code = Ranvier::lastExceptionCode();
    if (!code)
        return copyString(String { }, buffer, capacity, length);
    switch (part) {
    case RV_EXCEPTION_NAME:
        switch (*code) {
        case ExceptionCode::RangeError:
            return copyString("RangeError"_s, buffer, capacity, length);
        case ExceptionCode::TypeError:
            return copyString("TypeError"_s, buffer, capacity, length);
        case ExceptionCode::JSSyntaxError:
            return copyString("SyntaxError"_s, buffer, capacity, length);
        case ExceptionCode::ExistingExceptionError:
            // A host callback, such as an RvNodeFilterCallback, reported a failure.
            return copyString("ExistingExceptionError"_s, buffer, capacity, length);
        default:
            break;
        }
        return copyString(String { DOMException::name(*code) }, buffer, capacity, length);
    case RV_EXCEPTION_MESSAGE:
        return copyString(Ranvier::lastExceptionMessage(), buffer, capacity, length);
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

int32_t rv_host_set_form_submission_handler(RvHost* host, RvFormSubmissionHandler handler, void* context)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    host->formSubmissionHandler = handler;
    host->formSubmissionContext = handler ? context : nullptr;
    return RV_OK;
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
    if (!host->screen) {
        publishScreens();
        host->page->screenPropertiesDidChange();
    }
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

int32_t rv_host_set_page_scale(RvHost* host, double scale, int32_t originX, int32_t originY)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!std::isfinite(scale) || scale <= 0)
        return RV_ERR_UNSUPPORTED;
    host->page->setPageScaleFactor(static_cast<float>(scale), { originX, originY });
    host->dirty = { { }, host->size };
    host->requestFrame();
    return RV_OK;
}

int32_t rv_host_page_scale(RvHost* host, double* scale)
{
    if (!host || !scale)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    *scale = host->page->pageScaleFactor();
    return RV_OK;
}

int32_t rv_host_set_obscured_insets(RvHost* host, double top, double right, double bottom, double left)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    for (double inset : { top, right, bottom, left }) {
        if (!std::isfinite(inset) || inset < 0)
            return RV_ERR_UNSUPPORTED;
    }
    host->page->setObscuredContentInsets(FloatBoxExtent { static_cast<float>(top), static_cast<float>(right), static_cast<float>(bottom), static_cast<float>(left) });
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
    if (action == RV_MOUSE_DOWN)
        host->pressPoint = { x, y };
    // The drag client finds the host of a drag that starts during this call here.
    SetForScope dragHost { inputHost, host };
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
        // The first activation fires one window focus event when the main frame is focused while the page is unfocused.
        if (!focus.focusedFrame())
            focus.setFocusedFrame(&host->frame());
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

int32_t rv_host_cursor(RvHost* host)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return host->cursor;
}

int32_t rv_blob_read_bytes(RvBlob* handle, uint8_t* buffer, int64_t capacity, int64_t* length)
{
    if (!handle || !length || capacity < 0 || (capacity && !buffer))
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto& blob = *reinterpret_cast<Blob*>(handle);
    auto* registry = blobRegistry()->blobRegistryImpl();
    RefPtr data = registry ? registry->blobDataFromURL(blob.url()) : nullptr;
    if (!data)
        return RV_ERR_UNSUPPORTED;
    Vector<std::pair<const uint8_t*, size_t>> spans;
    uint64_t total = 0;
    for (auto& item : data->items()) {
        auto span = item.switchOn([&](const DataSegment& segment) -> std::optional<std::span<const uint8_t>> {
            auto bytes = segment.span();
            auto offset = item.offset();
            auto count = item.length();
            if (offset < 0 || count < 0 || static_cast<uint64_t>(offset) > bytes.size() || static_cast<uint64_t>(count) > bytes.size() - offset)
                return std::nullopt;
            return bytes.subspan(offset, count);
        }, [](const BlobDataFileReference&) -> std::optional<std::span<const uint8_t>> {
            return std::nullopt;
        });
        if (!span)
            return RV_ERR_UNSUPPORTED;
        total += span->size();
        spans.append({ span->data(), span->size() });
    }
    if (total > static_cast<uint64_t>(std::numeric_limits<int64_t>::max()))
        return RV_ERR_UNSUPPORTED;
    *length = static_cast<int64_t>(total);
    if (static_cast<uint64_t>(capacity) < total)
        return RV_ERR_BUFFER_TOO_SMALL;
    for (auto& [bytes, count] : spans) {
        if (count)
            std::memcpy(buffer, bytes, count);
        buffer += count;
    }
    return RV_OK;
}

int32_t rv_file_list_create(RvBlob* const* files, int32_t count, RvFileList** result)
{
    if (!result || count < 0 || (count && !files))
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    Vector<Ref<File>> list;
    list.reserveInitialCapacity(count);
    for (int32_t i = 0; i < count; ++i) {
        if (!files[i])
            return RV_ERR_NULL_ARGUMENT;
        RefPtr file = dynamicDowncast<File>(*reinterpret_cast<Blob*>(files[i]));
        if (!file)
            return RV_ERR_WRONG_INTERFACE;
        list.append(file.releaseNonNull());
    }
    *result = reinterpret_cast<RvFileList*>(&FileList::create(WTF::move(list)).leakRef());
    return RV_OK;
}

int32_t rv_blob_read(RvHost* host, RvBlob* blob, int32_t mode, RvResourceCompletion completion, void* context, uint64_t* operation)
{
    if (!host || !blob || !completion || !operation)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host))
        return RV_ERR_UNSUPPORTED;
    return ranvier_blob_read(reinterpret_cast<RvNode*>(&host->document()), blob, mode, completion, context, operation);
}

int32_t rv_blob_url_read(RvHost* host, const uint8_t* url, int32_t url_length, RvResourceCompletion completion, void* context, uint64_t* operation)
{
    if (!host || url_length < 0 || (url_length && !url) || !completion || !operation)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host))
        return RV_ERR_UNSUPPORTED;
    return ranvier_blob_url_read(reinterpret_cast<RvNode*>(&host->document()), url, url_length, completion, context, operation);
}

int32_t rv_blob_read_result(uint64_t operation, uint8_t* buffer, int64_t capacity, int64_t* length)
{
    return ranvier_blob_read_result(operation, buffer, capacity, length);
}

int32_t rv_blob_read_type(uint64_t operation, char* buffer, int32_t capacity, int32_t* length)
{
    return ranvier_blob_read_type(operation, buffer, capacity, length);
}

int32_t rv_blob_read_error(uint64_t operation, char* buffer, int32_t capacity, int32_t* length)
{
    return ranvier_blob_read_error(operation, buffer, capacity, length);
}

int32_t rv_file_create_from_path(RvHost* host, const uint8_t* path, int32_t path_length, RvBlob** result)
{
    if (!host || path_length < 0 || (path_length && !path) || !result)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host))
        return RV_ERR_UNSUPPORTED;
    auto text = String::fromUTF8(std::span<const char8_t> { reinterpret_cast<const char8_t*>(path), static_cast<size_t>(path_length) });
    if (text.isNull())
        return RV_ERR_NULL_ARGUMENT;
    auto native = std::filesystem::path(std::u8string_view { reinterpret_cast<const char8_t*>(path), static_cast<size_t>(path_length) });
    if (text.isEmpty() || !native.is_absolute() || text.contains('\0'))
        return RV_ERR_UNSUPPORTED;
    *result = reinterpret_cast<RvBlob*>(&File::create(&host->document(), text).leakRef());
    return RV_OK;
}

int32_t rv_file_reader_result(RvEventTarget* reader, int32_t* kind, uint8_t* buffer, int64_t capacity, int64_t* length)
{
    return ranvier_file_reader_result(reader, kind, buffer, capacity, length);
}

int32_t rv_file_reader_error(RvEventTarget* reader, char* buffer, int32_t capacity, int32_t* length)
{
    return ranvier_file_reader_error(reader, buffer, capacity, length);
}

int32_t rv_host_scroll_position(RvHost* host, int32_t* x, int32_t* y)
{
    if (!host || !x || !y)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr view = host->frame().view();
    if (!view)
        return RV_ERR_PAINT_FAILED;
    auto position = view->scrollPosition();
    *x = position.x();
    *y = position.y();
    return RV_OK;
}

int32_t rv_host_scroll_to(RvHost* host, int32_t x, int32_t y)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr view = host->frame().view();
    if (!view)
        return RV_ERR_PAINT_FAILED;
    host->document().updateLayoutIgnorePendingStylesheets();
    view->setScrollPosition({ x, y });
    return RV_OK;
}

// Runs an input method call on the focused frame's editor, which dispatches composition and input events.
template<typename Edit> static int32_t compose(RvHost& host, Edit&& edit)
{
    Ref frame = host.frame();
    return handleInput(host, [&] {
        edit(frame->editor());
        return true;
    }) < 0 ? RV_ERR_LISTENER_FAILED : RV_OK;
}

int32_t rv_host_ime_set_composition(RvHost* host, const char* text, int32_t selectionStart, int32_t selectionEnd)
{
    if (!host || !text)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto composition = utf8(text);
    if (selectionStart < 0 || selectionEnd < selectionStart || static_cast<unsigned>(selectionEnd) > composition.length())
        return RV_ERR_UNSUPPORTED;
    Vector<CompositionUnderline> underlines;
    if (!composition.isEmpty())
        underlines.append({ 0, composition.length(), CompositionUnderlineColor::TextColor, Color::black, false });
    return compose(*host, [&](Editor& editor) {
        editor.setComposition(composition, underlines, { }, { }, selectionStart, selectionEnd);
    });
}

int32_t rv_host_ime_commit(RvHost* host, const char* text)
{
    if (!host || !text)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto committed = utf8(text);
    return compose(*host, [&](Editor& editor) { editor.confirmComposition(committed); });
}

int32_t rv_host_ime_cancel(RvHost* host)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    // Editor::cancelComposition leaves the composition's text when the selection is a caret inside it; an
    // empty composition selects the composition, deletes it and fires compositionend.
    return compose(*host, [](Editor& editor) {
        if (editor.hasComposition())
            editor.setComposition(emptyString(), { }, { }, { }, 0, 0);
    });
}

int32_t rv_host_ime_rect(RvHost* host, int32_t* x, int32_t* y, int32_t* width, int32_t* height)
{
    if (!host || !x || !y || !width || !height)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    Ref frame = host->frame();
    RefPtr view = frame->view();
    IntRect rect;
    if (view) {
        host->document().updateLayoutIgnorePendingStylesheets();
        auto& editor = frame->editor();
        if (auto range = editor.compositionRange())
            rect = editor.firstRectForRange(*range);
        else
            rect = frame->selection().absoluteCaretBounds();
        rect = view->contentsToRootView(rect);
    }
    *x = rect.x();
    *y = rect.y();
    *width = rect.width();
    *height = rect.height();
    return rect.isEmpty() ? 0 : 1;
}

static Element* elementOf(RvNode* handle) { return handle ? dynamicDowncast<Element>(*node(handle)) : nullptr; }

int32_t rv_element_class(RvNode* target, const char* token, int32_t operation)
{
    if (!target || !token)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = elementOf(target);
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    auto name = AtomString::fromUTF8(token);
    Ref classes = element->classList();
    std::optional<bool> force;
    switch (operation) {
    case RV_CLASS_CONTAINS:
        return classes->contains(name) ? 1 : 0;
    case RV_CLASS_ADD:
        force = true;
        break;
    case RV_CLASS_REMOVE:
        force = false;
        break;
    case RV_CLASS_TOGGLE:
        break;
    default:
        return RV_ERR_UNSUPPORTED;
    }
    auto result = classes->toggle(name, force);
    if (result.hasException())
        return fail(result.exception());
    return result.returnValue() ? 1 : 0;
}

int32_t rv_element_set_style(RvNode* target, const char* property, const char* value, int32_t important)
{
    if (!target || !property || !value)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = dynamicDowncast<StyledElement>(*node(target));
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    Ref<CSSStyleDeclaration> style = element->cssomStyle();
    return status(style->setProperty(utf8(property), utf8(value), important ? "important"_s : emptyString()));
}

int32_t rv_element_get_style(RvNode* target, const char* property, char* buffer, int32_t capacity, int32_t* length)
{
    if (!target || !property)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = dynamicDowncast<StyledElement>(*node(target));
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    Ref<CSSStyleDeclaration> style = element->cssomStyle();
    return copyString(style->getPropertyValue(utf8(property)), buffer, capacity, length);
}

int32_t rv_element_computed_style(RvNode* target, const char* property, char* buffer, int32_t capacity, int32_t* length)
{
    if (!target || !property)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = elementOf(target);
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    Ref<CSSStyleDeclaration> style = CSSComputedStyleDeclaration::create(*element, CSSComputedStyleDeclaration::AllowVisited::No);
    return copyString(style->getPropertyValue(utf8(property)), buffer, capacity, length);
}

int32_t rv_element_rect(RvNode* target, double* x, double* y, double* width, double* height)
{
    if (!target || !x || !y || !width || !height)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = elementOf(target);
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    auto rect = element->boundingClientRect();
    *x = rect.x();
    *y = rect.y();
    *width = rect.width();
    *height = rect.height();
    return RV_OK;
}

int32_t rv_node_convert_points(RvNode* from, int32_t fromSpace, RvNode* to, int32_t toSpace, double* xy, int32_t count)
{
    if (!from)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return ranvier_convert_points(from, fromSpace, to, toSpace, xy, count);
}

int32_t rv_node_box_quad(RvNode* node, int32_t box, RvNode* to, int32_t toSpace, double* quad)
{
    if (!node || !quad)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return ranvier_box_quad(node, box, to, toSpace, quad);
}

RvNode* rv_host_element_at(RvHost* host, int32_t x, int32_t y)
{
    if (!host || !onOwningThread())
        return nullptr;
    Ref document = host->document();
    RefPtr element = document->elementFromPoint(x, y, HitTestSource::User);
    return handleOrNull(element.get());
}

static std::optional<ScrollLogicalPosition> alignment(int32_t value)
{
    if (value < RV_ALIGN_START || value > RV_ALIGN_NEAREST)
        return std::nullopt;
    return static_cast<ScrollLogicalPosition>(value);
}

int32_t rv_element_scroll_into_view(RvNode* target, int32_t block, int32_t inlineAlignment, int32_t smooth)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = elementOf(target);
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    auto blockPosition = alignment(block);
    auto inlinePosition = alignment(inlineAlignment);
    if (!blockPosition || !inlinePosition)
        return RV_ERR_UNSUPPORTED;
    ScrollIntoViewOptions options;
    options.behavior = smooth ? ScrollBehavior::Smooth : ScrollBehavior::Instant;
    options.blockPosition = blockPosition;
    options.inlinePosition = inlinePosition;
    element->scrollIntoView(Variant<bool, ScrollIntoViewOptions> { WTF::move(options) });
    return RV_OK;
}

int32_t rv_element_scroll_metric(RvNode* target, int32_t metric, int32_t* value)
{
    if (!target || !value)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = elementOf(target);
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    switch (metric) {
    case RV_SCROLL_LEFT:
        *value = element->scrollLeft();
        return RV_OK;
    case RV_SCROLL_TOP:
        *value = element->scrollTop();
        return RV_OK;
    case RV_SCROLL_WIDTH:
        *value = element->scrollWidth();
        return RV_OK;
    case RV_SCROLL_HEIGHT:
        *value = element->scrollHeight();
        return RV_OK;
    case RV_CLIENT_WIDTH:
        *value = element->clientWidth();
        return RV_OK;
    case RV_CLIENT_HEIGHT:
        *value = element->clientHeight();
        return RV_OK;
    }
    return RV_ERR_UNSUPPORTED;
}

int32_t rv_element_scroll_to(RvNode* target, int32_t left, int32_t top, int32_t smooth)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = elementOf(target);
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    ScrollToOptions options;
    options.behavior = smooth ? ScrollBehavior::Smooth : ScrollBehavior::Instant;
    options.left = left;
    options.top = top;
    element->scrollTo(options);
    return RV_OK;
}

RvNode* rv_element_attach_shadow(RvNode* target, int32_t* status)
{
    auto report = [&](int32_t value) -> RvNode* {
        if (status)
            *status = value;
        return nullptr;
    };
    if (!target)
        return report(RV_ERR_NULL_ARGUMENT);
    if (!onOwningThread())
        return report(RV_ERR_WRONG_THREAD);
    RefPtr element = elementOf(target);
    if (!element)
        return report(RV_ERR_NOT_ELEMENT);
    auto root = element->attachShadow({ ShadowRootMode::Open });
    if (root.hasException())
        return report(fail(root.exception()));
    if (status)
        *status = RV_OK;
    return handle(Ref<Node> { root.releaseReturnValue() });
}

RvNode* rv_element_shadow_root(RvNode* target)
{
    if (!target || !onOwningThread())
        return nullptr;
    RefPtr element = elementOf(target);
    RefPtr root = element ? element->shadowRoot() : nullptr;
    if (!root || root->mode() != ShadowRootMode::Open)
        return nullptr;
    return handle(root.releaseNonNull());
}

int32_t rv_text_selection(RvNode* target, int32_t* start, int32_t* end)
{
    if (!target || !start || !end)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr control = dynamicDowncast<HTMLTextFormControlElement>(*node(target));
    if (!control)
        return RV_ERR_NOT_INPUT;
    *start = control->selectionStart();
    *end = control->selectionEnd();
    return RV_OK;
}

int32_t rv_text_set_selection(RvNode* target, int32_t start, int32_t end)
{
    if (!target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr control = dynamicDowncast<HTMLTextFormControlElement>(*node(target));
    if (!control)
        return RV_ERR_NOT_INPUT;
    if (start < 0 || end < start)
        return RV_ERR_UNSUPPORTED;
    control->setSelectionRange(start, end);
    return RV_OK;
}

static WebAnimation* animation(RvAnimation* handle) { return reinterpret_cast<WebAnimation*>(handle); }

static int32_t copyAnimations(const Vector<Ref<WebAnimation>>& found, RvAnimation** animations, int32_t capacity, int32_t* count)
{
    *count = static_cast<int32_t>(found.size());
    if (capacity < *count)
        return RV_ERR_BUFFER_TOO_SMALL;
    for (size_t i = 0; i < found.size(); ++i)
        animations[i] = reinterpret_cast<RvAnimation*>(&Ref { found[i] }.leakRef());
    return RV_OK;
}

int32_t rv_element_animations(RvNode* target, int32_t subtree, RvAnimation** animations, int32_t capacity, int32_t* count)
{
    if (!target || !count || (capacity > 0 && !animations))
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = elementOf(target);
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    return copyAnimations(element->getAnimations(GetAnimationsOptions { !!subtree }), animations, capacity, count);
}

int32_t rv_host_animations(RvHost* host, RvAnimation** animations, int32_t capacity, int32_t* count)
{
    if (!host || !count || (capacity > 0 && !animations))
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return copyAnimations(host->document().getAnimations(), animations, capacity, count);
}

void rv_animation_release(RvAnimation* handle)
{
    if (handle && onOwningThread())
        animation(handle)->deref();
}

int32_t rv_animation_control(RvAnimation* handle, int32_t action)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    Ref subject = *animation(handle);
    switch (action) {
    case RV_ANIMATION_PLAY:
        return status(subject->play());
    case RV_ANIMATION_PAUSE:
        return status(subject->pause());
    case RV_ANIMATION_REVERSE:
        return status(subject->reverse());
    case RV_ANIMATION_FINISH:
        return status(subject->finish());
    case RV_ANIMATION_CANCEL:
        subject->cancel();
        return RV_OK;
    }
    return RV_ERR_UNSUPPORTED;
}

int32_t rv_animation_state(RvAnimation* handle)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    switch (animation(handle)->playState()) {
    case WebAnimation::PlayState::Idle:
        return RV_ANIMATION_IDLE;
    case WebAnimation::PlayState::Running:
        return RV_ANIMATION_RUNNING;
    case WebAnimation::PlayState::Paused:
        return RV_ANIMATION_PAUSED;
    case WebAnimation::PlayState::Finished:
        return RV_ANIMATION_FINISHED;
    }
    return RV_ERR_UNSUPPORTED;
}

int32_t rv_animation_time(RvAnimation* handle, double* milliseconds)
{
    if (!handle || !milliseconds)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto current = animation(handle)->currentTime();
    auto seconds = current ? current->time() : std::nullopt;
    *milliseconds = seconds ? seconds->milliseconds() : 0;
    return seconds ? 1 : 0;
}

int32_t rv_animation_seek(RvAnimation* handle, double milliseconds)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return status(animation(handle)->setCurrentTime(WebAnimationTime { Seconds::fromMilliseconds(milliseconds) }));
}

int32_t rv_animation_set_rate(RvAnimation* handle, double rate)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    animation(handle)->updatePlaybackRate(rate);
    return RV_OK;
}

int32_t rv_animation_name(RvAnimation* handle, char* buffer, int32_t capacity, int32_t* length)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto& subject = *animation(handle);
    if (auto* css = dynamicDowncast<CSSAnimation>(subject))
        return copyString(css->animationName(), buffer, capacity, length);
    if (auto* transition = dynamicDowncast<CSSTransition>(subject))
        return copyString(transition->transitionProperty(), buffer, capacity, length);
    return copyString(subject.id(), buffer, capacity, length);
}

RvNode* rv_animation_target(RvAnimation* handle)
{
    if (!handle || !onOwningThread())
        return nullptr;
    auto* effect = dynamicDowncast<KeyframeEffect>(animation(handle)->effect());
    return handleOrNull(effect ? effect->target() : nullptr);
}

RvNode* rv_node_retain(RvNode* target)
{
    if (!target || !onOwningThread())
        return nullptr;
    node(target)->ref();
    return target;
}

struct RvObserver {
    RefPtr<ResizeObserver> resize;
    RefPtr<IntersectionObserver> intersection;
    RefPtr<IntersectionObserverCallback> delivery;
    RefPtr<ResizeObserverCallback> resizeDelivery;
    RvResizeCallback resizeCallback { nullptr };
    RvIntersectionCallback intersectionCallback { nullptr };
    void* context { nullptr };
};

// WebCore registers a resize observer with its document only when it has a callback object; a native callback
// function is never delivered to.
class RvResizeDelivery final : public ResizeObserverCallback {
public:
    static Ref<RvResizeDelivery> create(ScriptExecutionContext& context) { return adoptRef(*new RvResizeDelivery(context)); }

    // Null once the observer is released; WebCore can hold the callback longer.
    RvObserver* owner { nullptr };

private:
    explicit RvResizeDelivery(ScriptExecutionContext& context)
        : ResizeObserverCallback(&context)
    {
    }

    bool hasCallback() const final { return true; }

    CallbackResult<void> invoke(ResizeObserver&, const Vector<Ref<ResizeObserverEntry>>& entries, ResizeObserver&) final
    {
        for (auto& entry : entries) {
            if (!owner)
                break;
            Ref target = entry->target();
            auto& rect = entry->contentRect();
            owner->resizeCallback(owner->context, reinterpret_cast<RvNode*>(target.ptr()), rect.width(), rect.height());
        }
        return { };
    }

    CallbackResult<void> invokeRethrowingException(ResizeObserver& observer, const Vector<Ref<ResizeObserverEntry>>& entries, ResizeObserver& thisObserver) final
    {
        return invoke(observer, entries, thisObserver);
    }
};

class RvIntersectionDelivery final : public IntersectionObserverCallback {
public:
    static Ref<RvIntersectionDelivery> create(ScriptExecutionContext& context) { return adoptRef(*new RvIntersectionDelivery(context)); }

    RvObserver* owner { nullptr };

private:
    explicit RvIntersectionDelivery(ScriptExecutionContext& context)
        : IntersectionObserverCallback(&context)
    {
    }

    bool hasCallback() const final { return true; }

    CallbackResult<void> invoke(IntersectionObserver&, const Vector<Ref<IntersectionObserverEntry>>& entries, IntersectionObserver&) final
    {
        for (auto& entry : entries) {
            if (!owner)
                break;
            Ref target = entry->target();
            owner->intersectionCallback(owner->context, reinterpret_cast<RvNode*>(target.ptr()), entry->isIntersecting() ? 1 : 0, entry->intersectionRatio());
        }
        return { };
    }

    CallbackResult<void> invokeRethrowingException(IntersectionObserver& observer, const Vector<Ref<IntersectionObserverEntry>>& entries, IntersectionObserver& thisObserver) final
    {
        return invoke(observer, entries, thisObserver);
    }
};

RvObserver* rv_host_observe_resize(RvHost* host, RvResizeCallback callback, void* context)
{
    if (!host || !callback || !onOwningThread())
        return nullptr;
    Ref document = host->document();
    Ref delivery = RvResizeDelivery::create(document.get());
    auto* observer = new RvObserver;
    observer->resizeCallback = callback;
    observer->context = context;
    observer->resize = ResizeObserver::create(document.get(), delivery.copyRef());
    delivery->owner = observer;
    observer->resizeDelivery = WTF::move(delivery);
    return observer;
}

RvObserver* rv_host_observe_intersection(RvHost* host, RvIntersectionCallback callback, void* context, const char* rootMargin,
    const double* thresholds, int32_t thresholdCount)
{
    if (!host || !callback || thresholdCount < 0 || (thresholdCount && !thresholds) || !onOwningThread())
        return nullptr;
    Ref document = host->document();
    Ref delivery = RvIntersectionDelivery::create(document.get());
    IntersectionObserver::Init init;
    init.rootMargin = rootMargin ? utf8(rootMargin) : "0px"_s;
    init.scrollMargin = "0px"_s;
    if (thresholdCount)
        init.threshold = Vector<double> { std::span { thresholds, static_cast<size_t>(thresholdCount) } };
    else
        init.threshold = 0.0;
    auto created = IntersectionObserver::create(document.get(), delivery.copyRef(), WTF::move(init));
    if (created.hasException()) {
        fail(created.exception());
        return nullptr;
    }
    auto* observer = new RvObserver;
    observer->intersection = created.releaseReturnValue();
    observer->intersectionCallback = callback;
    observer->context = context;
    delivery->owner = observer;
    observer->delivery = WTF::move(delivery);
    return observer;
}

int32_t rv_observer_observe(RvObserver* observer, RvNode* target)
{
    if (!observer || !target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = elementOf(target);
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    if (observer->resize)
        observer->resize->observe(*element);
    else
        observer->intersection->observe(*element);
    return RV_OK;
}

int32_t rv_observer_unobserve(RvObserver* observer, RvNode* target)
{
    if (!observer || !target)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = elementOf(target);
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    if (observer->resize)
        observer->resize->unobserve(*element);
    else
        observer->intersection->unobserve(*element);
    return RV_OK;
}

void rv_observer_release(RvObserver* observer)
{
    if (!observer || !onOwningThread())
        return;
    if (observer->resize) {
        static_cast<RvResizeDelivery*>(observer->resizeDelivery.get())->owner = nullptr;
        observer->resize->disconnect();
    }
    if (observer->intersection) {
        observer->intersection->disconnect();
        // The callback outlives the observer while WebCore holds it; it stops delivering here.
        static_cast<RvIntersectionDelivery*>(observer->delivery.get())->owner = nullptr;
    }
    delete observer;
}

int32_t rv_element_snapshot(RvNode* target, uint8_t* rgba, int32_t length, int32_t* width, int32_t* height)
{
    if (!target || !width || !height)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    Ref subject = *node(target);
    RefPtr frame = subject->document().frame();
    if (!frame)
        return RV_ERR_PAINT_FAILED;
    subject->document().updateLayoutIgnorePendingStylesheets();
    auto buffer = snapshotNode(*frame, subject, { { }, PixelFormat::BGRA8, DestinationColorSpace::SRGB() });
    if (!buffer)
        return RV_ERR_PAINT_FAILED;
    PixelBufferFormat format { AlphaPremultiplication::Unpremultiplied, PixelFormat::RGBA8, DestinationColorSpace::SRGB() };
    auto pixels = buffer->getPixelBuffer(format, IntRect { { }, buffer->truncatedLogicalSize() });
    if (!pixels)
        return RV_ERR_PAINT_FAILED;
    *width = pixels->size().width();
    *height = pixels->size().height();
    size_t required = pixels->bytes().size();
    if (!rgba || length < 0 || static_cast<size_t>(length) < required)
        return RV_ERR_BUFFER_TOO_SMALL;
    std::memcpy(rgba, pixels->bytes().data(), required);
    return RV_OK;
}

int32_t rv_host_set_popup_handler(RvHost* host, RvPopupCallback callback, void* context)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    host->popupCallback = callback;
    host->popupContext = callback ? context : nullptr;
    return RV_OK;
}

static RvPopupMenu* popupMenu(RvPopup* handle) { return reinterpret_cast<RvPopupMenu*>(handle); }

int32_t rv_popup_item_count(RvPopup* handle)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto* client = popupMenu(handle)->client;
    return client ? client->listSize() : 0;
}

int32_t rv_popup_item(RvPopup* handle, int32_t index, int32_t* kind, int32_t* enabled, char* buffer, int32_t capacity, int32_t* length)
{
    if (!handle || !kind || !enabled)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    auto* client = popupMenu(handle)->client;
    if (!client || index < 0 || index >= client->listSize())
        return RV_ERR_UNSUPPORTED;
    unsigned item = index;
    *kind = client->itemIsSeparator(item) ? RV_POPUP_ITEM_SEPARATOR : client->itemIsLabel(item) ? RV_POPUP_ITEM_GROUP : RV_POPUP_ITEM_OPTION;
    *enabled = client->itemIsEnabled(item) ? 1 : 0;
    return copyString(client->itemText(item), buffer, capacity, length);
}

int32_t rv_popup_choose(RvPopup* handle, int32_t index)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    Ref popup = *popupMenu(handle);
    if (!popup->shown)
        return RV_ERR_UNSUPPORTED;
    auto* client = popup->client;
    if (client && index >= client->listSize())
        return RV_ERR_UNSUPPORTED;
    auto status = dispatchCountingFailures([&] {
        if (client && index >= 0)
            client->valueChanged(index);
        if (popup->client)
            popup->client->popupDidHide();
    });
    popup->end();
    if (popup->host)
        popup->host->document().updateStyleIfNeeded();
    return status;
}

int32_t rv_host_tooltip(RvHost* host, char* buffer, int32_t capacity, int32_t* length)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    return copyString(host->tooltip.isNull() ? emptyString() : host->tooltip, buffer, capacity, length);
}

struct RvClipboardRequest {
    Vector<std::pair<String, String>> items;
};

int32_t rv_host_set_clipboard(RvHost* host, int32_t style, RvClipboardWrite write, RvClipboardRead read, void* context)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (style < RV_CLIPBOARD_APP || style > RV_CLIPBOARD_DOM)
        return RV_ERR_UNSUPPORTED;
#if PLATFORM(GTK) || PLATFORM(WPE)
    if (style == RV_CLIPBOARD_NATIVE)
        return RV_ERR_UNSUPPORTED;
#endif
    host->clipboardStyle = style;
    host->clipboardWrite = style == RV_CLIPBOARD_APP ? write : nullptr;
    host->clipboardRead = style == RV_CLIPBOARD_APP ? read : nullptr;
    host->clipboardContext = style == RV_CLIPBOARD_APP ? context : nullptr;
    return RV_OK;
}

int32_t rv_clipboard_offer(RvClipboardRequest* request, const char* type, const char* data)
{
    if (!request || !type || !data)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    request->items.append({ utf8(type), utf8(data) });
    return RV_OK;
}

// The element a clipboard event targets: the focused element, else the body.
static RefPtr<Element> clipboardTarget(Document& document)
{
    if (RefPtr focused = document.focusedElement())
        return focused;
    return document.body();
}

// Copy or cut in the App and DOM styles: the event, then the page's data or the selection, then the delete.
static int32_t copyOrCut(RvHost& host, bool cut)
{
    Ref document = host.document();
    Ref frame = host.frame();
    auto& editor = frame->editor();
    RefPtr target = clipboardTarget(document);
    if (!target)
        return 0;
    Ref dataTransfer = DataTransfer::createForCopyAndPaste(document, DataTransfer::StoreMode::ReadWrite, makeUnique<StaticPasteboard>());
    Ref event = ClipboardEvent::create(cut ? eventNames().cutEvent : eventNames().copyEvent, dataTransfer.copyRef());
    target->dispatchEvent(event);
    Vector<std::pair<String, String>> items;
    if (event->defaultPrevented()) {
        for (auto& type : dataTransfer->types(document))
            items.append({ type, dataTransfer->getData(document, type) });
    } else {
        auto range = frame->selection().selection().toNormalizedRange();
        if (!range || !(cut ? editor.canCut() : editor.canCopy()))
            return 0;
        items.append({ "text/plain"_s, editor.selectedText() });
        items.append({ "text/html"_s, serializePreservingVisualAppearance(*range) });
        if (cut)
            editor.performDelete();
    }
    if (host.clipboardStyle == RV_CLIPBOARD_APP && host.clipboardWrite) {
        bool first = true;
        for (auto& [type, data] : items) {
            host.clipboardWrite(host.clipboardContext, type.utf8().data(), data.utf8().data(), first ? 1 : 0);
            first = false;
        }
    }
    return 1;
}

// Paste in the App and DOM styles: the app's data, the event, then the insertion.
static int32_t paste(RvHost& host, bool plain)
{
    Ref document = host.document();
    Ref frame = host.frame();
    RvClipboardRequest request;
    if (host.clipboardStyle == RV_CLIPBOARD_APP && host.clipboardRead)
        host.clipboardRead(host.clipboardContext, &request);
    auto pasteboard = makeUnique<StaticPasteboard>();
    String text;
    String html;
    for (auto& [type, data] : request.items) {
        if (plain && type != "text/plain"_s)
            continue;
        pasteboard->writeString(type, data);
        if (type == "text/plain"_s)
            text = data;
        else if (type == "text/html"_s)
            html = data;
    }
    RefPtr target = clipboardTarget(document);
    if (!target)
        return 0;
    Ref dataTransfer = DataTransfer::createForCopyAndPaste(document, DataTransfer::StoreMode::Readonly, WTF::move(pasteboard));
    Ref event = ClipboardEvent::create(eventNames().pasteEvent, dataTransfer.copyRef());
    target->dispatchEvent(event);
    if (event->defaultPrevented())
        return 1;
    auto& editor = frame->editor();
    if (!html.isEmpty())
        editor.pasteAsFragment(createFragmentFromMarkup(document, html, emptyString(), { }), false, false);
    else if (!text.isEmpty())
        editor.pasteAsPlainText(text, false);
    else
        return 0;
    return 1;
}

static int32_t runEdit(RvHost& host, int32_t command)
{
    Ref frame = host.frame();
    auto& editor = frame->editor();
    bool native = host.clipboardStyle == RV_CLIPBOARD_NATIVE;
    switch (command) {
    case RV_EDIT_COPY:
        if (native) {
            editor.copy(Editor::FromMenuOrKeyBinding::Yes);
            return 1;
        }
        return copyOrCut(host, false);
    case RV_EDIT_CUT:
        if (native) {
            editor.cut(Editor::FromMenuOrKeyBinding::Yes);
            return 1;
        }
        return copyOrCut(host, true);
    case RV_EDIT_PASTE:
    case RV_EDIT_PASTE_PLAIN:
        if (native) {
            if (command == RV_EDIT_PASTE)
                editor.paste(Editor::FromMenuOrKeyBinding::Yes);
            else
                editor.pasteAsPlainText(Editor::FromMenuOrKeyBinding::Yes);
            return 1;
        }
        return paste(host, command == RV_EDIT_PASTE_PLAIN);
    case RV_EDIT_SELECT_ALL:
        return editor.command("SelectAll"_s).execute() ? 1 : 0;
    case RV_EDIT_DELETE:
        return editor.command("Delete"_s).execute() ? 1 : 0;
    }
    return RV_ERR_UNSUPPORTED;
}

static int32_t runEdit(Page* page, int32_t command)
{
    auto* host = hostForPage(page);
    return host ? runEdit(*host, command) : 0;
}

int32_t rv_host_edit(RvHost* host, int32_t command)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    int32_t result = 0;
    auto status = dispatchCountingFailures([&] { result = runEdit(*host, command); });
    host->document().updateStyleIfNeeded();
    return status == RV_OK ? result : status;
}

struct RvDragData {
    Vector<std::pair<String, String>> items;
};

int32_t rv_host_set_drag(RvHost* host, int32_t style)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (style != RV_DRAG_APP && style != RV_DRAG_DOM)
        return RV_ERR_UNSUPPORTED;
    host->dragStyle = style;
    host->dragTarget = nullptr;
    return RV_OK;
}

RvDragData* rv_drag_data_create(void)
{
    return new RvDragData;
}

int32_t rv_drag_data_add(RvDragData* data, const char* type, const char* value)
{
    if (!data || !type || !value)
        return RV_ERR_NULL_ARGUMENT;
    data->items.append({ utf8(type), utf8(value) });
    return RV_OK;
}

void rv_drag_data_release(RvDragData* data)
{
    delete data;
}

static OptionSet<DragOperation> dragOperations(int32_t operations)
{
    OptionSet<DragOperation> result;
    if (operations & RV_DROP_COPY)
        result.add(DragOperation::Copy);
    if (operations & RV_DROP_MOVE)
        result.add(DragOperation::Move);
    if (operations & RV_DROP_LINK)
        result.add(DragOperation::Link);
    return result;
}

// The one RV_DROP_* operation of a negotiated mask, preferring copy, then move, then link.
static int32_t dropOperation(OptionSet<DragOperation> operations, int32_t allowed)
{
    if (operations.contains(DragOperation::Copy) && (allowed & RV_DROP_COPY))
        return RV_DROP_COPY;
    if (operations.contains(DragOperation::Move) && (allowed & RV_DROP_MOVE))
        return RV_DROP_MOVE;
    if (operations.contains(DragOperation::Link) && (allowed & RV_DROP_LINK))
        return RV_DROP_LINK;
    return RV_DROP_NONE;
}

static String dragItem(const RvDragData* data, ASCIILiteral type)
{
    if (data) {
        for (auto& [itemType, value] : data->items) {
            if (itemType == type)
                return value;
        }
    }
    return { };
}

static Ref<DataTransfer> dropTransfer(Document& document, const RvDragData* data, int32_t allowed)
{
    auto pasteboard = makeUnique<StaticPasteboard>();
    if (data) {
        for (auto& [type, value] : data->items)
            pasteboard->writeString(type, value);
    }
    return DataTransfer::createForDrop(document, WTF::move(pasteboard), dragOperations(allowed), false);
}

// Fires a trusted drag event at the target and returns whether a listener cancelled it.
static bool fireDrag(Document& document, Element& target, const AtomString& type, DataTransfer* dataTransfer, IntPoint point,
    int32_t modifiers, Element* related = nullptr)
{
    bool cancelable = type != eventNames().dragleaveEvent;
    Ref event = DragEvent::create(type, Event::CanBubble::Yes, cancelable ? Event::IsCancelable::Yes : Event::IsCancelable::No,
        Event::IsComposed::Yes, MonotonicTime::now(), document.windowProxy(), 0, point, point, 0, 0, platformModifiers(modifiers),
        MouseButton::Left, 1, related, 0, SyntheticClickType::NoTap, dataTransfer);
    target.dispatchEvent(event);
    return event->defaultPrevented();
}

static bool editableForDrop(Element& element)
{
    return is<HTMLTextFormControlElement>(element) || element.isContentEditable();
}

int32_t rv_host_drag(RvHost* host, int32_t action, int32_t x, int32_t y, int32_t allowed, RvDragData* data, int32_t modifiers)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (action < RV_DRAG_OVER || action > RV_DRAG_DROP)
        return RV_ERR_UNSUPPORTED;
    if (host->dragStyle != RV_DRAG_APP)
        return RV_DROP_NONE;
    Ref document = host->document();
    Ref frame = host->frame();
    IntPoint point { x, y };
    int32_t operation = RV_DROP_NONE;
    auto status = dispatchCountingFailures([&] {
        if (action == RV_DRAG_LEAVE) {
            if (RefPtr previous = std::exchange(host->dragTarget, nullptr))
                fireDrag(document, *previous, eventNames().dragleaveEvent, dropTransfer(document, data, allowed).ptr(), point, modifiers);
            return;
        }
        RefPtr target = document->elementFromPoint(x, y, HitTestSource::User);
        if (target != host->dragTarget) {
            if (RefPtr previous = host->dragTarget)
                fireDrag(document, *previous, eventNames().dragleaveEvent, dropTransfer(document, data, allowed).ptr(), point, modifiers, target.get());
            host->dragTarget = target;
            if (target)
                fireDrag(document, *target, eventNames().dragenterEvent, dropTransfer(document, data, allowed).ptr(), point, modifiers);
        }
        if (!target)
            return;
        auto hasText = !dragItem(data, "text/plain"_s).isEmpty() || !dragItem(data, "text/html"_s).isEmpty();
        Ref over = dropTransfer(document, data, allowed);
        if (fireDrag(document, *target, eventNames().dragoverEvent, over.ptr(), point, modifiers))
            operation = dropOperation(over->destinationOperationMask(), allowed);
        else if (hasText && editableForDrop(*target))
            operation = allowed & RV_DROP_COPY ? RV_DROP_COPY : dropOperation(dragOperations(allowed), allowed);
        if (action != RV_DRAG_DROP)
            return;
        host->dragTarget = nullptr;
        if (operation == RV_DROP_NONE) {
            fireDrag(document, *target, eventNames().dragleaveEvent, over.ptr(), point, modifiers);
            return;
        }
        if (fireDrag(document, *target, eventNames().dropEvent, dropTransfer(document, data, allowed).ptr(), point, modifiers))
            return;
        if (!editableForDrop(*target) || !hasText) {
            operation = RV_DROP_NONE;
            return;
        }
        // The default action: insert at the point, as typing would.
        RefPtr view = frame->view();
        auto position = frame->visiblePositionForPoint(view ? view->rootViewToContents(point) : point);
        frame->selection().setSelection(VisibleSelection { position });
        auto html = dragItem(data, "text/html"_s);
        if (!html.isEmpty())
            frame->editor().pasteAsFragment(createFragmentFromMarkup(document, html, emptyString(), { }), false, false);
        else
            frame->editor().insertText(dragItem(data, "text/plain"_s), nullptr);
    });
    host->document().updateStyleIfNeeded();
    return status == RV_OK ? operation : status;
}

struct RvDrag {
    RvHost* host;
    Vector<std::pair<String, String>> items;
    // The dragged element; null for a selection.
    RefPtr<Element> source;
    IntPoint start;
};

static int32_t dropMask(OptionSet<DragOperation> operations)
{
    return (operations.containsAny({ DragOperation::Copy, DragOperation::Generic }) ? RV_DROP_COPY : 0)
        | (operations.contains(DragOperation::Move) ? RV_DROP_MOVE : 0)
        | (operations.contains(DragOperation::Link) ? RV_DROP_LINK : 0);
}

OptionSet<DragSourceAction> RvDragClient::dragSourceActionMaskForPoint(const IntPoint&)
{
    if (!inputHost || inputHost->dragStyle != RV_DRAG_APP || !inputHost->dragStartCallback)
        return { };
    return anyDragSourceAction();
}

// The element a drag from the press point moves: the nearest draggable element, link or image around it.
static RefPtr<Element> dragSource(Document& document, IntPoint point)
{
    for (RefPtr element = document.elementFromPoint(point.x(), point.y(), HitTestSource::User); element; element = element->parentElement()) {
        if (equalLettersIgnoringASCIICase(element->attributeWithoutSynchronization(HTMLNames::draggableAttr), "true"_s)
            || element->hasTagName(HTMLNames::imgTag) || (element->hasTagName(HTMLNames::aTag) && element->hasAttributeWithoutSynchronization(HTMLNames::hrefAttr)))
            return element;
    }
    return nullptr;
}

void RvDragClient::startDrag(DragItem item, DataTransfer& dataTransfer, Frame&, const std::optional<NodeIdentifier>&)
{
    auto* host = inputHost;
    if (!host || !host->dragStartCallback)
        return;
    auto* drag = new RvDrag { host, { }, nullptr, host->pressPoint };
    // The DataTransfer is no longer readable; its pasteboard holds the page's data and WebCore's own.
    auto& pasteboard = dataTransfer.pasteboard();
    for (auto& type : pasteboard.typesForLegacyUnsafeBindings()) {
        auto value = pasteboard.readString(type);
        if (value.isEmpty())
            value = pasteboard.readStringInCustomData(type);
        drag->items.append({ type, value });
    }
    if (drag->items.isEmpty() && !item.url.isEmpty()) {
        drag->items.append({ "text/uri-list"_s, item.url.string() });
        drag->items.append({ "text/plain"_s, item.url.string() });
    }
    if (drag->items.isEmpty() && item.sourceAction == DragSourceAction::Selection) {
        auto& editor = host->frame().editor();
        drag->items.append({ "text/plain"_s, editor.selectedText() });
        if (auto range = host->frame().selection().selection().toNormalizedRange())
            drag->items.append({ "text/html"_s, serializePreservingVisualAppearance(*range) });
    }
    if (item.sourceAction != DragSourceAction::Selection)
        drag->source = dragSource(host->document(), host->pressPoint);
    host->dragStartCallback(host->dragStartContext, reinterpret_cast<RvDrag*>(drag), drag->start.x(), drag->start.y(),
        dropMask(dataTransfer.sourceOperationMask()));
}

int32_t rv_host_set_drag_start(RvHost* host, RvDragStartCallback callback, void* context)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    host->dragStartCallback = callback;
    host->dragStartContext = callback ? context : nullptr;
    return RV_OK;
}

int32_t rv_drag_item_count(RvDrag* drag)
{
    if (!drag)
        return RV_ERR_NULL_ARGUMENT;
    return static_cast<int32_t>(drag->items.size());
}

int32_t rv_drag_item_type(RvDrag* drag, int32_t index, char* buffer, int32_t capacity, int32_t* length)
{
    if (!drag)
        return RV_ERR_NULL_ARGUMENT;
    if (index < 0 || static_cast<size_t>(index) >= drag->items.size())
        return RV_ERR_UNSUPPORTED;
    return copyString(drag->items[index].first, buffer, capacity, length);
}

int32_t rv_drag_item_value(RvDrag* drag, int32_t index, char* buffer, int32_t capacity, int32_t* length)
{
    if (!drag)
        return RV_ERR_NULL_ARGUMENT;
    if (index < 0 || static_cast<size_t>(index) >= drag->items.size())
        return RV_ERR_UNSUPPORTED;
    return copyString(drag->items[index].second, buffer, capacity, length);
}

RvDragData* rv_drag_data(RvDrag* drag)
{
    if (!drag)
        return nullptr;
    return new RvDragData { drag->items };
}

int32_t rv_drag_image(RvDrag* drag, uint8_t* rgba, int32_t length, int32_t* width, int32_t* height, int32_t* offsetX, int32_t* offsetY)
{
    if (!drag || !width || !height || !offsetX || !offsetY)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!drag->source)
        return RV_ERR_UNSUPPORTED;
    auto rect = drag->source->boundingClientRect();
    auto scale = drag->host->deviceScale;
    *offsetX = static_cast<int32_t>((drag->start.x() - rect.x()) * scale);
    *offsetY = static_cast<int32_t>((drag->start.y() - rect.y()) * scale);
    return rv_element_snapshot(reinterpret_cast<RvNode*>(drag->source.get()), rgba, length, width, height);
}

int32_t rv_drag_end(RvDrag* drag, int32_t x, int32_t y, int32_t operation)
{
    if (!drag)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    std::unique_ptr<RvDrag> ended { drag };
    auto& host = *drag->host;
    Ref frame = host.frame();
    DoublePoint position { static_cast<double>(x), static_cast<double>(y) };
    PlatformMouseEvent release(position, position, MouseButton::Left, PlatformEvent::Type::MouseReleased, 0, { }, MonotonicTime::now(), 0,
        SyntheticClickType::NoTap, MouseEventInputSource::UserDriven);
    auto status = dispatchCountingFailures([&] {
        frame->eventHandler().dragSourceEndedAt(release, dragOperations(operation));
        if (RefPtr page = frame->page())
            page->dragController().dragEnded();
    });
    host.document().updateStyleIfNeeded();
    return status;
}

// Accessibility: the tree of WebCore's accessibility objects, as docs/ACCESSIBILITY.md describes.

// The hosts with accessibility on; WebCore's accessibility mode is on while there is one.
static int accessibilityHosts;

static AXCoreObject* axObject(RvAxNode* handle) { return reinterpret_cast<AXCoreObject*>(handle); }

// Whether WebCore removed the object from its tree. AccessibilityObject::isDetached tells only on ports that
// attach a platform wrapper to every object; Windows attaches none, so the cache is asked instead.
static bool isGone(AXCoreObject& object)
{
    auto* accessibility = dynamicDowncast<AccessibilityObject>(object);
    if (!accessibility)
        return object.isDetached();
    RefPtr document = accessibility->document();
    auto* cache = document ? document->axObjectCache() : nullptr;
    return !cache || cache->objectForID(object.objectID()) != accessibility;
}

static RvAxNode* axHandle(AXCoreObject* object)
{
    if (!object)
        return nullptr;
    object->ref();
    return reinterpret_cast<RvAxNode*>(object);
}

// The RV_ROLE_* value of a WebCore role.
static int32_t roleValue(AccessibilityRole role)
{
    using enum AccessibilityRole;
    switch (role) {
    case WebArea:
    case Document:
    case GraphicsDocument: return RV_ROLE_DOCUMENT;
    case Application:
    case WebApplication: return RV_ROLE_APPLICATION;
    case Generic:
    case Inline:
    case TextGroup:
    case Emphasis:
    case Strong:
    case Code:
    case Mark:
    case Subscript:
    case Superscript:
    case Deletion:
    case Insertion:
    case RubyInline:
    case RubyText:
    case Pre:
    case Time:
    case SVGText:
    case SVGTSpan:
    case SVGTextPath:
    case SectionHeader:
    case SectionFooter:
    case Suggestion:
    case SliderThumb: return RV_ROLE_GENERIC;
    case Group:
    case Details:
    case Blockquote:
    case RowGroup:
    case TableHeaderContainer:
    case Audio:
    case Video:
    case Model:
    case FrameHost:
    case LocalFrame:
    case RemoteFrame:
    case ScrollArea:
    case GraphicsSymbol: return RV_ROLE_GROUP;
    case StaticText:
    case ListMarker:
    case LineBreak: return RV_ROLE_TEXT;
    case Paragraph: return RV_ROLE_PARAGRAPH;
    case Heading: return RV_ROLE_HEADING;
    case Link: return RV_ROLE_LINK;
    case Button:
    case Summary:
    case SpinButtonPart: return RV_ROLE_BUTTON;
    case ToggleButton: return RV_ROLE_TOGGLE_BUTTON;
    case Checkbox: return RV_ROLE_CHECKBOX;
    case RadioButton: return RV_ROLE_RADIO;
    case RadioGroup: return RV_ROLE_RADIO_GROUP;
    case Switch: return RV_ROLE_SWITCH;
    case TextField:
    case SearchField:
    case DateTime:
    case ColorWell: return RV_ROLE_TEXT_FIELD;
    case TextArea: return RV_ROLE_TEXT_AREA;
    case ComboBox:
    case PopUpButton: return RV_ROLE_COMBO_BOX;
    case ListBox:
    case MenuListPopup: return RV_ROLE_LIST_BOX;
    case ListBoxOption:
    case MenuListOption: return RV_ROLE_OPTION;
    case Menu: return RV_ROLE_MENU;
    case MenuBar: return RV_ROLE_MENU_BAR;
    case MenuItem: return RV_ROLE_MENU_ITEM;
    case MenuItemCheckbox: return RV_ROLE_MENU_ITEM_CHECKBOX;
    case MenuItemRadio: return RV_ROLE_MENU_ITEM_RADIO;
    case Slider: return RV_ROLE_SLIDER;
    case SpinButton: return RV_ROLE_SPIN_BUTTON;
    case ProgressIndicator: return RV_ROLE_PROGRESS;
    case Meter: return RV_ROLE_METER;
    case ScrollBar: return RV_ROLE_SCROLL_BAR;
    case Image:
    case ImageMap:
    case Canvas:
    case SVGRoot:
    case GraphicsObject: return RV_ROLE_IMAGE;
    case List:
    case DescriptionList:
    case Directory: return RV_ROLE_LIST;
    case ListItem: return RV_ROLE_LIST_ITEM;
    case DescriptionListTerm:
    case Term: return RV_ROLE_TERM;
    case DescriptionListDetail:
    case Definition: return RV_ROLE_DEFINITION;
    case Table: return RV_ROLE_TABLE;
    case Grid: return RV_ROLE_GRID;
    case TreeGrid: return RV_ROLE_TREE_GRID;
    case Row: return RV_ROLE_ROW;
    case Cell:
    case GridCell: return RV_ROLE_CELL;
    case ColumnHeader: return RV_ROLE_COLUMN_HEADER;
    case RowHeader: return RV_ROLE_ROW_HEADER;
    case Tree: return RV_ROLE_TREE;
    case TreeItem: return RV_ROLE_TREE_ITEM;
    case TabList:
    case TabGroup: return RV_ROLE_TAB_LIST;
    case Tab: return RV_ROLE_TAB;
    case TabPanel: return RV_ROLE_TAB_PANEL;
    case ApplicationDialog: return RV_ROLE_DIALOG;
    case ApplicationAlertDialog: return RV_ROLE_ALERT_DIALOG;
    case ApplicationAlert: return RV_ROLE_ALERT;
    case ApplicationStatus: return RV_ROLE_STATUS;
    case ApplicationLog: return RV_ROLE_LOG;
    case ApplicationMarquee: return RV_ROLE_MARQUEE;
    case ApplicationTimer: return RV_ROLE_TIMER;
    case UserInterfaceTooltip: return RV_ROLE_TOOLTIP;
    case Toolbar: return RV_ROLE_TOOLBAR;
    case HorizontalRule:
    case Splitter: return RV_ROLE_SEPARATOR;
    case LandmarkBanner: return RV_ROLE_BANNER;
    case LandmarkNavigation: return RV_ROLE_NAVIGATION;
    case LandmarkMain: return RV_ROLE_MAIN;
    case LandmarkComplementary: return RV_ROLE_COMPLEMENTARY;
    case LandmarkContentInfo: return RV_ROLE_CONTENT_INFO;
    case LandmarkRegion:
    case LandmarkDocRegion: return RV_ROLE_REGION;
    case LandmarkSearch: return RV_ROLE_SEARCH;
    case Form: return RV_ROLE_FORM;
    case DocumentArticle: return RV_ROLE_ARTICLE;
    case Feed: return RV_ROLE_FEED;
    case Figure: return RV_ROLE_FIGURE;
    case DocumentNote:
    case Footnote: return RV_ROLE_NOTE;
    case DocumentMath:
    case MathElement: return RV_ROLE_MATH;
    case Label:
    case Legend:
    case Caption: return RV_ROLE_LABEL;
    case Column:
    case Ignored:
    case Presentational:
    case Unknown: return RV_ROLE_UNKNOWN;
    }
    return RV_ROLE_UNKNOWN;
}

#if USE(AX_EMBEDDER_NOTIFICATIONS)
// The RV_AX_EVENT_* value of a WebCore notification, or nothing for one the ABI does not report.
static std::optional<int32_t> axEvent(AXNotification notification)
{
    using enum AXNotification;
    switch (notification) {
    case FocusedUIElementChanged: return RV_AX_EVENT_FOCUS;
    case ChildrenChanged: return RV_AX_EVENT_CHILDREN;
    case ValueChanged:
    case MenuListValueChanged:
    case MaximumValueChanged:
    case MinimumValueChanged: return RV_AX_EVENT_VALUE;
    case CheckedStateChanged:
    case DisabledStateChanged:
    case ExpandedChanged:
    case PressedStateChanged:
    case RequiredStatusChanged:
    case InvalidStatusChanged:
    case ReadOnlyStatusChanged:
    case ElementBusyChanged:
    case FocusableStateChanged:
    case VisitedStateChanged:
    case HasPopupChanged:
    case MultiSelectableStateChanged: return RV_AX_EVENT_STATE;
    case LabelChanged:
    case NameChanged:
    case TextUnderElementChanged: return RV_AX_EVENT_NAME;
    case DescribedByChanged:
    case ExtendedDescriptionChanged: return RV_AX_EVENT_DESCRIPTION;
    case RoleChanged: return RV_AX_EVENT_ROLE;
    case SelectedStateChanged:
    case SelectedChildrenChanged:
    case SelectedCellsChanged:
    case MenuListItemSelected: return RV_AX_EVENT_SELECTION;
    case LiveRegionChanged:
    case LiveRegionAnnouncement: return RV_AX_EVENT_LIVE_REGION;
    case LoadComplete:
    case NewDocumentLoadComplete: return RV_AX_EVENT_LOAD_COMPLETE;
    case LayoutComplete:
    case PageScrolled:
    case ScrolledToAnchor: return RV_AX_EVENT_LAYOUT;
    case MenuOpened: return RV_AX_EVENT_MENU_OPENED;
    case MenuClosed: return RV_AX_EVENT_MENU_CLOSED;
    case TextChanged: return RV_AX_EVENT_TEXT;
    case SelectedTextChanged: return RV_AX_EVENT_TEXT_SELECTION;
    default:
        return std::nullopt;
    }
}

static bool isLive(RvHost* host) { return host && liveHosts.contains(host); }

// Calls the host's accessibility callback for each event posted since the last delivery.
static void deliverAccessibilityEvents(RvHost& host)
{
    host.axDeliveryScheduled = false;
    auto pending = std::exchange(host.axPending, { });
    for (auto& [object, event] : pending) {
        // A callback may turn accessibility off, or destroy the host.
        if (!isLive(&host) || !host.axCallback)
            return;
        if (isGone(object))
            continue;
        host.axCallback(host.axContext, reinterpret_cast<RvAxNode*>(object.ptr()), event);
    }
}

// WebCore posts a notification while it updates its tree, which may be inside an ABI call (patch 0011); the
// host queues it and delivers it on the next run loop cycle.
void RvChromeClient::postAccessibilityNotification(AccessibilityObject& object, AXNotification notification)
{
    if (!host || !host->accessibility || !host->axCallback)
        return;
    auto event = axEvent(notification);
    if (!event)
        return;
    AXCoreObject& core = object;
    for (auto& [queued, queuedEvent] : host->axPending) {
        if (queued.ptr() == &core && queuedEvent == *event)
            return;
    }
    host->axPending.append({ Ref { core }, *event });
    if (host->axDeliveryScheduled)
        return;
    host->axDeliveryScheduled = true;
    RunLoop::mainSingleton().dispatch([target = host] {
        if (isLive(target) && target->axDeliveryScheduled)
            deliverAccessibilityEvents(*target);
    });
}
#endif

// Brings the tree of a document up to date: layout, then the cache's deferred updates.
static AXObjectCache* updatedCache(Document* document)
{
    if (!document)
        return nullptr;
    document->updateLayoutIgnorePendingStylesheets();
    auto* cache = document->axObjectCache();
    if (cache)
        cache->performDeferredCacheUpdate(ForceLayout::Yes);
    return cache;
}

// The host's cache with its tree up to date, or null while the host has accessibility off.
static AXObjectCache* updatedCache(RvHost& host)
{
    return host.accessibility ? updatedCache(&host.document()) : nullptr;
}

// The object itself when exposed, else its nearest exposed ancestor.
static AXCoreObject* exposed(AXCoreObject* object)
{
    while (object && object->isIgnored())
        object = object->parentObject();
    return object;
}

// The web area of a main frame's document: the root of a host's tree.
static bool isTreeRoot(AXCoreObject& object)
{
    if (!object.isWebArea())
        return false;
    RefPtr document = object.document();
    RefPtr frame = document ? document->frame() : nullptr;
    return frame && frame->isMainFrame();
}

int32_t rv_host_set_accessibility(RvHost* host, int32_t enabled, RvAxCallback callback, void* context)
{
    if (!host)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    bool on = !!enabled;
    if (on != host->accessibility) {
        host->accessibility = on;
        accessibilityHosts += on ? 1 : -1;
        if (on && !AXObjectCache::accessibilityEnabled())
            std::ignore = AXObjectCache::attemptMainThreadModeTransition();
        if (!on && !accessibilityHosts)
            AXObjectCache::disableAccessibilityForTesting();
    }
    host->axCallback = on ? callback : nullptr;
    host->axContext = host->axCallback ? context : nullptr;
    if (!host->axCallback) {
        host->axPending.clear();
        host->axDeliveryScheduled = false;
    }
    if (!on)
        return RV_OK;
    // WebCore posts notifications only for a document whose cache exists.
    return host->document().axObjectCache() ? RV_OK : RV_ERR_UNSUPPORTED;
}

RvAxNode* rv_host_ax_root(RvHost* host)
{
    if (!host || !onOwningThread())
        return nullptr;
    auto* cache = updatedCache(*host);
    return cache ? axHandle(cache->exportedGetOrCreate(host->document())) : nullptr;
}

RvAxNode* rv_host_ax_focus(RvHost* host)
{
    if (!host || !onOwningThread())
        return nullptr;
    auto* cache = updatedCache(*host);
    if (!cache)
        return nullptr;
    AXCoreObject* focused = cache->focusedObjectForPage(host->page.ptr());
    return axHandle(focused ? focused : cache->exportedGetOrCreate(host->document()));
}

RvAxNode* rv_host_ax_hit_test(RvHost* host, int32_t x, int32_t y)
{
    if (!host || !onOwningThread())
        return nullptr;
    auto* cache = updatedCache(*host);
    RefPtr view = host->frame().view();
    if (!cache || !view || x < 0 || y < 0 || x >= host->size.width() || y >= host->size.height())
        return nullptr;
    RefPtr<AXCoreObject> root = cache->exportedGetOrCreate(host->document());
    if (!root)
        return nullptr;
    auto hit = root->accessibilityHitTest(view->rootViewToContents(IntPoint { x, y }));
    return axHandle(exposed(hit ? hit.get() : root.get()));
}

RvAxNode* rv_node_ax(RvNode* target)
{
    if (!target || !onOwningThread())
        return nullptr;
    Ref subject = *node(target);
    auto* host = hostForPage(subject->document().page());
    if (!host)
        return nullptr;
    auto* cache = updatedCache(*host);
    AXCoreObject* object = cache ? cache->exportedGetOrCreate(subject.get()) : nullptr;
    return object && !object->isIgnored() ? axHandle(object) : nullptr;
}

RvNode* rv_ax_dom_node(RvAxNode* handle)
{
    if (!handle || !onOwningThread() || isGone(*axObject(handle)))
        return nullptr;
    return handleOrNull(axObject(handle)->node());
}

RvAxNode* rv_ax_retain(RvAxNode* handle)
{
    if (!handle || !onOwningThread())
        return nullptr;
    axObject(handle)->ref();
    return handle;
}

void rv_ax_release(RvAxNode* handle)
{
    if (handle && onOwningThread())
        axObject(handle)->deref();
}

// The checks every function on a node starts with: RV_OK, or the status to return.
static int32_t axStatus(RvAxNode* handle)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (isGone(*axObject(handle)))
        return RV_ERR_DETACHED;
    return RV_OK;
}

int64_t rv_ax_id(RvAxNode* handle)
{
    if (auto status = axStatus(handle))
        return status;
    return static_cast<int64_t>(axObject(handle)->objectID().toUInt64());
}

int32_t rv_ax_role(RvAxNode* handle)
{
    if (auto status = axStatus(handle))
        return status;
    return roleValue(axObject(handle)->role());
}

int32_t rv_ax_states(RvAxNode* handle)
{
    if (auto status = axStatus(handle))
        return status;
    auto& object = *axObject(handle);
    int32_t states = 0;
    auto set = [&](int32_t bit, bool value) {
        if (value)
            states |= bit;
    };
    set(RV_AX_FOCUSABLE, object.canSetFocusAttribute());
    set(RV_AX_FOCUSED, object.isFocused());
    set(RV_AX_DISABLED, !object.isEnabled());
    if (object.supportsCheckedState()) {
        states |= RV_AX_CHECKABLE;
        auto checked = object.checkboxOrRadioValue();
        set(RV_AX_CHECKED, checked == AccessibilityButtonState::On);
        set(RV_AX_MIXED, checked == AccessibilityButtonState::Mixed);
    }
    set(RV_AX_PRESSED, object.isPressed());
    if (object.supportsExpanded()) {
        states |= RV_AX_EXPANDABLE;
        set(RV_AX_EXPANDED, object.isExpanded());
    }
    set(RV_AX_SELECTABLE, object.canSetSelectedAttribute());
    set(RV_AX_SELECTED, object.isSelected());
    set(RV_AX_MULTISELECTABLE, object.isMultiSelectable());
    set(RV_AX_EDITABLE, object.canSetValueAttribute());
    set(RV_AX_REQUIRED, object.isRequired());
    auto invalid = object.invalidStatus();
    set(RV_AX_INVALID, !invalid.isEmpty() && invalid != "false"_s);
    set(RV_AX_MULTILINE, object.role() == AccessibilityRole::TextArea);
    set(RV_AX_PROTECTED, object.isSecureField());
    set(RV_AX_VISITED, object.isVisited());
    set(RV_AX_BUSY, object.isBusy());
    set(RV_AX_MODAL, object.isModalNode());
    set(RV_AX_HAS_POPUP, object.popupValue() != AccessibilityPopupValue::False);
    set(RV_AX_OFFSCREEN, object.isOffScreen());
    set(RV_AX_LIVE_REGION, AXCoreObject::liveRegionStatusIsEnabled(AtomString { object.liveRegionStatus() }));
    return states;
}

// The accessible name, taken from WebCore's text alternatives as the AT-SPI port takes it
// (accessibility/atspi/AccessibilityObjectAtspi.cpp, Copyright (C) 2021 Igalia S.L., LGPL-2.1-or-later): the
// first alternative that is not help text or a summary; an option's value first.
static String axName(AXCoreObject& object)
{
    if (object.role() == AccessibilityRole::ListBoxOption || object.role() == AccessibilityRole::MenuListOption) {
        auto value = object.stringValue();
        if (!value.isEmpty())
            return value;
    }
    Vector<AccessibilityText> texts;
    object.accessibilityText(texts);
    for (auto& text : texts) {
        if (!text.text.isEmpty() && text.textSource != AccessibilityTextSource::Help && text.textSource != AccessibilityTextSource::Summary)
            return text.text;
    }
    // A run of text is named by the text itself.
    if (object.isStaticText())
        return object.stringValue();
    return emptyString();
}

// The accessible description, as the AT-SPI port takes it: help text or a summary, or a title tag when another
// alternative gave the name.
static String axDescription(AXCoreObject& object)
{
    // aria-describedby first. The Cocoa ports leave it out of the text alternatives, which carry it elsewhere
    // as help text, so it is read directly on every port.
    if (auto* accessibility = dynamicDowncast<AccessibilityObject>(object)) {
        auto describedBy = accessibility->ariaDescribedByAttribute();
        if (!describedBy.isEmpty())
            return describedBy;
    }
    Vector<AccessibilityText> texts;
    object.accessibilityText(texts);
    bool named = false;
    for (auto& text : texts) {
        if (text.textSource == AccessibilityTextSource::Help || text.textSource == AccessibilityTextSource::Summary)
            return text.text;
        if (text.textSource == AccessibilityTextSource::TitleTag && named)
            return text.text;
        named = true;
    }
    return emptyString();
}

int32_t rv_ax_string(RvAxNode* handle, int32_t property, char* buffer, int32_t capacity, int32_t* length)
{
    if (auto status = axStatus(handle))
        return status;
    auto& object = *axObject(handle);
    String value;
    switch (property) {
    case RV_AX_NAME:
        value = axName(object);
        break;
    case RV_AX_DESCRIPTION:
        value = axDescription(object);
        break;
    case RV_AX_VALUE:
        value = object.isSecureField() ? emptyString() : object.stringValue();
        break;
    case RV_AX_ROLE_NAME:
        value = object.computedRoleString();
        break;
    case RV_AX_ROLE_DESCRIPTION:
        value = object.ariaRoleDescription();
        break;
    case RV_AX_PLACEHOLDER:
        value = object.placeholderValue();
        break;
    case RV_AX_KEY_SHORTCUTS:
        value = object.keyShortcuts();
        break;
    case RV_AX_URL:
        value = object.isLink() ? object.url().string() : emptyString();
        break;
    case RV_AX_LIVE: {
        auto live = object.liveRegionStatus();
        value = AXCoreObject::liveRegionStatusIsEnabled(AtomString { live }) ? live : emptyString();
        break;
    }
    case RV_AX_TEXT:
        value = object.textUnderElement();
        break;
    default:
        return RV_ERR_UNSUPPORTED;
    }
    return copyString(value.isNull() ? emptyString() : value, buffer, capacity, length);
}

static bool isRange(const AXCoreObject& object)
{
    switch (object.role()) {
    case AccessibilityRole::Slider:
    case AccessibilityRole::SpinButton:
    case AccessibilityRole::ProgressIndicator:
    case AccessibilityRole::Meter:
    case AccessibilityRole::ScrollBar:
        return true;
    default:
        return false;
    }
}

int32_t rv_ax_number(RvAxNode* handle, int32_t property, double* value)
{
    if (!value)
        return RV_ERR_NULL_ARGUMENT;
    if (auto status = axStatus(handle))
        return status;
    auto& object = *axObject(handle);
    switch (property) {
    case RV_AX_NUMBER_VALUE:
    case RV_AX_NUMBER_MIN:
    case RV_AX_NUMBER_MAX:
        if (!isRange(object))
            return RV_ERR_UNSUPPORTED;
        *value = property == RV_AX_NUMBER_VALUE ? object.valueForRange() : property == RV_AX_NUMBER_MIN ? object.minValueForRange() : object.maxValueForRange();
        return RV_OK;
    case RV_AX_NUMBER_LEVEL: {
        unsigned level = object.isHeading() ? object.headingLevel() : object.role() == AccessibilityRole::TreeItem ? object.hierarchicalLevel() : 0;
        if (!level)
            return RV_ERR_UNSUPPORTED;
        *value = level;
        return RV_OK;
    }
    }
    return RV_ERR_UNSUPPORTED;
}

int32_t rv_ax_rect(RvAxNode* handle, double* x, double* y, double* width, double* height)
{
    if (!x || !y || !width || !height)
        return RV_ERR_NULL_ARGUMENT;
    if (auto status = axStatus(handle))
        return status;
    Ref object = *axObject(handle);
    updatedCache(object->document());
    if (isGone(object))
        return RV_ERR_DETACHED;
    RefPtr view = object->documentFrameView();
    FloatRect rect;
    // The root is the viewport, scroll bars included; its element rectangle is the whole document.
    if (isTreeRoot(object) && view)
        rect = FloatRect { { }, view->frameRect().size() };
    else if (view)
        rect = view->contentsToRootView(snappedIntRect(object->elementRect()));
    *x = rect.x();
    *y = rect.y();
    *width = rect.width();
    *height = rect.height();
    return RV_OK;
}

RvAxNode* rv_ax_parent(RvAxNode* handle)
{
    if (axStatus(handle))
        return nullptr;
    auto& object = *axObject(handle);
    if (isTreeRoot(object))
        return nullptr;
    return axHandle(object.parentObjectUnignored());
}

int32_t rv_ax_children(RvAxNode* handle, RvAxNode** nodes, int32_t capacity, int32_t* count)
{
    if (!count)
        return RV_ERR_NULL_ARGUMENT;
    if (auto status = axStatus(handle))
        return status;
    Ref object = *axObject(handle);
    updatedCache(object->document());
    if (isGone(object))
        return RV_ERR_DETACHED;
    auto children = object->unignoredChildren();
    *count = static_cast<int32_t>(children.size());
    if (!nodes || capacity < *count)
        return RV_ERR_BUFFER_TOO_SMALL;
    for (size_t i = 0; i < children.size(); ++i)
        nodes[i] = axHandle(children[i].ptr());
    return RV_OK;
}

int32_t rv_ax_relations(RvAxNode* handle, int32_t kind, RvAxNode** nodes, int32_t capacity, int32_t* count)
{
    if (!count)
        return RV_ERR_NULL_ARGUMENT;
    if (auto status = axStatus(handle))
        return status;
    static constexpr AXRelation relations[] = { AXRelation::ActiveDescendant, AXRelation::ControllerFor, AXRelation::DescribedBy,
        AXRelation::Details, AXRelation::ErrorMessage, AXRelation::FlowsTo, AXRelation::LabeledBy, AXRelation::OwnerFor };
    if (kind < 0 || kind >= static_cast<int32_t>(std::size(relations)))
        return RV_ERR_UNSUPPORTED;
    Ref object = *axObject(handle);
    updatedCache(object->document());
    if (isGone(object))
        return RV_ERR_DETACHED;
    auto targets = object->relatedObjects(relations[kind]);
    *count = static_cast<int32_t>(targets.size());
    if (!nodes || capacity < *count)
        return RV_ERR_BUFFER_TOO_SMALL;
    for (size_t i = 0; i < targets.size(); ++i)
        nodes[i] = axHandle(targets[i].ptr());
    return RV_OK;
}

int32_t rv_ax_action(RvAxNode* handle, int32_t action)
{
    if (auto status = axStatus(handle))
        return status;
    Ref object = *axObject(handle);
    switch (action) {
    case RV_AX_PRESS: {
        bool pressed = false;
        auto status = dispatchCountingFailures([&] { pressed = object->press(); });
        return status ? status : pressed ? 1 : 0;
    }
    case RV_AX_FOCUS:
        if (!object->canSetFocusAttribute())
            return 0;
        object->setFocused(true);
        return 1;
    case RV_AX_SCROLL_INTO_VIEW:
        object->scrollToMakeVisible();
        return 1;
    case RV_AX_INCREMENT:
    case RV_AX_DECREMENT:
        if (!isRange(object) || !object->canSetValueAttribute())
            return 0;
        if (action == RV_AX_INCREMENT)
            object->increment();
        else
            object->decrement();
        return 1;
    case RV_AX_EXPAND:
    case RV_AX_COLLAPSE: {
        if (!object->supportsExpanded())
            return 0;
        bool expand = action == RV_AX_EXPAND;
        if (object->isExpanded() != expand)
            object->setIsExpanded(expand);
        return object->isExpanded() == expand ? 1 : 0;
    }
    case RV_AX_SELECT:
        if (!object->canSetSelectedAttribute())
            return 0;
        object->setSelected(true);
        return 1;
    }
    return RV_ERR_UNSUPPORTED;
}

int32_t rv_ax_set_value(RvAxNode* handle, const char* value)
{
    if (!value)
        return RV_ERR_NULL_ARGUMENT;
    if (auto status = axStatus(handle))
        return status;
    Ref object = *axObject(handle);
    if (!object->canSetValueAttribute() || isRange(object))
        return 0;
    // A form field's value changes as a user's edit does, with input and change.
    if (RefPtr input = dynamicDowncast<HTMLInputElement>(object->node())) {
        auto result = input->setValue(utf8(value), DispatchInputAndChangeEvent);
        return result.hasException() ? fail(result.exception()) : 1;
    }
    if (RefPtr area = dynamicDowncast<HTMLTextAreaElement>(object->node())) {
        area->setValue(utf8(value), DispatchInputAndChangeEvent);
        return 1;
    }
    return object->setValue(utf8(value)) ? 1 : 0;
}

int32_t rv_ax_set_number(RvAxNode* handle, double value)
{
    if (auto status = axStatus(handle))
        return status;
    Ref object = *axObject(handle);
    if (!object->canSetValueAttribute() || !isRange(object))
        return 0;
    auto clamped = std::clamp<double>(value, object->minValueForRange(), object->maxValueForRange());
    // A range input's value changes as a user's drag does, with input and change.
    if (RefPtr input = dynamicDowncast<HTMLInputElement>(object->node())) {
        auto result = input->setValue(String::number(clamped), DispatchInputAndChangeEvent);
        return result.hasException() ? fail(result.exception()) : 1;
    }
    return object->setValue(static_cast<float>(clamped)) ? 1 : 0;
}

// Accessibility text: a node's text as UTF-16 offsets, for the platforms' text interfaces (docs/ACCESSIBILITY.md).

// The DOM range whose text is the node's text: a text field's inner editor, else the node's contents. Null for a
// node without a DOM node.
static std::optional<SimpleRange> textScope(AXCoreObject& object)
{
    RefPtr subject = object.node();
    if (!subject)
        return std::nullopt;
    subject->document().updateLayoutIgnorePendingStylesheets();
    if (RefPtr control = dynamicDowncast<HTMLTextFormControlElement>(*subject)) {
        RefPtr inner = control->innerTextElement();
        if (!inner)
            return std::nullopt;
        return makeRangeSelectingNodeContents(*inner);
    }
    return makeRangeSelectingNodeContents(*subject);
}

// The offset of a boundary point in the scope, clamped to it.
static int32_t textOffset(const SimpleRange& scope, const std::optional<BoundaryPoint>& point)
{
    if (!point || is_lteq(treeOrder<ComposedTree>(*point, scope.start)))
        return 0;
    if (is_gteq(treeOrder<ComposedTree>(*point, scope.end)))
        return static_cast<int32_t>(characterCount(scope));
    return static_cast<int32_t>(characterCount({ scope.start, *point }));
}

static int32_t textOffset(const SimpleRange& scope, const VisiblePosition& position)
{
    return textOffset(scope, makeBoundaryPoint(position));
}

// Whether a boundary point lies in the scope, its ends included.
static bool inScope(const SimpleRange& scope, const std::optional<BoundaryPoint>& point)
{
    return point && is_gteq(treeOrder<ComposedTree>(*point, scope.start)) && is_lteq(treeOrder<ComposedTree>(*point, scope.end));
}

static SimpleRange textRange(const SimpleRange& scope, int32_t start, int32_t end)
{
    return resolveCharacterRange(scope, { static_cast<uint64_t>(start), static_cast<uint64_t>(end - start) });
}

static VisiblePosition textPosition(const SimpleRange& scope, int32_t offset)
{
    return VisiblePosition { makeContainerOffsetPosition(textRange(scope, offset, offset).start) };
}

// The checks the text functions start with, and the scope of the node's text.
static int32_t textStatus(RvAxNode* handle, std::optional<SimpleRange>& scope)
{
    if (auto status = axStatus(handle))
        return status;
    scope = textScope(*axObject(handle));
    return scope ? RV_OK : RV_ERR_UNSUPPORTED;
}

int32_t rv_ax_text_child_range(RvAxNode* ancestor, RvAxNode* child, int32_t* start, int32_t* end)
{
    if (!start || !end)
        return RV_ERR_NULL_ARGUMENT;
    std::optional<SimpleRange> parentScope, childScope;
    if (auto result = textStatus(ancestor, parentScope))
        return result;
    if (auto result = textStatus(child, childScope))
        return result;
    std::optional<BoundaryPoint> first { childScope->start }, last { childScope->end };
    if (!inScope(*parentScope, first) || !inScope(*parentScope, last))
        return RV_ERR_UNSUPPORTED;
    *start = textOffset(*parentScope, first);
    *end = textOffset(*parentScope, last);
    return RV_OK;
}

// The text of the scope, with a password field's characters masked.
static String scopeText(AXCoreObject& object, const SimpleRange& scope)
{
    auto text = plainText(scope);
    if (!object.isSecureField())
        return text;
    StringBuilder masked;
    for (unsigned i = 0; i < text.length(); ++i)
        masked.append(static_cast<char16_t>(0x2022));
    return masked.toString();
}

int32_t rv_ax_text_length(RvAxNode* handle)
{
    std::optional<SimpleRange> scope;
    if (auto status = textStatus(handle, scope))
        return status;
    return static_cast<int32_t>(characterCount(*scope));
}

int32_t rv_ax_text(RvAxNode* handle, int32_t start, int32_t end, char* buffer, int32_t capacity, int32_t* length)
{
    std::optional<SimpleRange> scope;
    if (auto status = textStatus(handle, scope))
        return status;
    auto text = scopeText(*axObject(handle), *scope);
    if (start < 0 || end < start || static_cast<unsigned>(end) > text.length())
        return RV_ERR_UNSUPPORTED;
    return copyString(text.substring(start, end - start), buffer, capacity, length);
}

int32_t rv_ax_text_boundary(RvAxNode* handle, int32_t offset, int32_t unit, int32_t* start, int32_t* end)
{
    if (!start || !end)
        return RV_ERR_NULL_ARGUMENT;
    std::optional<SimpleRange> scope;
    if (auto status = textStatus(handle, scope))
        return status;
    auto text = plainText(*scope);
    int32_t length = static_cast<int32_t>(text.length());
    if (offset < 0 || offset > length)
        return RV_ERR_UNSUPPORTED;
    if (unit == RV_TEXT_CHARACTER) {
        // A character at the end of the text is the empty unit there; a surrogate pair is one character.
        *start = offset;
        *end = offset < length ? offset + (U16_IS_LEAD(text[offset]) && offset + 1 < length && U16_IS_TRAIL(text[offset + 1]) ? 2 : 1) : offset;
        return RV_OK;
    }
    auto position = textPosition(*scope, offset);
    VisiblePosition first, last;
    switch (unit) {
    case RV_TEXT_WORD:
        first = startOfWord(position);
        last = endOfWord(position);
        break;
    case RV_TEXT_LINE:
        first = startOfLine(position);
        last = endOfLine(position);
        break;
    case RV_TEXT_SENTENCE:
        first = startOfSentence(position);
        last = endOfSentence(position);
        break;
    case RV_TEXT_PARAGRAPH:
        first = startOfParagraph(position);
        last = endOfParagraph(position);
        break;
    default:
        return RV_ERR_UNSUPPORTED;
    }
    *start = first.isNull() ? offset : textOffset(*scope, first);
    *end = last.isNull() ? offset : textOffset(*scope, last);
    // The unit ends before the newline that separates it from the next, which belongs to it.
    if (unit != RV_TEXT_WORD && *end < length && text[*end] == '\n')
        ++*end;
    if (*end < *start)
        *end = *start;
    return RV_OK;
}

int32_t rv_ax_text_selection(RvAxNode* handle, int32_t* start, int32_t* end)
{
    if (!start || !end)
        return RV_ERR_NULL_ARGUMENT;
    std::optional<SimpleRange> scope;
    if (auto status = textStatus(handle, scope))
        return status;
    *start = *end = -1;
    RefPtr frame = axObject(handle)->node()->document().frame();
    if (!frame)
        return 0;
    auto selection = frame->selection().selection();
    auto range = selection.firstRange();
    if (!range)
        return 0;
    auto overlap = intersection(*range, *scope);
    // A caret is in the scope when its point is; a range when it overlaps the scope.
    if (selection.isCaret() ? !inScope(*scope, range->start) : (!overlap || overlap->collapsed()))
        return 0;
    auto found = overlap ? *overlap : *range;
    *start = textOffset(*scope, found.start);
    *end = textOffset(*scope, found.end);
    return 1;
}

int32_t rv_ax_text_caret(RvAxNode* handle)
{
    std::optional<SimpleRange> scope;
    if (auto status = textStatus(handle, scope))
        return status;
    RefPtr frame = axObject(handle)->node()->document().frame();
    if (!frame)
        return -1;
    auto selection = frame->selection().selection();
    if (selection.isNone())
        return -1;
    auto focus = makeBoundaryPoint(selection.visibleExtent());
    return inScope(*scope, focus) ? textOffset(*scope, focus) : -1;
}

int32_t rv_ax_text_set_selection(RvAxNode* handle, int32_t start, int32_t end)
{
    std::optional<SimpleRange> scope;
    if (auto status = textStatus(handle, scope))
        return status;
    int32_t length = static_cast<int32_t>(characterCount(*scope));
    if (start < 0 || end < start || end > length)
        return RV_ERR_UNSUPPORTED;
    RefPtr frame = axObject(handle)->node()->document().frame();
    if (!frame)
        return RV_ERR_UNSUPPORTED;
    frame->selection().setSelection(VisibleSelection { textRange(*scope, start, end) });
    return RV_OK;
}

int32_t rv_ax_text_rects(RvAxNode* handle, int32_t start, int32_t end, double* rects, int32_t capacity, int32_t* count)
{
    if (!count)
        return RV_ERR_NULL_ARGUMENT;
    std::optional<SimpleRange> scope;
    if (auto status = textStatus(handle, scope))
        return status;
    int32_t length = static_cast<int32_t>(characterCount(*scope));
    if (start < 0 || end < start || end > length)
        return RV_ERR_UNSUPPORTED;
    RefPtr view = axObject(handle)->node()->document().view();
    if (!view)
        return RV_ERR_UNSUPPORTED;
    Vector<IntRect> found;
    if (start == end)
        found.append(textPosition(*scope, start).absoluteCaretBounds());
    else
        found = RenderObject::absoluteTextRects(textRange(*scope, start, end));
    found.removeAllMatching([](auto& rect) { return rect.isEmpty() && !rect.height(); });
    *count = static_cast<int32_t>(found.size());
    if (!rects || capacity < *count)
        return RV_ERR_BUFFER_TOO_SMALL;
    for (size_t i = 0; i < found.size(); ++i) {
        auto rect = view->contentsToRootView(found[i]);
        rects[i * 4] = rect.x();
        rects[i * 4 + 1] = rect.y();
        rects[i * 4 + 2] = rect.width();
        rects[i * 4 + 3] = rect.height();
    }
    return RV_OK;
}

int32_t rv_ax_text_offset_at(RvAxNode* handle, int32_t x, int32_t y)
{
    std::optional<SimpleRange> scope;
    if (auto status = textStatus(handle, scope))
        return status;
    RefPtr frame = axObject(handle)->node()->document().frame();
    RefPtr view = frame ? frame->view() : nullptr;
    if (!view)
        return -1;
    auto point = makeBoundaryPoint(frame->visiblePositionForPoint(view->rootViewToContents(IntPoint { x, y })));
    return inScope(*scope, point) ? textOffset(*scope, point) : -1;
}

// Text segmentation.

static int32_t textSegmentFailure(RvTextSegments* result, int32_t status)
{
    rv_text_segments_release(result);
    return status;
}

static char* copyLocale(const char* value)
{
    auto length = std::strlen(value ? value : "");
    auto* copy = static_cast<char*>(std::malloc(length + 1));
    RELEASE_ASSERT(copy);
    std::memcpy(copy, value ? value : "", length);
    copy[length] = 0;
    return copy;
}

int32_t rv_text_segment(int32_t granularity, const char* locale, const uint16_t* text, int32_t length, RvTextSegments* result)
{
    if (!result || length < 0 || (length && !text))
        return RV_ERR_NULL_ARGUMENT;
    *result = { };
    if (!segmentationInitialized || !onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (granularity < RV_SEGMENT_GRAPHEME || granularity > RV_SEGMENT_LINE)
        return RV_ERR_UNSUPPORTED;
    char icuLocale[ULOC_FULLNAME_CAPACITY] = { };
    if (locale && *locale) {
        UErrorCode status = U_ZERO_ERROR;
        int32_t parsed = 0;
        auto tagLength = static_cast<int32_t>(std::strlen(locale));
        uloc_forLanguageTag(locale, icuLocale, sizeof(icuLocale), &parsed, &status);
        if (U_FAILURE(status) || status == U_STRING_NOT_TERMINATED_WARNING || parsed != tagLength)
            return fail(Exception { ExceptionCode::RangeError, "Incorrect locale information provided"_s });
    }
    static constexpr UBreakIteratorType types[] = { UBRK_CHARACTER, UBRK_WORD, UBRK_SENTENCE, UBRK_LINE };
    auto type = types[granularity];
    auto* units = reinterpret_cast<const UChar*>(text);
    UErrorCode status = U_ZERO_ERROR;
    // An ICU iterator of the same type reports the locale, and serves words and sentences, whose WTF iterators
    // ignore the locale.
    UBreakIterator* icu = ubrk_open(type, icuLocale, length ? units : u"", length, &status);
    if (U_FAILURE(status) || !icu)
        return textSegmentFailure(result, RV_ERR_UNSUPPORTED);
    status = U_ZERO_ERROR;
    result->locale = copyLocale(ubrk_getLocaleByType(icu, ULOC_VALID_LOCALE, &status));
    Vector<int32_t> starts;
    Vector<int32_t> wordLike;
    if (length) {
        if (granularity == RV_SEGMENT_GRAPHEME || granularity == RV_SEGMENT_LINE) {
            StringView view { std::span<const char16_t> { reinterpret_cast<const char16_t*>(text), static_cast<size_t>(length) } };
            TextBreakIterator::Mode mode = TextBreakIterator::CaretMode { };
            if (granularity == RV_SEGMENT_LINE)
                mode = TextBreakIterator::LineMode { TextBreakIterator::LineMode::Behavior::Default };
            CachedTextBreakIterator iterator(view, { }, mode, AtomString { String::fromLatin1(icuLocale) });
            unsigned position = 0;
            while (position < static_cast<unsigned>(length)) {
                starts.append(static_cast<int32_t>(position));
                auto next = iterator.following(position);
                if (!next || *next <= position || *next > static_cast<unsigned>(length))
                    break;
                position = *next;
            }
        } else {
            for (int32_t start = ubrk_first(icu), end = ubrk_next(icu); end != UBRK_DONE; start = end, end = ubrk_next(icu)) {
                starts.append(start);
                if (granularity == RV_SEGMENT_WORD)
                    wordLike.append(ubrk_getRuleStatus(icu) >= UBRK_WORD_NONE_LIMIT ? 1 : 0);
            }
        }
    }
    ubrk_close(icu);
    if (length && granularity != RV_SEGMENT_GRAPHEME) {
        // A boundary inside a grapheme cluster joins its two segments, so no segment splits a grapheme; a joined
        // word is word-like when either part is.
        StringView view { std::span<const char16_t> { reinterpret_cast<const char16_t*>(text), static_cast<size_t>(length) } };
        CachedTextBreakIterator graphemes(view, { }, TextBreakIterator::CaretMode { }, AtomString { String::fromLatin1(icuLocale) });
        Vector<int32_t> keptStarts;
        Vector<int32_t> keptWordLike;
        for (size_t index = 0; index < starts.size(); ++index) {
            if (index && !graphemes.isBoundary(static_cast<unsigned>(starts[index]))) {
                if (granularity == RV_SEGMENT_WORD)
                    keptWordLike.last() |= wordLike[index];
                continue;
            }
            keptStarts.append(starts[index]);
            if (granularity == RV_SEGMENT_WORD)
                keptWordLike.append(wordLike[index]);
        }
        starts = WTF::move(keptStarts);
        wordLike = WTF::move(keptWordLike);
    }
    result->count = static_cast<int32_t>(starts.size());
    if (!starts.isEmpty()) {
        result->starts = static_cast<int32_t*>(std::malloc(starts.size() * sizeof(int32_t)));
        RELEASE_ASSERT(result->starts);
        std::memcpy(result->starts, starts.span().data(), starts.size() * sizeof(int32_t));
        if (granularity == RV_SEGMENT_WORD) {
            result->word_like = static_cast<int32_t*>(std::malloc(wordLike.size() * sizeof(int32_t)));
            RELEASE_ASSERT(result->word_like);
            std::memcpy(result->word_like, wordLike.span().data(), wordLike.size() * sizeof(int32_t));
        }
    }
    return RV_OK;
}

int32_t rv_text_segmentation_version(char* buffer, int32_t capacity, int32_t* length)
{
    if (!length || capacity < 0 || (capacity && !buffer))
        return RV_ERR_NULL_ARGUMENT;
    UVersionInfo icu { };
    UVersionInfo unicode { };
    u_getVersion(icu);
    u_getUnicodeVersion(unicode);
    auto text = makeString("icu="_s, icu[0], '.', icu[1], " unicode="_s, unicode[0], '.', unicode[1]).utf8();
    *length = static_cast<int32_t>(text.length());
    if (capacity < *length)
        return RV_ERR_BUFFER_TOO_SMALL;
    std::memcpy(buffer, text.data(), text.length());
    return RV_OK;
}

void rv_text_segments_release(RvTextSegments* segments)
{
    if (!segments)
        return;
    std::free(segments->starts);
    std::free(segments->word_like);
    std::free(segments->locale);
    *segments = { };
}
