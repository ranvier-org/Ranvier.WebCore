#include "../../examples/NativeMedia/WindowsPlayback.h"
#include <chrono>
#include <cstdio>
#include <thread>

using RanvierNativeMedia::Playback;
using RanvierNativeMedia::Frame;
using RanvierNativeMedia::State;
using Microsoft::WRL::ComPtr;

static unsigned assertions;
static bool require(bool condition, const char* label)
{
    ++assertions;
    if (!condition)
        std::fprintf(stderr, "FAIL: %s\n", label);
    return condition;
}

int wmain(int argc, wchar_t** argv)
{
    if (argc != 2)
        return 64;
    Playback player;
    if (!require(SUCCEEDED(player.initialize()) && SUCCEEDED(player.openFile(argv[1])), "actual local video opens"))
        return 1;
    if (!require(SUCCEEDED(player.play()), "video play admitted"))
        return 1;
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(8);
    bool colors[3] { false, false, false };
    unsigned frames = 0;
    LONGLONG previous = -1;
    Frame retained;
    ComPtr<ID3D11Device> device = player.device();
    ComPtr<ID3D11DeviceContext> context;
    device->GetImmediateContext(&context);
    while (std::chrono::steady_clock::now() < deadline) {
        Frame frame;
        auto status = player.nextFrame(frame);
        if (FAILED(status)) {
            std::fprintf(stderr, "FRAME_HRESULT=%08lx\n", static_cast<unsigned long>(status));
            return 1;
        }
        if (status == S_OK) {
            if (!require(frame.texture && frame.width == 96 && frame.height == 64, "actual decoded frame dimensions")
                || !require(frame.presentationTime >= previous, "provider presentation timestamps are monotonic"))
                return 1;
            previous = frame.presentationTime;
            D3D11_TEXTURE2D_DESC description;
            frame.texture->GetDesc(&description);
            if (!require(description.Format == DXGI_FORMAT_R8G8B8A8_UNORM, "RGBA8 is real provider output, not BGRA reinterpretation"))
                return 1;
            ComPtr<IDXGIKeyedMutex> mutex;
            if (!require(SUCCEEDED(frame.texture.As(&mutex)) && mutex->AcquireSync(1, 100) == S_OK, "consumer acquires published frame key1"))
                return 1;
            description.Usage = D3D11_USAGE_STAGING;
            description.BindFlags = 0;
            description.MiscFlags = 0;
            description.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
            ComPtr<ID3D11Texture2D> staging;
            if (!require(SUCCEEDED(device->CreateTexture2D(&description, nullptr, &staging)), "SDK readback texture created"))
                return 1;
            context->CopyResource(staging.Get(), frame.texture.Get());
            D3D11_MAPPED_SUBRESOURCE mapped;
            if (!require(SUCCEEDED(context->Map(staging.Get(), 0, D3D11_MAP_READ, 0, &mapped)), "actual GPU frame readback"))
                return 1;
            auto pixel = static_cast<const unsigned char*>(mapped.pData) + mapped.RowPitch * 32 + 48 * 4;
            unsigned red = pixel[0], green = pixel[1], blue = pixel[2], alpha = pixel[3];
            context->Unmap(staging.Get(), 0);
            context->Flush();
            if (!require(mutex->ReleaseSync(0) == S_OK, "consumer returns key0"))
                return 1;
            unsigned phase = frame.presentationTime < 6666666 ? 0 : frame.presentationTime < 13333333 ? 1 : 2;
            if (frame.presentationTime % 6666666 > 500000) {
                bool correct = phase == 0 ? red > 200 && green < 40 && blue < 40 :
                    phase == 1 ? green > 200 && red < 40 && blue < 40 : blue > 200 && red < 40 && green < 40;
                if (!require(correct && alpha > 250, "actual decoded RGBA color follows fixture presentation time")) {
                    std::fprintf(stderr, "PIXEL=%u,%u,%u,%u PTS=%lld\n", red, green, blue, alpha, frame.presentationTime);
                    return 1;
                }
                colors[phase] = true;
            }
            std::printf("MEDIA_FRAME=%u PTS=%lld PIXEL=%u,%u,%u,%u\n", frames, frame.presentationTime, red, green, blue, alpha);
            retained = std::move(frame);
            ++frames;
        }
        auto state = player.snapshot();
        if (state.state == State::Failed) {
            std::fprintf(stderr, "PLAYBACK_HRESULT=%08lx\n", static_cast<unsigned long>(state.error));
            return 1;
        }
        if (state.state == State::Ended)
            break;
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    if (!require(colors[0] && colors[1] && colors[2] && frames >= 3, "all three actual decoded video phases observed"))
        return 1;
    player.close();
    if (!require(retained.texture && SUCCEEDED(device->GetDeviceRemovedReason()), "retained frame and application device remain valid after provider close"))
        return 1;
    retained = { };
    std::printf("MEDIA_VIDEO_ASSERTIONS=%u FRAMES=%u\n", assertions, frames);
    return 0;
}
