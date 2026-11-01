#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>
#include <wtf/RefPtr.h>

namespace WebCore {
class ImageBuffer;
}

namespace Ranvier {
// The bitmap rv_canvas_encode, rv_canvas_to_data_url and rv_canvas_to_blob encode, after the host's thread check: RV_OK
// with a null buffer for a zero-size canvas, RV_ERR_WRONG_INTERFACE for another node, and a recorded SecurityError for
// a canvas whose origin is not clean.
WEBCORE_EXPORT int32_t canvasExportBuffer(RvNode* canvas, RefPtr<WebCore::ImageBuffer>& buffer);
}

// rv_canvas_to_blob's Blob and rv_canvas_get_bitmap_context after the host's thread check, with their contracts.
extern "C" {
WEBCORE_EXPORT int32_t ranvier_canvas_create_blob(RvNode* canvas, const uint8_t* bytes, int64_t length, const char* type, RvBlob** blob);
WEBCORE_EXPORT int32_t ranvier_canvas_get_bitmap_context(RvNode* canvas, RvImageBitmapRenderingContext** context);
}
