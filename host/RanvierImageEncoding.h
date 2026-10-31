#pragma once

#include <cstdint>
#include <optional>
#include <wtf/Forward.h>
#include <wtf/RefPtr.h>
#include <wtf/Vector.h>

namespace WebCore {
class ImageBuffer;
}

// The image encoder shared by snapshots and canvas export, for the host's units; not part of the C ABI.
// Encodings are the RV_IMAGE_ENCODING_* values of RanvierWebCoreAbi.h.
namespace Ranvier::Internal {

// quality for JPEG and WEBP when it is from 0 to 1; std::nullopt, the encoder's default, for NaN, a value outside
// [0, 1] and every other encoding, as HTMLCanvasElement.toBlob does.
std::optional<double> imageEncodingQuality(int32_t encoding, double quality);
// "image/png", "image/jpeg" or "image/webp"; a null String for RGBA8 and an unknown encoding.
String imageEncodingMIMEType(int32_t encoding);
// Whether the engine encodes the encoding on this flavor; RV_IMAGE_ENCODING_RGBA8 always is.
bool imageEncodingSupported(int32_t encoding);
// The buffer's pixels encoded through the engine's encodeData; empty when the encoder fails.
Vector<uint8_t> encodeImage(RefPtr<WebCore::ImageBuffer>&&, int32_t encoding, double quality);

}
