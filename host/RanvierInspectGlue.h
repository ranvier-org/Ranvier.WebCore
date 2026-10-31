#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

// Contract:
// - Each function takes the host's document and a target in it, updates style and layout first, and
//   returns RV_ERR_UNSUPPORTED for a target outside the document or with no renderer the call can read.
// - The sinks receive UTF-8 bytes valid only for the duration of the call.
// - None of them calls the page's inspector controller or instrumentation.
extern "C" {
typedef void (*RanvierInspectTextSink)(void* context, const char* text, int32_t length);
typedef struct RanvierInspectRule {
    int32_t origin;
    int32_t specificity[3];
    int32_t selectorCount;
    int32_t matchedSelectorCount;
    const char* selectorText;
    int32_t selectorTextLength;
    const char* matchedSelector;
    int32_t matchedSelectorLength;
    const char* declarations;
    int32_t declarationsLength;
} RanvierInspectRule;
typedef void (*RanvierInspectRuleSink)(void* context, const RanvierInspectRule*);

// target NULL dumps the main frame. flags are RV_RENDER_TREE_* bits, validated by the caller.
WEBCORE_EXPORT int32_t ranvier_inspect_render_tree(RvNode* document, RvNode* target, int32_t flags, RanvierInspectTextSink, void* context);
WEBCORE_EXPORT int32_t ranvier_inspect_matched_rules(RvNode* document, RvNode* element, RanvierInspectRuleSink, void* context);
// Writes RV_BOX_VALUES doubles only on success.
WEBCORE_EXPORT int32_t ranvier_inspect_box_model(RvNode* document, RvNode* element, double* values);
}
