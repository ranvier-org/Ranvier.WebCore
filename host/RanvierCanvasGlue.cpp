#include "config.h"
#include "RanvierCanvasGlue.h"
#include "CanvasRenderingContext2D.h"
#include "CanvasRenderingContext2DSettings.h"
#include "HTMLCanvasElement.h"
#include "HTMLElementTypeHelpers.h"
#include "Node.h"
#include <wtf/MainThread.h>

using namespace WebCore;

namespace {

bool isFlag(int32_t value) { return value == 0 || value == 1; }

// The engine settings for an app request, or nullopt for a request the engine cannot honour. WebKit draws every 2D
// context into an 8-bit sRGB buffer with an alpha channel: it ignores alpha and draws float16 into 8 bits.
std::optional<CanvasRenderingContext2DSettings> engineSettings(const RvCanvas2DSettings* requested)
{
    CanvasRenderingContext2DSettings settings;
    if (!requested)
        return settings;
    if (requested->size < static_cast<int32_t>(sizeof(RvCanvas2DSettings)))
        return std::nullopt;
    if (requested->alpha != 1 || !isFlag(requested->desynchronized) || !isFlag(requested->willReadFrequently))
        return std::nullopt;
    if (requested->colorSpace != RV_CANVAS_COLOR_SPACE_SRGB || requested->colorType != RV_CANVAS_COLOR_TYPE_UNORM8)
        return std::nullopt;
    settings.desynchronized = requested->desynchronized;
    settings.willReadFrequently = requested->willReadFrequently;
    return settings;
}

} // namespace

int32_t ranvier_canvas_get_context(RvNode* handle, int32_t type, const RvCanvas2DSettings* requested, RvCanvasRenderingContext2D** context)
{
    if (!handle || !context)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    *context = nullptr;
    RefPtr canvas = dynamicDowncast<HTMLCanvasElement>(reinterpret_cast<Node*>(handle));
    if (!canvas)
        return RV_ERR_WRONG_INTERFACE;
    if (type != RV_CANVAS_CONTEXT_2D)
        return RV_ERR_UNSUPPORTED;
    auto settings = engineSettings(requested);
    if (!settings)
        return RV_ERR_UNSUPPORTED;
    if (auto* existing = canvas->renderingContext()) {
        if (existing->isPlaceholder())
            return RV_ERR_UNSUPPORTED;
        if (auto* rendering = dynamicDowncast<CanvasRenderingContext2D>(*existing)) {
            rendering->ref();
            *context = reinterpret_cast<RvCanvasRenderingContext2D*>(rendering);
        }
        return RV_OK;
    }
    auto* created = canvas->getContext2d("2d"_s, WTF::move(*settings));
    if (!created)
        return RV_ERR_UNSUPPORTED;
    created->ref();
    *context = reinterpret_cast<RvCanvasRenderingContext2D*>(created);
    return RV_OK;
}

int32_t ranvier_canvas_context_2d_attributes(RvCanvasRenderingContext2D* handle, RvCanvas2DSettings* attributes)
{
    if (!handle || !attributes)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    if (attributes->size < static_cast<int32_t>(sizeof(RvCanvas2DSettings)))
        return RV_ERR_UNSUPPORTED;
    auto& settings = reinterpret_cast<CanvasRenderingContext2D*>(handle)->getContextAttributes();
    attributes->alpha = 1;
    attributes->desynchronized = settings.desynchronized;
    attributes->willReadFrequently = settings.willReadFrequently;
    attributes->colorSpace = RV_CANVAS_COLOR_SPACE_SRGB;
    attributes->colorType = settings.colorType == CanvasRenderingContext2DSettings::ColorType::Float16 ? RV_CANVAS_COLOR_TYPE_FLOAT16 : RV_CANVAS_COLOR_TYPE_UNORM8;
    return RV_OK;
}
