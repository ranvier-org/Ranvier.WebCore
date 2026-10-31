#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

// RvResourceCompletion and the RV_RESOURCE_* outcomes are declared in RanvierWebCoreAbi.h.
// Contract:
// - The starting calls never call the completion before they return; a terminal reached during the call is
//   delivered on a later run-loop turn (rv_run_loop_cycle), or by ranvier_resource_cancel/release, whichever is first.
// - ranvier_resource_cancel and ranvier_resource_release deliver a pending terminal synchronously before they return:
//   CANCELLED for an in-flight operation, or the outcome already reached.
// - A terminal operation stays registered until ranvier_resource_release; release is required for every operation and
//   is idempotent. After release the completion and its context are not used again.
// - ranvier_resource_invalidate_document delivers INVALIDATED to the document's in-flight operations and releases
//   them. Operations that already reached a terminal outcome keep it and stay registered until released.
// - A terminal image operation holds no Document, Element or CachedImage. A font operation that succeeded holds its
//   FontFace in the document's FontFaceSet until release or document invalidation, which remove it.
// - A blob read holds its bytes, type and error name from its terminal outcome until release.
extern "C" {
WEBCORE_EXPORT int32_t ranvier_resource_decode_image(RvNode* document, RvNode* target, RvResourceCompletion, void* context, uint64_t* operation);
WEBCORE_EXPORT int32_t ranvier_resource_load_font(RvNode* document, const char* family, const uint8_t* bytes, int32_t length, RvResourceCompletion, void* context, uint64_t* operation);
WEBCORE_EXPORT int32_t ranvier_resource_cancel(uint64_t operation);
WEBCORE_EXPORT int32_t ranvier_resource_release(uint64_t operation);
WEBCORE_EXPORT void ranvier_resource_invalidate_document(RvNode* document);
WEBCORE_EXPORT int32_t ranvier_blob_read(RvNode* document, RvBlob* blob, int32_t mode, RvResourceCompletion, void* context, uint64_t* operation);
WEBCORE_EXPORT int32_t ranvier_blob_url_read(RvNode* document, const uint8_t* url, int32_t url_length, RvResourceCompletion, void* context, uint64_t* operation);
WEBCORE_EXPORT int32_t ranvier_blob_read_result(uint64_t operation, uint8_t* buffer, int64_t capacity, int64_t* length);
WEBCORE_EXPORT int32_t ranvier_blob_read_type(uint64_t operation, char* buffer, int32_t capacity, int32_t* length);
WEBCORE_EXPORT int32_t ranvier_blob_read_error(uint64_t operation, char* buffer, int32_t capacity, int32_t* length);
WEBCORE_EXPORT int32_t ranvier_file_reader_result(RvEventTarget* reader, int32_t* kind, uint8_t* buffer, int64_t capacity, int64_t* length);
WEBCORE_EXPORT int32_t ranvier_file_reader_error(RvEventTarget* reader, char* buffer, int32_t capacity, int32_t* length);
}
