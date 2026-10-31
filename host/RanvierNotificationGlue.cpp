#include "config.h"
#include "RanvierNotificationGlue.h"
#include "Document.h"
#include "DocumentPage.h"
#include "EventTarget.h"
#include "EventTargetInlines.h"
#include "EventTargetInterfaces.h"
#include "Node.h"
#include "Notification.h"
#include "NotificationClient.h"
#include "NotificationController.h"
#include "NotificationData.h"
#include "NotificationPermission.h"
#include "Page.h"
#include <wtf/HashMap.h>
#include <wtf/TZoneMallocInlines.h>
#include <wtf/Vector.h>
#include <wtf/WeakPtr.h>
#include <cstring>

using namespace WebCore;

namespace {

Document* documentOf(RvNode* handle)
{
    return handle ? dynamicDowncast<Document>(reinterpret_cast<Node*>(handle)) : nullptr;
}

Notification* notificationOf(RvEventTarget* handle)
{
    auto* target = reinterpret_cast<EventTarget*>(handle);
    if (target->eventTargetInterface() != EventTargetInterfaceType::Notification)
        return nullptr;
    return static_cast<Notification*>(target);
}

String text(const uint8_t* bytes, int32_t length)
{
    if (!bytes || length <= 0)
        return emptyString();
    return String::fromUTF8(std::span { bytes, static_cast<size_t>(length) });
}

// The page's client: the host's permission, the notifications it created, and the presenter requests WebCore made.
class RanvierNotificationClient final : public NotificationClient {
    WTF_MAKE_TZONE_ALLOCATED_INLINE(RanvierNotificationClient);

public:
    NotificationPermission permission { NotificationPermission::Default };
    bool presenter { false };
    HashMap<WTF::UUID, WeakPtr<Notification, WeakPtrImplWithEventTargetData>> notifications;
    Vector<std::pair<int32_t, Ref<Notification>>> pending;

    void enqueue(int32_t request, const NotificationData& data)
    {
        RefPtr notification = notifications.get(data.notificationID);
        if (notification)
            pending.append({ request, notification.releaseNonNull() });
    }

private:
    bool show(ScriptExecutionContext&, NotificationData&& data, RefPtr<NotificationResources>&&, CompletionHandler<void()>&& completion) final
    {
        CompletionHandlerCallingScope scope { WTF::move(completion) };
        if (!presenter) {
            if (RefPtr notification = notifications.get(data.notificationID))
                notification->dispatchErrorEvent();
            return false;
        }
        enqueue(RV_NOTIFICATION_SHOW, data);
        return true;
    }

    void cancel(NotificationData&& data) final { enqueue(RV_NOTIFICATION_CANCEL, data); }

    void notificationObjectDestroyed(NotificationData&& data) final
    {
        enqueue(RV_NOTIFICATION_DESTROYED, data);
        notifications.remove(data.notificationID);
    }

    void notificationControllerDestroyed() final { delete this; }

    void requestPermission(ScriptExecutionContext&, PermissionHandler&& handler) final { handler(permission); }

    Permission checkPermission(ScriptExecutionContext*) final { return permission; }
};

RanvierNotificationClient* clientOf(Document& document)
{
    RefPtr page = document.page();
    if (!page)
        return nullptr;
    return static_cast<RanvierNotificationClient*>(NotificationController::clientFrom(*page));
}

int32_t permissionValue(NotificationPermission permission)
{
    switch (permission) {
    case NotificationPermission::Default:
        return RV_NOTIFICATION_DEFAULT;
    case NotificationPermission::Denied:
        return RV_NOTIFICATION_DENIED;
    case NotificationPermission::Granted:
        return RV_NOTIFICATION_GRANTED;
    }
    return RV_NOTIFICATION_DEFAULT;
}

}

void ranvier_notifications_attach(RvNode* documentHandle)
{
    RefPtr document = documentOf(documentHandle);
    if (!document || !document->page() || NotificationController::clientFrom(*document->page()))
        return;
    provideNotification(document->page(), new RanvierNotificationClient);
}

void ranvier_notifications_configure(RvNode* documentHandle, int32_t permission, int32_t presenter)
{
    RefPtr document = documentOf(documentHandle);
    auto* client = document ? clientOf(*document) : nullptr;
    if (!client)
        return;
    client->permission = permission == RV_NOTIFICATION_GRANTED ? NotificationPermission::Granted
        : permission == RV_NOTIFICATION_DENIED ? NotificationPermission::Denied : NotificationPermission::Default;
    client->presenter = !!presenter;
}

int32_t ranvier_notifications_permission(RvNode* documentHandle, int32_t* permission)
{
    RefPtr document = documentOf(documentHandle);
    if (!document || !permission)
        return RV_ERR_NULL_ARGUMENT;
    auto* client = clientOf(*document);
    if (!client)
        return RV_ERR_UNSUPPORTED;
    *permission = permissionValue(client->permission);
    return RV_OK;
}

int32_t ranvier_notification_create(RvNode* documentHandle, const uint8_t* title, int32_t titleLength, const RvNotificationOptions* options, RvEventTarget** result)
{
    RefPtr document = documentOf(documentHandle);
    if (!document || !result || (!title && titleLength > 0))
        return RV_ERR_NULL_ARGUMENT;
    *result = nullptr;
    auto* client = clientOf(*document);
    if (!client)
        return RV_ERR_UNSUPPORTED;
    NotificationData data;
    data.title = text(title, titleLength);
    if (options) {
        if (options->size != static_cast<int32_t>(sizeof(RvNotificationOptions)) || options->dir < RV_NOTIFICATION_DIR_AUTO || options->dir > RV_NOTIFICATION_DIR_RTL
            || options->silent < -1 || options->silent > 1)
            return RV_ERR_UNSUPPORTED;
        data.direction = options->dir == RV_NOTIFICATION_DIR_LTR ? NotificationDirection::Ltr
            : options->dir == RV_NOTIFICATION_DIR_RTL ? NotificationDirection::Rtl : NotificationDirection::Auto;
        if (options->silent >= 0)
            data.silent = options->silent == 1;
        data.body = text(options->body, options->body_length);
        data.tag = text(options->tag, options->tag_length);
        data.language = text(options->lang, options->lang_length);
        // The Notification constructor resolves the icon against the document.
        data.iconURL = text(options->icon, options->icon_length);
    }
    data.contextIdentifier = document->identifier();
    Ref notification = Notification::create(*document, WTF::move(data));
    client->notifications.set(notification->identifier(), WeakPtr<Notification, WeakPtrImplWithEventTargetData> { notification.get() });
    notification->showSoon();
    Ref<EventTarget> target = notification.get();
    *result = reinterpret_cast<RvEventTarget*>(&target.leakRef());
    return RV_OK;
}

int32_t ranvier_notifications_take(RvNode* documentHandle, int32_t* request, RvEventTarget** result)
{
    RefPtr document = documentOf(documentHandle);
    auto* client = document ? clientOf(*document) : nullptr;
    if (!client || client->pending.isEmpty())
        return 0;
    *request = client->pending.first().first;
    Ref<EventTarget> target = client->pending.first().second.get();
    client->pending.removeAt(0);
    *result = reinterpret_cast<RvEventTarget*>(&target.leakRef());
    return 1;
}

void ranvier_notifications_drop(RvNode* documentHandle)
{
    RefPtr document = documentOf(documentHandle);
    if (auto* client = document ? clientOf(*document) : nullptr)
        client->pending.clear();
}

int32_t ranvier_notification_close(RvEventTarget* handle)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    RefPtr notification = notificationOf(handle);
    if (!notification)
        return RV_ERR_WRONG_INTERFACE;
    notification->close();
    return RV_OK;
}

int32_t ranvier_notification_report(RvEventTarget* handle, int32_t event)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    RefPtr notification = notificationOf(handle);
    if (!notification)
        return RV_ERR_WRONG_INTERFACE;
    switch (event) {
    case RV_NOTIFICATION_EVENT_SHOW:
        notification->dispatchShowEvent();
        return RV_OK;
    case RV_NOTIFICATION_EVENT_CLICK:
        notification->dispatchClickEvent();
        return RV_OK;
    case RV_NOTIFICATION_EVENT_CLOSE:
        notification->dispatchCloseEvent();
        return RV_OK;
    case RV_NOTIFICATION_EVENT_ERROR:
        notification->dispatchErrorEvent();
        return RV_OK;
    }
    return RV_ERR_UNSUPPORTED;
}

int32_t ranvier_notification_string(RvEventTarget* handle, int32_t field, uint8_t* buffer, int32_t capacity, int32_t* length)
{
    if (!handle || !length)
        return RV_ERR_NULL_ARGUMENT;
    RefPtr notification = notificationOf(handle);
    if (!notification)
        return RV_ERR_WRONG_INTERFACE;
    String value;
    switch (field) {
    case RV_NOTIFICATION_TITLE:
        value = notification->title();
        break;
    case RV_NOTIFICATION_BODY:
        value = notification->body();
        break;
    case RV_NOTIFICATION_TAG:
        value = notification->tag();
        break;
    case RV_NOTIFICATION_LANG:
        value = notification->lang();
        break;
    case RV_NOTIFICATION_ICON:
        value = notification->icon().string();
        break;
    default:
        return RV_ERR_UNSUPPORTED;
    }
    auto bytes = value.utf8();
    *length = static_cast<int32_t>(bytes.length());
    if (capacity < *length || (!buffer && *length))
        return RV_ERR_BUFFER_TOO_SMALL;
    if (*length)
        std::memcpy(buffer, bytes.data(), bytes.length());
    return RV_OK;
}

int32_t ranvier_notification_flags(RvEventTarget* handle, int32_t* dir, int32_t* silent)
{
    if (!handle || !dir || !silent)
        return RV_ERR_NULL_ARGUMENT;
    RefPtr notification = notificationOf(handle);
    if (!notification)
        return RV_ERR_WRONG_INTERFACE;
    switch (notification->dir()) {
    case NotificationDirection::Ltr:
        *dir = RV_NOTIFICATION_DIR_LTR;
        break;
    case NotificationDirection::Rtl:
        *dir = RV_NOTIFICATION_DIR_RTL;
        break;
    default:
        *dir = RV_NOTIFICATION_DIR_AUTO;
        break;
    }
    auto value = notification->silent();
    *silent = value ? (*value ? 1 : 0) : -1;
    return RV_OK;
}
