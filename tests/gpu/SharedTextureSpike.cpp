#include <windows.h>
#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <EGL/eglext_angle.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <cstdio>
#include <stdexcept>
#include <string>
using Microsoft::WRL::ComPtr;
static void require(bool ok, const char* what) { if (!ok) throw std::runtime_error(what); }
static void hr(HRESULT result, const char* what) { if (FAILED(result)) { char b[200]; sprintf_s(b, "%s HRESULT=%08lx", what, result); throw std::runtime_error(b); } }
struct SDL_Window;
struct SDL_Renderer;
struct SDL_Texture;
struct SDL_FRect { float x, y, w, h; };
template<class T> T symbol(HMODULE module, const char* name) { auto p = GetProcAddress(module, name); require(p, name); return reinterpret_cast<T>(p); }
#define SDL_FN(result, name, ...) auto name = symbol<result (*)(__VA_ARGS__)>(sdl, #name)
int main() try {
    setvbuf(stdout, nullptr, _IONBF, 0);
    auto sdl = LoadLibraryW(L"SDL3.dll"); require(sdl, "SDL3.dll");
    SDL_FN(bool, SDL_Init, unsigned);
    SDL_FN(void, SDL_Quit);
    SDL_FN(const char*, SDL_GetError);
    SDL_FN(SDL_Window*, SDL_CreateWindow, const char*, int, int, unsigned long long);
    SDL_FN(void, SDL_DestroyWindow, SDL_Window*);
    SDL_FN(SDL_Renderer*, SDL_CreateRenderer, SDL_Window*, const char*);
    SDL_FN(void, SDL_DestroyRenderer, SDL_Renderer*);
    SDL_FN(unsigned, SDL_GetRendererProperties, SDL_Renderer*);
    SDL_FN(void*, SDL_GetPointerProperty, unsigned, const char*, void*);
    SDL_FN(unsigned, SDL_CreateProperties);
    SDL_FN(void, SDL_DestroyProperties, unsigned);
    SDL_FN(bool, SDL_SetNumberProperty, unsigned, const char*, long long);
    SDL_FN(bool, SDL_SetPointerProperty, unsigned, const char*, void*);
    SDL_FN(SDL_Texture*, SDL_CreateTextureWithProperties, SDL_Renderer*, unsigned);
    SDL_FN(void, SDL_DestroyTexture, SDL_Texture*);
    SDL_FN(bool, SDL_SetTextureBlendMode, SDL_Texture*, int);
    SDL_FN(bool, SDL_RenderTexture, SDL_Renderer*, SDL_Texture*, const SDL_FRect*, const SDL_FRect*);
    SDL_FN(bool, SDL_RenderPresent, SDL_Renderer*);
    SDL_FN(bool, SDL_FlushRenderer, SDL_Renderer*);
    SDL_FN(bool, SDL_SetRenderDrawColor, SDL_Renderer*, unsigned char, unsigned char, unsigned char, unsigned char);
    SDL_FN(bool, SDL_RenderClear, SDL_Renderer*);
    SDL_FN(void, SDL_PumpEvents);
    require(SDL_Init(0x20), SDL_GetError());
    auto window = SDL_CreateWindow("ANGLE shared D3D11 texture feasibility", 320, 240, 0);
    require(window, SDL_GetError());
    auto renderer = SDL_CreateRenderer(window, "direct3d11"); require(renderer, SDL_GetError());
    auto consumer = static_cast<ID3D11Device*>(SDL_GetPointerProperty(SDL_GetRendererProperties(renderer), "SDL.renderer.d3d11.device", nullptr));
    require(consumer, "SDL D3D11 device");
    auto swapchain = static_cast<IDXGISwapChain1*>(SDL_GetPointerProperty(SDL_GetRendererProperties(renderer), "SDL.renderer.d3d11.swap_chain", nullptr));
    require(swapchain, "SDL D3D11 swapchain");
    ComPtr<ID3D11Device1> consumer1; hr(consumer->QueryInterface(IID_PPV_ARGS(&consumer1)), "consumer device1");
    ComPtr<ID3D11DeviceContext> consumerContext; consumer->GetImmediateContext(&consumerContext);
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    EGLint major, minor; require(eglInitialize(display, &major, &minor), "eglInitialize");
    std::printf("EGL %d.%d %s\n", major, minor, eglQueryString(display, EGL_VENDOR));
    auto queryDisplay = reinterpret_cast<PFNEGLQUERYDISPLAYATTRIBEXTPROC>(eglGetProcAddress("eglQueryDisplayAttribEXT"));
    auto queryDevice = reinterpret_cast<PFNEGLQUERYDEVICEATTRIBEXTPROC>(eglGetProcAddress("eglQueryDeviceAttribEXT"));
    require(queryDisplay && queryDevice, "EGL device query entrypoints");
    EGLAttrib device, d3dDevice; require(queryDisplay(display, EGL_DEVICE_EXT, &device), "EGL device query");
    require(queryDevice(reinterpret_cast<EGLDeviceEXT>(device), EGL_D3D11_DEVICE_ANGLE, &d3dDevice), "ANGLE D3D11 device query");
    auto producer = reinterpret_cast<ID3D11Device*>(d3dDevice);
    EGLint attributes[] = { EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE };
    EGLConfig config; EGLint count; require(eglChooseConfig(display, attributes, &config, 1, &count) && count, "eglChooseConfig");
    EGLint contextAttributes[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, contextAttributes); require(context != EGL_NO_CONTEXT, "eglCreateContext");
    EGLint pbufferAttributes[] = { EGL_WIDTH, 1, EGL_HEIGHT, 1, EGL_NONE };
    EGLSurface pbuffer = eglCreatePbufferSurface(display, config, pbufferAttributes); require(pbuffer != EGL_NO_SURFACE, "eglCreatePbufferSurface");
    require(eglMakeCurrent(display, pbuffer, pbuffer, context), "eglMakeCurrent");
    auto createImage = reinterpret_cast<PFNEGLCREATEIMAGEKHRPROC>(eglGetProcAddress("eglCreateImageKHR"));
    auto destroyImage = reinterpret_cast<PFNEGLDESTROYIMAGEKHRPROC>(eglGetProcAddress("eglDestroyImageKHR"));
    auto imageTarget = reinterpret_cast<PFNGLEGLIMAGETARGETTEXTURE2DOESPROC>(eglGetProcAddress("glEGLImageTargetTexture2DOES"));
    require(createImage && destroyImage && imageTarget, "EGLImage entrypoints");
    for (unsigned size : { 64u, 128u, 32u }) {
        D3D11_TEXTURE2D_DESC desc = {};
        desc.Width = size; desc.Height = size; desc.MipLevels = 1; desc.ArraySize = 1;
        desc.Format = DXGI_FORMAT_R8G8B8A8_UNORM; desc.SampleDesc.Count = 1;
        desc.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
        desc.MiscFlags = D3D11_RESOURCE_MISC_SHARED_NTHANDLE | D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX;
        ComPtr<ID3D11Texture2D> texture; hr(producer->CreateTexture2D(&desc, nullptr, &texture), "producer texture");
        ComPtr<IDXGIResource1> resource; hr(texture.As(&resource), "shared resource");
        HANDLE handle = nullptr; hr(resource->CreateSharedHandle(nullptr, DXGI_SHARED_RESOURCE_READ | DXGI_SHARED_RESOURCE_WRITE, nullptr, &handle), "NT shared handle");
        ComPtr<ID3D11Texture2D> opened;
        HRESULT openedResult = consumer1->OpenSharedResource1(handle, IID_PPV_ARGS(&opened)); CloseHandle(handle);
        hr(openedResult, "open on SDL device");
        ComPtr<IDXGIKeyedMutex> producerMutex, consumerMutex;
        hr(texture.As(&producerMutex), "producer mutex"); hr(opened.As(&consumerMutex), "consumer mutex");
        auto image = createImage(display, EGL_NO_CONTEXT, EGL_D3D11_TEXTURE_ANGLE, texture.Get(), nullptr);
        if (image == EGL_NO_IMAGE_KHR) { std::printf("egl error=%x\n", eglGetError()); throw std::runtime_error("D3D11 EGLImage import"); }
        GLuint glTexture, framebuffer; glGenTextures(1, &glTexture); glBindTexture(GL_TEXTURE_2D, glTexture);
        imageTarget(GL_TEXTURE_2D, image); require(glGetError() == GL_NO_ERROR, "EGLImage GL target");
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glGenFramebuffers(1, &framebuffer); glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, glTexture, 0);
        require(glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE, "shared framebuffer complete");
        std::puts("EGLImage framebuffer ready");
        auto props = SDL_CreateProperties();
        SDL_SetNumberProperty(props, "SDL.texture.create.width", size);
        SDL_SetNumberProperty(props, "SDL.texture.create.height", size);
        SDL_SetNumberProperty(props, "SDL.texture.create.format", 0x16762004); // ABGR8888: RGBA byte order on little endian.
        SDL_SetPointerProperty(props, "SDL.texture.create.d3d11.texture", opened.Get());
        auto wrapped = SDL_CreateTextureWithProperties(renderer, props); SDL_DestroyProperties(props);
        require(wrapped, SDL_GetError()); require(SDL_SetTextureBlendMode(wrapped, 0x10), SDL_GetError());
        std::puts("SDL imported texture ready");
        for (int frame = 0; frame < 6; ++frame) {
            require(producerMutex->AcquireSync(0, 1000) == S_OK, "producer AcquireSync");
            glBindFramebuffer(GL_FRAMEBUFFER, framebuffer); glViewport(0, 0, size, size);
            glDisable(GL_SCISSOR_TEST); glClearColor(1, 0, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
            glEnable(GL_SCISSOR_TEST); glScissor(0, 0, size / 2, size / 2);
            glClearColor(0, 0.5f, 0, 0.5f); glClear(GL_COLOR_BUFFER_BIT); glDisable(GL_SCISSOR_TEST);
            glFlush(); require(glGetError() == GL_NO_ERROR, "producer GL render");
            hr(producerMutex->ReleaseSync(1), "producer ReleaseSync");
            require(consumerMutex->AcquireSync(1, 1000) == S_OK, "consumer AcquireSync");
            require(SDL_SetRenderDrawColor(renderer, 0, 0, 255, 255) && SDL_RenderClear(renderer), SDL_GetError());
            require(SDL_RenderTexture(renderer, wrapped, nullptr, nullptr), SDL_GetError());
            require(SDL_FlushRenderer(renderer), SDL_GetError());
            ComPtr<ID3D11Texture2D> backbuffer; hr(swapchain->GetBuffer(0, IID_PPV_ARGS(&backbuffer)), "SDL swapchain buffer");
            D3D11_TEXTURE2D_DESC backbufferDesc; backbuffer->GetDesc(&backbufferDesc);
            auto captureDesc = backbufferDesc; captureDesc.BindFlags = 0; captureDesc.MiscFlags = 0;
            captureDesc.Usage = D3D11_USAGE_STAGING; captureDesc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
            ComPtr<ID3D11Texture2D> capture; hr(consumer->CreateTexture2D(&captureDesc, nullptr, &capture), "SDL capture texture");
            consumerContext->CopyResource(capture.Get(), backbuffer.Get());
            D3D11_MAPPED_SUBRESOURCE screen; hr(consumerContext->Map(capture.Get(), 0, D3D11_MAP_READ, 0, &screen), "SDL capture map");
            auto top = static_cast<unsigned char*>(screen.pData) + 10 * screen.RowPitch + 10 * 4;
            auto bottom = static_cast<unsigned char*>(screen.pData) + (backbufferDesc.Height - 10) * screen.RowPitch + (backbufferDesc.Width - 10) * 4;
            unsigned redIndex = backbufferDesc.Format == DXGI_FORMAT_B8G8R8A8_UNORM ? 2 : 0;
            bool screenGreen = top[redIndex] == 0 && top[1] >= 127 && top[1] <= 128 && top[2 - redIndex] == 255 - top[1];
            bool screenRed = bottom[redIndex] == 255 && bottom[1] == 0 && bottom[2 - redIndex] == 0;
            if (!screenGreen || !screenRed) std::printf("PMA screen top=%u,%u,%u,%u bottom=%u,%u,%u,%u format=%d\n",top[0],top[1],top[2],top[3],bottom[0],bottom[1],bottom[2],bottom[3],backbufferDesc.Format);
            consumerContext->Unmap(capture.Get(), 0);
            require(screenGreen && screenRed, "SDL swapchain quadrant orientation and content");
            require(SDL_RenderPresent(renderer), SDL_GetError());
            D3D11_TEXTURE2D_DESC stagingDesc = desc; stagingDesc.BindFlags = 0; stagingDesc.MiscFlags = 0;
            stagingDesc.Usage = D3D11_USAGE_STAGING; stagingDesc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
            ComPtr<ID3D11Texture2D> staging; hr(consumer->CreateTexture2D(&stagingDesc, nullptr, &staging), "verification staging");
            consumerContext->CopyResource(staging.Get(), opened.Get());
            D3D11_MAPPED_SUBRESOURCE map; hr(consumerContext->Map(staging.Get(), 0, D3D11_MAP_READ, 0, &map), "verification map");
            auto bytes = static_cast<unsigned char*>(map.pData);
            bool green = bytes[0] == 0 && bytes[1] >= 127 && bytes[1] <= 128 && bytes[2] == 0 && bytes[3] == bytes[1];
            auto opposite = bytes + (size - 1) * map.RowPitch + (size - 1) * 4;
            bool red = opposite[0] == 255 && opposite[1] == 0 && opposite[2] == 0 && opposite[3] == 255;
            consumerContext->Unmap(staging.Get(), 0); require(green && red, "shared texture quadrant content");
            consumerContext->Flush(); hr(consumerMutex->ReleaseSync(0), "consumer ReleaseSync");
            SDL_PumpEvents();
        }
        SDL_DestroyTexture(wrapped);
        glBindFramebuffer(GL_FRAMEBUFFER, 0); glDeleteFramebuffers(1, &framebuffer); glDeleteTextures(1, &glTexture); destroyImage(display, image);
        std::printf("PASS shared texture size=%u frames=6 NT handle closed, SDL present, GPU content verified\n", size);
    }
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroySurface(display, pbuffer); eglDestroyContext(display, context); eglTerminate(display);
    consumerContext.Reset(); consumer1.Reset();
    SDL_DestroyRenderer(renderer); SDL_DestroyWindow(window); SDL_Quit(); FreeLibrary(sdl);
    std::puts("PASS shared D3D11 transport and resize/teardown feasibility"); return 0;
} catch (const std::exception& error) { std::fprintf(stderr, "FAIL %s\n", error.what()); return 1; }
