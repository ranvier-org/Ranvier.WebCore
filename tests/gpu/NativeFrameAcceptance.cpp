#define RV_EXPORT
#include "../../host/RanvierWebCoreAbi.h"
#define NOMINMAX
#include <windows.h>
#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

// A string literal's UTF-8 bytes and byte count, for a length-delimited string input.
#define RV_TEXT(literal) reinterpret_cast<const uint8_t*>(literal), static_cast<int32_t>(sizeof(literal) - 1)
using Microsoft::WRL::ComPtr;
static void require(bool value, const char* reason) { if (!value) throw std::runtime_error(reason); }
static void hr(HRESULT result, const char* reason) { require(SUCCEEDED(result), reason); }
template<class T> T symbol(HMODULE module, const char* name) { auto value = GetProcAddress(module, name); require(value, name); return reinterpret_cast<T>(value); }
struct SDL_Window; struct SDL_Renderer; struct SDL_Texture;
struct SDL_FRect { float x, y, w, h; };
#define SDL_FN(result, name, ...) auto name = symbol<result (*)(__VA_ARGS__)>(sdl, #name)
#define NATIVE_FN(name) auto name = symbol<decltype(&::name)>(native, #name)
int main(int argc, char** argv) try {
    setvbuf(stdout, nullptr, _IONBF, 0);
    std::string mode = argc > 1 ? argv[1] : "explicit";
    auto native = LoadLibraryW(L"RanvierWebCoreHost.dll"); require(native, "native host DLL");
    NATIVE_FN(rv_abi_has); NATIVE_FN(rv_host_create); NATIVE_FN(rv_host_destroy); NATIVE_FN(rv_host_load_html);
    NATIVE_FN(rv_host_set_accelerated_compositing); NATIVE_FN(rv_host_acquire_d3d11_frame);
    NATIVE_FN(rv_gpu_frame_info); NATIVE_FN(rv_gpu_frame_release); NATIVE_FN(rv_host_resize);
    NATIVE_FN(rv_host_set_device_scale); NATIVE_FN(rv_host_paint_rgba);
    NATIVE_FN(rv_host_update);
    require(rv_abi_has("presentation-d3d11") == 1, "GPU presentation capability");
    auto sdl = LoadLibraryW(L"SDL3.dll"); require(sdl, "SDL3.dll");
    SDL_FN(bool, SDL_Init, unsigned); SDL_FN(void, SDL_Quit); SDL_FN(const char*, SDL_GetError);
    SDL_FN(SDL_Window*, SDL_CreateWindow, const char*, int, int, unsigned long long);
    SDL_FN(void, SDL_DestroyWindow, SDL_Window*); SDL_FN(SDL_Renderer*, SDL_CreateRenderer, SDL_Window*, const char*);
    SDL_FN(void, SDL_DestroyRenderer, SDL_Renderer*); SDL_FN(unsigned, SDL_GetRendererProperties, SDL_Renderer*);
    SDL_FN(void*, SDL_GetPointerProperty, unsigned, const char*, void*); SDL_FN(unsigned, SDL_CreateProperties);
    SDL_FN(void, SDL_DestroyProperties, unsigned); SDL_FN(bool, SDL_SetNumberProperty, unsigned, const char*, long long);
    SDL_FN(bool, SDL_SetPointerProperty, unsigned, const char*, void*);
    SDL_FN(SDL_Texture*, SDL_CreateTextureWithProperties, SDL_Renderer*, unsigned); SDL_FN(void, SDL_DestroyTexture, SDL_Texture*);
    SDL_FN(bool, SDL_SetTextureBlendMode, SDL_Texture*, unsigned);
    SDL_FN(bool, SDL_RenderTexture, SDL_Renderer*, SDL_Texture*, const SDL_FRect*, const SDL_FRect*);
    SDL_FN(bool, SDL_RenderPresent, SDL_Renderer*); SDL_FN(bool, SDL_FlushRenderer, SDL_Renderer*);
    SDL_FN(bool, SDL_SetRenderDrawColor, SDL_Renderer*, unsigned char, unsigned char, unsigned char, unsigned char);
    SDL_FN(bool, SDL_RenderClear, SDL_Renderer*); SDL_FN(void, SDL_PumpEvents);
    require(SDL_Init(0x20), SDL_GetError());
    auto window = SDL_CreateWindow("WebCore GPU frame acceptance", 320, 240, 0); require(window, SDL_GetError());
    auto renderer = SDL_CreateRenderer(window, "direct3d11"); require(renderer, SDL_GetError());
    auto properties = SDL_GetRendererProperties(renderer);
    auto device = static_cast<ID3D11Device*>(SDL_GetPointerProperty(properties, "SDL.renderer.d3d11.device", nullptr));
    auto swapchain = static_cast<IDXGISwapChain1*>(SDL_GetPointerProperty(properties, "SDL.renderer.d3d11.swap_chain", nullptr));
    require(device && swapchain, "SDL D3D11 properties");
    auto host = rv_host_create(64, 64); require(host, "host creation");
    require(rv_host_load_html(host, RV_TEXT("<style>html,body{margin:0;width:100%;height:100%;background:red}div{position:absolute;left:0;top:0;width:50%;height:50%;background:#00ff00;transform:translateZ(0)}</style><div id='green'></div>")) == RV_OK, "load content");
    RvGpuFrame* frame = reinterpret_cast<RvGpuFrame*>(1);
    require(rv_host_acquire_d3d11_frame(host, nullptr, &frame) == RV_ERR_NULL_ARGUMENT && !frame, "failed acquire output clearing");
    require(rv_host_set_accelerated_compositing(host, RV_COMPOSITING_ALWAYS) == RV_OK, "enable compositor");
    require(rv_host_update(host) == RV_OK, "initial rendering update");
    ComPtr<ID3D11Device> warp;
    hr(D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_WARP, nullptr, 0, nullptr, 0, D3D11_SDK_VERSION, &warp, nullptr, nullptr), "WARP incompatible consumer device");
    DWORD failureHandles = 0, afterFailureHandles = 0;
    for (int attempt = 0; attempt < 25; ++attempt) {
        frame = reinterpret_cast<RvGpuFrame*>(1);
        require(rv_host_acquire_d3d11_frame(host, warp.Get(), &frame) == RV_ERR_UNSUPPORTED && !frame, "cross-adapter acquire failure leaves no frame");
        if (!attempt) require(GetProcessHandleCount(GetCurrentProcess(), &failureHandles), "initial process handle count");
    }
    require(GetProcessHandleCount(GetCurrentProcess(), &afterFailureHandles), "final process handle count");
    std::printf("failed-device handles: %lu -> %lu\n", failureHandles, afterFailureHandles);
    require(afterFailureHandles <= failureHandles + 4, "failed cross-device acquisition leaked NT handles");
    warp.Reset();
    int wrongThread = RV_OK;
    std::thread thread([&] { RvGpuFrame* invalid = nullptr; wrongThread = rv_host_acquire_d3d11_frame(host, device, &invalid); }); thread.join();
    require(wrongThread == RV_ERR_WRONG_THREAD, "acquire owner thread");
    RvGpuFrame* retained = nullptr;
    for (int size : { 64, 128, 32 }) {
        require(rv_host_resize(host, size, size) == RV_OK, "host resize with old frame retained");
        require(rv_host_update(host) == RV_OK, "rendering update after resize");
        require(rv_host_acquire_d3d11_frame(host, device, &frame) == RV_OK && frame, "acquire WebCore GPU frame");
        if (retained) { require(rv_gpu_frame_release(retained) == RV_OK, "release prior-size frame"); retained = nullptr; }
        void* texture = nullptr; int width, height, format;
        require(rv_gpu_frame_info(frame, &texture, &width, &height, &format) == RV_OK && width == size && height == size && format == RV_GPU_RGBA8_PREMULTIPLIED, "frame metadata");
        int wrongInfoThread = RV_OK;
        std::thread wrongFrameThread([&] {
            void* invalidTexture = nullptr; int invalidWidth, invalidHeight, invalidFormat;
            wrongInfoThread = rv_gpu_frame_info(frame, &invalidTexture, &invalidWidth, &invalidHeight, &invalidFormat);
            wrongThread = rv_gpu_frame_release(frame);
        }); wrongFrameThread.join();
        require(wrongInfoThread == RV_ERR_WRONG_THREAD, "frame info owner thread");
        require(wrongThread == RV_ERR_WRONG_THREAD, "frame release owner thread leaves lease alive");
        RvGpuFrame* busy = reinterpret_cast<RvGpuFrame*>(1);
        require(rv_host_acquire_d3d11_frame(host, device, &busy) == RV_ERR_UNSUPPORTED && !busy, "double acquire bounded busy");
        auto props = SDL_CreateProperties(); SDL_SetNumberProperty(props, "SDL.texture.create.width", width);
        SDL_SetNumberProperty(props, "SDL.texture.create.height", height); SDL_SetNumberProperty(props, "SDL.texture.create.format", 0x16762004);
        SDL_SetPointerProperty(props, "SDL.texture.create.d3d11.texture", texture);
        auto wrapped = SDL_CreateTextureWithProperties(renderer, props); SDL_DestroyProperties(props); require(wrapped, SDL_GetError());
        require(SDL_SetTextureBlendMode(wrapped, 0x10), SDL_GetError()); // SDL_BLENDMODE_BLEND_PREMULTIPLIED.
        require(SDL_SetRenderDrawColor(renderer, 0, 0, 255, 255) && SDL_RenderClear(renderer), SDL_GetError());
        require(SDL_RenderTexture(renderer, wrapped, nullptr, nullptr) && SDL_FlushRenderer(renderer), SDL_GetError());
        ComPtr<ID3D11Texture2D> backbuffer; hr(swapchain->GetBuffer(0, IID_PPV_ARGS(&backbuffer)), "swapchain backbuffer");
        D3D11_TEXTURE2D_DESC desc; backbuffer->GetDesc(&desc); auto captureDesc = desc;
        captureDesc.BindFlags = 0; captureDesc.MiscFlags = 0; captureDesc.Usage = D3D11_USAGE_STAGING; captureDesc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
        ComPtr<ID3D11Texture2D> capture; hr(device->CreateTexture2D(&captureDesc, nullptr, &capture), "capture texture");
        ComPtr<ID3D11DeviceContext> context; device->GetImmediateContext(&context); context->CopyResource(capture.Get(), backbuffer.Get());
        D3D11_MAPPED_SUBRESOURCE map; hr(context->Map(capture.Get(), 0, D3D11_MAP_READ, 0, &map), "capture map");
        auto top = static_cast<unsigned char*>(map.pData) + 10 * map.RowPitch + 10 * 4;
        auto bottom = static_cast<unsigned char*>(map.pData) + (desc.Height - 10) * map.RowPitch + (desc.Width - 10) * 4;
        unsigned r = desc.Format == DXGI_FORMAT_B8G8R8A8_UNORM ? 2 : 0;
        bool correct = top[0] == 0 && top[1] == 255 && top[2] == 0 && bottom[r] == 255 && bottom[1] == 0 && bottom[2-r] == 0;
        if (!correct) std::printf("size=%d format=%d top=%u,%u,%u,%u bottom=%u,%u,%u,%u\n", size, desc.Format, top[0], top[1], top[2], top[3], bottom[0], bottom[1], bottom[2], bottom[3]);
        context->Unmap(capture.Get(), 0);
        require(correct, "WebCore page in SDL swapchain (orientation/colors)");
        require(SDL_RenderPresent(renderer), SDL_GetError()); SDL_DestroyTexture(wrapped); SDL_PumpEvents();
        // Exercise actual asynchronous reuse without the verification Map forcing GPU completion.
        for (int repeat = 0; repeat < 12; ++repeat) {
            require(rv_gpu_frame_release(frame) == RV_OK, "release reusable frame");
            require(rv_host_acquire_d3d11_frame(host, device, &frame) == RV_OK, "reacquire after GPU handoff");
            void* nextTexture = nullptr; int nextWidth, nextHeight, nextFormat;
            require(rv_gpu_frame_info(frame, &nextTexture, &nextWidth, &nextHeight, &nextFormat) == RV_OK && nextTexture == texture, "surface reused after frame release");
            auto reuseProps = SDL_CreateProperties();
            SDL_SetNumberProperty(reuseProps, "SDL.texture.create.width", width); SDL_SetNumberProperty(reuseProps, "SDL.texture.create.height", height);
            SDL_SetNumberProperty(reuseProps, "SDL.texture.create.format", 0x16762004); SDL_SetPointerProperty(reuseProps, "SDL.texture.create.d3d11.texture", nextTexture);
            auto reuse = SDL_CreateTextureWithProperties(renderer, reuseProps); SDL_DestroyProperties(reuseProps); require(reuse, SDL_GetError());
            require(SDL_SetTextureBlendMode(reuse, 0x10) && SDL_RenderTexture(renderer, reuse, nullptr, nullptr) && SDL_RenderPresent(renderer), SDL_GetError());
            SDL_DestroyTexture(reuse);
        }
        retained = frame; frame = nullptr;
        std::printf("PASS real WebCore GPU frame size=%d in SDL swapchain\n", size);
    }
    require(rv_host_set_device_scale(host, 2) == RV_OK, "set device scale");
    require(rv_host_update(host) == RV_OK, "rendering update after scale");
    require(rv_host_acquire_d3d11_frame(host, device, &frame) == RV_ERR_UNSUPPORTED && !frame, "nonunit scale fallback");
    std::vector<unsigned char> pixels(64 * 64 * 4);
    require(rv_host_paint_rgba(host, pixels.data(), static_cast<int>(pixels.size())) == RV_OK, "CPU fallback after GPU unsupported");
    std::printf("CPU fallback top=%u,%u,%u,%u\n",pixels[0],pixels[1],pixels[2],pixels[3]);
    require(pixels[0] == 0 && pixels[1] == 255 && pixels[2] == 0, "CPU fallback painted content");
    if (mode == "host") { rv_host_destroy(host); host = nullptr; }
    if (mode == "renderer" || mode == "window") { SDL_DestroyRenderer(renderer); renderer = nullptr; }
    if (mode == "window") { SDL_DestroyWindow(window); window = nullptr; }
    void* texture; int width, height, format;
    require(rv_gpu_frame_info(retained, &texture, &width, &height, &format) == RV_OK && texture && width == 32, "retained metadata through teardown");
    require(rv_gpu_frame_release(retained) == RV_OK, "release retained frame through teardown");
    if (host) rv_host_destroy(host);
    if (renderer) SDL_DestroyRenderer(renderer);
    if (window) SDL_DestroyWindow(window);
    SDL_Quit(); FreeLibrary(sdl); FreeLibrary(native);
    std::printf("PASS native GPU acceptance teardown=%s\n", mode.c_str()); return 0;
} catch (const std::exception& error) { std::fprintf(stderr, "FAIL %s\n", error.what()); return 1; }
