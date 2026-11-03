#define main archived_spike_main
#include <spike.mm>
#undef main
#import <CoreGraphics/CoreGraphics.h>
#include <fstream>
#include <vector>

namespace {
Surface cpuPixels(RvHost* host)
{
    int32_t width = 0, height = 0;
    require(rv_host_paint_size(host, &width, &height) == RV_OK && width > 0 && height > 0, "CPU physical extent");
    std::vector<uint8_t> pixels(static_cast<size_t>(width) * height * 4);
    require(rv_host_paint_rgba(host, pixels.data(), pixels.size()) == RV_OK, "CPU-off rendered DOM");
    Surface borrowed(SDL_CreateSurfaceFrom(width, height, SDL_PIXELFORMAT_RGBA32, pixels.data(), width * 4), SDL_DestroySurface);
    require(borrowed != nullptr, "CPU RGBA view");
    Surface result(SDL_ConvertSurface(borrowed.get(), SDL_PIXELFORMAT_RGBA32), SDL_DestroySurface);
    require(result != nullptr, "owned CPU capture");
    return result;
}

std::string asymmetricMarkup()
{
    return "<style>html,body{margin:0;background:white}"
        "#tile{position:absolute;left:40px;top:40px;width:120px;height:100px;transform:translateZ(0);background:white}"
        "#top{position:absolute;left:0;top:0;width:120px;height:8px;background:red}"
        "#bottom{position:absolute;left:0;bottom:0;width:120px;height:8px;background:blue}"
        "#glyph{position:absolute;left:15px;top:10px;font:64px monospace;color:black;line-height:80px}"
        "</style><div id=tile><div id=top></div><div id=bottom></div><div id=glyph>F</div></div>";
}

void capturePair(const std::string& label, const std::string& scene, float scale)
{
    constexpr int width = 241, height = 181;
    int physicalWidth = static_cast<int>(std::floor(width * scale));
    int physicalHeight = static_cast<int>(std::floor(height * scale));
    Window window(SDL_CreateWindow("Cocoa glyph orientation diagnostic", physicalWidth, physicalHeight, 0), SDL_DestroyWindow);
    require(window != nullptr, "diagnostic window");
    Renderer renderer(SDL_CreateRenderer(window.get(), "metal"), SDL_DestroyRenderer);
    require(renderer && std::strcmp(SDL_GetRendererName(renderer.get()), "metal") == 0, "real Metal consumer");
    resizeWindow(window.get(), renderer.get(), physicalWidth, physicalHeight);
    Host host(rv_host_create(width, height), rv_host_destroy);
    require(host != nullptr, "same-runtime host");
    require(rv_host_set_device_scale(host.get(), scale) == RV_OK, "same device scale");
    require(rv_host_set_accelerated_compositing(host.get(), RV_COMPOSITING_OFF) == RV_OK, "explicit CPU control");
    require(rv_host_load_html(host.get(), reinterpret_cast<const uint8_t*>(scene.data()), scene.size()) == RV_OK, "exact scene");
    require(rv_host_update(host.get()) == RV_OK, "CPU layout");
    rv_run_loop_cycle(0);
    auto cpu = cpuPixels(host.get());
    require(SDL_SaveBMP(cpu.get(), (outputDirectory + "/" + label + "-cpu.bmp").c_str()), "save CPU control");
    require(rv_host_set_accelerated_compositing(host.get(), RV_COMPOSITING_ALWAYS) == RV_OK, "same host GPU path");
    require(rv_host_update(host.get()) == RV_OK, "GPU update");
    rv_run_loop_cycle(0);
    Frame frame;
    require(rv_mac_spike_acquire_frame(host.get(), &frame.value) == RV_OK && frame.value, "GPU frame");
    auto gpu = present(renderer.get(), frame.value);
    require(SDL_SaveBMP(gpu.get(), (outputDirectory + "/" + label + "-gpu.bmp").c_str()), "save GPU control");
    std::printf("GLYPH_PAIR scene=%s scale=%g size=%dx%d identity=%s\n", label.c_str(), scale,
        physicalWidth, physicalHeight, rv_mac_spike_identity());
}

void imageCopyControl()
{
    constexpr size_t width = 8, height = 8;
    uint32_t source[width * height];
    std::fill_n(source, width * height / 2, 0xffff0000u);
    std::fill_n(source + width * height / 2, width * height / 2, 0xff0000ffu);
    CGColorSpaceRef color = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    auto bits = static_cast<uint32_t>(kCGImageAlphaPremultipliedFirst) | static_cast<uint32_t>(kCGBitmapByteOrder32Little);
    CGContextRef original = CGBitmapContextCreate(source, width, height, 8, width * 4, color, bits);
    require(original != nullptr, "CG source bitmap");
    CGImageRef image = CGBitmapContextCreateImage(original);
    require(image != nullptr, "same CG native-image source type");
    for (bool flipped : { false, true }) {
        uint32_t pixels[width * height] { };
        CGContextRef context = CGBitmapContextCreate(pixels, width, height, 8, width * 4, color, bits);
        require(context != nullptr, "CG copy bitmap");
        if (flipped) {
            CGContextTranslateCTM(context, 0, height);
            CGContextScaleCTM(context, 1, -1);
        }
        CGContextSetBlendMode(context, kCGBlendModeCopy);
        CGContextDrawImage(context, CGRectMake(0, 0, width, height), image);
        auto path = outputDirectory + (flipped ? "/cg-copy-flipped.bgra" : "/cg-copy-identity.bgra");
        std::ofstream stream(path, std::ios::binary);
        stream.write(reinterpret_cast<const char*>(pixels), sizeof(pixels));
        require(stream.good(), "save exact CG copy rows");
        std::printf("CG_COPY flipped=%d sourceFirst=%08x sourceLast=%08x destFirst=%08x destLast=%08x\n",
            flipped, source[0], source[width * (height - 1)], pixels[0], pixels[width * (height - 1)]);
        CGContextRelease(context);
    }
    CGImageRelease(image);
    CGContextRelease(original);
    CGColorSpaceRelease(color);
}
}

int main(int argc, char** argv)
{
    @autoreleasepool {
        try {
            require(argc == 3 && !std::strcmp(argv[1], "--output"), "explicit output directory");
            outputDirectory = argv[2];
            require(SDL_Init(SDL_INIT_VIDEO), "SDL initialization");
            imageCopyControl();
            capturePair("original-1", markup(0), 1.0f);
            for (float scale : { 1.0f, 1.5f, 2.0f })
                capturePair("asymmetric-" + std::to_string(static_cast<int>(scale * 10)), asymmetricMarkup(), scale);
            SDL_Quit();
            std::printf("GLYPH_CAPTURE_COMPLETE assertions=%d pairs=4\n", assertions);
            return 0;
        } catch (const std::exception& error) {
            std::fprintf(stderr, "GLYPH_CAPTURE_FAIL %s\n", error.what());
            SDL_Quit();
            return 1;
        }
    }
}
