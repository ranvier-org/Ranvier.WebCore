#pragma once
#if defined(_WIN32) && RANVIER_COMPOSITING
#include <windows.h>
#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <EGL/eglext_angle.h>
#include "RenderBox.h"
#include "RenderBoxInlines.h"
#include "RenderLayer.h"
#include "RenderLayerBacking.h"
#include "TextureMapperPlatformLayer.h"

extern "C" __declspec(dllimport) void rv_native_texture_draw(WebCore::TextureMapper*, unsigned,
    const WebCore::FloatRect*, const WebCore::TransformationMatrix*, float);

struct RvNativeTextureInput final : WebCore::TextureMapperPlatformLayer {
    template<class T> using ComPtr = Microsoft::WRL::ComPtr<T>;
    RefPtr<WebCore::Element> element;
    RefPtr<WebCore::GraphicsLayer> layer;
    ComPtr<ID3D11Device> producerDevice;
    ComPtr<ID3D11Device> compositorDevice;
    ComPtr<ID3D11Texture2D> producerTexture;
    ComPtr<ID3D11Texture2D> openedTexture;
    ComPtr<IDXGIKeyedMutex> mutex;
    EGLDisplay display { EGL_NO_DISPLAY };
    EGLImageKHR image { EGL_NO_IMAGE_KHR };
    PFNEGLDESTROYIMAGEKHRPROC destroyImage { nullptr };
    bool (*makeCurrent)() { nullptr };
    GLuint texture { 0 };
    bool locked { false };
    bool failed { false };

    bool healthy() const
    {
        return !failed && producerDevice->GetDeviceRemovedReason() == S_OK
            && compositorDevice->GetDeviceRemovedReason() == S_OK;
    }

    static std::unique_ptr<RvNativeTextureInput> create(WebCore::Element& element, void* pointer, bool (*makeCurrent)())
    {
        if (!pointer || !makeCurrent())
            return nullptr;
        auto input = std::make_unique<RvNativeTextureInput>();
        input->element = &element;
        input->makeCurrent = makeCurrent;
        input->producerTexture = static_cast<ID3D11Texture2D*>(pointer);
        D3D11_TEXTURE2D_DESC desc { };
        input->producerTexture->GetDesc(&desc);
        if (!desc.Width || !desc.Height || desc.Format != DXGI_FORMAT_R8G8B8A8_UNORM
            || desc.MipLevels != 1 || desc.ArraySize != 1 || desc.SampleDesc.Count != 1
            || !(desc.MiscFlags & D3D11_RESOURCE_MISC_SHARED_NTHANDLE)
            || !(desc.MiscFlags & D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX))
            return nullptr;
        input->producerTexture->GetDevice(&input->producerDevice);
        input->display = eglGetCurrentDisplay();
        auto queryDisplay = reinterpret_cast<PFNEGLQUERYDISPLAYATTRIBEXTPROC>(eglGetProcAddress("eglQueryDisplayAttribEXT"));
        auto queryDevice = reinterpret_cast<PFNEGLQUERYDEVICEATTRIBEXTPROC>(eglGetProcAddress("eglQueryDeviceAttribEXT"));
        auto createImage = reinterpret_cast<PFNEGLCREATEIMAGEKHRPROC>(eglGetProcAddress("eglCreateImageKHR"));
        auto imageTarget = reinterpret_cast<PFNGLEGLIMAGETARGETTEXTURE2DOESPROC>(eglGetProcAddress("glEGLImageTargetTexture2DOES"));
        input->destroyImage = reinterpret_cast<PFNEGLDESTROYIMAGEKHRPROC>(eglGetProcAddress("eglDestroyImageKHR"));
        if (!queryDisplay || !queryDevice || !createImage || !imageTarget || !input->destroyImage)
            return nullptr;
        EGLAttrib device = 0, d3d = 0;
        if (!queryDisplay(input->display, EGL_DEVICE_EXT, &device)
            || !queryDevice(reinterpret_cast<EGLDeviceEXT>(device), EGL_D3D11_DEVICE_ANGLE, &d3d) || !d3d)
            return nullptr;
        input->compositorDevice = reinterpret_cast<ID3D11Device*>(d3d);
        if (!input->healthy())
            return nullptr;
        ComPtr<IDXGIResource1> resource;
        ComPtr<ID3D11Device1> compositor1;
        if (FAILED(input->producerTexture.As(&resource)) || FAILED(input->compositorDevice.As(&compositor1)))
            return nullptr;
        HANDLE handle = nullptr;
        if (FAILED(resource->CreateSharedHandle(nullptr, DXGI_SHARED_RESOURCE_READ | DXGI_SHARED_RESOURCE_WRITE, nullptr, &handle)))
            return nullptr;
        auto result = compositor1->OpenSharedResource1(handle, IID_PPV_ARGS(&input->openedTexture));
        CloseHandle(handle);
        if (FAILED(result) || FAILED(input->openedTexture.As(&input->mutex)))
            return nullptr;
        input->image = createImage(input->display, EGL_NO_CONTEXT, EGL_D3D11_TEXTURE_ANGLE, input->openedTexture.Get(), nullptr);
        if (input->image == EGL_NO_IMAGE_KHR)
            return nullptr;
        glGenTextures(1, &input->texture);
        glBindTexture(GL_TEXTURE_2D, input->texture);
        imageTarget(GL_TEXTURE_2D, input->image);
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
        auto* box = dynamicDowncast<WebCore::RenderBox>(element->renderer());
        auto* backing = box && box->layer() ? box->layer()->backing() : nullptr;
        auto* current = backing ? backing->graphicsLayer() : nullptr;
        if (current != layer.get()) {
            detach();
            layer = current;
        }
        if (!layer)
            return false;
        auto rect = WebCore::FloatRect { box->contentBoxRect() };
        rect.move(-layer->offsetFromRenderer());
        layer->setContentsToPlatformLayer(this, WebCore::GraphicsLayer::ContentsLayerPurpose::Canvas);
        layer->setContentsRect(rect);
        layer->setContentsClippingRect(WebCore::FloatRoundedRect { rect });
        layer->flushCompositingStateForThisLayerOnly();
        return true;
    }

    bool begin()
    {
        if (!healthy() || mutex->AcquireSync(1, 16) != S_OK)
            return false;
        locked = true;
        return true;
    }

    void end()
    {
        if (locked) {
            glFlush();
            failed = FAILED(mutex->ReleaseSync(0));
            locked = false;
        }
    }

    void paintToTextureMapper(WebCore::TextureMapper& mapper, const WebCore::FloatRect& rect,
        const WebCore::TransformationMatrix& matrix, float opacity) final
    {
        if (locked)
            rv_native_texture_draw(&mapper, texture, &rect, &matrix, opacity);
    }

    ~RvNativeTextureInput()
    {
        detach();
        if (makeCurrent && makeCurrent()) {
            end();
            glDeleteTextures(1, &texture);
            if (image != EGL_NO_IMAGE_KHR)
                destroyImage(display, image);
        }
        openedTexture.Reset();
        mutex.Reset();
        if (compositorDevice) {
            ComPtr<ID3D11DeviceContext> context;
            compositorDevice->GetImmediateContext(&context);
            context->Flush();
        }
    }
};
#endif
