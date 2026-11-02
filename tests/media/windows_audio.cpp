#include "../../examples/NativeMedia/WindowsPlayback.h"
#include <mmdeviceapi.h>
#include <audiopolicy.h>
#include <endpointvolume.h>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <thread>

using RanvierNativeMedia::Playback;
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
    if (!require(SUCCEEDED(player.initialize()), "actual provider initialized"))
        return 1;
    ComPtr<IMMDeviceEnumerator> devices;
    auto status = CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&devices));
    ComPtr<IMMDevice> endpoint;
    if (SUCCEEDED(status))
        status = devices->GetDefaultAudioEndpoint(eRender, eMultimedia, &endpoint);
    if (FAILED(status)) {
        std::printf("MEDIA_AUDIO_ENDPOINT_UNAVAILABLE=%08lx\n", static_cast<unsigned long>(status));
        return 77;
    }
    ComPtr<IAudioSessionManager2> sessions;
    status = endpoint->Activate(__uuidof(IAudioSessionManager2), CLSCTX_ALL, nullptr, &sessions);
    if (!require(SUCCEEDED(status), "actual OS audio-session manager acquired"))
        return 1;
    if (!require(SUCCEEDED(player.openFile(argv[1])) && SUCCEEDED(player.play()), "actual audio/video starts on OS provider"))
        return 1;
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    ComPtr<IAudioSessionControl2> ownSession;
    ComPtr<IAudioMeterInformation> meter;
    float highest = 0;
    double position = 0;
    while (std::chrono::steady_clock::now() < deadline) {
        if (!ownSession) {
            ComPtr<IAudioSessionEnumerator> enumeration;
            if (FAILED(sessions->GetSessionEnumerator(&enumeration)))
                return 1;
            int count = 0;
            enumeration->GetCount(&count);
            for (int index = 0; index < count; ++index) {
                ComPtr<IAudioSessionControl> control;
                ComPtr<IAudioSessionControl2> candidate;
                DWORD process = 0;
                if (SUCCEEDED(enumeration->GetSession(index, &control)) && SUCCEEDED(control.As(&candidate))
                    && SUCCEEDED(candidate->GetProcessId(&process)) && process == GetCurrentProcessId()) {
                    AudioSessionState state;
                    if (SUCCEEDED(candidate->GetState(&state)) && state == AudioSessionStateActive) {
                        ownSession = std::move(candidate);
                        ownSession.As(&meter);
                        break;
                    }
                }
            }
        }
        auto snapshot = player.snapshot();
        position = snapshot.position;
        if (meter) {
            float peak = 0;
            if (SUCCEEDED(meter->GetPeakValue(&peak)))
                highest = (std::max)(highest, peak);
        }
        if (ownSession && meter && highest > .0001f && position > .15)
            break;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    std::printf("MEDIA_AUDIO_OWN_SESSION=%d METER=%d PEAK=%.9f CLOCK=%.6f\n", !!ownSession, !!meter, highest, position);
    if (!require(ownSession && meter && highest > .0001f && position > .15, "current-process OS audio sink emits nonzero samples while provider clock advances"))
        return 1;
    if (!require(SUCCEEDED(player.pause()), "actual audio pause admitted"))
        return 1;
    auto paused = player.snapshot().position;
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    float pausedPeak = 1;
    meter->GetPeakValue(&pausedPeak);
    if (!require(std::abs(player.snapshot().position - paused) < .03 && pausedPeak < .0001f, "paused sink becomes silent and clock stays fixed"))
        return 1;
    if (!require(SUCCEEDED(player.play()), "actual audio resumes"))
        return 1;
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    if (!require(player.snapshot().position > paused, "same synchronized provider clock resumes"))
        return 1;
    player.close();
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    AudioSessionState closedState = AudioSessionStateActive;
    ownSession->GetState(&closedState);
    float closedPeak = 1;
    meter->GetPeakValue(&closedPeak);
    std::printf("MEDIA_AUDIO_AFTER_CLOSE_STATE=%d PEAK=%.9f\n", static_cast<int>(closedState), closedPeak);
    if (!require(closedState != AudioSessionStateActive && closedPeak < .0001f, "closed playback releases active OS audio sink and stops samples"))
        return 1;
    std::printf("MEDIA_AUDIO_ASSERTIONS=%u\n", assertions);
    return 0;
}
