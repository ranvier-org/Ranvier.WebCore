#pragma once
#include "RanvierGpuRetirement.h"
#if defined(_WIN32) && RANVIER_COMPOSITING
#include <windows.h>
#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <EGL/eglext_angle.h>
#include <WebCore/TextureMapperPlatformLayer.h>

extern "C" __declspec(dllimport) void rv_native_texture_draw(WebCore::TextureMapper*, unsigned,
    const WebCore::FloatRect*, const WebCore::TransformationMatrix*, float);
extern "C" __declspec(dllimport) WebCore::GraphicsLayer* rv_native_texture_layer(WebCore::Element*, WebCore::FloatRect*);

struct RvNativeTextureInput final : WebCore::TextureMapperPlatformLayer {
    template<class T> using ComPtr = Microsoft::WRL::ComPtr<T>;
    RefPtr<WebCore::Element> element;
    WeakPtr<WebCore::GraphicsLayer> layer;
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
    ComPtr<ID3D11Texture2D> cachedTexture;
    EGLImageKHR cachedImage { EGL_NO_IMAGE_KHR };
    GLuint cachedGlTexture { 0 };
    size_t cachedBytes { 0 };
    bool cachedValid { false };
    bool usingCache { false };

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

    bool begin(bool nonblocking = false)
    {
        usingCache = nonblocking;
        if (nonblocking)
            return beginCached();
        if (!healthy() || mutex->AcquireSync(1, 16) != S_OK)
            return false;
        locked = true;
        return true;
    }

    bool beginCached()
    {
        if (!healthy())
            return false;
        if (!cachedTexture) {
            RvGpuRetirement::collect();
            D3D11_TEXTURE2D_DESC desc { };
            openedTexture->GetDesc(&desc);
            cachedBytes = RvGpuMemoryBudget::acquire(desc.Width, desc.Height, 4);
            if (!cachedBytes)
                return false;
            desc.MiscFlags = 0;
            if (FAILED(compositorDevice->CreateTexture2D(&desc, nullptr, &cachedTexture))) {
                failed = true;
                return false;
            }
            auto createImage = reinterpret_cast<PFNEGLCREATEIMAGEKHRPROC>(eglGetProcAddress("eglCreateImageKHR"));
            auto imageTarget = reinterpret_cast<PFNGLEGLIMAGETARGETTEXTURE2DOESPROC>(eglGetProcAddress("glEGLImageTargetTexture2DOES"));
            cachedImage = createImage(display, EGL_NO_CONTEXT, EGL_D3D11_TEXTURE_ANGLE, cachedTexture.Get(), nullptr);
            if (cachedImage == EGL_NO_IMAGE_KHR) {
                failed = true;
                return false;
            }
            glGenTextures(1, &cachedGlTexture);
            glBindTexture(GL_TEXTURE_2D, cachedGlTexture);
            imageTarget(GL_TEXTURE_2D, cachedImage);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
            glBindTexture(GL_TEXTURE_2D, 0);
            if (glGetError() != GL_NO_ERROR) {
                failed = true;
                return false;
            }
        }
        auto acquired = mutex->AcquireSync(1, 0);
        if (acquired == WAIT_TIMEOUT)
            return cachedValid;
        if (acquired != S_OK) {
            failed = true;
            return false;
        }
        // The owned shared image is copied on ANGLE's device. Future paints sample only this cache.
        glFlush();
        ComPtr<ID3D11DeviceContext> context;
        compositorDevice->GetImmediateContext(&context);
        context->CopyResource(cachedTexture.Get(), openedTexture.Get());
        context->Flush();
        failed = FAILED(mutex->ReleaseSync(0));
        cachedValid = !failed;
        return cachedValid;
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
        if (usingCache ? cachedValid : locked)
            rv_native_texture_draw(&mapper, usingCache ? cachedGlTexture : texture, &rect, &matrix, opacity);
    }

    ~RvNativeTextureInput()
    {
        detach();
        if (makeCurrent && makeCurrent()) {
            end();
            glDeleteTextures(1, &texture);
            glDeleteTextures(1, &cachedGlTexture);
            if (image != EGL_NO_IMAGE_KHR)
                destroyImage(display, image);
            if (cachedImage != EGL_NO_IMAGE_KHR)
                destroyImage(display, cachedImage);
            glFlush();
        }
        RvGpuRetirement::retire(cachedBytes, compositorDevice.Get(), cachedTexture.Get());
        cachedTexture.Reset();
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
