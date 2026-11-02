#include "config.h"
#if RANVIER_COMPOSITING
#include "TextureMapper.h"
#include "TextureMapperFlags.h"
#include "Element.h"
#include "RenderBox.h"
#include "RenderBoxInlines.h"
#include "RenderLayer.h"
#include "RenderLayerBacking.h"

extern "C" WEBCORE_EXPORT WebCore::GraphicsLayer* rv_native_texture_layer(WebCore::Element* element, WebCore::FloatRect* rect)
{
    auto* box = dynamicDowncast<WebCore::RenderBox>(static_cast<WebCore::Node&>(*element).renderer());
    auto* backing = box && box->layer() ? box->layer()->backing() : nullptr;
    auto* layer = backing ? backing->graphicsLayer() : nullptr;
    if (layer) {
        *rect = WebCore::FloatRect { box->contentBoxRect() };
        rect->move(-layer->offsetFromRenderer());
    }
    return layer;
}

extern "C" WEBCORE_EXPORT void rv_native_texture_draw(WebCore::TextureMapper* mapper, unsigned texture,
    const WebCore::FloatRect* target, const WebCore::TransformationMatrix* matrix, float opacity)
{
    mapper->drawTexture(texture, WebCore::TextureMapperFlags::ShouldBlend, *target, *matrix, opacity);
}

extern "C" WEBCORE_EXPORT void rv_native_texture_draw_flipped(WebCore::TextureMapper* mapper, unsigned texture,
    const WebCore::FloatRect* target, const WebCore::TransformationMatrix* matrix, float opacity, bool flipY)
{
    OptionSet<WebCore::TextureMapperFlags> flags { WebCore::TextureMapperFlags::ShouldBlend };
    if (flipY)
        flags.add(WebCore::TextureMapperFlags::ShouldFlipTexture);
    mapper->drawTexture(texture, flags, *target, *matrix, opacity);
}
#endif
