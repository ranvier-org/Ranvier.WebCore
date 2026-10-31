#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

// Contract:
// - ranvier_window_metrics writes the document window's innerWidth, innerHeight and devicePixelRatio, or returns RV_ERR_PAINT_FAILED when the window has no frame.
// - ranvier_match_media returns a new MediaQueryList reference from the window's matchMedia, or NULL without a window.
// - ranvier_resize_observe_box observes the element's content box, or its border box when border is true, as
//   ResizeObserver.observe(element, { box }) does.
// - ranvier_media_query_matches and ranvier_media_query_media read a MediaQueryList, and return
//   RV_ERR_WRONG_INTERFACE for any other target. Both remain valid after the document is destroyed.
extern "C" {
WEBCORE_EXPORT int32_t ranvier_window_metrics(RvNode* document, RvWindowMetrics*);
WEBCORE_EXPORT RvEventTarget* ranvier_match_media(RvNode* document, const char* query);
WEBCORE_EXPORT int32_t ranvier_media_query_matches(RvEventTarget*, int32_t* matches);
WEBCORE_EXPORT int32_t ranvier_media_query_media(RvEventTarget*, char* buffer, int32_t capacity, int32_t* length);
// Moves the document's page to the display displayID, whose PlatformScreen data its screen reports.
WEBCORE_EXPORT void ranvier_page_set_display(RvNode* document, uint32_t displayID);
}

namespace WebCore {
class Element;
class ResizeObserver;
}

WEBCORE_EXPORT void ranvier_resize_observe_box(WebCore::ResizeObserver&, WebCore::Element&, bool border);
