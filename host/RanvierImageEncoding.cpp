#include "config.h"
#include "RanvierImageEncoding.h"

#include "RanvierWebCoreAbi.h"
#include <WebCore/ImageBuffer.h>
#include <WebCore/ImageUtilities.h>
#include <WebCore/MIMETypeRegistry.h>
#include <wtf/text/WTFString.h>

using namespace WebCore;

namespace Ranvier::Internal {

std::optional<double> imageEncodingQuality(int32_t encoding, double quality)
{
    if ((encoding != RV_IMAGE_ENCODING_JPEG && encoding != RV_IMAGE_ENCODING_WEBP) || !(quality >= 0 && quality <= 1))
        return std::nullopt;
    return quality;
}

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
