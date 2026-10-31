#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

// Contract:
// - ranvier_element_request_pointer_lock runs Element.requestPointerLock on the element. A request the engine rejects
//   at once returns RV_ERR_DOM_EXCEPTION with the exception recorded for rv_last_exception; a request it accepts
//   returns RV_OK, and its outcome arrives as pointerlockchange or pointerlockerror on the document.
// - ranvier_document_exit_pointer_lock runs Document.exitPointerLock.
// - ranvier_pointer_lock_state writes the RV_POINTER_LOCK_* state of the document's page and, when element is not
//   NULL, a new reference to the lock target or NULL.
// - ranvier_pointer_lock_lose ends a held lock as the platform losing it does: pointerlockchange on the document.
// - ranvier_touch_geometry writes the prefixed radius, rotation and force of a Touch.
// Every function returns RV_ERR_UNSUPPORTED for a document without a page, or where WebKit builds without POINTER_LOCK.
extern "C" {
WEBCORE_EXPORT int32_t ranvier_element_request_pointer_lock(RvNode* element, int32_t unadjustedMovement);
WEBCORE_EXPORT int32_t ranvier_document_exit_pointer_lock(RvNode* document);
WEBCORE_EXPORT int32_t ranvier_pointer_lock_state(RvNode* document, int32_t* state, RvNode** element);
WEBCORE_EXPORT int32_t ranvier_pointer_lock_lose(RvNode* document);
WEBCORE_EXPORT int32_t ranvier_touch_geometry(RvTouch* touch, RvTouchGeometry* geometry);
}
