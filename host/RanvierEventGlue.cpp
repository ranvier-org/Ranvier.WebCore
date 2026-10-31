#include "config.h"
#include "RanvierEventGlue.h"
#include "CustomEvent.h"
#include "Document.h"
#include "Event.h"
#include "EventTargetConcrete.h"
#include "EventTargetInlines.h"
#include "FocusEvent.h"
#include "JSValueInWrappedObjectInlines.h"
#include "KeyboardEvent.h"
#include "LocalDOMWindow.h"
#include "MouseEvent.h"
#include "Navigator.h"
#include "Node.h"
#include "UIEvent.h"
#include <JavaScriptCore/JSLock.h>
#include <JavaScriptCore/JSONObject.h>
#include <JavaScriptCore/Strong.h>
#include <JavaScriptCore/StrongInlines.h>
#include <wtf/MainThread.h>
#include <wtf/NeverDestroyed.h>
#include <wtf/Vector.h>
#include <wtf/WeakPtr.h>
#include <cstring>

using namespace WebCore;

namespace {

struct DetailRoot {
    WeakPtr<Event> event;
    WeakPtr<Document, WeakPtrImplWithEventTargetData> document;
    JSC::Strong<JSC::Unknown> detail;
};

Vector<DetailRoot>& roots()
{
    static NeverDestroyed<Vector<DetailRoot>> value;
    return value;
}

// Drops the roots of destroyed events or documents; a root outlives its event by at most one later glue call.
void prune()
{
    roots().removeAllMatching([](auto& root) { return !root.event || !root.document; });
}

bool validUtf8(const char* text)
{
    return !text || !String::fromUTF8(text).isNull();
}

String text(const char* value)
{
    return value ? String::fromUTF8(value) : emptyString();
}

void modifiers(EventModifierInit& target, int32_t bits)
{
    target.shiftKey = bits & RV_MODIFIER_SHIFT;
    target.ctrlKey = bits & RV_MODIFIER_CONTROL;
    target.altKey = bits & RV_MODIFIER_ALT;
    target.metaKey = bits & RV_MODIFIER_META;
}

void base(EventInit& target, const RvEventInit& init)
{
    target.bubbles = init.bubbles;
    target.cancelable = init.cancelable;
    target.composed = init.composed;
}

RefPtr<EventTarget> related(const RvEventInit& init)
{
    return reinterpret_cast<EventTarget*>(init.relatedTarget);
}

Document* documentOf(RvNode* handle)
{
    return handle ? dynamicDowncast<Document>(reinterpret_cast<Node*>(handle)) : nullptr;
}

}

RvEvent* ranvier_event_construct(RvNode* documentHandle, int32_t kind, const char* type, const RvEventInit* init)
{
    if (!isMainThread() || !type || !init || init->size != static_cast<int32_t>(sizeof(RvEventInit)))
        return nullptr;
    auto* document = documentOf(documentHandle);
    if (!document || !validUtf8(type) || !validUtf8(init->key) || !validUtf8(init->code) || !validUtf8(init->customDetailJson))
        return nullptr;
    auto name = AtomString::fromUTF8(type);
    RefPtr<Event> result;
    switch (kind) {
    case RV_CONSTRUCT_EVENT: {
        EventInit value;
        base(value, *init);
        result = Event::create(name, value);
        break;
    }
    case RV_CONSTRUCT_CUSTOM: {
        auto* globalObject = document->globalObject();
        if (!globalObject)
            return nullptr;
        auto& vm = globalObject->vm();
        JSC::JSLockHolder lock(vm);
        JSC::JSValue detail = JSC::jsNull();
        if (init->customDetailJson) {
            detail = JSC::JSONParse(globalObject, String::fromUTF8(init->customDetailJson));
            if (!detail)
                return nullptr;
        }
        CustomEvent::Init value;
        base(value, *init);
        value.detail = detail;
        Ref created = CustomEvent::create(*globalObject, name, WTF::move(value));
        prune();
        roots().append({ WeakPtr<Event> { created.get() }, WeakPtr<Document, WeakPtrImplWithEventTargetData> { *document }, JSC::Strong<JSC::Unknown> { vm, detail } });
        result = WTF::move(created);
        break;
    }
    case RV_CONSTRUCT_UI: {
        UIEventInit value;
        base(value, *init);
        value.detail = init->detail;
        result = UIEvent::create(name, value);
        break;
    }
    case RV_CONSTRUCT_MOUSE: {
        MouseEventInit value;
        base(value, *init);
        value.detail = init->detail;
        modifiers(value, init->modifiers);
        value.screenX = init->screenX;
        value.screenY = init->screenY;
        value.clientX = init->clientX;
        value.clientY = init->clientY;
        value.button = static_cast<int16_t>(init->button);
        value.buttons = static_cast<unsigned short>(init->buttons);
        value.relatedTarget = related(*init);
        result = MouseEvent::create(name, value);
        break;
    }
    case RV_CONSTRUCT_KEYBOARD: {
        KeyboardEvent::Init value { };
        base(value, *init);
        value.detail = init->detail;
        modifiers(value, init->modifiers);
        value.key = text(init->key);
        value.code = text(init->code);
        value.location = static_cast<unsigned>(init->location);
        value.repeat = init->repeat;
        value.isComposing = init->isComposing;
        value.charCode = 0;
        value.keyCode = 0;
        value.which = 0;
        result = KeyboardEvent::create(name, value);
        break;
    }
    case RV_CONSTRUCT_FOCUS: {
        FocusEvent::Init value;
        base(value, *init);
        value.detail = init->detail;
        value.relatedTarget = related(*init);
        result = FocusEvent::create(name, WTF::move(value));
        break;
    }
    default:
        return nullptr;
    }
    return reinterpret_cast<RvEvent*>(result.leakRef());
}

int32_t ranvier_custom_event_detail_json(RvEvent* handle, char* buffer, int32_t capacity, int32_t* length)
{
    if (!handle || !length)
        return RV_ERR_NULL_ARGUMENT;
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto& subject = *reinterpret_cast<Event*>(handle);
    if (subject.interfaceType() != EventInterfaceType::CustomEvent)
        return RV_ERR_UNSUPPORTED;
    auto* custom = static_cast<CustomEvent*>(&subject);
    prune();
    DetailRoot* root = nullptr;
    for (auto& candidate : roots()) {
        if (candidate.event.get() == custom) {
            root = &candidate;
            break;
        }
    }
    if (!root)
        return RV_ERR_UNSUPPORTED;
    auto* globalObject = root->document->globalObject();
    if (!globalObject)
        return RV_ERR_UNSUPPORTED;
    JSC::JSLockHolder lock(globalObject->vm());
    auto json = JSC::JSONStringify(globalObject, custom->detail().getValue(JSC::jsNull()), 0u);
    if (json.isNull())
        return RV_ERR_UNSUPPORTED;
    auto bytes = json.utf8();
    auto size = static_cast<int32_t>(bytes.length());
    if (!buffer || capacity < size) {
        *length = size;
        return RV_ERR_BUFFER_TOO_SMALL;
    }
    std::memcpy(buffer, bytes.data(), bytes.length());
    *length = size;
    return RV_OK;
}

RvEventTarget* ranvier_event_target_create(RvNode* documentHandle)
{
    if (!isMainThread())
        return nullptr;
    auto* document = documentOf(documentHandle);
    if (!document)
        return nullptr;
    Ref<EventTarget> target = EventTargetConcrete::create(*document);
    return reinterpret_cast<RvEventTarget*>(&target.leakRef());
}

void ranvier_event_glue_invalidate_document(RvNode* documentHandle)
{
    auto* document = documentOf(documentHandle);
    roots().removeAllMatching([&](auto& root) { return !root.event || !root.document || root.document.get() == document; });
}

RvEventTarget* ranvier_window_event_target(RvNode* documentHandle)
{
    if (!isMainThread())
        return nullptr;
    auto* document = documentOf(documentHandle);
    RefPtr window = document ? document->window() : nullptr;
    if (!window)
        return nullptr;
    Ref<EventTarget> target = *window;
    return reinterpret_cast<RvEventTarget*>(&target.leakRef());
}

int32_t ranvier_window_max_touch_points(RvNode* documentHandle, int32_t* value)
{
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* document = documentOf(documentHandle);
    RefPtr window = document ? document->window() : nullptr;
    if (!window)
        return RV_ERR_UNSUPPORTED;
    *value = window->navigator().maxTouchPoints();
    return RV_OK;
}
