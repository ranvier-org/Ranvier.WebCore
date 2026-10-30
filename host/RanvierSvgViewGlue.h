#pragma once
#include "RanvierWebCoreAbi.h"
#include <WebCore/ExceptionCode.h>

extern "C" WEBCORE_EXPORT int32_t ranvier_host_select_svg_view(RvNode* document, const char* fragment, int32_t* selected);
