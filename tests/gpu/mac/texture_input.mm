#define main macOutputFixtureMain
#include "spike.mm"
#undef main
#include <utility>

namespace {
using Node = std::unique_ptr<RvNode, decltype(&rv_node_release)>;

struct MetalInput {
    struct SurfaceOwner {
        IOSurfaceRef value { nullptr };
        ~SurfaceOwner() { if (value) CFRelease(value); }
    } allocation;
    IOSurfaceRef surface { nullptr };
    id<MTLTexture> texture;
    id<MTLDevice> device;
    id<MTLCommandQueue> queue;
    id<MTLRenderPipelineState> pipeline;
    int width;
    int height;

    MetalInput(SDL_Renderer* renderer, int width, int height, bool wrongFormat = false)
        : width(width), height(height)
    {
        auto properties = SDL_GetRendererProperties(renderer);
        device = (__bridge id<MTLDevice>)SDL_GetPointerProperty(properties, SDL_PROP_RENDERER_METAL_DEVICE_POINTER, nullptr);
        queue = [device newCommandQueue];
        require(device && queue, "native Metal producer device and independent queue");
        NSDictionary* attributes = @{
            (__bridge id)kIOSurfaceWidth: @(width), (__bridge id)kIOSurfaceHeight: @(height),
            (__bridge id)kIOSurfaceBytesPerElement: @4,
            (__bridge id)kIOSurfaceBytesPerRow: @(IOSurfaceAlignProperty(kIOSurfaceBytesPerRow, static_cast<size_t>(width) * 4)),
            (__bridge id)kIOSurfacePixelFormat: @(wrongFormat ? 0x52474241 : 0x42475241)
        };
        surface = IOSurfaceCreate((__bridge CFDictionaryRef)attributes);
        allocation.value = surface;
        require(surface != nullptr, "owned native input IOSurface");
        if (wrongFormat)
            return;
        auto* descriptor = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm
            width:width height:height mipmapped:NO];
        descriptor.usage = MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget;
        descriptor.storageMode = MTLStorageModeShared;
        texture = [device newTextureWithDescriptor:descriptor iosurface:surface plane:0];
        require(texture != nil, "native Metal render-target texture shares IOSurface storage");
        NSError* error = nil;
        NSString* source = @"#include <metal_stdlib>\nusing namespace metal;\n"
            "vertex float4 v(uint i [[vertex_id]]) { float2 p[3] = {float2(-1,-1),float2(3,-1),float2(-1,3)}; return float4(p[i],0,1); }\n"
            "fragment float4 f(float4 p [[position]], constant float4& top [[buffer(0)]], constant float4& bottom [[buffer(1)]], constant float& halfHeight [[buffer(2)]]) { return p.y < halfHeight ? top : bottom; }\n";
        id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
        require(library != nil && error == nil, "compile bounded native Metal producer shader");
        auto* configuration = [MTLRenderPipelineDescriptor new];
        configuration.vertexFunction = [library newFunctionWithName:@"v"];
        configuration.fragmentFunction = [library newFunctionWithName:@"f"];
        configuration.colorAttachments[0].pixelFormat = MTLPixelFormatBGRA8Unorm;
        pipeline = [device newRenderPipelineStateWithDescriptor:configuration error:&error];
        require(pipeline != nil && error == nil, "native Metal input pipeline");
    }

    void publish(bool changed = false)
    {
        @autoreleasepool {
            float top[] { changed ? 0.0f : 0.5f, changed ? 0.5f : 0.0f, 0, 0.5f };
            float bottom[] { changed ? 1.0f : 0.0f, changed ? 1.0f : 0.0f, changed ? 0.0f : 1.0f, 1 };
            float halfHeight = height / 2.0f;
            auto* pass = [MTLRenderPassDescriptor renderPassDescriptor];
            pass.colorAttachments[0].texture = texture;
            pass.colorAttachments[0].loadAction = MTLLoadActionClear;
            pass.colorAttachments[0].storeAction = MTLStoreActionStore;
            id<MTLCommandBuffer> command = [queue commandBuffer];
            id<MTLRenderCommandEncoder> encoder = [command renderCommandEncoderWithDescriptor:pass];
            require(command && encoder, "native GPU render command");
            [encoder setRenderPipelineState:pipeline];
            [encoder setFragmentBytes:top length:sizeof(top) atIndex:0];
            [encoder setFragmentBytes:bottom length:sizeof(bottom) atIndex:1];
            [encoder setFragmentBytes:&halfHeight length:sizeof(halfHeight) atIndex:2];
            [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
            [encoder endEncoding];
            [command commit];
            [command waitUntilCompleted];
            require(command.status == MTLCommandBufferStatusCompleted && !command.error,
                "producer completion precedes input publication");
        }
    }

    void dropCallerOwnership()
    {
        texture = nil;
        CFRelease(std::exchange(allocation.value, nullptr));
        surface = nullptr;
    }

    ~MetalInput()
    {
        texture = nil;
    }
};

Node find(RvHost* host, const char* id)
{
    auto* value = rv_document_get_element_by_id(host, reinterpret_cast<const uint8_t*>(id), std::strlen(id));
    require(value != nullptr, "retained DOM target");
    return Node(value, rv_node_release);
}

void style(RvNode* target, const char* name, const char* value)
{
    require(rv_element_set_style(target, name, reinterpret_cast<const uint8_t*>(value), std::strlen(value), 0) == RV_OK,
        "change real DOM style");
}

void inputCycle(float scale)
{
    int width = static_cast<int>(std::floor(161 * scale));
    int height = static_cast<int>(std::floor(121 * scale));
    Window window(SDL_CreateWindow("Ranvier native texture input", width, height, 0), SDL_DestroyWindow);
    require(window != nullptr, "input SDL window");
    Renderer renderer(SDL_CreateRenderer(window.get(), "metal"), SDL_DestroyRenderer);
    require(renderer && std::strcmp(SDL_GetRendererName(renderer.get()), "metal") == 0, "input strict Metal renderer");
    resizeWindow(window.get(), renderer.get(), width, height);
    Host host(rv_host_create(161, 121), rv_host_destroy);
    require(host != nullptr, "input host");
    require(rv_host_set_device_scale(host.get(), scale) == RV_OK
        && rv_host_set_accelerated_compositing(host.get(), RV_COMPOSITING_ALWAYS) == RV_OK, "input compositor and DPI");
    const char* html = "<style>html,body{margin:0;background:white}"
        "#clip{position:absolute;left:10px;top:10px;width:80px;height:70px;overflow:hidden;transform:translateZ(0)}"
        "#content{height:160px}#input{position:absolute;left:20px;top:10px;width:80px;height:60px;"
        "will-change:transform,opacity;transform:translateX(5px);opacity:.5}"
        "#cover{position:absolute;left:60px;top:40px;width:12px;height:12px;background:black;z-index:5}"
        "</style><div id=clip><div id=content><div id=input></div></div></div><div id=cover></div>";
    require(rv_host_load_html(host.get(), reinterpret_cast<const uint8_t*>(html), std::strlen(html)) == RV_OK, "input DOM");
    auto target = find(host.get(), "input");
    auto clip = find(host.get(), "clip");
    MetalInput input(renderer.get(), 16, 16);
    input.publish();
    require(rv_mac_spike_bind_iosurface(host.get(), target.get(), input.surface, 0) == RV_OK, "bind native Metal-produced IOSurface");
    auto sample = [&](SDL_Surface* image, int x, int y, int red, int green, int blue) {
        pixel(image, static_cast<int>(std::floor(x * scale)), static_cast<int>(std::floor(y * scale)), red, green, blue);
    };
    auto acquire = [&]() {
        require(rv_host_update(host.get()) == RV_OK, "input layout update");
        rv_run_loop_cycle(0);
        Frame frame;
        require(rv_mac_spike_acquire_frame(host.get(), &frame.value) == RV_OK && frame.value, "input composited GPU frame");
        return present(renderer.get(), frame.value);
    };
    auto first = acquire();
    if (!outputDirectory.empty())
        require(SDL_SaveBMP(first.get(), (outputDirectory + "/input-" + std::to_string(static_cast<int>(scale * 10)) + "-first.bmp").c_str()), "save native input composition evidence");
    sample(first.get(), 40, 25, 255, 191, 191);
    sample(first.get(), 40, 65, 128, 128, 255);
    sample(first.get(), 95, 65, 255, 255, 255);
    sample(first.get(), 61, 45, 0, 0, 0);
    uint64_t firstGpu = 0, firstReadback = 0, firstPaints = 0;
    require(rv_mac_spike_counters(host.get(), &firstGpu, &firstReadback, &firstPaints) == RV_OK && firstReadback == 0,
        "capture base DOM backing count before input-only updates");
    require(rv_mac_spike_bind_iosurface(host.get(), target.get(), input.surface, 2) == RV_ERR_UNSUPPORTED, "unknown orientation rejected");
    MetalInput unsupported(renderer.get(), 16, 16, true);
    require(rv_mac_spike_bind_iosurface(host.get(), target.get(), unsupported.surface, 0) == RV_ERR_UNSUPPORTED,
        "unsupported surface format rejected without replacing live input");
    sample(acquire().get(), 40, 25, 255, 191, 191);
    int wrongThread = RV_OK;
    std::thread worker([&] { wrongThread = rv_mac_spike_bind_iosurface(host.get(), target.get(), input.surface, 0); });
    worker.join();
    require(wrongThread == RV_ERR_WRONG_THREAD, "wrong-thread input does not transfer ownership");
    Host foreign(rv_host_create(80, 80), rv_host_destroy);
    const uint8_t other[] = "<div id=input></div>";
    require(rv_host_load_html(foreign.get(), other, sizeof(other) - 1) == RV_OK, "foreign document");
    auto foreignTarget = find(foreign.get(), "input");
    require(rv_mac_spike_bind_iosurface(host.get(), foreignTarget.get(), input.surface, 0) == RV_ERR_WRONG_HOST,
        "foreign target does not transfer ownership");
    input.publish(true);
    require(rv_host_native_texture_changed(host.get(), target.get()) == RV_OK, "completed producer update publication");
    sample(acquire().get(), 40, 25, 191, 255, 191);
    uint64_t updateGpu = 0, updateReadback = 0, updatePaints = 0;
    require(rv_mac_spike_counters(host.get(), &updateGpu, &updateReadback, &updatePaints) == RV_OK
        && updateGpu > firstGpu && updateReadback == 0 && updatePaints == firstPaints,
        "native input-only GPU update reuses the unchanged base DOM backing");
    require(rv_mac_spike_bind_iosurface(host.get(), target.get(), input.surface, 1) == RV_OK, "explicit vertical flip");
    auto flipped = acquire();
    if (!outputDirectory.empty())
        require(SDL_SaveBMP(flipped.get(), (outputDirectory + "/input-" + std::to_string(static_cast<int>(scale * 10)) + "-flipped.bmp").c_str()), "save flipped input evidence");
    sample(flipped.get(), 40, 25, 255, 255, 128);
    sample(flipped.get(), 40, 65, 191, 255, 191);
    style(target.get(), "transform", "translateX(20px)");
    style(target.get(), "opacity", "1");
    auto transformed = acquire();
    sample(transformed.get(), 40, 25, 255, 255, 255);
    sample(transformed.get(), 55, 25, 255, 255, 0);
    require(rv_element_scroll_to(clip.get(), 0, 20, 0) == RV_OK, "DOM ancestor scroll");
    auto scrolled = acquire();
    if (!outputDirectory.empty())
        require(SDL_SaveBMP(scrolled.get(), (outputDirectory + "/input-" + std::to_string(static_cast<int>(scale * 10)) + "-scrolled.bmp").c_str()), "save clipped and scrolled input evidence");
    sample(scrolled.get(), 55, 5, 255, 255, 255);
    sample(scrolled.get(), 55, 15, 255, 255, 0);
    sample(scrolled.get(), 55, 35, 128, 255, 128);
    style(target.get(), "display", "none");
    sample(acquire().get(), 55, 15, 255, 255, 255);
    style(target.get(), "display", "block");
    sample(acquire().get(), 55, 15, 255, 255, 0);
    MetalInput resizedInput(renderer.get(), 23, 17);
    resizedInput.publish(true);
    require(rv_mac_spike_bind_iosurface(host.get(), target.get(), resizedInput.surface, 1) == RV_OK, "replace differently sized native surface");
    resizedInput.dropCallerOwnership();
    sample(acquire().get(), 55, 15, 255, 255, 0);
    require(rv_host_resize(host.get(), 181, 141) == RV_OK, "resize target host");
    resizeWindow(window.get(), renderer.get(), static_cast<int>(std::floor(181 * scale)), static_cast<int>(std::floor(141 * scale)));
    sample(acquire().get(), 55, 15, 255, 255, 0);
    require(rv_mac_spike_bind_iosurface(host.get(), target.get(), nullptr, 0) == RV_OK, "explicit input unbind");
    require(rv_host_native_texture_changed(host.get(), target.get()) == RV_ERR_UNSUPPORTED, "unbound input rejects publication");
    sample(acquire().get(), 55, 15, 255, 255, 255);
    require(rv_mac_spike_bind_iosurface(host.get(), target.get(), input.surface, 0) == RV_OK, "rebind for removal");
    auto parent = find(host.get(), "content");
    require(rv_node_remove_child(parent.get(), target.get()) == RV_OK, "remove retained input target");
    sample(acquire().get(), 55, 15, 255, 255, 255);
    require(rv_mac_spike_bind_iosurface(host.get(), target.get(), input.surface, 0) == RV_ERR_WRONG_HOST,
        "removed target cannot rebind");
    require(rv_host_load_html(host.get(), reinterpret_cast<const uint8_t*>(html), std::strlen(html)) == RV_OK, "HTML replacement drops inputs");
    target = find(host.get(), "input");
    require(rv_mac_spike_bind_iosurface(host.get(), target.get(), input.surface, 0) == RV_OK, "bind new document");
    const uint8_t svg[] = "<svg xmlns='http://www.w3.org/2000/svg' width='181' height='141'><rect width='181' height='141' fill='blue' style='will-change:transform'/></svg>";
    require(rv_host_load_svg(host.get(), svg, sizeof(svg) - 1) == RV_OK, "SVG replacement drops inputs");
    sample(acquire().get(), 40, 25, 0, 0, 255);
    require(rv_host_load_html(host.get(), reinterpret_cast<const uint8_t*>(html), std::strlen(html)) == RV_OK, "restore before final destruction");
    target = find(host.get(), "input");
    require(rv_mac_spike_bind_iosurface(host.get(), target.get(), input.surface, 0) == RV_OK, "bind before host destruction");
    Frame retained;
    require(rv_mac_spike_acquire_frame(host.get(), &retained.value) == RV_OK && retained.value, "retain independent output frame");
    uint64_t gpu = 0, readback = 0, paints = 0;
    require(rv_mac_spike_counters(host.get(), &gpu, &readback, &paints) == RV_OK && readback == 0, "input composition has no host readback");
    auto* stale = host.get();
    host.reset();
    require(rv_mac_spike_bind_iosurface(stale, target.get(), input.surface, 0) == RV_ERR_DETACHED, "destroyed host rejects input before dereference");
    sample(present(renderer.get(), retained.value).get(), 40, 25, 191, 255, 191);
    retained.release();
    std::printf("MAC_TEXTURE_INPUT scale=%g gpuFrames=%llu hostReadbacks=%llu nativeMetalRender=PASS retainedOutput=PASS\n", scale,
        static_cast<unsigned long long>(gpu), static_cast<unsigned long long>(readback));
}
}

int main(int argc, char** argv)
{
    @autoreleasepool {
        try {
            require(SDL_Init(SDL_INIT_VIDEO), "input SDL init");
            if (argc == 3 && std::strcmp(argv[1], "--output") == 0)
                outputDirectory = argv[2];
            for (float scale : { 1.0f, 1.5f, 2.0f })
                inputCycle(scale);
            SDL_Quit();
            std::printf("MAC_TEXTURE_INPUT PASS assertions=%d frames=%llu label=private-unqualified-until-run\n", assertions,
                static_cast<unsigned long long>(presented));
            return 0;
        } catch (const std::exception& error) {
            std::fprintf(stderr, "MAC_TEXTURE_INPUT FAIL %s\n", error.what());
            SDL_Quit();
            return 1;
        }
    }
}
