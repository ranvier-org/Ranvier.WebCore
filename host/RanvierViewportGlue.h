#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>
#include <wtf/Ref.h>
#include <wtf/Vector.h>

// Contract:
// - ranvier_window_metrics writes the document window's innerWidth, innerHeight and devicePixelRatio, or returns RV_ERR_PAINT_FAILED when the window has no frame.
// - ranvier_match_media returns a new MediaQueryList reference from the window's matchMedia, or NULL without a window.
// - ranvier_document_now writes the document window's performance.now() in milliseconds, or returns
//   RV_ERR_DETACHED when the document has no window.
// - ranvier_intersection_take_records returns the observer's queued entries and empties its queue, as
//   IntersectionObserver.takeRecords() does.
// - ranvier_resize_observe_box observes the element with an RV_RESIZE_BOX_* option.
// - ranvier_media_query_matches and ranvier_media_query_media read a MediaQueryList, and return
//   RV_ERR_WRONG_INTERFACE for any other target. Both remain valid after the document is destroyed.
extern "C" {
WEBCORE_EXPORT int32_t ranvier_window_metrics(RvNode* document, RvWindowMetrics*);
WEBCORE_EXPORT RvEventTarget* ranvier_match_media(RvNode* document, const char* query);
WEBCORE_EXPORT int32_t ranvier_media_query_matches(RvEventTarget*, int32_t* matches);
WEBCORE_EXPORT int32_t ranvier_media_query_media(RvEventTarget*, char* buffer, int32_t capacity, int32_t* length);
// Moves the document's page to the display displayID, whose PlatformScreen data its screen reports.
WEBCORE_EXPORT void ranvier_page_set_display(RvNode* document, uint32_t displayID);
// rv_node_convert_points and rv_node_box_quad after the thread check, with their contracts.
WEBCORE_EXPORT int32_t ranvier_convert_points(RvNode* from, int32_t fromSpace, RvNode* to, int32_t toSpace, double* xy, int32_t count);
WEBCORE_EXPORT int32_t ranvier_box_quad(RvNode* node, int32_t box, RvNode* to, int32_t toSpace, double* quad);
WEBCORE_EXPORT int32_t ranvier_document_now(RvNode* document, double* milliseconds);
}

namespace WebCore {
class Element;
class IntersectionObserver;
class IntersectionObserverEntry;
class ResizeObserver;
}

WEBCORE_EXPORT void ranvier_resize_observe_box(WebCore::ResizeObserver&, WebCore::Element&, int32_t box);
WEBCORE_EXPORT Vector<Ref<WebCore::IntersectionObserverEntry>> ranvier_intersection_take_records(WebCore::IntersectionObserver&);
