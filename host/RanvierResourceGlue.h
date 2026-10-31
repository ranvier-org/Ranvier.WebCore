#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

// RvResourceCompletion and the RV_RESOURCE_* outcomes are declared in RanvierWebCoreAbi.h.
// Contract:
// - ranvier_resource_decode_image never calls the completion before it returns; a terminal reached during the call is
//   delivered on a later run-loop turn (rv_run_loop_cycle), or by ranvier_resource_cancel/release, whichever is first.
// - ranvier_resource_cancel and ranvier_resource_release deliver a pending terminal synchronously before they return:
//   CANCELLED for an in-flight operation, or the outcome already reached.
// - A terminal operation stays registered until ranvier_resource_release; release is required for every operation and
//   is idempotent. After release the completion and its context are not used again.
// - ranvier_resource_invalidate_document delivers INVALIDATED to the document's in-flight operations and releases
//   them. Operations that already reached a terminal outcome keep it and stay registered until released.
// - A terminal operation holds no Document, Element or CachedImage.
extern "C" {
WEBCORE_EXPORT int32_t ranvier_resource_decode_image(RvNode* document, RvNode* target, RvResourceCompletion, void* context, uint64_t* operation);
WEBCORE_EXPORT int32_t ranvier_resource_cancel(uint64_t operation);
WEBCORE_EXPORT int32_t ranvier_resource_release(uint64_t operation);
WEBCORE_EXPORT void ranvier_resource_invalidate_document(RvNode* document);
}
