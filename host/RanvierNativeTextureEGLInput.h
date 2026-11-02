#pragma once
#if defined(__linux__) && RANVIER_COMPOSITING
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <WebCore/TextureMapperPlatformLayer.h>
#include "RanvierWebCoreEGL.h"

extern "C" WEBCORE_EXPORT void rv_native_texture_draw_flipped(WebCore::TextureMapper*, unsigned,
    const WebCore::FloatRect*, const WebCore::TransformationMatrix*, float, bool);
extern "C" WEBCORE_EXPORT WebCore::GraphicsLayer* rv_native_texture_layer(WebCore::Element*, WebCore::FloatRect*);

struct RvNativeEGLTextureInput final : WebCore::TextureMapperPlatformLayer {
    RefPtr<WebCore::Element> element;
    WeakPtr<WebCore::GraphicsLayer> layer;
    bool (*makeCurrent)() { nullptr };
    GLuint texture { 0 };
    bool locked { false };
    bool flipY { false };

    static std::unique_ptr<RvNativeEGLTextureInput> create(WebCore::Element& element, EGLImageKHR image, bool flipY, bool (*makeCurrent)())
    {
        if (!image || !makeCurrent())
            return nullptr;
        auto target = reinterpret_cast<PFNGLEGLIMAGETARGETTEXTURE2DOESPROC>(eglGetProcAddress("glEGLImageTargetTexture2DOES"));
        if (!target || glGetError() != GL_NO_ERROR)
            return nullptr;
        auto input = std::make_unique<RvNativeEGLTextureInput>();
        input->element = &element;
        input->makeCurrent = makeCurrent;
        input->flipY = flipY;
        glGenTextures(1, &input->texture);
        glBindTexture(GL_TEXTURE_2D, input->texture);
        target(GL_TEXTURE_2D, image);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glBindTexture(GL_TEXTURE_2D, 0);
        if (glGetError() != GL_NO_ERROR)
            return nullptr;
        return input;
    }

    void detach()
    {
        if (layer) {
            layer->setContentsToPlatformLayer(nullptr, WebCore::GraphicsLayer::ContentsLayerPurpose::None);
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
        layer->setContentsToPlatformLayer(this, WebCore::GraphicsLayer::ContentsLayerPurpose::Canvas);
        layer->setContentsRect(rect);
        layer->setContentsClippingRect(WebCore::FloatRoundedRect { rect });
        layer->flushCompositingStateForThisLayerOnly();
        return true;
    }

    bool begin()
    {
        locked = glGetError() == GL_NO_ERROR;
        return locked;
    }

    void end()
    {
        if (locked) {
            glFinish();
            locked = false;
        }
    }

    void paintToTextureMapper(WebCore::TextureMapper& mapper, const WebCore::FloatRect& rect,
        const WebCore::TransformationMatrix& matrix, float opacity) final
    {
        if (locked)
            rv_native_texture_draw_flipped(&mapper, texture, &rect, &matrix, opacity, flipY);
    }

    ~RvNativeEGLTextureInput()
    {
        detach();
        RvEGLContextScope contextScope;
        if (makeCurrent && makeCurrent()) {
            end();
            glDeleteTextures(1, &texture);
        }
    }
};
#endif
