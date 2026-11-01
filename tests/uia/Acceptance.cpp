#define NOMINMAX
#include <windows.h>
#include <UIAutomation.h>
#include <wrl/client.h>
#include <atomic>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>
#include "../../host/RanvierWebCoreAbi.h"

// A string literal's UTF-8 bytes and byte count, for a length-delimited string input.
#define RV_TEXT(literal) reinterpret_cast<const uint8_t*>(literal), static_cast<int32_t>(sizeof(literal) - 1)

using Microsoft::WRL::ComPtr;
constexpr UINT removeMessage = WM_APP + 21;
constexpr UINT closeMessage = WM_APP + 22;
constexpr UINT addChurnMessage = WM_APP + 23;
constexpr UINT removeChurnMessage = WM_APP + 24;
constexpr UINT cacheSizeMessage = WM_APP + 25;
static bool closeRequested = false;
static bool synchronousDetach = false;
void require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
void ok(HRESULT result, const char* message) { if (FAILED(result)) { std::fprintf(stderr, "%s: HRESULT %08lx\n", message, result); throw std::runtime_error(message); } }
std::wstring name(IUIAutomationElement* element)
{
    BSTR value = nullptr; ok(element->get_CurrentName(&value), "read name");
    std::wstring result(value ? value : L""); SysFreeString(value); return result;
}
ComPtr<IUIAutomationElement> find(IUIAutomation* automation, IUIAutomationElement* root, const wchar_t* value, CONTROLTYPEID type = 0)
{
    VARIANT v {}; v.vt = VT_BSTR; v.bstrVal = SysAllocString(value);
    ComPtr<IUIAutomationCondition> condition;
    ok(automation->CreatePropertyCondition(UIA_NamePropertyId, v, &condition), "name condition"); VariantClear(&v);
    if (type) {
        v.vt = VT_I4; v.lVal = type;
        ComPtr<IUIAutomationCondition> kind, both;
        ok(automation->CreatePropertyCondition(UIA_ControlTypePropertyId, v, &kind), "type condition");
        ok(automation->CreateAndCondition(condition.Get(), kind.Get(), &both), "name and type condition"); condition = both;
    }
    ComPtr<IUIAutomationElement> result;
    ok(root->FindFirst(TreeScope_Descendants, condition.Get(), &result), "find descendant");
    return result;
}
template<class T> ComPtr<T> pattern(IUIAutomationElement* element, PATTERNID id)
{
    ComPtr<T> result; ok(element->GetCurrentPatternAs(id, __uuidof(T), reinterpret_cast<void**>(result.GetAddressOf())), "get pattern");
    require(result.Get() != nullptr, "expected pattern is missing"); return result;
}
class NameEvents final : public IUIAutomationPropertyChangedEventHandler {
    std::atomic<ULONG> references { 1 };
public:
    std::atomic<int> count { 0 };
    PROPERTYID expected = UIA_NamePropertyId;
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** out) override { if (!out) return E_POINTER; *out = nullptr; if (iid != IID_IUnknown && iid != __uuidof(IUIAutomationPropertyChangedEventHandler)) return E_NOINTERFACE; *out = this; AddRef(); return S_OK; }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references; }
    ULONG STDMETHODCALLTYPE Release() override { auto left = --references; if (!left) delete this; return left; }
    HRESULT STDMETHODCALLTYPE HandlePropertyChangedEvent(IUIAutomationElement*, PROPERTYID property, VARIANT) override { if (property == expected) ++count; return S_OK; }
};

int client(HWND hwnd, const std::string& mode)
{
    ok(CoInitializeEx(nullptr, COINIT_MULTITHREADED), "client COM MTA");
    int result = 0;
    try {
        ComPtr<IUIAutomation> automation;
        ok(CoCreateInstance(CLSID_CUIAutomation, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&automation)), "create OS UI Automation client");
        ComPtr<IUIAutomationElement> root;
        ok(automation->ElementFromHandle(hwnd, &root), "discover HWND through OS UIA");
        // Window messages are externally sendable. An unsolicited internal-dispatch message must be harmless.
        SendMessageW(hwnd, RegisterWindowMessageW(L"Ranvier.UIAutomation.Dispatch.v1"), 0, 0);
        auto button = find(automation.Get(), root.Get(), L"Press me");
        require(button.Get(), "WebCore button absent from actual OS accessibility tree");
        CONTROLTYPEID type = 0; ok(button->get_CurrentControlType(&type), "button control type"); require(type == UIA_ButtonControlTypeId, "button control type mapping");
        BSTR localizedType = nullptr; ok(button->get_CurrentLocalizedControlType(&localizedType), "localized control type");
        require(localizedType && SysStringLen(localizedType), "default localized button role is empty"); SysFreeString(localizedType);
        require(!find(automation.Get(), root.Get(), L"Hidden secret"), "hidden element exposed");
        RECT bounds {}; ok(button->get_CurrentBoundingRectangle(&bounds), "button bounds"); require(bounds.right > bounds.left && bounds.bottom > bounds.top, "button bounds are empty");
        POINT clientOrigin {}; ClientToScreen(hwnd, &clientOrigin); require(bounds.left >= clientOrigin.x && bounds.top >= clientOrigin.y, "bounds are not screen coordinates");
        if (mode == "overflow") {
            require(abs(bounds.left - clientOrigin.x - 30) <= 1 && abs(bounds.top - clientOrigin.y - 45) <= 1 && abs(bounds.right - bounds.left - 120) <= 1 && abs(bounds.bottom - bounds.top - 48) <= 1,
                "moved HWND + overflowing document + scale1.5 produced incorrect physical screen bounds");
        }
        POINT center { (bounds.left + bounds.right)/2, (bounds.top + bounds.bottom)/2 };
        ComPtr<IUIAutomationElement> hit; ok(automation->ElementFromPoint(center, &hit), "OS hit testing");
        std::fwprintf(stderr, L"UIA point %ld,%ld found '%ls' (button rect %ld,%ld,%ld,%ld)\n", center.x, center.y, name(hit.Get()).c_str(), bounds.left, bounds.top, bounds.right, bounds.bottom);
        require(name(hit.Get()) == L"Press me", "hit test does not find rendered button");
        SAFEARRAY* before = nullptr; ok(button->GetRuntimeId(&before), "runtime identity before action");
        auto events = new NameEvents;
        PROPERTYID names[] = { UIA_NamePropertyId };
        ok(automation->AddPropertyChangedEventHandlerNativeArray(button.Get(), TreeScope_Element, nullptr, events, names, 1), "subscribe to actual UIA property changes");
        auto invoke = pattern<IUIAutomationInvokePattern>(button.Get(), UIA_InvokePatternId);
        ok(invoke->Invoke(), "OS invoke action");
        require(name(button.Get()) == L"Pressed once", "Invoke did not mutate the WebCore DOM");
        auto renamed = find(automation.Get(), root.Get(), L"Pressed once"); require(renamed.Get(), "changed name absent from tree");
        auto documentText = pattern<IUIAutomationTextPattern>(root.Get(), UIA_TextPatternId);
        ComPtr<IUIAutomationTextRange> childRange;
        ok(documentText->RangeFromChild(renamed.Get(), &childRange), "document text range for actual child");
        BSTR childText = nullptr; ok(childRange->GetText(-1, &childText), "read child text in document range");
        require(std::wstring(childText) == L"Pressed once", "RangeFromChild offsets do not enclose the child's text"); SysFreeString(childText);
        ComPtr<IUIAutomationElement> enclosing;
        ok(childRange->GetEnclosingElement(&enclosing), "innermost enclosing element of child text");
        CONTROLTYPEID enclosingType = 0; ok(enclosing->get_CurrentControlType(&enclosingType), "enclosing element type");
        require(enclosingType != UIA_DocumentControlTypeId && name(enclosing.Get()) == L"Pressed once", "child text range reports its document instead of its innermost enclosing element");
        ComPtr<IUIAutomationTextRange> documentRange; ok(documentText->get_DocumentRange(&documentRange), "document range");
        ComPtr<IUIAutomationElementArray> embedded; ok(documentRange->GetChildren(&embedded), "document range children");
        int embeddedCount = 0; ok(embedded->get_Length(&embeddedCount), "document range child count");
        require(embeddedCount > 0, "document text range hid all of its accessible child elements");
        SAFEARRAY* after = nullptr; ok(renamed->GetRuntimeId(&after), "runtime identity after action");
        BOOL equal = FALSE; ok(automation->CompareRuntimeIds(before, after, &equal), "compare runtime identity");
        SafeArrayDestroy(before); SafeArrayDestroy(after); require(equal, "provider identity changed during property update");
        for (int i = 0; i < 300 && events->count.load() == 0; ++i) Sleep(10);
        require(events->count.load() > 0, "name change notification absent from OS UIA subscription");
        ok(automation->RemovePropertyChangedEventHandler(button.Get(), events), "unsubscribe UIA event"); events->Release();

        auto edit = find(automation.Get(), root.Get(), L"Your name", UIA_EditControlTypeId); require(edit.Get(), "labelled input absent");
        auto value = pattern<IUIAutomationValuePattern>(edit.Get(), UIA_ValuePatternId);
        BSTR input = SysAllocString(L"Ada \xD83D\xDE00"); ok(value->SetValue(input), "OS SetValue"); SysFreeString(input);
        BSTR actual = nullptr; ok(value->get_CurrentValue(&actual), "read OS value"); require(std::wstring(actual) == L"Ada \xD83D\xDE00", "UTF16/UTF8 editable value mismatch"); SysFreeString(actual);
        auto text = pattern<IUIAutomationTextPattern>(edit.Get(), UIA_TextPatternId);
        ComPtr<IUIAutomationTextRange> range; ok(text->get_DocumentRange(&range), "text document range");
        ok(range->GetText(-1, &actual), "read text through OS range"); require(std::wstring(actual) == L"Ada \xD83D\xDE00", "text range contents mismatch"); SysFreeString(actual);
        ComPtr<IUIAutomationTextRange> copy; ok(range->Clone(&copy), "clone text range");
        ok(copy->Compare(range.Get(), &equal), "compare cloned ranges"); require(equal, "clone changed endpoints");
        int moved = 0; ok(copy->MoveEndpointByUnit(TextPatternRangeEndpoint_End, TextUnit_Character, -1, &moved), "move text endpoint by code point"); require(moved == -1, "character endpoint movement count");
        ok(copy->GetText(-1, &actual), "read shortened text range"); require(std::wstring(actual) == L"Ada ", "character endpoint split a surrogate pair"); SysFreeString(actual);
        ok(copy->Select(), "OS text selection");
        ComPtr<IUIAutomationTextRangeArray> selection; ok(text->GetSelection(&selection), "read selected ranges");
        int length = 0; ok(selection->get_Length(&length), "selection count"); require(length == 1, "single selection missing");
        ComPtr<IUIAutomationTextRange> selected; ok(selection->GetElement(0, &selected), "selected range");
        ok(selected->GetText(-1, &actual), "selected text"); require(std::wstring(actual) == L"Ada ", "selection not reflected in WebCore"); SysFreeString(actual);
        SAFEARRAY* rectangles = nullptr; ok(range->GetBoundingRectangles(&rectangles), "text range screen geometry");
        LONG lower = 0, upper = -1; SafeArrayGetLBound(rectangles, 1, &lower); SafeArrayGetUBound(rectangles, 1, &upper); require(upper-lower+1 >= 4, "text geometry empty"); SafeArrayDestroy(rectangles);
        if (mode != "cache") {
            ComPtr<IUIAutomationTextRange> caret; ok(range->Clone(&caret), "caret range clone");
            ok(caret->MoveEndpointByRange(TextPatternRangeEndpoint_End, caret.Get(), TextPatternRangeEndpoint_Start), "collapse caret range");
            ok(caret->GetBoundingRectangles(&rectangles), "degenerate range rectangles");
            SafeArrayGetLBound(rectangles, 1, &lower); SafeArrayGetUBound(rectangles, 1, &upper);
            require(upper < lower, "UIA degenerate text range incorrectly exposes a native caret rectangle"); SafeArrayDestroy(rectangles);
            BSTR needle = SysAllocString(L"Far below"); ComPtr<IUIAutomationTextRange> offscreen;
            ok(documentRange->FindText(needle, FALSE, FALSE, &offscreen), "find offscreen text range"); SysFreeString(needle);
            require(offscreen.Get(), "offscreen text absent from document text");
            ok(offscreen->GetBoundingRectangles(&rectangles), "offscreen range rectangles");
            SafeArrayGetLBound(rectangles, 1, &lower); SafeArrayGetUBound(rectangles, 1, &upper);
            require(upper < lower, "UIA text geometry exposes text wholly outside the viewport"); SafeArrayDestroy(rectangles);
        }
        VARIANT attribute {}; ok(range->GetAttributeValue(UIA_FontNameAttributeId, &attribute), "unsupported text attribute");
        IUnknown* unsupported = nullptr; ok(automation->get_ReservedNotSupportedValue(&unsupported), "reserved unsupported value");
        require(attribute.vt == VT_UNKNOWN, "unsupported text attribute fabricated a value");
        BOOL same = FALSE; // The OS marshals the reserved sentinel back into its canonical identity.
        IUnknown* actualUnknown = nullptr; attribute.punkVal->QueryInterface(IID_IUnknown, reinterpret_cast<void**>(&actualUnknown));
        IUnknown* expectedUnknown = nullptr; unsupported->QueryInterface(IID_IUnknown, reinterpret_cast<void**>(&expectedUnknown));
        same = actualUnknown == expectedUnknown; actualUnknown->Release(); expectedUnknown->Release(); unsupported->Release(); VariantClear(&attribute); require(same, "unsupported text attribute sentinel mismatch");
        auto checkbox = find(automation.Get(), root.Get(), L"Accept terms", UIA_CheckBoxControlTypeId); require(checkbox.Get(), "checkbox absent");
        auto toggle = pattern<IUIAutomationTogglePattern>(checkbox.Get(), UIA_TogglePatternId);
        ok(toggle->Toggle(), "OS Toggle"); ToggleState toggleState; ok(toggle->get_CurrentToggleState(&toggleState), "checked state"); require(toggleState == ToggleState_On, "Toggle did not change DOM state");
        auto password = find(automation.Get(), root.Get(), L"Password"); require(password.Get(), "password input absent");
        ComPtr<IUnknown> passwordPattern; ok(password->GetCurrentPattern(UIA_ValuePatternId, &passwordPattern), "password pattern availability"); require(!passwordPattern, "password Value pattern exposes protected data");
        auto volume = find(automation.Get(), root.Get(), L"Volume", UIA_SliderControlTypeId); require(volume.Get(), "slider absent");
        auto rangeValue = pattern<IUIAutomationRangeValuePattern>(volume.Get(), UIA_RangeValuePatternId);
        auto rangeEvents = new NameEvents; rangeEvents->expected = UIA_RangeValueValuePropertyId;
        PROPERTYID rangeProperties[] = { UIA_RangeValueValuePropertyId };
        ok(automation->AddPropertyChangedEventHandlerNativeArray(volume.Get(), TreeScope_Element, nullptr, rangeEvents, rangeProperties, 1), "subscribe range value changes");
        ok(rangeValue->SetValue(7), "OS range value action"); double number = 0; ok(rangeValue->get_CurrentValue(&number), "range current value"); require(number == 7, "range value not changed");
        for (int i = 0; i < 300 && rangeEvents->count.load() == 0; ++i) Sleep(10);
        require(rangeEvents->count.load() > 0, "range value notification absent from OS UIA subscription");
        ok(automation->RemovePropertyChangedEventHandler(volume.Get(), rangeEvents), "unsubscribe range value changes"); rangeEvents->Release();
        ok(rangeValue->get_CurrentMinimum(&number), "range minimum"); require(number == 0, "wrong range minimum");
        ok(rangeValue->get_CurrentMaximum(&number), "range maximum"); require(number == 10, "wrong range maximum");
        require(rangeValue->SetValue(30) == E_INVALIDARG, "out-of-range UIA value was silently clamped");
        auto disabled = find(automation.Get(), root.Get(), L"Disabled action", UIA_ButtonControlTypeId); require(disabled.Get(), "disabled button absent");
        auto disabledInvoke = pattern<IUIAutomationInvokePattern>(disabled.Get(), UIA_InvokePatternId);
        require(disabledInvoke->Invoke() == UIA_E_ELEMENTNOTENABLED, "disabled Invoke was accepted");
        auto multiline = find(automation.Get(), root.Get(), L"Clipped text", UIA_EditControlTypeId); require(multiline.Get(), "clipped textarea absent");
        auto multilineText = pattern<IUIAutomationTextPattern>(multiline.Get(), UIA_TextPatternId);
        ComPtr<IUIAutomationTextRangeArray> visible; ok(multilineText->GetVisibleRanges(&visible), "visible text ranges");
        ok(visible->get_Length(&length), "visible range count"); require(length > 0, "visible first line missing");
        ComPtr<IUIAutomationTextRange> firstVisible; ok(visible->GetElement(0, &firstVisible), "first visible text range");
        ok(firstVisible->GetText(-1, &actual), "visible text contents");
        require(std::wstring(actual).find(L"third line") == std::wstring::npos, "visible ranges contain text clipped by textarea"); SysFreeString(actual);
        if (mode == "cache") {
            LRESULT baseline = SendMessageW(hwnd, cacheSizeMessage, 0, 0);
            require(baseline > 0, "cache probe was not built with real provider source");
            for (int i = 0; i < 128; ++i) {
                SendMessageW(hwnd, addChurnMessage, 0, 0);
                auto transient = find(automation.Get(), root.Get(), L"Transient item", UIA_ButtonControlTypeId);
                require(transient.Get(), "churn item absent from OS tree");
                SendMessageW(hwnd, removeChurnMessage, 0, 0);
                BSTR ignored = nullptr; HRESULT gone = transient->get_CurrentName(&ignored); SysFreeString(ignored);
                require(gone == UIA_E_ELEMENTNOTAVAILABLE, "removed churn provider remained available");
            }
            LRESULT retained = SendMessageW(hwnd, cacheSizeMessage, 0, 0);
            std::printf("UIA provider cache: baseline %lld, after128 DOM/UIA cycles %lld\n", static_cast<long long>(baseline), static_cast<long long>(retained));
            require(retained >= 0 && retained <= baseline + 16, "provider/node cache grew with removed DOM items");
        }
        PostMessageW(hwnd, removeMessage, 0, 0);
        HRESULT removed = S_OK;
        for (int i = 0; i < 300 && SUCCEEDED(removed); ++i) { BSTR ignored = nullptr; removed = button->get_CurrentName(&ignored); SysFreeString(ignored); if (SUCCEEDED(removed)) Sleep(10); }
        require(removed == UIA_E_ELEMENTNOTAVAILABLE, "removed DOM node remains callable or wrong error");
        if (mode == "sync") require(SendMessageW(hwnd, closeMessage, 0, 0) == RV_OK, "detach failed inside a synchronous window message");
        else PostMessageW(hwnd, closeMessage, 0, 0);
        HRESULT closed = S_OK;
        for (int i = 0; i < 300 && SUCCEEDED(closed); ++i) { BSTR ignored = nullptr; closed = edit->get_CurrentName(&ignored); SysFreeString(ignored); if (SUCCEEDED(closed)) Sleep(10); }
        require(closed == UIA_E_ELEMENTNOTAVAILABLE, "provider retained across teardown remains callable or wrong error");
        std::puts("UIA acceptance passed: OS discovery, tree, bounds, hit test, stable identity, Invoke, name events, Value, Toggle, UTF16 text/ranges/selection, protected values, removal and teardown");
    } catch (const std::exception& e) { std::fprintf(stderr, "UIA acceptance failed: %s\n", e.what()); result = 1; PostMessageW(hwnd, closeMessage, 0, 0); }
    CoUninitialize(); return result;
}

static RvHost* fixtureHost = nullptr;
static RvNode* fixtureButton = nullptr;
static RvNode* transientNode = nullptr;
LRESULT CALLBACK windowProcedure(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam)
{
    if (message == removeMessage) { rv_node_remove(fixtureButton); return 0; }
    if (message == addChurnMessage) {
        transientNode = rv_document_create_element(fixtureHost, "button"); rv_node_set_text_content(transientNode, RV_TEXT("Transient item"));
        auto* body = rv_document_body(fixtureHost); rv_node_append_child(body, transientNode); rv_node_release(body); rv_host_update(fixtureHost); return 0;
    }
    if (message == removeChurnMessage) {
        rv_node_remove(transientNode); rv_node_release(transientNode); transientNode = nullptr;
        rv_host_update(fixtureHost); rv_run_loop_cycle(0); return 0;
    }
    if (message == cacheSizeMessage) {
#if defined(RV_UIA_CACHE_PROBE)
        auto found = attachments.find(fixtureHost); if (found == attachments.end()) return -1;
        found->second->flush();
        if (found->second->nodes.size() != found->second->providers.size()) return -2;
        return static_cast<LRESULT>(found->second->nodes.size());
#else
        return -1;
#endif
    }
    if (message == closeMessage || message == WM_CLOSE) { closeRequested = true; return synchronousDetach ? rv_host_detach_uia(fixtureHost) : 0; }
    return DefWindowProcW(hwnd, message, wparam, lparam);
}
int main(int argc, char** argv)
{
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    if (argc >= 3 && std::string(argv[1]) == "--client") return client(reinterpret_cast<HWND>(std::stoull(argv[2])), argc > 3 ? argv[3] : "explicit");
    std::string teardown = argc > 1 ? argv[1] : "explicit";
    synchronousDetach = teardown == "sync";
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    WNDCLASSW wc {}; wc.lpfnWndProc = windowProcedure; wc.hInstance = GetModuleHandleW(nullptr); wc.lpszClassName = L"Ranvier.UIA.Acceptance";
    RegisterClassW(&wc);
    // OS ElementFromPoint examines the desktop's topmost window. Avoid letting another app obscure the fixture.
    HWND hwnd = CreateWindowExW(WS_EX_TOPMOST | WS_EX_NOACTIVATE, wc.lpszClassName, L"Ranvier UIA acceptance", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 100, 120, teardown == "overflow" ? 1000 : 640, teardown == "overflow" ? 700 : 480, nullptr, nullptr, wc.hInstance, nullptr);
    require(hwnd != nullptr, "create visible fixture HWND");
    fixtureHost = rv_host_create(teardown == "overflow" ? 640 : 600, 400); require(fixtureHost != nullptr, "create actual WebCore host");
    require(rv_host_load_html(fixtureHost, RV_TEXT("<!doctype html><title>UIA fixture</title><body><button id='action'>Press me</button><label>Your name<input aria-label='Your name'></label><label><input type='checkbox' aria-label='Accept terms'>Accept terms</label><input type='password' aria-label='Password' value='secret'><button style='display:none'>Hidden secret</button><input type='range' aria-label='Volume' min='0' max='10' value='3'><button disabled>Disabled action</button><textarea aria-label='Clipped text' style='display:block;height:20px;line-height:20px'>first line\nsecond line\nthird line</textarea><p style='position:absolute;top:1800px'>Far below</p></body>")) == RV_OK, "load fixture HTML");
    fixtureButton = rv_document_get_element_by_id(fixtureHost, RV_TEXT("action"));
    if (teardown == "overflow") {
        require(rv_host_set_device_scale(fixtureHost, 1.5f) == RV_OK, "set nonunit device scale");
        require(rv_element_set_attribute(fixtureButton, "style", RV_TEXT("position:absolute;left:20px;top:30px;width:80px;height:32px;padding:0;border:0;z-index:10")) == RV_OK, "set known CSS button geometry");
        auto* wide = rv_document_create_element(fixtureHost, "div"); auto* body = rv_document_body(fixtureHost);
        rv_element_set_attribute(wide, "style", RV_TEXT("width:2000px;height:2px")); rv_node_append_child(body, wide); rv_node_release(wide); rv_node_release(body);
        SetWindowPos(hwnd, nullptr, 420, 260, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
    }
    RvListener* listener = rv_node_add_event_listener(fixtureButton, RV_TEXT("click"), 0, [](void*, RvEvent*) -> int32_t { return rv_node_set_text_content(fixtureButton, RV_TEXT("Pressed once")); }, nullptr);
    require(listener != nullptr, "attach actual DOM event listener");
    require(rv_host_attach_uia(fixtureHost, hwnd) == RV_OK, "attach native UIA bridge");
    rv_host_update(fixtureHost);
    wchar_t exe[MAX_PATH]; GetModuleFileNameW(nullptr, exe, MAX_PATH);
    std::wstring command = L"\"" + std::wstring(exe) + L"\" --client " + std::to_wstring(reinterpret_cast<uintptr_t>(hwnd));
    command += L" " + std::wstring(teardown.begin(), teardown.end());
    STARTUPINFOW startup {}; startup.cb = sizeof(startup); PROCESS_INFORMATION process {};
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE); startup.hStdError = GetStdHandle(STD_ERROR_HANDLE); startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    SetHandleInformation(startup.hStdOutput, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT); SetHandleInformation(startup.hStdError, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT);
    require(CreateProcessW(nullptr, command.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, nullptr, &startup, &process), "launch independent UIA client");
    CloseHandle(process.hThread);
    bool detached = false;
    auto deadline = GetTickCount64() + (teardown == "cache" ? 120000 : 30000);
    while (WaitForSingleObject(process.hProcess, 0) == WAIT_TIMEOUT && GetTickCount64() < deadline) {
        MSG message; while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) { TranslateMessage(&message); DispatchMessageW(&message); }
        if (closeRequested && !detached) {
            if (teardown == "window") DestroyWindow(hwnd);
            if (teardown != "host") {
                require(rv_host_detach_uia(fixtureHost) == RV_OK, "detach native bridge");
                require(rv_host_detach_uia(fixtureHost) == RV_OK, "idempotent detach");
            }
            rv_listener_remove(listener); rv_node_release(fixtureButton); fixtureButton = nullptr;
            rv_host_destroy(fixtureHost); fixtureHost = nullptr; detached = true;
            if (teardown != "window") DestroyWindow(hwnd);
        }
        if (!detached) { rv_run_loop_cycle(0); rv_host_update(fixtureHost); }
        Sleep(1);
    }
    DWORD code = 1;
    if (WaitForSingleObject(process.hProcess, 0) == WAIT_TIMEOUT) { TerminateProcess(process.hProcess, 2); WaitForSingleObject(process.hProcess, 5000); std::fputs("UIA client timeout\n", stderr); }
    GetExitCodeProcess(process.hProcess, &code); CloseHandle(process.hProcess);
    if (!detached) { rv_host_detach_uia(fixtureHost); rv_listener_remove(listener); rv_node_release(fixtureButton); rv_host_destroy(fixtureHost); DestroyWindow(hwnd); }
    return static_cast<int>(code);
}
