#include "config.h"
#include "RanvierCanvasExportGlue.h"
#include "Blob.h"
#include "Document.h"
#include "DocumentInlines.h"
#include "HTMLCanvasElement.h"
#include "HTMLElementTypeHelpers.h"
#include "ImageBitmapRenderingContext.h"
#include "ImageBitmapRenderingContextSettings.h"
#include "ImageBuffer.h"
#include "Node.h"
#include "NodeDocument.h"
#include "ScriptTrackingPrivacyCategory.h"
#include "dom/RanvierDomGlue.h"
#include <wtf/MainThread.h>

using namespace WebCore;

namespace {

HTMLCanvasElement* canvasFromHandle(RvNode* handle)
{
    return dynamicDowncast<HTMLCanvasElement>(reinterpret_cast<Node*>(handle));
}

} // namespace

namespace Ranvier {

int32_t canvasExportBuffer(RvNode* handle, RefPtr<ImageBuffer>& buffer)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    buffer = nullptr;
    RefPtr canvas = canvasFromHandle(handle);
    if (!canvas)
        return RV_ERR_WRONG_INTERFACE;
    if (!canvas->originClean())
        return recordException(Exception { ExceptionCode::SecurityError });
    if (canvas->size().isEmpty())
        return RV_OK;
    // The pixels toBlob and toDataURL encode, noise included where the document requires it.
    if (canvas->document().requiresScriptTrackingPrivacyProtection(ScriptTrackingPrivacyCategory::Canvas))
        buffer = canvas->createImageForNoiseInjection();
    else
        buffer = canvas->makeRenderingResultsAvailable();
    if (!buffer)
        return recordException(Exception { ExceptionCode::EncodingError });
    return RV_OK;
}

} // namespace Ranvier

int32_t ranvier_canvas_create_blob(RvNode* handle, const uint8_t* bytes, int64_t length, const char* type, RvBlob** blob)
{
    if (!handle || !bytes || length <= 0 || !type || !blob)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr canvas = canvasFromHandle(handle);
    if (!canvas)
        return RV_ERR_WRONG_INTERFACE;
    Vector<uint8_t> data { std::span<const uint8_t> { bytes, static_cast<size_t>(length) } };
    Ref document = canvas->document();
    *blob = reinterpret_cast<RvBlob*>(&Blob::create(document.ptr(), WTF::move(data), String::fromLatin1(type)).leakRef());
    return RV_OK;
}

int32_t ranvier_canvas_get_bitmap_context(RvNode* handle, RvImageBitmapRenderingContext** context)
{
    if (!handle || !context)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    *context = nullptr;
    RefPtr canvas = canvasFromHandle(handle);
    if (!canvas)
        return RV_ERR_WRONG_INTERFACE;
    if (auto* existing = canvas->renderingContext()) {
        if (existing->isPlaceholder())
            return RV_ERR_UNSUPPORTED;
        if (auto* bitmap = dynamicDowncast<ImageBitmapRenderingContext>(*existing)) {
            bitmap->ref();
            *context = reinterpret_cast<RvImageBitmapRenderingContext*>(bitmap);
        }
        return RV_OK;
    }
    auto* created = canvas->getContextBitmapRenderer("bitmaprenderer"_s, ImageBitmapRenderingContextSettings { });
    if (!created)
        return RV_ERR_UNSUPPORTED;
    created->ref();
    *context = reinterpret_cast<RvImageBitmapRenderingContext*>(created);
    return RV_OK;
}
