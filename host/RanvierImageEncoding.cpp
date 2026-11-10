#include "config.h"
#include "RanvierImageEncoding.h"

#include "RanvierWebCoreAbi.h"
#include <WebCore/ImageBuffer.h>
#include <WebCore/ImageUtilities.h>
#include <WebCore/MIMETypeRegistry.h>
#include <WebCore/PixelBuffer.h>
#include <cstring>
#include <wtf/text/WTFString.h>

using namespace WebCore;

namespace Ranvier::Internal {

std::optional<double> imageEncodingQuality(int32_t encoding, double quality)
{
    if ((encoding != RV_IMAGE_ENCODING_JPEG && encoding != RV_IMAGE_ENCODING_WEBP) || !(quality >= 0 && quality <= 1))
        return std::nullopt;
    return quality;
}

}

struct RvEncodedImage {
    Vector<uint8_t> bytes;
};

int32_t rv_image_encode_rgba(const uint8_t* rgba, int64_t length, int32_t width, int32_t height,
    int32_t colorSpace, int32_t encoding, double quality, RvEncodedImage** result)
{
    if (!result)
        return RV_ERR_NULL_ARGUMENT;
    *result = nullptr;
    if (!rgba)
        return RV_ERR_NULL_ARGUMENT;
    if (width <= 0 || height <= 0 || width > 8192 || height > 8192
        || length != static_cast<int64_t>(width) * height * 4 || length > 64 * 1024 * 1024
        || encoding < RV_IMAGE_ENCODING_RGBA8 || encoding > RV_IMAGE_ENCODING_WEBP)
        return RV_ERR_UNSUPPORTED;
    const DestinationColorSpace* space = nullptr;
    if (colorSpace == RV_SNAPSHOT_SRGB)
        space = &DestinationColorSpace::SRGB();
#if ENABLE(DESTINATION_COLOR_SPACE_DISPLAY_P3)
    else if (colorSpace == RV_SNAPSHOT_DISPLAY_P3)
        space = &DestinationColorSpace::DisplayP3();
#endif
    if (!space)
        return RV_ERR_UNSUPPORTED;
    auto source = unsafeMakeSpan(rgba, static_cast<size_t>(length));
    Vector<uint8_t> bytes;
    if (encoding == RV_IMAGE_ENCODING_RGBA8)
        bytes.append(source);
    else {
        IntSize size { width, height };
        auto pixels = PixelBufferSourceView::create({ AlphaPremultiplication::Unpremultiplied, PixelFormat::RGBA8, *space }, size, source);
        auto buffer = ImageBuffer::create(FloatSize { size }, RenderingMode::Unaccelerated, RenderingPurpose::Snapshot,
            1, *space, PixelFormat::BGRA8);
        if (!pixels || !buffer)
            return RV_ERR_PAINT_FAILED;
        buffer->putPixelBuffer(*pixels, { { }, size });
        bytes = Ranvier::Internal::encodeImage(WTF::move(buffer), encoding, quality);
        if (bytes.isEmpty())
            return RV_ERR_UNSUPPORTED;
    }
    *result = new RvEncodedImage { WTF::move(bytes) };
    return RV_OK;
}

int32_t rv_encoded_image_bytes(RvEncodedImage* image, uint8_t* buffer, int64_t capacity, int64_t* length)
{
    if (!image || !length)
        return RV_ERR_NULL_ARGUMENT;
    *length = static_cast<int64_t>(image->bytes.size());
    if (!buffer || capacity < *length)
        return RV_ERR_BUFFER_TOO_SMALL;
    std::memcpy(buffer, image->bytes.span().data(), image->bytes.size());
    return RV_OK;
}

void rv_encoded_image_release(RvEncodedImage* image)
{
    delete image;
}

namespace Ranvier::Internal {

String imageEncodingMIMEType(int32_t encoding)
{
    switch (encoding) {
    case RV_IMAGE_ENCODING_PNG:
        return "image/png"_s;
    case RV_IMAGE_ENCODING_JPEG:
        return "image/jpeg"_s;
    case RV_IMAGE_ENCODING_WEBP:
        return "image/webp"_s;
    default:
        return { };
    }
}

bool imageEncodingSupported(int32_t encoding)
{
    if (encoding == RV_IMAGE_ENCODING_RGBA8)
        return true;
    auto type = imageEncodingMIMEType(encoding);
    return !type.isNull() && MIMETypeRegistry::isSupportedImageMIMETypeForEncoding(type);
}

Vector<uint8_t> encodeImage(RefPtr<ImageBuffer>&& buffer, int32_t encoding, double quality)
{
    return encodeData(WTF::move(buffer), imageEncodingMIMEType(encoding), imageEncodingQuality(encoding, quality));
}

}
