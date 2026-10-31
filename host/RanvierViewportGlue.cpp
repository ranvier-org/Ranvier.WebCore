#include "config.h"
#include "RanvierViewportGlue.h"
#include "Document.h"
#include "EventTarget.h"
#include "EventTargetInlines.h"
#include "EventTargetInterfaces.h"
#include "LocalDOMWindow.h"
#include "MediaQueryList.h"
#include "Node.h"
#include "DocumentPage.h"
#include "Page.h"
#include "ResizeObserver.h"
#include "ResizeObserverOptions.h"
#include <cstring>

using namespace WebCore;

namespace {

Document* documentOf(RvNode* handle)
{
    return handle ? dynamicDowncast<Document>(reinterpret_cast<Node*>(handle)) : nullptr;
}

MediaQueryList* mediaQueryList(RvEventTarget* handle)
{
    auto* target = reinterpret_cast<EventTarget*>(handle);
    if (target->eventTargetInterface() != EventTargetInterfaceType::MediaQueryList)
        return nullptr;
    return static_cast<MediaQueryList*>(target);
}

}

int32_t ranvier_window_metrics(RvNode* documentHandle, RvWindowMetrics* metrics)
{
    RefPtr document = documentOf(documentHandle);
    if (!document || !metrics)
        return RV_ERR_NULL_ARGUMENT;
    RefPtr window = document->window();
    if (!window || !window->frame())
        return RV_ERR_PAINT_FAILED;
    metrics->innerWidth = window->innerWidth();
    metrics->innerHeight = window->innerHeight();
    metrics->devicePixelRatio = window->devicePixelRatio();
    return RV_OK;
}

RvEventTarget* ranvier_match_media(RvNode* documentHandle, const char* query)
{
    RefPtr document = documentOf(documentHandle);
    if (!document || !query)
        return nullptr;
    RefPtr window = document->window();
    if (!window)
        return nullptr;
    RefPtr list = window->matchMedia(String::fromUTF8(query));
    if (!list)
        return nullptr;
    EventTarget& target = *list;
    target.ref();
    return reinterpret_cast<RvEventTarget*>(&target);
}

void ranvier_page_set_display(RvNode* documentHandle, uint32_t displayID)
{
    RefPtr document = dynamicDowncast<Document>(reinterpret_cast<Node*>(documentHandle));
    if (!document || !document->page())
        return;
    document->page()->windowScreenDidChange(displayID, std::nullopt);
}

int32_t ranvier_media_query_matches(RvEventTarget* handle, int32_t* matches)
{
    if (!handle || !matches)
        return RV_ERR_NULL_ARGUMENT;
    RefPtr list = mediaQueryList(handle);
    if (!list)
        return RV_ERR_WRONG_INTERFACE;
    *matches = list->matches() ? 1 : 0;
    return RV_OK;
}

int32_t ranvier_media_query_media(RvEventTarget* handle, char* buffer, int32_t capacity, int32_t* length)
{
    if (!handle || !length)
        return RV_ERR_NULL_ARGUMENT;
    RefPtr list = mediaQueryList(handle);
    if (!list)
        return RV_ERR_WRONG_INTERFACE;
    auto bytes = list->media().utf8();
    *length = static_cast<int32_t>(bytes.length());
    if (!buffer || capacity < *length)
        return RV_ERR_BUFFER_TOO_SMALL;
    std::memcpy(buffer, bytes.data(), bytes.length());
    return RV_OK;
}

void ranvier_resize_observe_box(ResizeObserver& observer, Element& element, bool border)
{
    observer.observe(element, ResizeObserverOptions { border ? ResizeObserverBoxOptions::BorderBox : ResizeObserverBoxOptions::ContentBox });
}
