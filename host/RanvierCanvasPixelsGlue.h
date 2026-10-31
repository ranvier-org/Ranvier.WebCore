#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

// rv_image_data_create, rv_image_data_layout, rv_image_data_read and rv_image_data_write after the host's thread
// check, with their contracts.
extern "C" {
WEBCORE_EXPORT int32_t ranvier_image_data_create(uint32_t width, uint32_t height, const uint8_t* bytes, int64_t length, int32_t colorSpace, int32_t pixelFormat, RvImageData** result);
WEBCORE_EXPORT int32_t ranvier_image_data_layout(RvImageData*, RvImageDataLayout*);
WEBCORE_EXPORT int32_t ranvier_image_data_read(RvImageData*, int64_t offset, uint8_t* buffer, int64_t length);
WEBCORE_EXPORT int32_t ranvier_image_data_write(RvImageData*, int64_t offset, const uint8_t* bytes, int64_t length);
}
