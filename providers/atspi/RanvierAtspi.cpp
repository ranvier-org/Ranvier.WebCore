#include "RanvierAtspi.h"
#include <atspi/atspi.h>
#include <gio/gio.h>
#include <algorithm>
#include <cmath>
#include <condition_variable>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

namespace {
#include "AtspiInterfaces.inc"
constexpr auto rootPath = "/org/a11y/atspi/accessible/root";
constexpr auto nullPath = "/org/a11y/atspi/null";
constexpr auto accessible = "org.a11y.atspi.Accessible";
constexpr auto application = "org.a11y.atspi.Application";
constexpr auto component = "org.a11y.atspi.Component";
constexpr auto action = "org.a11y.atspi.Action";
constexpr auto value = "org.a11y.atspi.Value";
constexpr auto text = "org.a11y.atspi.Text";
constexpr auto editableText = "org.a11y.atspi.EditableText";

std::string protocolText(const char* bytes, size_t length)
{
    std::string result;
    for (size_t offset = 0; offset < length;) {
        auto character = g_utf8_get_char_validated(bytes + offset, length - offset);
        if (!character || character == static_cast<gunichar>(-1) || character == static_cast<gunichar>(-2)) {
            result += "\xef\xbf\xbd";
            ++offset;
        } else {
            auto size = g_utf8_next_char(bytes + offset) - (bytes + offset);
            result.append(bytes + offset, size);
            offset += size;
        }
    }
    return result;
}

template<typename Getter> std::string readString(Getter getter)
{
    int32_t length = 0;
    auto status = getter(nullptr, 0, &length);
    if ((status != RV_OK && status != RV_ERR_BUFFER_TOO_SMALL) || length < 0)
        return {};
    std::vector<char> bytes(static_cast<size_t>(length) + 1);
    if (getter(bytes.data(), static_cast<int32_t>(bytes.size()), &length) != RV_OK || length < 0)
        return {};
    return protocolText(bytes.data(), length);
}

std::string nativeString(RvAxNode* node, int property)
{
    return readString([&](char* buffer, int capacity, int* length) { return rv_ax_string(node, property, buffer, capacity, length); });
}

struct TextSnapshot {
    std::string bytes;
    std::vector<int> utf16 { 0 };
    std::vector<size_t> utf8 { 0 };

    explicit TextSnapshot(RvAxNode* node)
    {
        auto length = rv_ax_text_length(node);
        if (length < 0)
            return;
        bytes = readString([&](char* buffer, int capacity, int* count) { return rv_ax_text(node, 0, length, buffer, capacity, count); });
        for (const char* cursor = bytes.data(); cursor < bytes.data() + bytes.size();) {
            auto character = g_utf8_get_char(cursor);
            cursor = g_utf8_next_char(cursor);
            utf16.push_back(utf16.back() + (character > 0xffff ? 2 : 1));
            utf8.push_back(cursor - bytes.data());
        }
    }
    int size() const { return static_cast<int>(utf16.size()) - 1; }
    bool valid(int offset) const { return offset >= 0 && offset <= size(); }
    int fromNative(int offset) const
    {
        if (offset < 0)
            return -1;
        return static_cast<int>(std::upper_bound(utf16.begin(), utf16.end(), offset) - utf16.begin()) - 1;
    }
    std::string slice(int start, int end) const { return bytes.substr(utf8[start], utf8[end] - utf8[start]); }
};

unsigned roleOf(RvAxNode* node)
{
    switch (rv_ax_role(node)) {
    case RV_ROLE_DOCUMENT: return ATSPI_ROLE_DOCUMENT_WEB;
    case RV_ROLE_APPLICATION: return ATSPI_ROLE_APPLICATION;
    case RV_ROLE_TEXT: return ATSPI_ROLE_STATIC;
    case RV_ROLE_PARAGRAPH: return ATSPI_ROLE_PARAGRAPH;
    case RV_ROLE_HEADING: return ATSPI_ROLE_HEADING;
    case RV_ROLE_LINK: return ATSPI_ROLE_LINK;
    case RV_ROLE_BUTTON: return ATSPI_ROLE_PUSH_BUTTON;
    case RV_ROLE_TOGGLE_BUTTON: return ATSPI_ROLE_TOGGLE_BUTTON;
    case RV_ROLE_CHECKBOX: return ATSPI_ROLE_CHECK_BOX;
    case RV_ROLE_RADIO: return ATSPI_ROLE_RADIO_BUTTON;
    case RV_ROLE_RADIO_GROUP: return ATSPI_ROLE_GROUPING;
    case RV_ROLE_SWITCH: return ATSPI_ROLE_CHECK_BOX;
    case RV_ROLE_TEXT_FIELD: return rv_ax_states(node) & RV_AX_PROTECTED ? ATSPI_ROLE_PASSWORD_TEXT : ATSPI_ROLE_ENTRY;
    case RV_ROLE_TEXT_AREA: return ATSPI_ROLE_TEXT;
    case RV_ROLE_COMBO_BOX: return ATSPI_ROLE_COMBO_BOX;
    case RV_ROLE_LIST_BOX: return ATSPI_ROLE_LIST_BOX;
    case RV_ROLE_OPTION: return ATSPI_ROLE_LIST_ITEM;
    case RV_ROLE_MENU: return ATSPI_ROLE_MENU;
    case RV_ROLE_MENU_BAR: return ATSPI_ROLE_MENU_BAR;
    case RV_ROLE_MENU_ITEM: return ATSPI_ROLE_MENU_ITEM;
    case RV_ROLE_MENU_ITEM_CHECKBOX: return ATSPI_ROLE_CHECK_MENU_ITEM;
    case RV_ROLE_MENU_ITEM_RADIO: return ATSPI_ROLE_RADIO_MENU_ITEM;
    case RV_ROLE_SLIDER: return ATSPI_ROLE_SLIDER;
    case RV_ROLE_SPIN_BUTTON: return ATSPI_ROLE_SPIN_BUTTON;
    case RV_ROLE_PROGRESS: return ATSPI_ROLE_PROGRESS_BAR;
    case RV_ROLE_METER: return ATSPI_ROLE_LEVEL_BAR;
    case RV_ROLE_SCROLL_BAR: return ATSPI_ROLE_SCROLL_BAR;
    case RV_ROLE_IMAGE: return ATSPI_ROLE_IMAGE;
    case RV_ROLE_LIST: return ATSPI_ROLE_LIST;
    case RV_ROLE_LIST_ITEM: return ATSPI_ROLE_LIST_ITEM;
    case RV_ROLE_TABLE: return ATSPI_ROLE_TABLE;
    case RV_ROLE_GRID: case RV_ROLE_TREE_GRID: return ATSPI_ROLE_TREE_TABLE;
    case RV_ROLE_ROW: return ATSPI_ROLE_TABLE_ROW;
    case RV_ROLE_CELL: return ATSPI_ROLE_TABLE_CELL;
    case RV_ROLE_COLUMN_HEADER: return ATSPI_ROLE_COLUMN_HEADER;
    case RV_ROLE_ROW_HEADER: return ATSPI_ROLE_ROW_HEADER;
    case RV_ROLE_TREE: return ATSPI_ROLE_TREE;
    case RV_ROLE_TREE_ITEM: return ATSPI_ROLE_TREE_ITEM;
    case RV_ROLE_TAB_LIST: return ATSPI_ROLE_PAGE_TAB_LIST;
    case RV_ROLE_TAB: return ATSPI_ROLE_PAGE_TAB;
    case RV_ROLE_TAB_PANEL: return ATSPI_ROLE_PANEL;
    case RV_ROLE_DIALOG: case RV_ROLE_ALERT_DIALOG: return ATSPI_ROLE_DIALOG;
    case RV_ROLE_ALERT: return ATSPI_ROLE_ALERT;
    case RV_ROLE_STATUS: return ATSPI_ROLE_STATUS_BAR;
    case RV_ROLE_LOG: return ATSPI_ROLE_LOG;
    case RV_ROLE_MARQUEE: return ATSPI_ROLE_MARQUEE;
    case RV_ROLE_TIMER: return ATSPI_ROLE_TIMER;
    case RV_ROLE_TOOLTIP: return ATSPI_ROLE_TOOL_TIP;
    case RV_ROLE_TOOLBAR: return ATSPI_ROLE_TOOL_BAR;
    case RV_ROLE_SEPARATOR: return ATSPI_ROLE_SEPARATOR;
    case RV_ROLE_LABEL: return ATSPI_ROLE_LABEL;
    case RV_ROLE_MATH: return ATSPI_ROLE_MATH;
    case RV_ROLE_ARTICLE: return ATSPI_ROLE_ARTICLE;
    case RV_ROLE_FORM: return ATSPI_ROLE_FORM;
    case RV_ROLE_BANNER: case RV_ROLE_NAVIGATION: case RV_ROLE_MAIN: case RV_ROLE_COMPLEMENTARY:
    case RV_ROLE_CONTENT_INFO: case RV_ROLE_REGION: case RV_ROLE_SEARCH: return ATSPI_ROLE_LANDMARK;
    default: return ATSPI_ROLE_PANEL;
    }
}

struct StateMapping { int native; unsigned atspi; const char* name; };
constexpr StateMapping stateMapping[] {
    { RV_AX_FOCUSABLE, ATSPI_STATE_FOCUSABLE, "focusable" }, { RV_AX_FOCUSED, ATSPI_STATE_FOCUSED, "focused" },
    { RV_AX_CHECKABLE, ATSPI_STATE_CHECKABLE, "checkable" }, { RV_AX_CHECKED, ATSPI_STATE_CHECKED, "checked" },
    { RV_AX_MIXED, ATSPI_STATE_INDETERMINATE, "indeterminate" }, { RV_AX_PRESSED, ATSPI_STATE_PRESSED, "pressed" },
    { RV_AX_EXPANDABLE, ATSPI_STATE_EXPANDABLE, "expandable" }, { RV_AX_EXPANDED, ATSPI_STATE_EXPANDED, "expanded" },
    { RV_AX_SELECTABLE, ATSPI_STATE_SELECTABLE, "selectable" }, { RV_AX_SELECTED, ATSPI_STATE_SELECTED, "selected" },
    { RV_AX_MULTISELECTABLE, ATSPI_STATE_MULTISELECTABLE, "multiselectable" }, { RV_AX_EDITABLE, ATSPI_STATE_EDITABLE, "editable" },
    { RV_AX_REQUIRED, ATSPI_STATE_REQUIRED, "required" }, { RV_AX_INVALID, ATSPI_STATE_INVALID_ENTRY, "invalid-entry" },
    { RV_AX_MULTILINE, ATSPI_STATE_MULTI_LINE, "multi-line" },
    { RV_AX_VISITED, ATSPI_STATE_VISITED, "visited" }, { RV_AX_BUSY, ATSPI_STATE_BUSY, "busy" },
    { RV_AX_MODAL, ATSPI_STATE_MODAL, "modal" }, { RV_AX_HAS_POPUP, ATSPI_STATE_HAS_POPUP, "has-popup" }
};

struct Bridge;
struct Node {
    Bridge* bridge { nullptr };
    RvAxNode* native { nullptr };
    std::string path;
    std::vector<unsigned> registrations;
    std::vector<const char*> interfaces;
    int states { 0 };
    ~Node() { if (native) rv_ax_release(native); }
};

struct Bridge : std::enable_shared_from_this<Bridge> {
    RvHost* host;
    GDBusConnection* connection { nullptr };
    GDBusNodeInfo* schema { nullptr };
    std::thread::id owner { std::this_thread::get_id() };
    RvAtspiGeometry geometry;
    std::string name;
    std::unordered_map<int64_t, std::unique_ptr<Node>> nodes;
    std::unique_ptr<Node> applicationNode;
    bool closed { false };
    bool ownsAccessibility { false };
    int applicationId { 0 };

    Bridge(RvHost* host, RvAtspiGeometry geometry, std::string name) : host(host), geometry(geometry), name(std::move(name)) { }
    ~Bridge() { close(); if (schema) g_dbus_node_info_unref(schema); if (connection) g_object_unref(connection); }
    const char* bus() const { return g_dbus_connection_get_unique_name(connection); }
    bool onOwner() const { return owner == std::this_thread::get_id(); }
    GVariant* reference(const char* path) const { return g_variant_new("(so)", bus(), path); }
    GVariant* nullReference() const { return g_variant_new("(so)", "", nullPath); }
    static void method(GDBusConnection*, const char*, const char*, const char*, const char*, GVariant*, GDBusMethodInvocation*, void*);
    static GVariant* property(GDBusConnection*, const char*, const char*, const char*, const char*, GError**, void*);
    static gboolean setProperty(GDBusConnection*, const char*, const char*, const char*, const char*, GVariant*, GError**, void*);
    static GDBusInterfaceVTable vtable;

    void unregister(Node& node)
    {
        for (auto id : node.registrations)
            g_dbus_connection_unregister_object(connection, id);
        node.registrations.clear();
    }
    void close()
    {
        if (closed)
            return;
        closed = true;
        if (ownsAccessibility) {
            rv_host_set_accessibility(host, 0, nullptr, nullptr);
            ownsAccessibility = false;
        }
        for (auto& entry : nodes)
            unregister(*entry.second);
        nodes.clear();
        if (applicationNode) {
            unregister(*applicationNode);
            applicationNode.reset();
        }
    }
    bool registerNode(Node& node)
    {
        node.interfaces = { accessible };
        if (!node.native)
            node.interfaces.push_back(application);
        else {
            node.interfaces.push_back(component);
            node.interfaces.push_back(action);
            double number;
            if (rv_ax_number(node.native, RV_AX_NUMBER_VALUE, &number) == RV_OK)
                node.interfaces.push_back(value);
            if (rv_abi_has("accessibility-text") && rv_ax_text_length(node.native) >= 0)
                node.interfaces.push_back(text);
            if ((node.states & RV_AX_EDITABLE) && rv_ax_number(node.native, RV_AX_NUMBER_VALUE, &number) != RV_OK)
                node.interfaces.push_back(editableText);
        }
        for (auto* interface : node.interfaces) {
            GError* error = nullptr;
            auto id = g_dbus_connection_register_object(connection, node.path.c_str(), g_dbus_node_info_lookup_interface(schema, interface), &vtable, &node, nullptr, &error);
            if (!id) {
                g_clear_error(&error);
                unregister(node);
                return false;
            }
            node.registrations.push_back(id);
        }
        return true;
    }
    Node* remember(RvAxNode* native)
    {
        if (!native)
            return nullptr;
        auto id = rv_ax_id(native);
        if (id < 0) { rv_ax_release(native); return nullptr; }
        if (auto found = nodes.find(id); found != nodes.end()) { rv_ax_release(native); return found->second.get(); }
        auto node = std::make_unique<Node>();
        node->bridge = this;
        node->native = native;
        node->states = rv_ax_states(native);
        node->path = "/org/a11y/atspi/accessible/node_" + std::to_string(id);
        if (!registerNode(*node))
            return nullptr;
        auto* result = node.get();
        nodes.emplace(id, std::move(node));
        return result;
    }
    Node* root() { return closed ? nullptr : remember(rv_host_ax_root(host)); }
    GVariant* reference(Node* node) const { return node ? reference(node->path.c_str()) : nullReference(); }
    std::vector<Node*> children(Node& node)
    {
        if (!node.native) {
            if (auto* child = root()) return { child };
            return {};
        }
        int count = 0;
        auto status = rv_ax_children(node.native, nullptr, 0, &count);
        if ((status != RV_OK && status != RV_ERR_BUFFER_TOO_SMALL) || count <= 0)
            return {};
        std::vector<RvAxNode*> raw(count);
        if (rv_ax_children(node.native, raw.data(), count, &count) != RV_OK)
            return {};
        std::vector<Node*> result;
        for (auto* item : raw) if (auto* child = remember(item)) result.push_back(child);
        return result;
    }
    GVariant* parent(Node& node)
    {
        if (!node.native) return nullReference();
        if (auto* parent = remember(rv_ax_parent(node.native))) return reference(parent);
        return reference(rootPath);
    }
    void event(Node& node, const char* signal, const char* detail, int first, int second, GVariant* data)
    {
        g_dbus_connection_emit_signal(connection, nullptr, node.path.c_str(), "org.a11y.atspi.Event.Object", signal,
            g_variant_new("(siiva{sv})", detail, first, second, data, nullptr), nullptr);
    }
    static void notification(void* context, RvAxNode* native, int type)
    {
        auto& bridge = *static_cast<Bridge*>(context);
        auto protectedBridge = bridge.shared_from_this();
        if (bridge.closed)
            return;
        if (type == RV_AX_EVENT_LOAD_COMPLETE) {
            for (auto& entry : bridge.nodes) {
                bridge.event(*entry.second, "StateChanged", "defunct", 1, 0, g_variant_new_string(""));
                bridge.unregister(*entry.second);
            }
            bridge.nodes.clear();
            if (auto* root = bridge.root())
                bridge.event(*bridge.applicationNode, "ChildrenChanged", "add", 0, 0, bridge.reference(root));
            return;
        }
        auto* node = bridge.remember(rv_ax_retain(native));
        if (!node) return;
        if (type == RV_AX_EVENT_FOCUS)
            bridge.event(*node, "StateChanged", "focused", 1, 0, g_variant_new_string(""));
        else if (type == RV_AX_EVENT_NAME || type == RV_AX_EVENT_DESCRIPTION)
            bridge.event(*node, "PropertyChange", type == RV_AX_EVENT_NAME ? "accessible-name" : "accessible-description", 0, 0,
                g_variant_new_string(nativeString(native, type == RV_AX_EVENT_NAME ? RV_AX_NAME : RV_AX_DESCRIPTION).c_str()));
        else if (type == RV_AX_EVENT_VALUE) {
            double number;
            if (rv_ax_number(native, RV_AX_NUMBER_VALUE, &number) == RV_OK)
                bridge.event(*node, "PropertyChange", "accessible-value", 0, 0, g_variant_new_double(number));
        } else if (type == RV_AX_EVENT_STATE) {
            auto current = rv_ax_states(native);
            for (auto mapping : stateMapping)
                if ((node->states ^ current) & mapping.native)
                    bridge.event(*node, "StateChanged", mapping.name, !!(current & mapping.native), 0, g_variant_new_string(""));
            node->states = current;
        } else if (type == RV_AX_EVENT_TEXT_SELECTION) {
            bridge.event(*node, "TextSelectionChanged", "", 0, 0, g_variant_new_string(""));
            bridge.event(*node, "TextCaretMoved", "", TextSnapshot(native).fromNative(rv_ax_text_caret(native)), 0, g_variant_new_string(""));
        }
    }
};

GDBusInterfaceVTable Bridge::vtable { Bridge::method, Bridge::property, Bridge::setProperty, { nullptr } };

bool alive(Node& node, GError** error)
{
    if (!node.bridge->closed && (!node.native || rv_ax_id(node.native) >= 0))
        return true;
    g_set_error_literal(error, G_DBUS_ERROR, G_DBUS_ERROR_UNKNOWN_OBJECT, "The native accessible object is detached");
    return false;
}

std::vector<std::pair<const char*, int>> actions(Node& node)
{
    std::vector<std::pair<const char*, int>> result;
    if (!node.native) return result;
    auto role = rv_ax_role(node.native);
    if (role == RV_ROLE_BUTTON || role == RV_ROLE_TOGGLE_BUTTON || role == RV_ROLE_CHECKBOX || role == RV_ROLE_RADIO || role == RV_ROLE_SWITCH
        || role == RV_ROLE_LINK || role == RV_ROLE_MENU_ITEM || role == RV_ROLE_MENU_ITEM_CHECKBOX || role == RV_ROLE_MENU_ITEM_RADIO)
        result.emplace_back("click", RV_AX_PRESS);
    auto states = rv_ax_states(node.native);
    if (states & RV_AX_FOCUSABLE) result.emplace_back("focus", RV_AX_FOCUS);
    if (states & RV_AX_SELECTABLE) result.emplace_back("select", RV_AX_SELECT);
    if (states & RV_AX_EXPANDABLE) { result.emplace_back("expand", RV_AX_EXPAND); result.emplace_back("collapse", RV_AX_COLLAPSE); }
    double number;
    if (rv_ax_number(node.native, RV_AX_NUMBER_VALUE, &number) == RV_OK) { result.emplace_back("increment", RV_AX_INCREMENT); result.emplace_back("decrement", RV_AX_DECREMENT); }
    result.emplace_back("scroll-into-view", RV_AX_SCROLL_INTO_VIEW);
    return result;
}

GVariant* Bridge::property(GDBusConnection*, const char*, const char*, const char* interface, const char* property, GError** error, void* data)
{
    auto& node = *static_cast<Node*>(data);
    auto protectedBridge = node.bridge->shared_from_this();
    auto& bridge = *node.bridge;
    if (!alive(node, error)) return nullptr;
    if (!strcmp(interface, accessible)) {
        if (!strcmp(property, "Name")) return g_variant_new_string(node.native ? nativeString(node.native, RV_AX_NAME).c_str() : bridge.name.c_str());
        if (!strcmp(property, "Description")) return g_variant_new_string(node.native ? nativeString(node.native, RV_AX_DESCRIPTION).c_str() : "");
        if (!strcmp(property, "Parent")) return bridge.parent(node);
        if (!strcmp(property, "ChildCount")) return g_variant_new_int32(bridge.children(node).size());
        if (!strcmp(property, "Locale")) return g_variant_new_string(g_get_language_names()[0]);
        if (!strcmp(property, "AccessibleId")) return g_variant_new_string(node.native ? std::to_string(rv_ax_id(node.native)).c_str() : "application");
    } else if (!strcmp(interface, application)) {
        if (!strcmp(property, "ToolkitName")) return g_variant_new_string("Ranvier WebCore");
        if (!strcmp(property, "Version")) return g_variant_new_string("private-prototype");
        if (!strcmp(property, "AtspiVersion")) return g_variant_new_string("2.1");
        if (!strcmp(property, "Id")) return g_variant_new_int32(bridge.applicationId);
    } else if (!strcmp(interface, action) && !strcmp(property, "NActions")) return g_variant_new_int32(actions(node).size());
    else if (!strcmp(interface, value)) {
        double number = 0;
        if (!strcmp(property, "MinimumIncrement")) return g_variant_new_double(0);
        int kind = !strcmp(property, "CurrentValue") ? RV_AX_NUMBER_VALUE : !strcmp(property, "MinimumValue") ? RV_AX_NUMBER_MIN : RV_AX_NUMBER_MAX;
        if (rv_ax_number(node.native, kind, &number) == RV_OK) return g_variant_new_double(number);
    } else if (!strcmp(interface, text)) {
        TextSnapshot snapshot(node.native);
        if (!strcmp(property, "CharacterCount")) return g_variant_new_int32(snapshot.size());
        if (!strcmp(property, "CaretOffset")) return g_variant_new_int32(snapshot.fromNative(rv_ax_text_caret(node.native)));
    }
    g_set_error_literal(error, G_DBUS_ERROR, G_DBUS_ERROR_NOT_SUPPORTED, "The native accessibility property is unavailable");
    return nullptr;
}

gboolean Bridge::setProperty(GDBusConnection*, const char*, const char*, const char* interface, const char* property, GVariant* input, GError** error, void* data)
{
    auto& node = *static_cast<Node*>(data);
    auto protectedBridge = node.bridge->shared_from_this();
    if (!alive(node, error)) return false;
    if (!strcmp(interface, application) && !strcmp(property, "Id")) { node.bridge->applicationId = g_variant_get_int32(input); return true; }
    if (!strcmp(interface, value) && !strcmp(property, "CurrentValue") && !(rv_ax_states(node.native) & RV_AX_DISABLED)
        && rv_ax_set_number(node.native, g_variant_get_double(input)) == 1) return true;
    g_set_error_literal(error, G_DBUS_ERROR, G_DBUS_ERROR_NOT_SUPPORTED, "The native accessibility value cannot be changed");
    return false;
}

void Bridge::method(GDBusConnection*, const char*, const char*, const char* interface, const char* method, GVariant* input, GDBusMethodInvocation* invocation, void* data)
{
    auto& node = *static_cast<Node*>(data);
    auto protectedBridge = node.bridge->shared_from_this();
    auto& bridge = *node.bridge;
    GError* error = nullptr;
    if (!alive(node, &error)) { g_dbus_method_invocation_return_gerror(invocation, error); g_clear_error(&error); return; }
    auto answer = [&](GVariant* result) { g_dbus_method_invocation_return_value(invocation, result); };
    auto unsupported = [&] { g_dbus_method_invocation_return_error_literal(invocation, G_DBUS_ERROR, G_DBUS_ERROR_NOT_SUPPORTED, "The native accessibility operation is unavailable"); };
    if (!strcmp(interface, accessible)) {
        if (!strcmp(method, "GetRole")) { answer(g_variant_new("(u)", node.native ? roleOf(node.native) : ATSPI_ROLE_APPLICATION)); return; }
        if (!strcmp(method, "GetRoleName") || !strcmp(method, "GetLocalizedRoleName")) { answer(g_variant_new("(s)", node.native ? nativeString(node.native, RV_AX_ROLE_NAME).c_str() : "application")); return; }
        if (!strcmp(method, "GetApplication")) { answer(g_variant_new("(@(so))", bridge.reference(rootPath))); return; }
        if (!strcmp(method, "GetChildren") || !strcmp(method, "GetChildAtIndex")) {
            auto children = bridge.children(node);
            if (!strcmp(method, "GetChildAtIndex")) {
                int index; g_variant_get(input, "(i)", &index);
                answer(g_variant_new("(@(so))", index >= 0 && static_cast<size_t>(index) < children.size() ? bridge.reference(children[index]) : bridge.nullReference()));
            } else {
                GVariantBuilder builder; g_variant_builder_init(&builder, G_VARIANT_TYPE("a(so)"));
                for (auto* child : children) g_variant_builder_add_value(&builder, bridge.reference(child));
                answer(g_variant_new("(a(so))", &builder));
            }
            return;
        }
        if (!strcmp(method, "GetIndexInParent")) {
            int result = 0;
            if (node.native) if (auto* parent = bridge.remember(rv_ax_parent(node.native))) {
                auto siblings = bridge.children(*parent);
                auto found = std::find(siblings.begin(), siblings.end(), &node);
                result = found == siblings.end() ? -1 : static_cast<int>(found - siblings.begin());
            }
            answer(g_variant_new("(i)", result)); return;
        }
        if (!strcmp(method, "GetInterfaces")) {
            GVariantBuilder builder; g_variant_builder_init(&builder, G_VARIANT_TYPE("as"));
            for (auto* name : node.interfaces) g_variant_builder_add(&builder, "s", name);
            answer(g_variant_new("(as)", &builder)); return;
        }
        if (!strcmp(method, "GetAttributes")) {
            GVariantBuilder builder; g_variant_builder_init(&builder, G_VARIANT_TYPE("a{ss}"));
            g_variant_builder_add(&builder, "{ss}", "toolkit", "Ranvier WebCore");
            if (node.native) { auto live = nativeString(node.native, RV_AX_LIVE); if (!live.empty()) g_variant_builder_add(&builder, "{ss}", "live", live.c_str()); }
            answer(g_variant_new("(a{ss})", &builder)); return;
        }
        if (!strcmp(method, "GetState")) {
            uint64_t state = 0;
            if (node.native) {
                auto native = rv_ax_states(node.native);
                for (auto mapping : stateMapping) if (native & mapping.native) state |= uint64_t { 1 } << mapping.atspi;
                if (!(native & RV_AX_DISABLED)) state |= (uint64_t { 1 } << ATSPI_STATE_ENABLED) | (uint64_t { 1 } << ATSPI_STATE_SENSITIVE);
                state |= uint64_t { 1 } << ATSPI_STATE_VISIBLE;
                if (!(native & RV_AX_OFFSCREEN)) state |= uint64_t { 1 } << ATSPI_STATE_SHOWING;
            }
            GVariantBuilder builder; g_variant_builder_init(&builder, G_VARIANT_TYPE("au"));
            g_variant_builder_add(&builder, "u", static_cast<uint32_t>(state)); g_variant_builder_add(&builder, "u", static_cast<uint32_t>(state >> 32));
            answer(g_variant_new("(au)", &builder)); return;
        }
        if (!strcmp(method, "GetRelationSet")) { GVariantBuilder builder; g_variant_builder_init(&builder, G_VARIANT_TYPE("a(ua(so))")); answer(g_variant_new("(a(ua(so)))", &builder)); return; }
    } else if (!strcmp(interface, application)) {
        if (!strcmp(method, "GetLocale")) { answer(g_variant_new("(s)", g_get_language_names()[0])); return; }
        if (!strcmp(method, "RegisterEventListener") || !strcmp(method, "DeregisterEventListener")) { answer(nullptr); return; }
    } else if (!strcmp(interface, action)) {
        auto available = actions(node);
        if (!strcmp(method, "GetActions")) {
            GVariantBuilder builder; g_variant_builder_init(&builder, G_VARIANT_TYPE("a(sss)"));
            for (auto [name, unused] : available) g_variant_builder_add(&builder, "(sss)", name, name, "");
            answer(g_variant_new("(a(sss))", &builder)); return;
        }
        int index; g_variant_get(input, "(i)", &index);
        if (!strcmp(method, "DoAction")) {
            auto performed = index >= 0 && static_cast<size_t>(index) < available.size() && !(rv_ax_states(node.native) & RV_AX_DISABLED)
                && rv_ax_action(node.native, available[index].second) == 1;
            answer(g_variant_new("(b)", performed)); return;
        }
        if (index < 0 || static_cast<size_t>(index) >= available.size()) { unsupported(); return; }
        if (!strcmp(method, "GetName") || !strcmp(method, "GetLocalizedName") || !strcmp(method, "GetDescription")) { answer(g_variant_new("(s)", available[index].first)); return; }
        if (!strcmp(method, "GetKeyBinding")) { answer(g_variant_new("(s)", nativeString(node.native, RV_AX_KEY_SHORTCUTS).c_str())); return; }
    } else if (!strcmp(interface, component)) {
        if (!strcmp(method, "GrabFocus")) { answer(g_variant_new("(b)", !(rv_ax_states(node.native) & RV_AX_DISABLED) && rv_ax_action(node.native, RV_AX_FOCUS) == 1)); return; }
        if (!strcmp(method, "GetLayer")) { answer(g_variant_new("(u)", ATSPI_LAYER_WIDGET)); return; }
        if (!strcmp(method, "GetMDIZOrder")) { answer(g_variant_new("(n)", 0)); return; }
        if (!strcmp(method, "GetAlpha")) { answer(g_variant_new("(d)", 1.0)); return; }
        if (!strcmp(method, "ScrollTo")) { answer(g_variant_new("(b)", rv_ax_action(node.native, RV_AX_SCROLL_INTO_VIEW) == 1)); return; }
        unsigned coordinates = ATSPI_COORD_TYPE_WINDOW;
        int x = 0, y = 0;
        if (!strcmp(method, "Contains") || !strcmp(method, "GetAccessibleAtPoint")) g_variant_get(input, "(iiu)", &x, &y, &coordinates);
        else if (strcmp(method, "GetSize")) {
            if (!strcmp(method, "GetExtents") || !strcmp(method, "GetPosition")) g_variant_get(input, "(u)", &coordinates);
            else { unsupported(); return; }
        }
        double left, top, width, height;
        if (rv_ax_rect(node.native, &left, &top, &width, &height) != RV_OK) { unsupported(); return; }
        auto scale = bridge.geometry.device_scale;
        left *= scale; top *= scale; width *= scale; height *= scale;
        if (coordinates == ATSPI_COORD_TYPE_SCREEN) {
            if (!bridge.geometry.screen_position_known) { unsupported(); return; }
            left += bridge.geometry.screen_x; top += bridge.geometry.screen_y;
        } else if (coordinates == ATSPI_COORD_TYPE_PARENT) {
            if (auto* parent = bridge.remember(rv_ax_parent(node.native))) {
                double px, py, pw, ph;
                if (rv_ax_rect(parent->native, &px, &py, &pw, &ph) == RV_OK) { left -= px * scale; top -= py * scale; }
            }
        } else if (coordinates != ATSPI_COORD_TYPE_WINDOW) { unsupported(); return; }
        int ix = static_cast<int>(std::floor(left)), iy = static_cast<int>(std::floor(top));
        int iw = static_cast<int>(std::ceil(left + width)) - ix, ih = static_cast<int>(std::ceil(top + height)) - iy;
        if (!strcmp(method, "GetExtents")) answer(g_variant_new("((iiii))", ix, iy, iw, ih));
        else if (!strcmp(method, "GetPosition")) answer(g_variant_new("(ii)", ix, iy));
        else if (!strcmp(method, "GetSize")) answer(g_variant_new("(ii)", iw, ih));
        else if (!strcmp(method, "Contains")) answer(g_variant_new("(b)", x >= ix && y >= iy && x < ix + iw && y < iy + ih));
        else { unsupported(); }
        return;
    } else if (!strcmp(interface, editableText)) {
        if (!strcmp(method, "SetTextContents")) {
            const char* content; g_variant_get(input, "(&s)", &content);
            answer(g_variant_new("(b)", !(rv_ax_states(node.native) & RV_AX_DISABLED)
                && rv_ax_set_value(node.native, reinterpret_cast<const uint8_t*>(content), strlen(content)) == 1)); return;
        }
    } else if (!strcmp(interface, text)) {
        TextSnapshot snapshot(node.native);
        if (!strcmp(method, "GetText")) {
            int start, end; g_variant_get(input, "(ii)", &start, &end); if (end == -1) end = snapshot.size();
            if (!snapshot.valid(start) || !snapshot.valid(end) || end < start) { unsupported(); return; }
            answer(g_variant_new("(s)", snapshot.slice(start, end).c_str())); return;
        }
        if (!strcmp(method, "GetCharacterAtOffset")) {
            int offset; g_variant_get(input, "(i)", &offset);
            if (!snapshot.valid(offset) || offset == snapshot.size()) { unsupported(); return; }
            answer(g_variant_new("(i)", g_utf8_get_char(snapshot.bytes.c_str() + snapshot.utf8[offset]))); return;
        }
        if (!strcmp(method, "SetCaretOffset")) {
            int offset; g_variant_get(input, "(i)", &offset);
            answer(g_variant_new("(b)", snapshot.valid(offset) && rv_ax_text_set_selection(node.native, snapshot.utf16[offset], snapshot.utf16[offset]) == RV_OK)); return;
        }
        int start = -1, end = -1;
        auto selected = rv_ax_text_selection(node.native, &start, &end) == 1 && end > start;
        if (!strcmp(method, "GetNSelections")) { answer(g_variant_new("(i)", selected ? 1 : 0)); return; }
        if (!strcmp(method, "GetSelection")) {
            int index; g_variant_get(input, "(i)", &index);
            if (index || !selected) { unsupported(); return; }
            answer(g_variant_new("(ii)", snapshot.fromNative(start), snapshot.fromNative(end))); return;
        }
        if (!strcmp(method, "SetSelection") || !strcmp(method, "AddSelection")) {
            int index = 0, from, to;
            if (!strcmp(method, "SetSelection")) g_variant_get(input, "(iii)", &index, &from, &to);
            else g_variant_get(input, "(ii)", &from, &to);
            answer(g_variant_new("(b)", !index && (strcmp(method, "AddSelection") || !selected) && snapshot.valid(from) && snapshot.valid(to)
                && to >= from && rv_ax_text_set_selection(node.native, snapshot.utf16[from], snapshot.utf16[to]) == RV_OK)); return;
        }
        if (!strcmp(method, "RemoveSelection")) {
            int index; g_variant_get(input, "(i)", &index);
            answer(g_variant_new("(b)", !index && selected && rv_ax_text_set_selection(node.native, start, start) == RV_OK)); return;
        }
        if (!strcmp(method, "GetStringAtOffset")) {
            int offset; unsigned granularity; g_variant_get(input, "(iu)", &offset, &granularity);
            constexpr int units[] { RV_TEXT_CHARACTER, RV_TEXT_WORD, RV_TEXT_SENTENCE, RV_TEXT_LINE, RV_TEXT_PARAGRAPH };
            if (!snapshot.valid(offset) || granularity >= std::size(units)
                || rv_ax_text_boundary(node.native, snapshot.utf16[offset], units[granularity], &start, &end) != RV_OK) { unsupported(); return; }
            auto from = snapshot.fromNative(start), to = snapshot.fromNative(end);
            answer(g_variant_new("(sii)", snapshot.slice(from, to).c_str(), from, to)); return;
        }
    }
    unsupported();
}

std::unordered_map<uint64_t, std::shared_ptr<Bridge>> bridges;
std::recursive_mutex registryMutex;
std::thread::id providerOwner;
uint64_t nextBridge { 1 };
bool geometryValid(const RvAtspiGeometry* geometry)
{
    return geometry && geometry->size == sizeof(*geometry) && (geometry->screen_position_known == 0 || geometry->screen_position_known == 1)
        && std::isfinite(geometry->device_scale) && geometry->device_scale > 0;
}
}

int32_t rv_atspi_bridge_create(RvHost* host, const char* address, const uint8_t* name, int32_t nameLength, const RvAtspiGeometry* geometry, uint64_t* result)
{
    std::lock_guard lock(registryMutex);
    if (result) *result = 0;
    if (providerOwner != std::thread::id {} && providerOwner != std::this_thread::get_id()) return RV_ERR_WRONG_THREAD;
    if (!host || !address || !result || nameLength < 0 || (nameLength && !name)) return RV_ERR_NULL_ARGUMENT;
    if (!geometryValid(geometry)) return RV_ERR_UNSUPPORTED;
    for (auto& entry : bridges) if (entry.second->host == host) return RV_ERR_UNSUPPORTED;
    auto bridge = std::make_shared<Bridge>(host, *geometry, protocolText(reinterpret_cast<const char*>(name), nameLength));
    GError* error = nullptr;
    auto* cancellable = g_cancellable_new();
    std::mutex timerMutex;
    std::condition_variable timerWake;
    bool connected = false;
    std::thread timeout([&] {
        std::unique_lock timerLock(timerMutex);
        if (!timerWake.wait_for(timerLock, std::chrono::seconds(2), [&] { return connected; }))
            g_cancellable_cancel(cancellable);
    });
    bridge->connection = g_dbus_connection_new_for_address_sync(address,
        static_cast<GDBusConnectionFlags>(G_DBUS_CONNECTION_FLAGS_AUTHENTICATION_CLIENT | G_DBUS_CONNECTION_FLAGS_MESSAGE_BUS_CONNECTION), nullptr, cancellable, &error);
    { std::lock_guard timerLock(timerMutex); connected = true; }
    timerWake.notify_one();
    timeout.join();
    g_object_unref(cancellable);
    if (!bridge->connection) { g_clear_error(&error); return RV_ERR_UNSUPPORTED; }
    g_dbus_connection_set_exit_on_close(bridge->connection, false);
    bridge->schema = g_dbus_node_info_new_for_xml(interfaceXml, &error);
    if (!bridge->schema) { g_clear_error(&error); return RV_ERR_UNSUPPORTED; }
    if (rv_host_set_accessibility(host, 1, Bridge::notification, bridge.get()) != RV_OK) return RV_ERR_UNSUPPORTED;
    bridge->ownsAccessibility = true;
    providerOwner = std::this_thread::get_id();
    bridge->applicationNode = std::make_unique<Node>();
    bridge->applicationNode->bridge = bridge.get();
    bridge->applicationNode->native = nullptr;
    bridge->applicationNode->path = rootPath;
    if (!bridge->registerNode(*bridge->applicationNode) || !bridge->root()) return RV_ERR_UNSUPPORTED;
    auto id = nextBridge++;
    bridges.emplace(id, std::move(bridge));
    *result = id;
    return RV_OK;
}

int32_t rv_atspi_bridge_set_geometry(uint64_t token, const RvAtspiGeometry* geometry)
{
    std::lock_guard lock(registryMutex);
    auto found = bridges.find(token);
    if (found == bridges.end()) return RV_ERR_DETACHED;
    if (!found->second->onOwner()) return RV_ERR_WRONG_THREAD;
    if (!geometryValid(geometry)) return RV_ERR_UNSUPPORTED;
    found->second->geometry = *geometry;
    return RV_OK;
}

int32_t rv_atspi_bridge_bus_name(uint64_t token, char* buffer, int32_t capacity, int32_t* length)
{
    std::lock_guard lock(registryMutex);
    auto found = bridges.find(token);
    if (found == bridges.end()) return RV_ERR_DETACHED;
    if (!found->second->onOwner()) return RV_ERR_WRONG_THREAD;
    if (!length || capacity < 0 || (capacity && !buffer)) return RV_ERR_NULL_ARGUMENT;
    auto* bus = found->second->bus();
    *length = strlen(bus);
    if (capacity < *length) return RV_ERR_BUFFER_TOO_SMALL;
    if (*length) memcpy(buffer, bus, *length);
    return RV_OK;
}

int32_t rv_atspi_bridge_release(uint64_t token)
{
    std::lock_guard lock(registryMutex);
    auto found = bridges.find(token);
    if (found == bridges.end()) return RV_ERR_DETACHED;
    if (!found->second->onOwner()) return RV_ERR_WRONG_THREAD;
    auto bridge = std::move(found->second);
    bridges.erase(found);
    bridge->close();
    return RV_OK;
}
