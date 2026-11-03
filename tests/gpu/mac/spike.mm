#import <Foundation/Foundation.h>
#import <IOSurface/IOSurface.h>
#import <Metal/Metal.h>
#include <SDL3/SDL.h>
#include "RanvierMacGpuSpike.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>

namespace {
int assertions;
uint64_t presented;
std::string outputDirectory;

void require(bool value, const char* message)
{
    if (!value)
        throw std::runtime_error(std::string(message) + ": " + SDL_GetError());
    ++assertions;
}

struct Frame {
    RvMacSpikeFrame* value { nullptr };
    ~Frame() { if (value) rv_mac_spike_frame_release(value); }
    void release()
    {
        require(rv_mac_spike_frame_release(value) == RV_OK, "frame release");
        value = nullptr;
    }
};

using Host = std::unique_ptr<RvHost, decltype(&rv_host_destroy)>;
using Window = std::unique_ptr<SDL_Window, decltype(&SDL_DestroyWindow)>;
using Renderer = std::unique_ptr<SDL_Renderer, decltype(&SDL_DestroyRenderer)>;
using Texture = std::unique_ptr<SDL_Texture, decltype(&SDL_DestroyTexture)>;
using Surface = std::unique_ptr<SDL_Surface, decltype(&SDL_DestroySurface)>;
using Animation = std::unique_ptr<RvAnimation, decltype(&rv_animation_release)>;

struct ConsumerDrain {
    SDL_Renderer* renderer;
    id<MTLCommandQueue> queue;
    bool completed { false };

    bool finish()
    {
        bool submitted = SDL_FlushRenderer(renderer);
        id<MTLCommandBuffer> completion = [queue commandBuffer];
        if (!completion)
            return false;
        [completion commit];
        [completion waitUntilCompleted];
        completed = true;
        return submitted && completion.status == MTLCommandBufferStatusCompleted;
    }
    ~ConsumerDrain() { if (!completed) finish(); }
};

std::string markup(int shift)
{
    return "<style>html,body{margin:0;background:white}"
        ".corner{position:fixed;width:24px;height:24px;will-change:transform;transform:translateZ(0)}"
        "#clip{position:absolute;left:40px;top:40px;width:120px;height:80px;overflow:hidden;transform:translateZ(0)}"
        "#moving{width:80px;height:60px;background:red;will-change:transform,opacity;animation:travel 1s linear both paused}"
        "@keyframes travel{from{opacity:.5;transform:translateX(" + std::to_string(shift)
        + "px)}to{opacity:.75;transform:translateX(" + std::to_string(shift + 60) + "px)}}"
        "#text{position:absolute;left:40px;top:130px;font:20px monospace;color:black;transform:translateZ(0)}"
        "</style><div class=corner style='left:0;top:0;background:red'></div>"
        "<div class=corner style='right:0;top:0;background:blue'></div>"
        "<div class=corner style='left:0;bottom:0;background:lime'></div>"
        "<div class=corner style='right:0;bottom:0;background:yellow'></div>"
        "<div id=clip><div id=moving></div></div><div id=text>GPU frame</div>";
}

void load(RvHost* host, int shift)
{
    auto html = markup(shift);
    require(rv_host_load_html(host, reinterpret_cast<const uint8_t*>(html.data()), html.size()) == RV_OK, "load painted DOM");
    require(rv_host_update(host) == RV_OK, "update DOM layout");
    rv_run_loop_cycle(0);
}

void resizeWindow(SDL_Window* window, SDL_Renderer* renderer, int width, int height)
{
    require(SDL_SetWindowSize(window, width, height), "resize SDL window");
    int actualWidth = 0, actualHeight = 0;
    for (int attempt = 0; attempt < 100; ++attempt) {
        SDL_PumpEvents();
        require(SDL_GetRenderOutputSize(renderer, &actualWidth, &actualHeight), "backbuffer size");
        if (actualWidth == width && actualHeight == height)
            return;
        SDL_Delay(5);
    }
    require(false, "SDL backbuffer must match the acquired physical frame");
}

void pixel(SDL_Surface* image, int x, int y, int red, int green, int blue)
{
    Uint8 r, g, b, a;
    require(SDL_ReadSurfacePixel(image, x, y, &r, &g, &b, &a), "read final backbuffer sample");
    if (std::abs(int(r) - red) > 3 || std::abs(int(g) - green) > 3 || std::abs(int(b) - blue) > 3 || a < 252)
        std::fprintf(stderr, "pixel(%d,%d) actual=%u,%u,%u,%u expected=%d,%d,%d,255\n", x, y, r, g, b, a, red, green, blue);
    require(std::abs(int(r) - red) <= 3 && std::abs(int(g) - green) <= 3
            && std::abs(int(b) - blue) <= 3 && a >= 252, "expected BGRA/orientation/alpha/clipping sample");
}

void validate(SDL_Surface* image, int shift, float scale, int translucentChannel = 128)
{
    auto physical = [=](int css) { return static_cast<int>(std::floor(css * scale)); };
    pixel(image, physical(4), physical(4), 255, 0, 0);
    pixel(image, image->w - physical(5), physical(4), 0, 0, 255);
    pixel(image, physical(4), image->h - physical(5), 0, 255, 0);
    pixel(image, image->w - physical(5), image->h - physical(5), 255, 255, 0);
    pixel(image, physical(50), physical(50), 255, shift ? 255 : translucentChannel, shift ? 255 : translucentChannel);
    pixel(image, physical(110), physical(50), 255, translucentChannel, translucentChannel);
    pixel(image, physical(170), physical(50), 255, 255, 255);
    int darkPixels = 0;
    bool textRead = true;
    for (int y = physical(132); y < physical(155); ++y) {
        for (int x = physical(40); x < physical(150); ++x) {
            Uint8 r, g, b, a;
            if (!SDL_ReadSurfacePixel(image, x, y, &r, &g, &b, &a)) {
                textRead = false;
                continue;
            }
            darkPixels += r < 80 && g < 80 && b < 80;
        }
    }
    require(textRead, "read rasterized text region");
    require(darkPixels > 40, "CoreGraphics text survives texture upload and composition");
}

Surface present(SDL_Renderer* renderer, RvMacSpikeFrame* frame)
{
    void* rawSurface = nullptr;
    int32_t width = 0, height = 0;
    require(rv_mac_spike_frame_info(frame, &rawSurface, &width, &height) == RV_OK && rawSurface, "owned IOSurface frame info");
    auto rendererProperties = SDL_GetRendererProperties(renderer);
    id<MTLDevice> device = (__bridge id<MTLDevice>)SDL_GetPointerProperty(rendererProperties, SDL_PROP_RENDERER_METAL_DEVICE_POINTER, nullptr);
    id<MTLCommandQueue> queue = (__bridge id<MTLCommandQueue>)SDL_GetPointerProperty(rendererProperties, SDL_PROP_RENDERER_METAL_COMMAND_QUEUE_POINTER, nullptr);
    require(device && queue, "SDL exposes real Metal device and queue");
    if (!presented)
        std::printf("MAC_GPU_SPIKE SDL=%d device=%s registryID=%llu\n", SDL_GetVersion(), device.name.UTF8String,
            static_cast<unsigned long long>(device.registryID));
    ConsumerDrain drain { renderer, queue };
    MTLTextureDescriptor* descriptor = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm
        width:width height:height mipmapped:NO];
    descriptor.usage = MTLTextureUsageShaderRead;
    descriptor.storageMode = MTLStorageModeShared;
    id<MTLTexture> metal = [device newTextureWithDescriptor:descriptor iosurface:static_cast<IOSurfaceRef>(rawSurface) plane:0];
    require(metal != nil, "IOSurface imports on SDL Metal device");
    SDL_PropertiesID properties = SDL_CreateProperties();
    require(properties != 0, "texture properties");
    SDL_SetNumberProperty(properties, SDL_PROP_TEXTURE_CREATE_FORMAT_NUMBER, SDL_PIXELFORMAT_ARGB8888);
    SDL_SetNumberProperty(properties, SDL_PROP_TEXTURE_CREATE_WIDTH_NUMBER, width);
    SDL_SetNumberProperty(properties, SDL_PROP_TEXTURE_CREATE_HEIGHT_NUMBER, height);
    SDL_SetPointerProperty(properties, SDL_PROP_TEXTURE_CREATE_METAL_TEXTURE_POINTER, (__bridge void*)metal);
    Texture texture(SDL_CreateTextureWithProperties(renderer, properties), SDL_DestroyTexture);
    SDL_DestroyProperties(properties);
    require(texture != nullptr, "SDL wraps producer Metal texture");
    require(SDL_SetTextureBlendMode(texture.get(), SDL_BLENDMODE_NONE), "opaque page blend mode");
    require(SDL_SetRenderDrawColor(renderer, 255, 0, 255, 255) && SDL_RenderClear(renderer), "clear final backbuffer");
    require(SDL_RenderTexture(renderer, texture.get(), nullptr, nullptr), "GPU render imported texture");
    Surface result(SDL_RenderReadPixels(renderer, nullptr), SDL_DestroySurface);
    require(result != nullptr, "test-only final backbuffer readback");
    require(SDL_RenderPresent(renderer), "present consumer work");
    require(drain.finish(), "consumer completed before frame or texture release");
    ++presented;
    return result;
}

void cycle(int index, float scale)
{
    constexpr int cssWidth = 241, cssHeight = 181;
    int physicalWidth = static_cast<int>(std::floor(cssWidth * scale));
    int physicalHeight = static_cast<int>(std::floor(cssHeight * scale));
    Window window(SDL_CreateWindow("Ranvier macOS GPU spike", physicalWidth, physicalHeight, 0), SDL_DestroyWindow);
    require(window != nullptr, "SDL window");
    Renderer renderer(SDL_CreateRenderer(window.get(), "metal"), SDL_DestroyRenderer);
    require(renderer && std::strcmp(SDL_GetRendererName(renderer.get()), "metal") == 0, "strict Metal renderer");
    resizeWindow(window.get(), renderer.get(), physicalWidth, physicalHeight);
    Host host(rv_host_create(cssWidth, cssHeight), rv_host_destroy);
    require(host != nullptr, "host with ANGLE Metal display");
    require(rv_host_set_device_scale(host.get(), scale) == RV_OK, "set tested backing scale");
    int32_t paintWidth = 0, paintHeight = 0;
    require(rv_host_paint_size(host.get(), &paintWidth, &paintHeight) == RV_OK
            && paintWidth == physicalWidth && paintHeight == physicalHeight, "odd CSS physical floor matches paint size");
    load(host.get(), 0);
    require(rv_host_set_accelerated_compositing(host.get(), RV_COMPOSITING_OFF) == RV_OK, "disable compositor");
    Frame unavailable;
    require(rv_mac_spike_acquire_frame(host.get(), &unavailable.value) == RV_ERR_UNSUPPORTED && !unavailable.value, "no CPU fallback when compositor disabled");
    require(rv_host_set_accelerated_compositing(host.get(), RV_COMPOSITING_ALWAYS) == RV_OK, "force real compositor");
    Frame first;
    int wrongThread = 0;
    std::thread worker([&] { wrongThread = rv_mac_spike_acquire_frame(host.get(), &first.value); });
    worker.join();
    require(wrongThread == RV_ERR_WRONG_THREAD && !first.value, "acquire is owner-thread only");
    require(rv_mac_spike_acquire_frame(host.get(), &first.value) == RV_OK && first.value, "first composited frame");
    std::thread releaseWorker([&] { wrongThread = rv_mac_spike_frame_release(first.value); });
    releaseWorker.join();
    require(wrongThread == RV_ERR_WRONG_THREAD, "wrong-thread release preserves the frame");
    auto identity = rv_mac_spike_identity();
    require(identity && std::strstr(identity, "Metal"), "producer reports real ANGLE Metal renderer");
    std::printf("MAC_GPU_SPIKE identity cycle=%d scale=%g physical=%dx%d %s\n", index, scale, physicalWidth, physicalHeight, identity);
    auto before = present(renderer.get(), first.value);
    validate(before.get(), 0, scale);
    uint64_t gpu = 0, readback = 0, basePaints = 0;
    require(rv_mac_spike_counters(host.get(), &gpu, &readback, &basePaints) == RV_OK && gpu == 1 && readback == 0, "GPU first frame counters");
    auto stablePaints = basePaints;
    for (int repeat = 0; repeat < 3; ++repeat) {
        Frame unchanged;
        require(rv_mac_spike_acquire_frame(host.get(), &unchanged.value) == RV_OK && unchanged.value, "unchanged frame");
        validate(present(renderer.get(), unchanged.value).get(), 0, scale);
    }
    require(rv_mac_spike_counters(host.get(), &gpu, &readback, &basePaints) == RV_OK
            && basePaints == stablePaints && readback == 0, "unchanged DOM does not repaint base backing");
    RvAnimation* rawAnimation = nullptr;
    int32_t animationCount = 0;
    require(rv_host_animations(host.get(), &rawAnimation, 1, &animationCount) == RV_OK
            && animationCount == 1 && rawAnimation, "actual WebCore transform and opacity animation");
    Animation animation(rawAnimation, rv_animation_release);
    require(rv_animation_control(animation.get(), RV_ANIMATION_PAUSE) == RV_OK, "pause deterministic animation");
    for (int milliseconds : { 1000, 0 }) {
        require(rv_animation_seek(animation.get(), milliseconds) == RV_OK, "seek compositor animation");
        require(rv_host_update(host.get()) == RV_OK, "update animation state");
        rv_run_loop_cycle(0);
        Frame animated;
        require(rv_mac_spike_acquire_frame(host.get(), &animated.value) == RV_OK && animated.value, "animated GPU frame");
        validate(present(renderer.get(), animated.value).get(), milliseconds ? 60 : 0, scale, milliseconds ? 64 : 128);
        require(rv_mac_spike_counters(host.get(), &gpu, &readback, &basePaints) == RV_OK
                && basePaints == stablePaints && readback == 0, "transform and opacity animation reuse base backing");
    }
    animation.reset();
    if (!outputDirectory.empty())
        require(SDL_SaveBMP(before.get(), (outputDirectory + "/cycle" + std::to_string(index) + "-before.bmp").c_str()), "save first backbuffer evidence");
    load(host.get(), 60);
    Frame second;
    require(rv_mac_spike_acquire_frame(host.get(), &second.value) == RV_OK && second.value, "second changed frame");
    auto after = present(renderer.get(), second.value);
    validate(after.get(), 60, scale);
    if (!outputDirectory.empty())
        require(SDL_SaveBMP(after.get(), (outputDirectory + "/cycle" + std::to_string(index) + "-after.bmp").c_str()), "save changed backbuffer evidence");
    auto retained = present(renderer.get(), first.value);
    validate(retained.get(), 0, scale);
    first.release();
    require(rv_host_resize(host.get(), 281, 201) == RV_OK, "resize host with retained old frame");
    resizeWindow(window.get(), renderer.get(), static_cast<int>(std::floor(281 * scale)), static_cast<int>(std::floor(201 * scale)));
    Frame resized;
    require(rv_mac_spike_acquire_frame(host.get(), &resized.value) == RV_OK && resized.value, "resized frame");
    validate(present(renderer.get(), resized.value).get(), 60, scale);
    void* oldSurface = nullptr;
    int32_t oldWidth = 0, oldHeight = 0;
    require(rv_mac_spike_frame_info(second.value, &oldSurface, &oldWidth, &oldHeight) == RV_OK
            && oldWidth == physicalWidth && oldHeight == physicalHeight, "old frame size preserved across resize");
    require(rv_mac_spike_counters(host.get(), &gpu, &readback, &basePaints) == RV_OK && gpu == 8 && readback == 0, "native GPU frames8 with host readback frames0");
    auto* expiredHost = host.get();
    host.reset();
    require(rv_mac_spike_acquire_frame(expiredHost, &unavailable.value) == RV_ERR_DETACHED && !unavailable.value, "destroyed host cannot acquire");
    validate(present(renderer.get(), resized.value).get(), 60, scale);
    second.release();
    resized.release();
    std::printf("MAC_GPU_SPIKE lifetime cycle=%d scale=%g gpuFrames=%llu cpuFrames=%llu retainedAfterDestroy=PASS\n", index, scale,
        static_cast<unsigned long long>(gpu), static_cast<unsigned long long>(readback));
}
}

int main(int argc, char** argv)
{
    @autoreleasepool {
        try {
            require(SDL_Init(SDL_INIT_VIDEO), "SDL init");
            if (argc == 3 && std::strcmp(argv[1], "--output") == 0)
                outputDirectory = argv[2];
            if (argc == 2 && std::strcmp(argv[1], "--reject-software") == 0) {
                Window window(SDL_CreateWindow("unsupported renderer", 240, 180, 0), SDL_DestroyWindow);
                require(window != nullptr, "unsupported renderer window");
                Renderer renderer(SDL_CreateRenderer(window.get(), "software"), SDL_DestroyRenderer);
                require(renderer && std::strcmp(SDL_GetRendererName(renderer.get()), "metal") != 0, "software is explicitly excluded from strict Metal proof");
                std::puts("MAC_GPU_SPIKE unsupportedRenderer=PASS presented=0");
                renderer.reset();
                window.reset();
                SDL_Quit();
                return 0;
            }
            Frame invalid;
            require(rv_mac_spike_acquire_frame(nullptr, &invalid.value) == RV_ERR_NULL_ARGUMENT && !invalid.value, "null host guard");
            for (int index = 0; index < 3; ++index)
                cycle(index, index == 0 ? 1.0f : index == 1 ? 1.5f : 2.0f);
            SDL_Quit();
            std::printf("MAC_GPU_SPIKE PASS assertions=%d presented=%llu cycles=3 label=experimental\n", assertions,
                static_cast<unsigned long long>(presented));
            return 0;
        } catch (const std::exception& error) {
            std::fprintf(stderr, "MAC_GPU_SPIKE FAIL %s\n", error.what());
            SDL_Quit();
            return 1;
        }
    }
}
