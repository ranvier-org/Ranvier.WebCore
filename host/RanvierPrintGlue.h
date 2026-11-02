#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

struct RvPrintPdfData;

extern "C" {
WEBCORE_EXPORT int32_t ranvier_print_pdf_supported();
WEBCORE_EXPORT int32_t ranvier_print_pdf(RvNode*, const RvPrintOptions*, RvPrintCancelPoll, void* cancel_context, RvPrintPdfData**);
WEBCORE_EXPORT void ranvier_print_pdf_data(RvPrintPdfData*, const uint8_t** bytes, int64_t* length, int32_t* page_count, int32_t* cancelled);
WEBCORE_EXPORT void ranvier_print_pdf_release(RvPrintPdfData*);
}
