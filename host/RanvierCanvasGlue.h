#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

// rv_canvas_get_context and rv_canvas_context_2d_attributes after the host's thread check, with their contracts.
extern "C" {
WEBCORE_EXPORT int32_t ranvier_canvas_get_context(RvNode* canvas, int32_t type, const RvCanvas2DSettings*, RvCanvasRenderingContext2D** context);
WEBCORE_EXPORT int32_t ranvier_canvas_context_2d_attributes(RvCanvasRenderingContext2D*, RvCanvas2DSettings*);
}
