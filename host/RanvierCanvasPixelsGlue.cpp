#include "config.h"
#include "RanvierCanvasPixelsGlue.h"
#include "ImageData.h"
#include "ExceptionOr.h"
#include "ImageDataArray.h"
#include "dom/RanvierDomGlue.h"
#include <JavaScriptCore/ArrayBufferView.h>
#include <wtf/MainThread.h>

using namespace WebCore;

namespace {

constexpr int32_t pixelFormatUnorm8 = 0;
constexpr int64_t bytesPerPixel = 4;

ImageData& imageData(RvImageData* handle) { return *reinterpret_cast<ImageData*>(handle); }

// The pixel bytes, or nullopt with the exception recorded for detached data.
std::optional<std::span<uint8_t>> pixelBytes(ImageData& data, int32_t& status)
{
    if (data.data().isDetached()) {
        status = Ranvier::recordException(Exception { ExceptionCode::InvalidStateError, "The ImageData's data is detached"_s });
        return std::nullopt;
    }
    return data.data().arrayBufferView().mutableSpan();
}

// RangeError unless [offset, offset + length) lies within size bytes.
int32_t checkRange(int64_t offset, int64_t length, size_t size)
{
    if (offset < 0 || length < 0 || static_cast<uint64_t>(offset) > size || static_cast<uint64_t>(length) > size - static_cast<uint64_t>(offset))
        return Ranvier::recordException(Exception { ExceptionCode::RangeError, "The range lies outside the ImageData's data"_s });
    return RV_OK;
}

} // namespace

int32_t ranvier_image_data_create(uint32_t width, uint32_t height, const uint8_t* bytes, int64_t length, int32_t colorSpace, int32_t pixelFormat, RvImageData** result)
{
    if (!result || (!bytes && length))
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    *result = nullptr;
    if (colorSpace != RV_CANVAS_COLOR_SPACE_SRGB || pixelFormat != pixelFormatUnorm8)
        return RV_ERR_UNSUPPORTED;
    if (length < 0)
        return Ranvier::recordException(Exception { ExceptionCode::RangeError, "The length is negative"_s });
    std::span<const uint8_t> source;
    if (bytes) {
        // The checks and their order are those of new ImageData(data, sw, sh).
        if (!length || length % bytesPerPixel)
            return Ranvier::recordException(Exception { ExceptionCode::InvalidStateError, "Length is not a non-zero multiple of 4"_s });
        auto pixels = static_cast<uint64_t>(length / bytesPerPixel);
        if (!width || pixels % width)
            return Ranvier::recordException(Exception { ExceptionCode::IndexSizeError, "Length is not a multiple of sw"_s });
        if (pixels / width != height)
            return Ranvier::recordException(Exception { ExceptionCode::IndexSizeError, "sh value is not equal to height"_s });
        source = { bytes, static_cast<size_t>(length) };
    }
    auto created = ImageData::create(width, height, PredefinedColorSpace::SRGB, std::nullopt, source);
    if (created.hasException())
        return Ranvier::recordException(created.releaseException());
    *result = reinterpret_cast<RvImageData*>(&created.releaseReturnValue().leakRef());
    return RV_OK;
}

int32_t ranvier_image_data_layout(RvImageData* handle, RvImageDataLayout* layout)
{
    if (!handle || !layout)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    if (layout->size < static_cast<int32_t>(sizeof(RvImageDataLayout)))
        return RV_ERR_UNSUPPORTED;
    auto& data = imageData(handle);
    auto perPixel = data.pixelFormat() == ImageDataPixelFormat::RgbaFloat16 ? 8 : 4;
    layout->width = data.width();
    layout->height = data.height();
    layout->colorSpace = data.colorSpace() == PredefinedColorSpace::SRGB ? RV_CANVAS_COLOR_SPACE_SRGB : RV_CANVAS_COLOR_SPACE_DISPLAY_P3;
    layout->pixelFormat = data.pixelFormat() == ImageDataPixelFormat::RgbaFloat16 ? 1 : pixelFormatUnorm8;
    layout->bytesPerPixel = perPixel;
    layout->rowBytes = static_cast<int64_t>(data.width()) * perPixel;
    layout->byteLength = data.data().isDetached() ? 0 : static_cast<int64_t>(data.data().byteLength());
    return RV_OK;
}

int32_t ranvier_image_data_read(RvImageData* handle, int64_t offset, uint8_t* buffer, int64_t length)
{
    if (!handle || (!buffer && length))
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    int32_t status = RV_OK;
    auto span = pixelBytes(imageData(handle), status);
    if (!span)
        return status;
    if (auto code = checkRange(offset, length, span->size()))
        return code;
    if (length)
        memcpySpan(std::span { buffer, static_cast<size_t>(length) }, span->subspan(offset, length));
    return RV_OK;
}

int32_t ranvier_image_data_write(RvImageData* handle, int64_t offset, const uint8_t* bytes, int64_t length)
{
    if (!handle || (!bytes && length))
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    int32_t status = RV_OK;
    auto span = pixelBytes(imageData(handle), status);
    if (!span)
        return status;
    if (auto code = checkRange(offset, length, span->size()))
        return code;
    if (length)
        memcpySpan(span->subspan(offset, length), std::span { bytes, static_cast<size_t>(length) });
    return RV_OK;
}
