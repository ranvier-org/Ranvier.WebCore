#pragma once

#include <WebCore/PixelBuffer.h>
#include <wtf/Ref.h>

// Immutable after capture. PixelBuffer has thread-safe reference counting; no DOM or graphics context crosses threads.
struct RvSnapshotPixels {
    Ref<WebCore::PixelBuffer> pixels;
    int32_t colorSpace;
};
