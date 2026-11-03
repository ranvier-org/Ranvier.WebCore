#pragma once
#if defined(RANVIER_MAC_GPU_SPIKE) && RANVIER_MAC_GPU_SPIKE && RANVIER_COMPOSITING
#include "RanvierMacGpuSpike.h"
#include <WebCore/TextureMapperPlatformLayer.h>

extern "C" WEBCORE_EXPORT void rv_native_texture_draw_flipped(WebCore::TextureMapper*, unsigned,
    const WebCore::FloatRect*, const WebCore::TransformationMatrix*, float, bool);
extern "C" WEBCORE_EXPORT WebCore::GraphicsLayer* rv_native_texture_layer(WebCore::Element*, WebCore::FloatRect*);
extern "C" WEBCORE_EXPORT void rv_native_texture_set_mac_contents(WebCore::GraphicsLayer*, WebCore::TextureMapperPlatformLayer*);

struct RvNativeMacTextureInput final : WebCore::TextureMapperPlatformLayer {
    RefPtr<WebCore::Element> element;
    WeakPtr<WebCore::GraphicsLayer> layer;
    std::unique_ptr<RvMacSpikeInputSurface> surface;
    bool flipY { false };
    bool locked { false };
    bool failed { false };

    static std::unique_ptr<RvNativeMacTextureInput> create(WebCore::Element& element, void* pointer, bool flipY, bool (*makeCurrent)())
    {
        auto surface = RvMacSpikeInputSurface::create(pointer, makeCurrent);
        if (!surface)
            return nullptr;
        auto input = std::make_unique<RvNativeMacTextureInput>();
        input->element = &element;
        input->surface = WTF::move(surface);
        input->flipY = flipY;
        return input;
    }

    void detach()
    {
        if (layer) {
            rv_native_texture_set_mac_contents(layer.get(), nullptr);
            layer = nullptr;
        }
    }

    bool attach()
    {
        WebCore::FloatRect rect;
        auto* current = rv_native_texture_layer(element.get(), &rect);
        if (current != layer.get()) {
            detach();
            layer = current;
        }
        if (!layer)
            return false;
        rv_native_texture_set_mac_contents(layer.get(), this);
        layer->setContentsRect(rect);
        layer->setContentsClippingRect(WebCore::FloatRoundedRect { rect });
        layer->flushCompositingStateForThisLayerOnly();
        return true;
    }

    bool begin()
    {
        locked = !failed && surface->begin();
        failed |= !locked;
        return locked;
    }

    void end()
    {
        if (locked) {
            failed |= !surface->end();
            locked = false;
        }
    }

    void paintToTextureMapper(WebCore::TextureMapper& mapper, const WebCore::FloatRect& rect,
        const WebCore::TransformationMatrix& matrix, float opacity) final
    {
        if (locked)
            rv_native_texture_draw_flipped(&mapper, surface->texture(), &rect, &matrix, opacity, flipY);
    }

    ~RvNativeMacTextureInput()
    {
        detach();
        end();
    }
};
#endif
