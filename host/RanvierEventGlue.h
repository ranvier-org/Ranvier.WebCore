#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

// Contract:
// - ranvier_event_construct builds the event with the engine constructor of kind and returns a new reference, or NULL.
//   A CustomEvent detail is parsed from JSON in the document realm. The glue keeps it reachable while the event is
//   alive, because the engine holds detail weakly through a JavaScript wrapper the host never creates.
// - ranvier_custom_event_detail_json serializes that detail with JSON.stringify.
// - ranvier_event_target_create returns a new EventTargetConcrete reference for the document context.
// - ranvier_event_glue_invalidate_document drops the detail roots of the document events.
// - ranvier_window_event_target returns a new reference to the document's LocalDOMWindow as an EventTarget, or NULL.
// - ranvier_window_max_touch_points writes Navigator.maxTouchPoints of the document's window.
extern "C" {
WEBCORE_EXPORT RvEvent* ranvier_event_construct(RvNode* document, int32_t kind, const char* type, const RvEventInit* init);
WEBCORE_EXPORT int32_t ranvier_custom_event_detail_json(RvEvent*, char* buffer, int32_t capacity, int32_t* length);
WEBCORE_EXPORT RvEventTarget* ranvier_event_target_create(RvNode* document);
WEBCORE_EXPORT void ranvier_event_glue_invalidate_document(RvNode* document);
WEBCORE_EXPORT RvEventTarget* ranvier_window_event_target(RvNode* document);
WEBCORE_EXPORT int32_t ranvier_window_max_touch_points(RvNode* document, int32_t* value);
}
