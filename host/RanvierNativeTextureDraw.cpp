#include "config.h"
#if RANVIER_COMPOSITING
#include "TextureMapper.h"
#include "TextureMapperFlags.h"
#include "Element.h"
#include "RenderBox.h"
#include "RenderBoxInlines.h"
#include "RenderLayer.h"
#include "RenderLayerBacking.h"
#if defined(RANVIER_MAC_GPU_SPIKE) && RANVIER_MAC_GPU_SPIKE
#include "GraphicsLayerTextureMapper.h"
#endif

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

#if defined(RANVIER_MAC_GPU_SPIKE) && RANVIER_MAC_GPU_SPIKE
extern "C" WEBCORE_EXPORT void rv_native_texture_set_mac_contents(WebCore::GraphicsLayer* layer, WebCore::TextureMapperPlatformLayer* contents)
{
    downcast<WebCore::GraphicsLayerTextureMapper>(*layer).setTextureMapperContents(contents,
        contents ? WebCore::GraphicsLayer::ContentsLayerPurpose::Canvas : WebCore::GraphicsLayer::ContentsLayerPurpose::None);
}
#endif

extern "C" WEBCORE_EXPORT void rv_native_texture_draw_flipped(WebCore::TextureMapper* mapper, unsigned texture,
    const WebCore::FloatRect* target, const WebCore::TransformationMatrix* matrix, float opacity, bool flipY)
{
    OptionSet<WebCore::TextureMapperFlags> flags { WebCore::TextureMapperFlags::ShouldBlend };
    if (flipY)
        flags.add(WebCore::TextureMapperFlags::ShouldFlipTexture);
    mapper->drawTexture(texture, flags, *target, *matrix, opacity);
}
#endif
