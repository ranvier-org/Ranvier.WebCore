#include "../../examples/NativeMedia/WindowsPlayback.h"
#include <chrono>
#include <cmath>
#include <cstdio>
#include <thread>
#include <filesystem>
#include <fstream>

using RanvierNativeMedia::Playback;
using RanvierNativeMedia::State;
static unsigned assertions;
static bool require(bool condition, const char* label)
{
    ++assertions;
    if (!condition)
        std::fprintf(stderr, "FAIL: %s\n", label);
    return condition;
}

static bool waitFor(Playback& player, auto predicate)
{
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    do {
        RanvierNativeMedia::Frame frame;
        auto video = player.nextFrame(frame);
        if (FAILED(video))
            return false;
        if (video == S_OK) {
            Microsoft::WRL::ComPtr<IDXGIKeyedMutex> mutex;
            if (FAILED(frame.texture.As(&mutex)) || mutex->AcquireSync(1,100) != S_OK || mutex->ReleaseSync(0) != S_OK)
                return false;
        }
        auto value = player.snapshot();
        if (predicate(value))
            return true;
        if (value.state == State::Failed)
            return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    } while (std::chrono::steady_clock::now() < deadline);
    return false;
}

int wmain(int argc, wchar_t** argv)
{
    if (argc != 2)
        return 64;
    Playback player;
    if (!require(player.snapshot().state == State::Closed, "initial session is closed"))
        return 1;
    auto status = player.initialize();
    std::printf("MEDIA_INITIALIZE_HRESULT=%08lx\n", static_cast<unsigned long>(status));
    if (FAILED(status))
        return player.snapshot().state == State::Unavailable ? 77 : 1;
    if (!require(SUCCEEDED(player.openFile(argv[1])), "open local owned audio/video fixture"))
        return 1;
    if (!require(waitFor(player, [](auto value) { return value.ready && value.duration > 1; }), "actual provider resolves local media"))
        return 1;
    auto initial = player.snapshot();
    std::printf("MEDIA_DURATION=%.6f HAS_AUDIO=%d HAS_VIDEO=%d\n", initial.duration, initial.hasAudio, initial.hasVideo);
    if (!require(initial.hasAudio, "provider reports an actual audio stream"))
        return 1;
    if (!require(FAILED(player.openFile(argv[1])), "one source is owned until the session is explicitly reinitialized"))
        return 1;
    if (!require(SUCCEEDED(player.play()), "play admitted"))
        return 1;
    if (!require(waitFor(player, [](auto value) { return value.position > .08 && value.state == State::Playing; }), "provider playback clock advances"))
        return 1;
    if (!require(SUCCEEDED(player.pause()), "pause admitted"))
        return 1;
    auto paused = player.snapshot();
    std::this_thread::sleep_for(std::chrono::milliseconds(120));
    if (!require(player.snapshot().state == State::Paused && std::abs(player.snapshot().position - paused.position) < .03, "paused provider clock stays fixed"))
        return 1;
    if (!require(SUCCEEDED(player.seek(.5)), "seek admitted"))
        return 1;
    if (!require(waitFor(player, [](auto value) { return !value.seeking && std::abs(value.position - .5) < .05; }), "actual provider completes seek"))
        return 1;
    if (!require(FAILED(player.seek(-1)), "negative seek rejected"))
        return 1;
    if (!require(SUCCEEDED(player.play()) && waitFor(player, [](auto value) { return value.state == State::Ended; }), "playback reaches real provider end"))
        return 1;
    player.close();
    player.close();
    if (!require(player.snapshot().state == State::Closed && FAILED(player.play()), "idempotent close rejects later play"))
        return 1;
    Playback cancelled;
    if (!require(SUCCEEDED(cancelled.initialize()) && SUCCEEDED(cancelled.openFile(argv[1])), "independent session opens"))
        return 1;
    cancelled.cancel();
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    if (!require(cancelled.snapshot().state == State::Cancelled && FAILED(cancelled.play()), "cancelled opening cannot become live from a late callback"))
        return 1;
    Playback missing;
    if (!require(SUCCEEDED(missing.initialize()) && FAILED(missing.openFile(L"Z:\\ranvier-no-such-media-file.wav")), "missing local source retains an explicit failure"))
        return 1;
    missing.close();
    auto invalid = std::filesystem::path(argv[0]).parent_path() / L"invalid-media.bin";
    std::ofstream(invalid, std::ios::binary) << "This is original invalid test media, not an encoded stream.";
    Playback broken;
    if (!require(SUCCEEDED(broken.initialize()), "asynchronous-error session initializes"))
        return 1;
    auto opened = broken.openFile(invalid.c_str());
    bool failed = FAILED(opened) || waitFor(broken, [](auto value) { return value.state == State::Failed && FAILED(value.error); });
    if (!require(failed, "invalid source produces an actual provider error instead of endless loading"))
        return 1;
    auto failure = broken.snapshot();
    std::printf("MEDIA_INVALID_SOURCE_STATE=%d HRESULT=%08lx\n", static_cast<int>(failure.state), static_cast<unsigned long>(failure.error));
    if (!require(SUCCEEDED(broken.initialize()) && SUCCEEDED(broken.openFile(argv[1]))
        && waitFor(broken, [](auto value) { return value.ready; }), "fresh explicit session recovers without stale source-error callbacks"))
        return 1;
    std::printf("MEDIA_PROVIDER_ASSERTIONS=%u\n", assertions);
    return 0;
}
