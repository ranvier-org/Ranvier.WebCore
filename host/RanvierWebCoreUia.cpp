// The Windows bridge uses only the public host ABI. UIA calls may arrive on arbitrary threads;
// all tree reads, actions and native-reference releases run through the HWND owner thread.
#include "RanvierWebCoreAbi.h"

#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <commctrl.h>
#include <UIAutomation.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {
class Provider;
class TextRange;
struct Attachment;
void retireProvider(Provider*);
constexpr UINT_PTR subclassId = 0x52565549;
UINT dispatchMessage() { static UINT value = RegisterWindowMessageW(L"Ranvier.UIAutomation.Dispatch.v1"); return value; }
UINT eventMessage() { static UINT value = RegisterWindowMessageW(L"Ranvier.UIAutomation.Events.v1"); return value; }
std::unordered_map<RvHost*, std::shared_ptr<Attachment>> attachments;
const GUID providerIdentity = { 0x954fc4e9, 0xa49c, 0x4b39, {0xa4,0x3a,0x98,0x37,0x2b,0x09,0xae,0x64} };

HRESULT status(int value)
{
    if (value >= 0) return S_OK;
    if (value == RV_ERR_DETACHED || value == RV_ERR_NULL_ARGUMENT) return UIA_E_ELEMENTNOTAVAILABLE;
    if (value == RV_ERR_UNSUPPORTED) return UIA_E_NOTSUPPORTED;
    return E_FAIL;
}
std::wstring wide(const std::string& value)
{
    int count = MultiByteToWideChar(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0);
    std::wstring output(count, L'\0');
    if (count) MultiByteToWideChar(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), output.data(), count);
    return output;
}
std::string utf8(const wchar_t* value)
{
    if (!value) return {};
    int size = static_cast<int>(wcslen(value));
    int count = WideCharToMultiByte(CP_UTF8, 0, value, size, nullptr, 0, nullptr, nullptr);
    std::string output(count, '\0');
    if (count) WideCharToMultiByte(CP_UTF8, 0, value, size, output.data(), count, nullptr, nullptr);
    return output;
}
template<class Read> HRESULT stringValue(Read read, BSTR* output)
{
    if (!output) return E_POINTER;
    *output = nullptr;
    int length = 0;
    int result = read(nullptr, 0, &length);
    if (result < 0 && result != RV_ERR_BUFFER_TOO_SMALL) return status(result);
    std::string bytes(std::max(0, length), '\0');
    if (length > 0) {
        result = read(bytes.data(), length, &length);
        if (result < 0) return status(result);
    }
    auto value = wide(bytes);
    *output = SysAllocStringLen(value.data(), static_cast<UINT>(value.size()));
    return *output ? S_OK : E_OUTOFMEMORY;
}
HRESULT axString(RvAxNode* node, int property, BSTR* output)
{
    return stringValue([&](char* b, int c, int* n) { return rv_ax_string(node, property, b, c, n); }, output);
}
HRESULT unknownArray(const std::vector<IUnknown*>& values, SAFEARRAY** output)
{
    if (!output) return E_POINTER;
    *output = SafeArrayCreateVector(VT_UNKNOWN, 0, static_cast<ULONG>(values.size()));
    if (!*output) return E_OUTOFMEMORY;
    for (LONG i = 0; i < static_cast<LONG>(values.size()); ++i) {
        HRESULT hr = SafeArrayPutElement(*output, &i, values[i]);
        if (FAILED(hr)) { SafeArrayDestroy(*output); *output = nullptr; return hr; }
    }
    return S_OK;
}

struct Attachment : std::enable_shared_from_this<Attachment> {
    RvHost* host;
    HWND hwnd;
    DWORD owner = GetCurrentThreadId();
    std::atomic<bool> closing { false };
    std::unordered_map<int64_t, RvAxNode*> nodes;
    std::unordered_map<int64_t, Provider*> providers;
    std::unordered_map<int64_t, std::wstring> names;
    std::vector<std::pair<int64_t, int>> events;
    bool eventPosted = false;
    bool cleaned = false;
    unsigned adoptions = 0;
    std::mutex requestMutex;
    std::unordered_map<UINT_PTR, std::function<void()>> requests;
    std::atomic<UINT_PTR> nextRequest { 1 };
    Attachment(RvHost* h, HWND w) : host(h), hwnd(w) { }
    HRESULT call(const std::function<HRESULT()>& work)
    {
        if (closing.load()) return UIA_E_ELEMENTNOTAVAILABLE;
        if (GetCurrentThreadId() == owner) return work();
        HRESULT result = UIA_E_ELEMENTNOTAVAILABLE;
        UINT_PTR token = nextRequest++;
        {
            std::lock_guard lock(requestMutex);
            requests[token] = [&] { if (!closing.load()) result = work(); };
        }
        // Only an opaque lookup key crosses the window-message boundary. Other processes can send
        // any message to this HWND, so the receiver must never dereference a message's pointer value.
        SendMessageW(hwnd, dispatchMessage(), token, 0);
        { std::lock_guard lock(requestMutex); requests.erase(token); }
        return result;
    }
    RvAxNode* node(int64_t id);
    void sweep();
    Provider* adopt(RvAxNode* node);
    Provider* root() { return adopt(rv_host_ax_root(host)); }
    double scale()
    {
        RvAxNode* rootNode = rv_host_ax_root(host);
        if (!rootNode) return 1;
        double x, y, width = 0, height = 0;
        rv_ax_rect(rootNode, &x, &y, &width, &height);
        rv_ax_release(rootNode);
        int pixels = 0, ignored = 0;
        rv_host_paint_size(host, &pixels, &ignored);
        return width > 0 && pixels > 0 ? pixels / width : 1;
    }
    UiaRect screen(double x, double y, double w, double h)
    {
        POINT origin {};
        ClientToScreen(hwnd, &origin);
        double factor = scale();
        return { origin.x + x * factor, origin.y + y * factor, w * factor, h * factor };
    }
    POINT viewport(double x, double y)
    {
        POINT origin {};
        ClientToScreen(hwnd, &origin);
        double factor = scale();
        return { static_cast<LONG>(std::floor((x - origin.x) / factor)), static_cast<LONG>(std::floor((y - origin.y) / factor)) };
    }
    HRESULT clip(RvAxNode* node, UiaRect* output)
    {
        auto* document = rv_host_ax_root(host); if (!document) return UIA_E_ELEMENTNOTAVAILABLE;
        double x, y, width, height; int result = rv_ax_rect(document, &x, &y, &width, &height); rv_ax_release(document);
        if (result < 0) return status(result);
        RECT client {}; GetClientRect(hwnd, &client); double factor = scale();
        double left = x, top = y, right = std::min(x + width, (client.right-client.left)/factor), bottom = std::min(y + height, (client.bottom-client.top)/factor);
        auto* current = rv_ax_retain(node);
        while (current) {
            int role = rv_ax_role(current);
            bool clipX = role == RV_ROLE_TEXT_FIELD || role == RV_ROLE_TEXT_AREA, clipY = clipX;
            auto* dom = rv_ax_dom_node(current);
            if (dom) {
                if (rv_node_type(dom) == 1) {
                    auto clips = [&](const char* property) {
                        BSTR value = nullptr;
                        HRESULT hr = stringValue([&](char* b, int capacity, int* length) { return rv_element_computed_style(dom, property, b, capacity, length); }, &value);
                        bool clipped = SUCCEEDED(hr) && value && (!wcscmp(value, L"hidden") || !wcscmp(value, L"clip") || !wcscmp(value, L"scroll") || !wcscmp(value, L"auto"));
                        SysFreeString(value); return clipped;
                    };
                    clipX = clipX || clips("overflow-x"); clipY = clipY || clips("overflow-y");
                }
                rv_node_release(dom);
            }
            if ((clipX || clipY) && rv_ax_rect(current, &x, &y, &width, &height) >= 0) {
                if (clipX) { left = std::max(left, x); right = std::min(right, x + width); }
                if (clipY) { top = std::max(top, y); bottom = std::min(bottom, y + height); }
            }
            auto* parent = rv_ax_parent(current); rv_ax_release(current); current = parent;
        }
        *output = { left, top, std::max(0.0, right-left), std::max(0.0, bottom-top) }; return S_OK;
    }
    void queue(RvAxNode*, int);
    void flush();
    void disconnect();
};

int controlType(int role)
{
    switch (role) {
    case RV_ROLE_DOCUMENT: return UIA_DocumentControlTypeId;
    case RV_ROLE_BUTTON: case RV_ROLE_TOGGLE_BUTTON: return UIA_ButtonControlTypeId;
    case RV_ROLE_LINK: return UIA_HyperlinkControlTypeId;
    case RV_ROLE_CHECKBOX: case RV_ROLE_SWITCH: return UIA_CheckBoxControlTypeId;
    case RV_ROLE_RADIO: return UIA_RadioButtonControlTypeId;
    case RV_ROLE_TEXT_FIELD: case RV_ROLE_TEXT_AREA: return UIA_EditControlTypeId;
    case RV_ROLE_COMBO_BOX: return UIA_ComboBoxControlTypeId;
    case RV_ROLE_LIST: case RV_ROLE_LIST_BOX: return UIA_ListControlTypeId;
    case RV_ROLE_OPTION: case RV_ROLE_LIST_ITEM: return UIA_ListItemControlTypeId;
    case RV_ROLE_MENU: return UIA_MenuControlTypeId;
    case RV_ROLE_MENU_BAR: return UIA_MenuBarControlTypeId;
    case RV_ROLE_MENU_ITEM: case RV_ROLE_MENU_ITEM_CHECKBOX: case RV_ROLE_MENU_ITEM_RADIO: return UIA_MenuItemControlTypeId;
    case RV_ROLE_SLIDER: return UIA_SliderControlTypeId;
    case RV_ROLE_SPIN_BUTTON: return UIA_SpinnerControlTypeId;
    case RV_ROLE_PROGRESS: case RV_ROLE_METER: return UIA_ProgressBarControlTypeId;
    case RV_ROLE_SCROLL_BAR: return UIA_ScrollBarControlTypeId;
    case RV_ROLE_IMAGE: return UIA_ImageControlTypeId;
    case RV_ROLE_TABLE: return UIA_TableControlTypeId;
    case RV_ROLE_GRID: case RV_ROLE_TREE_GRID: return UIA_DataGridControlTypeId;
    case RV_ROLE_ROW: case RV_ROLE_CELL: return UIA_DataItemControlTypeId;
    case RV_ROLE_COLUMN_HEADER: case RV_ROLE_ROW_HEADER: return UIA_HeaderItemControlTypeId;
    case RV_ROLE_TREE: return UIA_TreeControlTypeId;
    case RV_ROLE_TREE_ITEM: return UIA_TreeItemControlTypeId;
    case RV_ROLE_TAB_LIST: return UIA_TabControlTypeId;
    case RV_ROLE_TAB: return UIA_TabItemControlTypeId;
    case RV_ROLE_TAB_PANEL: return UIA_PaneControlTypeId;
    case RV_ROLE_DIALOG: case RV_ROLE_ALERT_DIALOG: return UIA_WindowControlTypeId;
    case RV_ROLE_STATUS: return UIA_StatusBarControlTypeId;
    case RV_ROLE_TOOLTIP: return UIA_ToolTipControlTypeId;
    case RV_ROLE_TOOLBAR: return UIA_ToolBarControlTypeId;
    case RV_ROLE_SEPARATOR: return UIA_SeparatorControlTypeId;
    case RV_ROLE_TEXT: case RV_ROLE_PARAGRAPH: case RV_ROLE_HEADING: case RV_ROLE_LABEL:
    case RV_ROLE_TERM: case RV_ROLE_DEFINITION: case RV_ROLE_ALERT: case RV_ROLE_LOG: case RV_ROLE_TIMER: return UIA_TextControlTypeId;
    default: return UIA_GroupControlTypeId;
    }
}

class Provider final : public IRawElementProviderSimple, public IRawElementProviderFragment,
    public IRawElementProviderFragmentRoot, public IInvokeProvider, public IValueProvider,
    public IToggleProvider, public IRangeValueProvider, public IExpandCollapseProvider,
    public ISelectionItemProvider, public IScrollItemProvider, public ITextProvider {
    std::atomic<ULONG> references { 1 };
public:
    std::shared_ptr<Attachment> attachment;
    int64_t id;
    Provider(std::shared_ptr<Attachment> a, int64_t i) : attachment(std::move(a)), id(i) { }
    template<class F> HRESULT read(F work) { return attachment->call([&]() -> HRESULT { auto* n = attachment->node(id); return n ? work(n) : UIA_E_ELEMENTNOTAVAILABLE; }); }
    HRESULT action(int action)
    {
        return read([&](RvAxNode* n) -> HRESULT {
            if (rv_ax_states(n) & RV_AX_DISABLED) return UIA_E_ELEMENTNOTENABLED;
            int result = rv_ax_action(n, action);
            return result == 0 ? UIA_E_INVALIDOPERATION : status(result);
        });
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** out) override
    {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (iid == IID_IUnknown || iid == __uuidof(IRawElementProviderSimple) || iid == providerIdentity) *out = static_cast<IRawElementProviderSimple*>(this);
        else if (iid == __uuidof(IRawElementProviderFragment)) *out = static_cast<IRawElementProviderFragment*>(this);
        else if (iid == __uuidof(IRawElementProviderFragmentRoot)) *out = static_cast<IRawElementProviderFragmentRoot*>(this);
        else if (iid == __uuidof(IInvokeProvider)) *out = static_cast<IInvokeProvider*>(this);
        else if (iid == __uuidof(IValueProvider)) *out = static_cast<IValueProvider*>(this);
        else if (iid == __uuidof(IToggleProvider)) *out = static_cast<IToggleProvider*>(this);
        else if (iid == __uuidof(IRangeValueProvider)) *out = static_cast<IRangeValueProvider*>(this);
        else if (iid == __uuidof(IExpandCollapseProvider)) *out = static_cast<IExpandCollapseProvider*>(this);
        else if (iid == __uuidof(ISelectionItemProvider)) *out = static_cast<ISelectionItemProvider*>(this);
        else if (iid == __uuidof(IScrollItemProvider)) *out = static_cast<IScrollItemProvider*>(this);
        else if (iid == __uuidof(ITextProvider)) *out = static_cast<ITextProvider*>(this);
        if (!*out) return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references; }
    ULONG STDMETHODCALLTYPE Release() override { ULONG left = --references; if (!left) delete this; return left; }
    HRESULT STDMETHODCALLTYPE get_ProviderOptions(ProviderOptions* out) override { if (!out) return E_POINTER; *out = ProviderOptions_ServerSideProvider; return S_OK; }
    HRESULT STDMETHODCALLTYPE GetPatternProvider(PATTERNID pattern, IUnknown** out) override
    {
        if (!out) return E_POINTER;
        *out = nullptr;
        return read([&](RvAxNode* n) -> HRESULT {
            int role = rv_ax_role(n), states = rv_ax_states(n);
            if (pattern == UIA_InvokePatternId && (role == RV_ROLE_BUTTON || role == RV_ROLE_LINK || role == RV_ROLE_MENU_ITEM)) *out = static_cast<IInvokeProvider*>(this);
            else if (pattern == UIA_ValuePatternId && (role == RV_ROLE_TEXT_FIELD || role == RV_ROLE_TEXT_AREA) && !(states & RV_AX_PROTECTED)) *out = static_cast<IValueProvider*>(this);
            else if (pattern == UIA_TogglePatternId && ((states & RV_AX_CHECKABLE) || role == RV_ROLE_TOGGLE_BUTTON)) *out = static_cast<IToggleProvider*>(this);
            else if (pattern == UIA_RangeValuePatternId && role >= RV_ROLE_SLIDER && role <= RV_ROLE_SCROLL_BAR) *out = static_cast<IRangeValueProvider*>(this);
            else if (pattern == UIA_ExpandCollapsePatternId && (states & RV_AX_EXPANDABLE)) *out = static_cast<IExpandCollapseProvider*>(this);
            else if (pattern == UIA_SelectionItemPatternId && (states & RV_AX_SELECTABLE)) *out = static_cast<ISelectionItemProvider*>(this);
            else if (pattern == UIA_ScrollItemPatternId && role != RV_ROLE_DOCUMENT) *out = static_cast<IScrollItemProvider*>(this);
            else if (pattern == UIA_TextPatternId && !(states & RV_AX_PROTECTED) && (role == RV_ROLE_DOCUMENT || role == RV_ROLE_TEXT_FIELD || role == RV_ROLE_TEXT_AREA || role == RV_ROLE_TEXT || role == RV_ROLE_PARAGRAPH) && rv_ax_text_length(n) >= 0) *out = static_cast<ITextProvider*>(this);
            if (*out) AddRef();
            return S_OK;
        });
    }
    HRESULT STDMETHODCALLTYPE GetPropertyValue(PROPERTYID property, VARIANT* out) override
    {
        if (!out) return E_POINTER;
        VariantInit(out);
        return read([&](RvAxNode* n) -> HRESULT {
            int states = rv_ax_states(n);
            switch (property) {
            case UIA_ControlTypePropertyId: out->vt = VT_I4; out->lVal = controlType(rv_ax_role(n)); break;
            case UIA_NamePropertyId: out->vt = VT_BSTR; return axString(n, RV_AX_NAME, &out->bstrVal);
            case UIA_HelpTextPropertyId: case UIA_FullDescriptionPropertyId: out->vt = VT_BSTR; return axString(n, RV_AX_DESCRIPTION, &out->bstrVal);
            case UIA_AriaRolePropertyId: out->vt = VT_BSTR; return axString(n, RV_AX_ROLE_NAME, &out->bstrVal);
            case UIA_LocalizedControlTypePropertyId: {
                out->vt = VT_BSTR; HRESULT hr = axString(n, RV_AX_ROLE_DESCRIPTION, &out->bstrVal);
                // An empty override suppresses UIA's localized name for a standard control type.
                if (SUCCEEDED(hr) && !SysStringLen(out->bstrVal)) VariantClear(out);
                return hr;
            }
            case UIA_AcceleratorKeyPropertyId: out->vt = VT_BSTR; return axString(n, RV_AX_KEY_SHORTCUTS, &out->bstrVal);
            case UIA_FrameworkIdPropertyId: out->vt = VT_BSTR; out->bstrVal = SysAllocString(L"Ranvier.WebCore"); break;
            case UIA_AutomationIdPropertyId: out->vt = VT_BSTR; out->bstrVal = SysAllocString(std::to_wstring(id).c_str()); break;
            case UIA_ProcessIdPropertyId: out->vt = VT_I4; out->lVal = GetCurrentProcessId(); break;
            case UIA_IsKeyboardFocusablePropertyId: out->vt = VT_BOOL; out->boolVal = states & RV_AX_FOCUSABLE ? VARIANT_TRUE : VARIANT_FALSE; break;
            case UIA_HasKeyboardFocusPropertyId: out->vt = VT_BOOL; out->boolVal = states & RV_AX_FOCUSED ? VARIANT_TRUE : VARIANT_FALSE; break;
            case UIA_IsEnabledPropertyId: out->vt = VT_BOOL; out->boolVal = states & RV_AX_DISABLED ? VARIANT_FALSE : VARIANT_TRUE; break;
            case UIA_IsPasswordPropertyId: out->vt = VT_BOOL; out->boolVal = states & RV_AX_PROTECTED ? VARIANT_TRUE : VARIANT_FALSE; break;
            case UIA_IsOffscreenPropertyId: out->vt = VT_BOOL; out->boolVal = states & RV_AX_OFFSCREEN ? VARIANT_TRUE : VARIANT_FALSE; break;
            case UIA_IsRequiredForFormPropertyId: out->vt = VT_BOOL; out->boolVal = states & RV_AX_REQUIRED ? VARIANT_TRUE : VARIANT_FALSE; break;
            case UIA_IsControlElementPropertyId: case UIA_IsContentElementPropertyId: out->vt = VT_BOOL; out->boolVal = VARIANT_TRUE; break;
            case UIA_LiveSettingPropertyId: {
                BSTR live = nullptr; HRESULT hr = axString(n, RV_AX_LIVE, &live); if (FAILED(hr)) return hr;
                // UIA LiveSetting values: Off=0, Polite=1, Assertive=2.
                out->vt = VT_I4; out->lVal = live && !wcscmp(live, L"assertive") ? 2 : live && !wcscmp(live, L"polite") ? 1 : 0;
                SysFreeString(live); break;
            }
            default: break;
            }
            return S_OK;
        });
    }
    HRESULT STDMETHODCALLTYPE get_HostRawElementProvider(IRawElementProviderSimple** out) override
    {
        if (!out) return E_POINTER;
        *out = nullptr;
        return read([&](RvAxNode* n) -> HRESULT { return rv_ax_role(n) == RV_ROLE_DOCUMENT ? UiaHostProviderFromHwnd(attachment->hwnd, out) : S_OK; });
    }
    HRESULT STDMETHODCALLTYPE Navigate(NavigateDirection direction, IRawElementProviderFragment** out) override
    {
        if (!out) return E_POINTER;
        *out = nullptr;
        return read([&](RvAxNode* n) -> HRESULT {
            RvAxNode* target = nullptr;
            if (direction == NavigateDirection_Parent) target = rv_ax_parent(n);
            else {
                bool sibling = direction == NavigateDirection_NextSibling || direction == NavigateDirection_PreviousSibling;
                RvAxNode* parent = sibling ? rv_ax_parent(n) : rv_ax_retain(n);
                if (!parent) return S_OK;
                int count = 0; int result = rv_ax_children(parent, nullptr, 0, &count);
                if (result < 0 && result != RV_ERR_BUFFER_TOO_SMALL) { rv_ax_release(parent); return status(result); }
                if (!count) { rv_ax_release(parent); return S_OK; }
                std::vector<RvAxNode*> children(std::max(0, count));
                result = rv_ax_children(parent, children.data(), count, &count);
                rv_ax_release(parent);
                if (result < 0) return status(result);
                int index = direction == NavigateDirection_LastChild ? count - 1 : 0;
                if (sibling) {
                    index = -1;
                    for (int i = 0; i < count; ++i) if (rv_ax_id(children[i]) == id) { index = i + (direction == NavigateDirection_NextSibling ? 1 : -1); break; }
                }
                if (index >= 0 && index < count) target = rv_ax_retain(children[index]);
                for (auto* child : children) rv_ax_release(child);
            }
            if (auto* provider = attachment->adopt(target)) { *out = static_cast<IRawElementProviderFragment*>(provider); provider->AddRef(); }
            return S_OK;
        });
    }
    HRESULT STDMETHODCALLTYPE GetRuntimeId(SAFEARRAY** out) override
    {
        if (!out) return E_POINTER;
        *out = nullptr;
        return read([&](RvAxNode*) -> HRESULT {
            *out = SafeArrayCreateVector(VT_I4, 0, 3); if (!*out) return E_OUTOFMEMORY;
            LONG values[] = { UiaAppendRuntimeId, static_cast<LONG>(id & 0xffffffff), static_cast<LONG>(static_cast<uint64_t>(id) >> 32) };
            for (LONG i = 0; i < 3; ++i) SafeArrayPutElement(*out, &i, &values[i]);
            return S_OK;
        });
    }
    HRESULT STDMETHODCALLTYPE get_BoundingRectangle(UiaRect* out) override
    {
        if (!out) return E_POINTER;
        *out = {};
        return read([&](RvAxNode* n) -> HRESULT { double x, y, w, h; int result = rv_ax_rect(n, &x, &y, &w, &h); if (result < 0) return status(result); *out = attachment->screen(x, y, w, h); return S_OK; });
    }
    HRESULT STDMETHODCALLTYPE GetEmbeddedFragmentRoots(SAFEARRAY** out) override { return unknownArray({}, out); }
    HRESULT STDMETHODCALLTYPE SetFocus() override { return read([&](RvAxNode*) -> HRESULT { ::SetFocus(attachment->hwnd); return action(RV_AX_FOCUS); }); }
    HRESULT STDMETHODCALLTYPE get_FragmentRoot(IRawElementProviderFragmentRoot** out) override
    {
        if (!out) return E_POINTER;
        *out = nullptr;
        return read([&](RvAxNode*) -> HRESULT { auto* p = attachment->root(); if (!p) return UIA_E_ELEMENTNOTAVAILABLE; p->AddRef(); *out = static_cast<IRawElementProviderFragmentRoot*>(p); return S_OK; });
    }
    HRESULT STDMETHODCALLTYPE ElementProviderFromPoint(double x, double y, IRawElementProviderFragment** out) override
    {
        if (!out) return E_POINTER;
        *out = nullptr;
        return read([&](RvAxNode*) -> HRESULT { POINT p = attachment->viewport(x, y); auto* provider = attachment->adopt(rv_host_ax_hit_test(attachment->host, p.x, p.y)); if (provider) { provider->AddRef(); *out = static_cast<IRawElementProviderFragment*>(provider); } return S_OK; });
    }
    HRESULT STDMETHODCALLTYPE GetFocus(IRawElementProviderFragment** out) override
    {
        if (!out) return E_POINTER;
        *out = nullptr;
        return read([&](RvAxNode*) -> HRESULT { auto* p = attachment->adopt(rv_host_ax_focus(attachment->host)); if (p) { p->AddRef(); *out = static_cast<IRawElementProviderFragment*>(p); } return S_OK; });
    }
    HRESULT STDMETHODCALLTYPE Invoke() override { return action(RV_AX_PRESS); }
    HRESULT STDMETHODCALLTYPE SetValue(LPCWSTR value) override
    {
        if (!value) return E_INVALIDARG;
        std::string bytes = utf8(value);
        return read([&](RvAxNode* n) -> HRESULT { int states = rv_ax_states(n); if (states & RV_AX_DISABLED) return UIA_E_ELEMENTNOTENABLED; if (!(states & RV_AX_EDITABLE) || states & RV_AX_PROTECTED) return UIA_E_INVALIDOPERATION; int result = rv_ax_set_value(n, bytes.c_str()); return result == 0 ? UIA_E_INVALIDOPERATION : status(result); });
    }
    HRESULT STDMETHODCALLTYPE get_Value(BSTR* out) override { return read([&](RvAxNode* n) -> HRESULT { return axString(n, RV_AX_VALUE, out); }); }
    HRESULT STDMETHODCALLTYPE get_IsReadOnly(BOOL* out) override { if (!out) return E_POINTER; return read([&](RvAxNode* n) -> HRESULT { *out = !(rv_ax_states(n) & RV_AX_EDITABLE); return S_OK; }); }
    HRESULT STDMETHODCALLTYPE Toggle() override { return action(RV_AX_PRESS); }
    HRESULT STDMETHODCALLTYPE get_ToggleState(ToggleState* out) override { if (!out) return E_POINTER; return read([&](RvAxNode* n) -> HRESULT { int states = rv_ax_states(n); *out = states & RV_AX_MIXED ? ToggleState_Indeterminate : states & (RV_AX_CHECKED | RV_AX_PRESSED) ? ToggleState_On : ToggleState_Off; return S_OK; }); }
    HRESULT STDMETHODCALLTYPE SetValue(double value) override
    {
        if (!std::isfinite(value)) return E_INVALIDARG;
        return read([&](RvAxNode* n) -> HRESULT {
            if (rv_ax_states(n) & RV_AX_DISABLED) return UIA_E_ELEMENTNOTENABLED;
            double minimum = 0, maximum = 0;
            int result = rv_ax_number(n, RV_AX_NUMBER_MIN, &minimum); if (result < 0) return status(result);
            result = rv_ax_number(n, RV_AX_NUMBER_MAX, &maximum); if (result < 0) return status(result);
            if (value < minimum || value > maximum) return E_INVALIDARG;
            result = rv_ax_set_number(n, value); return result == 0 ? UIA_E_INVALIDOPERATION : status(result);
        });
    }
    HRESULT number(int property, double* out) { if (!out) return E_POINTER; return read([&](RvAxNode* n) -> HRESULT { return status(rv_ax_number(n, property, out)); }); }
    HRESULT STDMETHODCALLTYPE get_Value(double* out) override { return number(RV_AX_NUMBER_VALUE, out); }
    HRESULT STDMETHODCALLTYPE get_Maximum(double* out) override { return number(RV_AX_NUMBER_MAX, out); }
    HRESULT STDMETHODCALLTYPE get_Minimum(double* out) override { return number(RV_AX_NUMBER_MIN, out); }
    HRESULT STDMETHODCALLTYPE get_LargeChange(double* out) override { if (!out) return E_POINTER; *out = 0; return S_OK; }
    HRESULT STDMETHODCALLTYPE get_SmallChange(double* out) override { if (!out) return E_POINTER; *out = 0; return S_OK; }
    HRESULT STDMETHODCALLTYPE Expand() override { return action(RV_AX_EXPAND); }
    HRESULT STDMETHODCALLTYPE Collapse() override { return action(RV_AX_COLLAPSE); }
    HRESULT STDMETHODCALLTYPE get_ExpandCollapseState(ExpandCollapseState* out) override { if (!out) return E_POINTER; return read([&](RvAxNode* n) -> HRESULT { int states = rv_ax_states(n); *out = !(states & RV_AX_EXPANDABLE) ? ExpandCollapseState_LeafNode : states & RV_AX_EXPANDED ? ExpandCollapseState_Expanded : ExpandCollapseState_Collapsed; return S_OK; }); }
    HRESULT STDMETHODCALLTYPE Select() override { return action(RV_AX_SELECT); }
    HRESULT STDMETHODCALLTYPE AddToSelection() override { return action(RV_AX_SELECT); }
    HRESULT STDMETHODCALLTYPE RemoveFromSelection() override { return UIA_E_INVALIDOPERATION; }
    HRESULT STDMETHODCALLTYPE get_IsSelected(BOOL* out) override { if (!out) return E_POINTER; return read([&](RvAxNode* n) -> HRESULT { *out = !!(rv_ax_states(n) & RV_AX_SELECTED); return S_OK; }); }
    HRESULT STDMETHODCALLTYPE get_SelectionContainer(IRawElementProviderSimple** out) override
    {
        if (!out) return E_POINTER;
        *out = nullptr;
        return read([&](RvAxNode* n) -> HRESULT { auto* parent = rv_ax_parent(n); auto* p = attachment->adopt(parent); if (p) { p->AddRef(); *out = static_cast<IRawElementProviderSimple*>(p); } return S_OK; });
    }
    HRESULT STDMETHODCALLTYPE ScrollIntoView() override { return action(RV_AX_SCROLL_INTO_VIEW); }
    HRESULT STDMETHODCALLTYPE GetSelection(SAFEARRAY** out) override;
    HRESULT STDMETHODCALLTYPE GetVisibleRanges(SAFEARRAY** out) override;
    HRESULT STDMETHODCALLTYPE RangeFromChild(IRawElementProviderSimple*, ITextRangeProvider** out) override;
    HRESULT STDMETHODCALLTYPE RangeFromPoint(UiaPoint point, ITextRangeProvider** out) override;
    HRESULT STDMETHODCALLTYPE get_DocumentRange(ITextRangeProvider** out) override;
    HRESULT STDMETHODCALLTYPE get_SupportedTextSelection(SupportedTextSelection* out) override { if (!out) return E_POINTER; *out = SupportedTextSelection_Single; return S_OK; }
};

Provider* Attachment::adopt(RvAxNode* n)
{
    if (!n) return nullptr;
    int64_t id = rv_ax_id(n);
    if (id < 0 || rv_ax_role(n) < 0) { rv_ax_release(n); return nullptr; }
    auto found = providers.find(id);
    if (found != providers.end()) { rv_ax_release(n); return found->second; }
    if (++adoptions % 64 == 0) sweep();
    nodes[id] = n;
    auto* provider = new Provider(shared_from_this(), id);
    providers[id] = provider;
    BSTR name = nullptr;
    if (SUCCEEDED(axString(n, RV_AX_NAME, &name))) names[id] = name ? name : L"";
    SysFreeString(name);
    return provider;
}

RvAxNode* Attachment::node(int64_t id)
{
    auto found = nodes.find(id);
    if (found == nodes.end()) return nullptr;
    if (rv_ax_role(found->second) >= 0) return found->second;
    rv_ax_release(found->second); nodes.erase(found); names.erase(id);
    auto provider = providers.find(id);
    if (provider != providers.end()) {
        auto* removed = provider->second; providers.erase(provider);
        retireProvider(removed);
    }
    return nullptr;
}
void Attachment::sweep()
{
    std::vector<int64_t> identities;
    identities.reserve(nodes.size());
    for (auto [id, value] : nodes) identities.push_back(id);
    for (auto id : identities) node(id);
}

// This private identity can only be returned by ranges belonging to this implementation.
const GUID rangeIdentity = { 0xbbf35934, 0x406e, 0x41c0, {0x81,0x45,0x8a,0x73,0x1d,0xad,0x11,0x7e} };
class TextRange final : public ITextRangeProvider {
    std::atomic<ULONG> references { 1 };
public:
    Provider* provider;
    int start, end;
    TextRange(Provider* p, int s, int e) : provider(p), start(s), end(e) { p->AddRef(); }
    ~TextRange() { provider->Release(); }
    HRESULT live(const std::function<HRESULT(RvAxNode*)>& work)
    {
        return provider->read([&](RvAxNode* n) -> HRESULT { int length = rv_ax_text_length(n); if (length < 0) return status(length); start = std::clamp(start, 0, length); end = std::clamp(end, start, length); return work(n); });
    }
    HRESULT other(ITextRangeProvider* value, TextRange** out)
    {
        *out = nullptr;
        if (!value) return E_INVALIDARG;
        void* identity = nullptr;
        if (FAILED(value->QueryInterface(rangeIdentity, &identity))) return E_INVALIDARG;
        auto* range = static_cast<TextRange*>(static_cast<ITextRangeProvider*>(identity));
        if (range->provider->id != provider->id || range->provider->attachment != provider->attachment) { range->Release(); return E_INVALIDARG; }
        *out = range;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** out) override { if (!out) return E_POINTER; *out = nullptr; if (iid != IID_IUnknown && iid != __uuidof(ITextRangeProvider) && iid != rangeIdentity) return E_NOINTERFACE; *out = static_cast<ITextRangeProvider*>(this); AddRef(); return S_OK; }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references; }
    ULONG STDMETHODCALLTYPE Release() override { auto n = --references; if (!n) delete this; return n; }
    HRESULT STDMETHODCALLTYPE Clone(ITextRangeProvider** out) override { if (!out) return E_POINTER; *out = nullptr; return live([&](RvAxNode*) -> HRESULT { *out = new TextRange(provider, start, end); return S_OK; }); }
    HRESULT STDMETHODCALLTYPE Compare(ITextRangeProvider* range, BOOL* out) override
    {
        if (!out) return E_POINTER; *out = FALSE;
        TextRange* r = nullptr; HRESULT hr = other(range, &r); if (FAILED(hr)) return hr;
        hr = live([&](RvAxNode*) -> HRESULT { *out = start == r->start && end == r->end; return S_OK; }); r->Release(); return hr;
    }
    HRESULT STDMETHODCALLTYPE CompareEndpoints(TextPatternRangeEndpoint endpoint, ITextRangeProvider* range, TextPatternRangeEndpoint target, int* out) override
    {
        if (!out) return E_POINTER;
        TextRange* r = nullptr; HRESULT hr = other(range, &r); if (FAILED(hr)) return hr;
        hr = live([&](RvAxNode*) -> HRESULT { *out = (endpoint == TextPatternRangeEndpoint_Start ? start : end) - (target == TextPatternRangeEndpoint_Start ? r->start : r->end); return S_OK; }); r->Release(); return hr;
    }
    static int unit(TextUnit value)
    {
        switch (value) { case TextUnit_Character: return RV_TEXT_CHARACTER; case TextUnit_Format: case TextUnit_Word: return RV_TEXT_WORD; case TextUnit_Line: return RV_TEXT_LINE; case TextUnit_Paragraph: return RV_TEXT_PARAGRAPH; default: return -1; }
    }
    static int boundary(RvAxNode* n, int offset, TextUnit value, bool forward)
    {
        int length = rv_ax_text_length(n);
        if (unit(value) < 0) return forward ? length : 0;
        if (forward && offset >= length) return length;
        if (!forward && offset <= 0) return 0;
        if (value == TextUnit_Character) {
            BSTR text = nullptr;
            if (FAILED(stringValue([&](char* b, int c, int* size) { return rv_ax_text(n, 0, length, b, c, size); }, &text))) return offset;
            int next = offset + (forward ? 1 : -1);
            if (forward && text[offset] >= 0xd800 && text[offset] <= 0xdbff && next < length && text[next] >= 0xdc00 && text[next] <= 0xdfff) ++next;
            if (!forward && next > 0 && text[next] >= 0xdc00 && text[next] <= 0xdfff && text[next-1] >= 0xd800 && text[next-1] <= 0xdbff) --next;
            SysFreeString(text); return next;
        }
        int s = 0, e = 0;
        if (rv_ax_text_boundary(n, forward ? offset : offset - 1, unit(value), &s, &e) < 0) return offset;
        return forward ? e : s;
    }
    HRESULT STDMETHODCALLTYPE ExpandToEnclosingUnit(TextUnit value) override
    {
        return live([&](RvAxNode* n) -> HRESULT {
            int length = rv_ax_text_length(n);
            if (unit(value) < 0) { start = 0; end = length; return S_OK; }
            int s = 0, e = 0; int result = rv_ax_text_boundary(n, start, unit(value), &s, &e); if (result < 0) return status(result);
            start = s; end = e; return S_OK;
        });
    }
    HRESULT STDMETHODCALLTYPE FindAttribute(TEXTATTRIBUTEID, VARIANT, BOOL, ITextRangeProvider** out) override { if (!out) return E_POINTER; *out = nullptr; return S_OK; }
    HRESULT STDMETHODCALLTYPE FindText(BSTR needle, BOOL backward, BOOL ignoreCase, ITextRangeProvider** out) override
    {
        if (!out) return E_POINTER; *out = nullptr;
        if (!needle || !SysStringLen(needle)) return E_INVALIDARG;
        return live([&](RvAxNode*) -> HRESULT {
            BSTR text = nullptr; HRESULT hr = GetText(-1, &text); if (FAILED(hr)) return hr;
            std::wstring hay(text, SysStringLen(text)), find(needle, SysStringLen(needle)); SysFreeString(text);
            if (ignoreCase) { std::transform(hay.begin(), hay.end(), hay.begin(), towlower); std::transform(find.begin(), find.end(), find.begin(), towlower); }
            auto offset = backward ? hay.rfind(find) : hay.find(find);
            if (offset != std::wstring::npos) *out = new TextRange(provider, start + static_cast<int>(offset), start + static_cast<int>(offset + find.size()));
            return S_OK;
        });
    }
    HRESULT STDMETHODCALLTYPE GetAttributeValue(TEXTATTRIBUTEID, VARIANT* out) override { if (!out) return E_POINTER; VariantInit(out); out->vt = VT_UNKNOWN; return UiaGetReservedNotSupportedValue(&out->punkVal); }
    HRESULT STDMETHODCALLTYPE GetBoundingRectangles(SAFEARRAY** out) override
    {
        if (!out) return E_POINTER; *out = nullptr;
        return live([&](RvAxNode* n) -> HRESULT {
            if (start == end) { *out = SafeArrayCreateVector(VT_R8, 0, 0); return *out ? S_OK : E_OUTOFMEMORY; }
            int count = 0; int result = rv_ax_text_rects(n, start, end, nullptr, 0, &count); if (result < 0 && result != RV_ERR_BUFFER_TOO_SMALL) return status(result);
            if (!count) { *out = SafeArrayCreateVector(VT_R8, 0, 0); return *out ? S_OK : E_OUTOFMEMORY; }
            std::vector<double> rects(static_cast<size_t>(std::max(0, count)) * 4);
            result = rv_ax_text_rects(n, start, end, rects.data(), count, &count); if (result < 0) return status(result);
            UiaRect clip {}; HRESULT hr = provider->attachment->clip(n, &clip); if (FAILED(hr)) return hr;
            std::vector<double> visible;
            for (int i = 0; i < count; ++i) {
                double left = std::max(rects[4*i], clip.left), top = std::max(rects[4*i+1], clip.top);
                double right = std::min(rects[4*i] + rects[4*i+2], clip.left + clip.width), bottom = std::min(rects[4*i+1] + rects[4*i+3], clip.top + clip.height);
                if (right <= left || bottom <= top) continue;
                auto r = provider->attachment->screen(left, top, right-left, bottom-top);
                double values[] = { r.left, r.top, r.width, r.height };
                visible.insert(visible.end(), std::begin(values), std::end(values));
            }
            *out = SafeArrayCreateVector(VT_R8, 0, static_cast<ULONG>(visible.size())); if (!*out) return E_OUTOFMEMORY;
            for (LONG i = 0; i < static_cast<LONG>(visible.size()); ++i) SafeArrayPutElement(*out, &i, &visible[i]);
            return S_OK;
        });
    }
    HRESULT STDMETHODCALLTYPE GetEnclosingElement(IRawElementProviderSimple** out) override
    {
        if (!out) return E_POINTER; *out = nullptr;
        return live([&](RvAxNode* n) -> HRESULT {
            Provider* enclosing = provider;
            for (;;) {
                auto* scope = provider->attachment->node(enclosing->id); if (!scope) break;
                int count = 0; int result = rv_ax_children(scope, nullptr, 0, &count);
                if (result < 0 && result != RV_ERR_BUFFER_TOO_SMALL) return status(result);
                if (!count) break;
                std::vector<RvAxNode*> children(std::max(0, count));
                result = rv_ax_children(scope, children.data(), count, &count); if (result < 0) return status(result);
                Provider* deeper = nullptr;
                for (auto* child : children) {
                    int first = 0, last = 0;
                    if (!deeper && rv_ax_text_child_range(n, child, &first, &last) >= 0 && first <= start && last >= end) deeper = provider->attachment->adopt(child);
                    else rv_ax_release(child);
                }
                if (!deeper || deeper == enclosing) break;
                enclosing = deeper;
            }
            enclosing->AddRef(); *out = static_cast<IRawElementProviderSimple*>(enclosing); return S_OK;
        });
    }
    HRESULT STDMETHODCALLTYPE GetText(int maximum, BSTR* out) override
    {
        if (!out) return E_POINTER; *out = nullptr;
        if (maximum < -1) return E_INVALIDARG;
        return live([&](RvAxNode* n) -> HRESULT {
            BSTR value = nullptr; HRESULT hr = stringValue([&](char* b, int c, int* size) { return rv_ax_text(n, start, end, b, c, size); }, &value);
            if (FAILED(hr)) return hr;
            if (maximum >= 0 && SysStringLen(value) > static_cast<UINT>(maximum)) { *out = SysAllocStringLen(value, maximum); SysFreeString(value); } else *out = value;
            return *out ? S_OK : E_OUTOFMEMORY;
        });
    }
    HRESULT STDMETHODCALLTYPE Move(TextUnit value, int count, int* moved) override
    {
        if (!moved) return E_POINTER; *moved = 0;
        return live([&](RvAxNode* n) -> HRESULT {
            if (!count) return S_OK;
            bool collapsed = start == end;
            if (!collapsed) { HRESULT hr = ExpandToEnclosingUnit(value); if (FAILED(hr)) return hr; }
            int offset = start;
            int64_t remaining = count > 0 ? static_cast<int64_t>(count) : -static_cast<int64_t>(count);
            while (remaining--) { int next = boundary(n, offset, value, count > 0); if (next == offset || (!collapsed && next == rv_ax_text_length(n))) break; offset = next; *moved += count > 0 ? 1 : -1; }
            start = offset; end = offset;
            if (!collapsed) return ExpandToEnclosingUnit(value);
            return S_OK;
        });
    }
    HRESULT STDMETHODCALLTYPE MoveEndpointByUnit(TextPatternRangeEndpoint endpoint, TextUnit value, int count, int* moved) override
    {
        if (!moved) return E_POINTER; *moved = 0;
        return live([&](RvAxNode* n) -> HRESULT {
            int& position = endpoint == TextPatternRangeEndpoint_Start ? start : end;
            int64_t remaining = count > 0 ? static_cast<int64_t>(count) : -static_cast<int64_t>(count);
            while (remaining--) { int next = boundary(n, position, value, count > 0); if (next == position) break; position = next; *moved += count > 0 ? 1 : -1; }
            if (start > end) { if (endpoint == TextPatternRangeEndpoint_Start) end = start; else start = end; }
            return S_OK;
        });
    }
    HRESULT STDMETHODCALLTYPE MoveEndpointByRange(TextPatternRangeEndpoint endpoint, ITextRangeProvider* range, TextPatternRangeEndpoint target) override
    {
        TextRange* r = nullptr; HRESULT hr = other(range, &r); if (FAILED(hr)) return hr;
        hr = live([&](RvAxNode*) -> HRESULT { int position = target == TextPatternRangeEndpoint_Start ? r->start : r->end; if (endpoint == TextPatternRangeEndpoint_Start) { start = position; end = std::max(end, start); } else { end = position; start = std::min(start, end); } return S_OK; }); r->Release(); return hr;
    }
    HRESULT STDMETHODCALLTYPE Select() override { return live([&](RvAxNode* n) -> HRESULT { return status(rv_ax_text_set_selection(n, start, end)); }); }
    HRESULT STDMETHODCALLTYPE AddToSelection() override { return UIA_E_INVALIDOPERATION; }
    HRESULT STDMETHODCALLTYPE RemoveFromSelection() override { return UIA_E_INVALIDOPERATION; }
    HRESULT STDMETHODCALLTYPE ScrollIntoView(BOOL) override
    {
        return live([&](RvAxNode* n) -> HRESULT {
            // The ABI can scroll an object, but has no range-specific scrolling operation.
            return start == 0 && end == rv_ax_text_length(n) ? provider->action(RV_AX_SCROLL_INTO_VIEW) : UIA_E_NOTSUPPORTED;
        });
    }
    HRESULT STDMETHODCALLTYPE GetChildren(SAFEARRAY** out) override
    {
        if (!out) return E_POINTER; *out = nullptr;
        return live([&](RvAxNode* n) -> HRESULT {
            int count = 0; int result = rv_ax_children(n, nullptr, 0, &count);
            if (result < 0 && result != RV_ERR_BUFFER_TOO_SMALL) return status(result);
            if (!count) return unknownArray({}, out);
            std::vector<RvAxNode*> children(std::max(0, count));
            result = rv_ax_children(n, children.data(), count, &count); if (result < 0) return status(result);
            std::vector<IUnknown*> enclosed;
            for (auto* child : children) {
                int first = 0, last = 0;
                if (rv_ax_text_child_range(n, child, &first, &last) >= 0 && first >= start && last <= end) {
                    if (auto* p = provider->attachment->adopt(child)) enclosed.push_back(static_cast<IRawElementProviderSimple*>(p));
                } else rv_ax_release(child);
            }
            return unknownArray(enclosed, out);
        });
    }
};

HRESULT Provider::get_DocumentRange(ITextRangeProvider** out)
{
    if (!out) return E_POINTER; *out = nullptr;
    return read([&](RvAxNode* n) -> HRESULT { int length = rv_ax_text_length(n); if (length < 0) return status(length); *out = new TextRange(this, 0, length); return S_OK; });
}
HRESULT Provider::GetSelection(SAFEARRAY** out)
{
    if (!out) return E_POINTER; *out = nullptr;
    return read([&](RvAxNode* n) -> HRESULT {
        int start = 0, end = 0; int result = rv_ax_text_selection(n, &start, &end); if (result < 0) return status(result);
        if (!result) return unknownArray({}, out);
        auto* range = new TextRange(this, start, end); HRESULT hr = unknownArray({ static_cast<ITextRangeProvider*>(range) }, out); range->Release(); return hr;
    });
}
HRESULT Provider::GetVisibleRanges(SAFEARRAY** out)
{
    if (!out) return E_POINTER; *out = nullptr;
    return read([&](RvAxNode* n) -> HRESULT {
        if (rv_ax_states(n) & RV_AX_OFFSCREEN) return unknownArray({}, out);
        UiaRect clip {}; HRESULT clipped = attachment->clip(n, &clip); if (FAILED(clipped)) return clipped;
        double left = clip.left, top = clip.top, right = clip.left + clip.width, bottom = clip.top + clip.height;
        int length = rv_ax_text_length(n); if (length < 0) return status(length);
        std::vector<IUnknown*> ranges;
        int offset = 0;
        do {
            int first = 0, last = length;
            rv_ax_text_boundary(n, offset, RV_TEXT_LINE, &first, &last);
            last = std::clamp(last, offset, length);
            if (last == offset && offset < length) last = TextRange::boundary(n, offset, TextUnit_Character, true);
            int count = 0; rv_ax_text_rects(n, offset, last, nullptr, 0, &count);
            std::vector<double> rects(static_cast<size_t>(std::max(0, count)) * 4);
            bool visible = false;
            if (rv_ax_text_rects(n, offset, last, rects.data(), count, &count) >= 0) {
                for (int i = 0; i < count; ++i) {
                    if (rects[4*i] < right && rects[4*i] + std::max(1.0, rects[4*i+2]) > left && rects[4*i+1] < bottom && rects[4*i+1] + rects[4*i+3] > top) visible = true;
                }
            }
            if (visible) ranges.push_back(static_cast<ITextRangeProvider*>(new TextRange(this, offset, last)));
            if (last <= offset) break;
            offset = last;
        } while (offset < length);
        HRESULT hr = unknownArray(ranges, out);
        for (auto* range : ranges) range->Release();
        return hr;
    });
}
HRESULT Provider::RangeFromChild(IRawElementProviderSimple* child, ITextRangeProvider** out)
{
    if (!out) return E_POINTER; *out = nullptr;
    if (!child) return E_INVALIDARG;
    IRawElementProviderSimple* identity = nullptr;
    if (FAILED(child->QueryInterface(providerIdentity, reinterpret_cast<void**>(&identity)))) return E_INVALIDARG;
    auto* target = static_cast<Provider*>(identity);
    if (target->attachment != attachment) { target->Release(); return E_INVALIDARG; }
    HRESULT hr = read([&](RvAxNode* n) -> HRESULT {
        auto* descendant = attachment->node(target->id); if (!descendant) return UIA_E_ELEMENTNOTAVAILABLE;
        int start = 0, end = 0; int result = rv_ax_text_child_range(n, descendant, &start, &end);
        if (result < 0) return result == RV_ERR_UNSUPPORTED ? E_INVALIDARG : status(result);
        *out = new TextRange(this, start, end); return S_OK;
    });
    target->Release(); return hr;
}
HRESULT Provider::RangeFromPoint(UiaPoint point, ITextRangeProvider** out)
{
    if (!out) return E_POINTER; *out = nullptr;
    return read([&](RvAxNode* n) -> HRESULT { auto p = attachment->viewport(point.x, point.y); int offset = rv_ax_text_offset_at(n, p.x, p.y); if (offset < 0) return UIA_E_INVALIDOPERATION; *out = new TextRange(this, offset, offset); return S_OK; });
}

void Attachment::queue(RvAxNode* node, int event)
{
    if (closing.load()) return;
    auto* provider = adopt(rv_ax_retain(node));
    if (!provider) return;
    events.emplace_back(provider->id, event);
    if (!eventPosted) eventPosted = PostMessageW(hwnd, eventMessage(), 0, 0) != FALSE;
}
void Attachment::flush()
{
    eventPosted = false;
    auto pending = std::move(events); events.clear();
    // WebCore can report ChildrenChanged when a button's content also changes its computed name.
    // Compare exposed names at delivery, so clients receive the derived property change as well.
    std::vector<std::shared_ptr<Provider>> snapshot;
    for (auto [id, provider] : providers) { provider->AddRef(); snapshot.emplace_back(provider, [](Provider* p) { p->Release(); }); }
    for (const auto& reference : snapshot) {
        if (closing.load()) break;
        auto* provider = reference.get(); auto id = provider->id;
        auto* n = node(id); if (!n) continue;
        BSTR value = nullptr; if (FAILED(axString(n, RV_AX_NAME, &value))) continue;
        std::wstring current = value ? value : L"";
        auto& previous = names[id];
        if (previous != current) {
            VARIANT oldValue {}, newValue {}; oldValue.vt = newValue.vt = VT_BSTR;
            oldValue.bstrVal = SysAllocString(previous.c_str()); newValue.bstrVal = value;
            previous = current;
            UiaRaiseAutomationPropertyChangedEvent(static_cast<IRawElementProviderSimple*>(provider), UIA_NamePropertyId, oldValue, newValue);
            VariantClear(&oldValue);
        }
        SysFreeString(value);
    }
    for (auto [id, event] : pending) {
        if (closing.load()) return;
        auto found = providers.find(id); if (found == providers.end() || !node(id)) continue;
        auto* p = static_cast<IRawElementProviderSimple*>(found->second);
        EVENTID automation = 0;
        PROPERTYID property = 0;
        switch (event) {
        case RV_AX_EVENT_FOCUS: automation = UIA_AutomationFocusChangedEventId; break;
        case RV_AX_EVENT_CHILDREN: UiaRaiseStructureChangedEvent(p, StructureChangeType_ChildrenInvalidated, nullptr, 0); break;
        case RV_AX_EVENT_NAME: break;
        case RV_AX_EVENT_DESCRIPTION: property = UIA_HelpTextPropertyId; break;
        case RV_AX_EVENT_ROLE: property = UIA_ControlTypePropertyId; break;
        case RV_AX_EVENT_VALUE: {
            int role = rv_ax_role(node(id));
            property = role >= RV_ROLE_SLIDER && role <= RV_ROLE_SCROLL_BAR ? UIA_RangeValueValuePropertyId : UIA_ValueValuePropertyId;
            break;
        }
        case RV_AX_EVENT_TEXT: automation = UIA_Text_TextChangedEventId; break;
        case RV_AX_EVENT_TEXT_SELECTION: automation = UIA_Text_TextSelectionChangedEventId; break;
        case RV_AX_EVENT_SELECTION: automation = UIA_SelectionItem_ElementSelectedEventId; break;
        case RV_AX_EVENT_LIVE_REGION: automation = UIA_LiveRegionChangedEventId; break;
        case RV_AX_EVENT_LOAD_COMPLETE: automation = UIA_AsyncContentLoadedEventId; break;
        case RV_AX_EVENT_LAYOUT: property = UIA_BoundingRectanglePropertyId; break;
        case RV_AX_EVENT_MENU_OPENED: automation = UIA_MenuOpenedEventId; break;
        case RV_AX_EVENT_MENU_CLOSED: automation = UIA_MenuClosedEventId; break;
        case RV_AX_EVENT_STATE: {
            int states = rv_ax_states(node(id));
            VARIANT oldValue {}, value {}; value.vt = VT_BOOL; value.boolVal = states & RV_AX_DISABLED ? VARIANT_FALSE : VARIANT_TRUE;
            UiaRaiseAutomationPropertyChangedEvent(p, UIA_IsEnabledPropertyId, oldValue, value);
            value.vt = VT_I4; value.lVal = states & RV_AX_MIXED ? ToggleState_Indeterminate : states & (RV_AX_CHECKED | RV_AX_PRESSED) ? ToggleState_On : ToggleState_Off;
            UiaRaiseAutomationPropertyChangedEvent(p, UIA_ToggleToggleStatePropertyId, oldValue, value);
            break;
        }
        }
        if (automation) UiaRaiseAutomationEvent(p, automation);
        if (property) {
            VARIANT previous {}, next {};
            if (property == UIA_ValueValuePropertyId) { next.vt = VT_BSTR; axString(node(id), RV_AX_VALUE, &next.bstrVal); }
            else if (property == UIA_RangeValueValuePropertyId) { next.vt = VT_R8; rv_ax_number(node(id), RV_AX_NUMBER_VALUE, &next.dblVal); }
            else p->GetPropertyValue(property, &next);
            UiaRaiseAutomationPropertyChangedEvent(p, property, previous, next); VariantClear(&next);
        }
    }
}

struct DisconnectWork {
    HWND hwnd;
    std::unordered_map<int64_t, Provider*> providers;
};
void retireProvider(Provider* provider)
{
    if (InSendMessageEx(nullptr) & ISMEX_SEND) {
        if (QueueUserWorkItem([](void* context) -> DWORD {
            auto* removed = static_cast<Provider*>(context);
            HRESULT initialized = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
            UiaDisconnectProvider(static_cast<IRawElementProviderSimple*>(removed));
            removed->Release();
            if (SUCCEEDED(initialized)) CoUninitialize();
            return 0;
        }, provider, WT_EXECUTEDEFAULT)) return;
    } else UiaDisconnectProvider(static_cast<IRawElementProviderSimple*>(provider));
    provider->Release();
}
void disconnectProviders(DisconnectWork* work)
{
    for (auto [id, provider] : work->providers) UiaDisconnectProvider(static_cast<IRawElementProviderSimple*>(provider));
    UiaReturnRawElementProvider(work->hwnd, 0, 0, nullptr);
    for (auto [id, provider] : work->providers) provider->Release();
    delete work;
}
void Attachment::disconnect()
{
    if (cleaned) return;
    cleaned = true;
    closing.store(true);
    rv_host_set_accessibility(host, 0, nullptr, nullptr);
    events.clear();
    for (auto [id, n] : nodes) rv_ax_release(n);
    nodes.clear();
    names.clear();
    auto* work = new DisconnectWork { hwnd, std::move(providers) }; providers.clear();
    host = nullptr;
    if (InSendMessageEx(nullptr) & ISMEX_SEND) {
        // UIA forbids COM disconnect inside SendMessage. Native nodes are already released on their
        // owner thread; the independent cleanup owns only COM references to unavailable providers.
        if (!QueueUserWorkItem([](void* context) -> DWORD {
            HRESULT initialized = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
            disconnectProviders(static_cast<DisconnectWork*>(context));
            if (SUCCEEDED(initialized)) CoUninitialize();
            return 0;
        }, work, WT_EXECUTEDEFAULT)) {
            // On thread-pool exhaustion, clients still see unavailable providers and can release
            // their own references. Drop our cache without making forbidden outbound COM calls.
            for (auto [id, provider] : work->providers) provider->Release();
            delete work;
        }
    } else disconnectProviders(work);
}
LRESULT CALLBACK subclass(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam, UINT_PTR, DWORD_PTR data)
{
    auto* a = reinterpret_cast<Attachment*>(data);
    auto keepAlive = a->shared_from_this();
    if (message == dispatchMessage()) {
        if (!a->closing.load()) {
            std::function<void()> request;
            {
                std::lock_guard lock(a->requestMutex);
                auto found = a->requests.find(wparam);
                if (found != a->requests.end()) { request = std::move(found->second); a->requests.erase(found); }
            }
            if (request) request();
        }
        return 0;
    }
    if (message == eventMessage()) { a->flush(); return 0; }
    if (message == WM_GETOBJECT && static_cast<LONG>(lparam) == UiaRootObjectId && !a->closing.load()) {
        if (auto* p = a->root()) return UiaReturnRawElementProvider(hwnd, wparam, lparam, static_cast<IRawElementProviderSimple*>(p));
    }
    if (message == WM_NCDESTROY) {
        // The app normally detaches before DestroyWindow. Keep the state alive until normal loop cleanup;
        // disconnecting COM in a synchronous window-message callback is forbidden by UI Automation.
        a->closing.store(true);
        RemoveWindowSubclass(hwnd, subclass, subclassId);
    }
    return DefSubclassProc(hwnd, message, wparam, lparam);
}
}

int32_t rv_host_attach_uia(RvHost* host, void* nativeWindow)
{
    if (!host || !nativeWindow) return RV_ERR_NULL_ARGUMENT;
    int thread = rv_host_scripts_enabled(host); if (thread < 0) return thread;
    auto hwnd = static_cast<HWND>(nativeWindow);
    if (!IsWindow(hwnd) || GetWindowThreadProcessId(hwnd, nullptr) != GetCurrentThreadId()) return RV_ERR_WRONG_THREAD;
    if (attachments.count(host)) return RV_ERR_UNSUPPORTED;
    for (auto& [other, a] : attachments) if (a->hwnd == hwnd) return RV_ERR_UNSUPPORTED;
    auto attachment = std::make_shared<Attachment>(host, hwnd);
    if (!SetWindowSubclass(hwnd, subclass, subclassId, reinterpret_cast<DWORD_PTR>(attachment.get()))) return RV_ERR_UNSUPPORTED;
    int result = rv_host_set_accessibility(host, 1, [](void* context, RvAxNode* node, int event) { static_cast<Attachment*>(context)->queue(node, event); }, attachment.get());
    if (result < 0) { rv_host_set_accessibility(host, 0, nullptr, nullptr); RemoveWindowSubclass(hwnd, subclass, subclassId); return result; }
    attachments[host] = std::move(attachment);
    return RV_OK;
}
int32_t rv_host_detach_uia(RvHost* host)
{
    if (!host) return RV_ERR_NULL_ARGUMENT;
    int thread = rv_host_scripts_enabled(host); if (thread < 0) return thread;
    auto found = attachments.find(host); if (found == attachments.end()) return RV_OK;
    auto attachment = found->second;
    attachment->disconnect();
    RemoveWindowSubclass(attachment->hwnd, subclass, subclassId);
    attachments.erase(found);
    return RV_OK;
}
#else
int32_t rv_host_attach_uia(RvHost*, void*) { return RV_ERR_UNSUPPORTED; }
int32_t rv_host_detach_uia(RvHost*) { return RV_ERR_UNSUPPORTED; }
#endif
