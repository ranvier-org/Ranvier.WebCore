#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

// Contract:
// - ranvier_notifications_attach gives the document's page a NotificationClient. It runs once per page, before any
//   notification exists.
// - ranvier_notifications_configure sets the page's permission and whether a presenter receives show requests.
//   Without a presenter, a granted show fires "error".
// - ranvier_notifications_permission writes the page's permission.
// - ranvier_notification_create builds a Notification of the document from UTF-8 title and options and queues its
//   show, as the constructor does, without JavaScript.
// - ranvier_notifications_take pops the page's oldest presenter request: 1 with *request and a new *target reference,
//   0 when none is pending. Requests queue while WebCore runs and are delivered only by the host.
// - ranvier_notification_close, ranvier_notification_report, ranvier_notification_string and
//   ranvier_notification_flags: the functions of the ABI after the thread check, with their contracts.
extern "C" {
WEBCORE_EXPORT void ranvier_notifications_attach(RvNode* document);
WEBCORE_EXPORT void ranvier_notifications_configure(RvNode* document, int32_t permission, int32_t presenter);
WEBCORE_EXPORT int32_t ranvier_notifications_permission(RvNode* document, int32_t* permission);
WEBCORE_EXPORT int32_t ranvier_notification_create(RvNode* document, const uint8_t* title, int32_t titleLength, const RvNotificationOptions*, RvEventTarget** notification);
WEBCORE_EXPORT int32_t ranvier_notifications_take(RvNode* document, int32_t* request, RvEventTarget** notification);
WEBCORE_EXPORT void ranvier_notifications_drop(RvNode* document);
WEBCORE_EXPORT int32_t ranvier_notification_close(RvEventTarget*);
WEBCORE_EXPORT int32_t ranvier_notification_report(RvEventTarget*, int32_t event);
WEBCORE_EXPORT int32_t ranvier_notification_string(RvEventTarget*, int32_t field, uint8_t* buffer, int32_t capacity, int32_t* length);
WEBCORE_EXPORT int32_t ranvier_notification_flags(RvEventTarget*, int32_t* dir, int32_t* silent);
}
