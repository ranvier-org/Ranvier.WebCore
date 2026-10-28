#include "RanvierWebCoreD3D11.h"
#if defined(_WIN32) && RANVIER_COMPOSITING
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <EGL/eglext_angle.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
using Microsoft::WRL::ComPtr;

struct RvD3D11Surface::State {
    ComPtr<ID3D11Device> producerDevice;
    ComPtr<ID3D11Device> consumerDevice;
    ComPtr<ID3D11DeviceContext> consumerContext;
    ComPtr<ID3D11Texture2D> producerTexture;
    ComPtr<ID3D11Texture2D> consumerTexture;
    ComPtr<IDXGIKeyedMutex> producerMutex;
    ComPtr<IDXGIKeyedMutex> consumerMutex;
    EGLDisplay display { EGL_NO_DISPLAY };
    EGLImageKHR image { EGL_NO_IMAGE_KHR };
    PFNEGLDESTROYIMAGEKHRPROC destroyImage { nullptr };
    bool (*makeCurrent)() { nullptr };
    GLuint texture { 0 };
    GLuint framebuffer { 0 };
    GLuint depthStencil { 0 };
    int width { 0 };
    int height { 0 };
    enum class Owner { None, Producer, Consumer, Failed } owner { Owner::None };

    ~State()
    {
        if (owner == Owner::Producer)
            producerMutex->ReleaseSync(0);
        if (owner == Owner::Consumer) {
            consumerContext->Flush();
            consumerMutex->ReleaseSync(0);
        }
        if (makeCurrent && makeCurrent()) {
            glDeleteFramebuffers(1, &framebuffer);
            glDeleteRenderbuffers(1, &depthStencil);
            glDeleteTextures(1, &texture);
            if (image != EGL_NO_IMAGE_KHR)
                destroyImage(display, image);
        }
        // D3D11 defers resource destruction until Flush, including a shared texture whose open failed.
        // Drop every resource interface first; otherwise repeated failed acquires retain kernel handles.
        consumerMutex.Reset();
        producerMutex.Reset();
        consumerTexture.Reset();
        producerTexture.Reset();
        if (producerDevice) {
            ComPtr<ID3D11DeviceContext> producerContext;
            producerDevice->GetImmediateContext(&producerContext);
            producerContext->Flush();
        }
    }
};

RvD3D11Surface::RvD3D11Surface(std::unique_ptr<State> state)
    : state(std::move(state)) { }
RvD3D11Surface::~RvD3D11Surface() = default;

std::shared_ptr<RvD3D11Surface> RvD3D11Surface::create(void* consumer, int width, int height, bool (*makeCurrent)())
{
    if (!consumer || width <= 0 || height <= 0 || !makeCurrent || !makeCurrent())
        return nullptr;
    auto state = std::make_unique<State>();
    state->makeCurrent = makeCurrent;
    state->display = eglGetCurrentDisplay();
    auto queryDisplay = reinterpret_cast<PFNEGLQUERYDISPLAYATTRIBEXTPROC>(eglGetProcAddress("eglQueryDisplayAttribEXT"));
    auto queryDevice = reinterpret_cast<PFNEGLQUERYDEVICEATTRIBEXTPROC>(eglGetProcAddress("eglQueryDeviceAttribEXT"));
    auto createImage = reinterpret_cast<PFNEGLCREATEIMAGEKHRPROC>(eglGetProcAddress("eglCreateImageKHR"));
    auto imageTarget = reinterpret_cast<PFNGLEGLIMAGETARGETTEXTURE2DOESPROC>(eglGetProcAddress("glEGLImageTargetTexture2DOES"));
    state->destroyImage = reinterpret_cast<PFNEGLDESTROYIMAGEKHRPROC>(eglGetProcAddress("eglDestroyImageKHR"));
    if (!queryDisplay || !queryDevice || !createImage || !imageTarget || !state->destroyImage)
        return nullptr;
    EGLAttrib eglDevice, producer;
    if (!queryDisplay(state->display, EGL_DEVICE_EXT, &eglDevice)
        || !queryDevice(reinterpret_cast<EGLDeviceEXT>(eglDevice), EGL_D3D11_DEVICE_ANGLE, &producer))
        return nullptr;
    state->producerDevice = reinterpret_cast<ID3D11Device*>(producer);
    // The ABI accepts an actual ID3D11Device COM interface, not an arbitrary address.
    state->consumerDevice = static_cast<ID3D11Device*>(consumer);
    ComPtr<ID3D11Device1> consumer1;
    if (FAILED(state->consumerDevice.As(&consumer1)))
        return nullptr;
    state->consumerDevice->GetImmediateContext(&state->consumerContext);
    D3D11_TEXTURE2D_DESC desc = { };
    desc.Width = width; desc.Height = height; desc.MipLevels = 1; desc.ArraySize = 1;
    desc.Format = DXGI_FORMAT_R8G8B8A8_UNORM; desc.SampleDesc.Count = 1;
    desc.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
    desc.MiscFlags = D3D11_RESOURCE_MISC_SHARED_NTHANDLE | D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX;
    if (FAILED(state->producerDevice->CreateTexture2D(&desc, nullptr, &state->producerTexture)))
        return nullptr;
    ComPtr<IDXGIResource1> resource;
    if (FAILED(state->producerTexture.As(&resource)))
        return nullptr;
    HANDLE handle = nullptr;
    if (FAILED(resource->CreateSharedHandle(nullptr, DXGI_SHARED_RESOURCE_READ | DXGI_SHARED_RESOURCE_WRITE, nullptr, &handle)))
        return nullptr;
    HRESULT opened = consumer1->OpenSharedResource1(handle, IID_PPV_ARGS(&state->consumerTexture));
    CloseHandle(handle);
    if (FAILED(opened) || FAILED(state->producerTexture.As(&state->producerMutex)) || FAILED(state->consumerTexture.As(&state->consumerMutex)))
        return nullptr;
    state->image = createImage(state->display, EGL_NO_CONTEXT, EGL_D3D11_TEXTURE_ANGLE, state->producerTexture.Get(), nullptr);
    if (state->image == EGL_NO_IMAGE_KHR)
        return nullptr;
    glGenTextures(1, &state->texture);
    glBindTexture(GL_TEXTURE_2D, state->texture);
    imageTarget(GL_TEXTURE_2D, state->image);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glGenRenderbuffers(1, &state->depthStencil);
    glBindRenderbuffer(GL_RENDERBUFFER, state->depthStencil);
    glRenderbufferStorage(GL_RENDERBUFFER, 0x88F0 /* GL_DEPTH24_STENCIL8_OES */, width, height);
    glGenFramebuffers(1, &state->framebuffer);
    glBindFramebuffer(GL_FRAMEBUFFER, state->framebuffer);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, state->texture, 0);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, state->depthStencil);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_STENCIL_ATTACHMENT, GL_RENDERBUFFER, state->depthStencil);
    bool complete = glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE && glGetError() == GL_NO_ERROR;
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glBindTexture(GL_TEXTURE_2D, 0);
    if (!complete)
        return nullptr;
    state->width = width; state->height = height;
    return std::shared_ptr<RvD3D11Surface>(new RvD3D11Surface(std::move(state)));
}

bool RvD3D11Surface::matches(void* device, int width, int height) const
{
    return state->consumerDevice.Get() == device && state->width == width && state->height == height;
}
bool RvD3D11Surface::available() const { return state->owner == State::Owner::None; }
bool RvD3D11Surface::beginProducer()
{
    if (!available() || !state->makeCurrent())
        return false;
    // No outstanding frame may stall the UI thread: a failed/stale GPU handoff is recoverable.
    if (state->producerMutex->AcquireSync(0, 16) != S_OK) {
        state->owner = State::Owner::Failed;
        return false;
    }
    state->owner = State::Owner::Producer;
    return true;
}
bool RvD3D11Surface::finishProducer()
{
    if (state->owner != State::Owner::Producer)
        return false;
    glFlush();
    if (glGetError() != GL_NO_ERROR) {
        cancelProducer();
        return false;
    }
    HRESULT released = state->producerMutex->ReleaseSync(1);
    state->owner = State::Owner::Failed;
    if (FAILED(released) || state->consumerMutex->AcquireSync(1, 16) != S_OK)
        return false;
    state->owner = State::Owner::Consumer;
    return true;
}
void RvD3D11Surface::cancelProducer()
{
    if (state->owner == State::Owner::Producer) {
        glFlush();
        state->owner = SUCCEEDED(state->producerMutex->ReleaseSync(0)) ? State::Owner::None : State::Owner::Failed;
    }
}
bool RvD3D11Surface::releaseConsumer()
{
    if (state->owner != State::Owner::Consumer)
        return false;
    state->consumerContext->Flush();
    state->owner = SUCCEEDED(state->consumerMutex->ReleaseSync(0)) ? State::Owner::None : State::Owner::Failed;
    return state->owner == State::Owner::None;
}
unsigned RvD3D11Surface::framebuffer() const { return state->framebuffer; }
void* RvD3D11Surface::texture() const { return state->consumerTexture.Get(); }
int RvD3D11Surface::width() const { return state->width; }
int RvD3D11Surface::height() const { return state->height; }
#endif
