#include "../../examples/NativeMedia/WindowsMediaControls.h"
#include <winrt/Windows.Media.Control.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <shellapi.h>
#include <shobjidl.h>
#include <chrono>
#include <cstdio>
#include <thread>

using namespace RanvierNativeMedia;
using namespace winrt::Windows::Media::Control;
static unsigned assertions;
static bool require(bool condition, const char* label)
{
    ++assertions;
    if (!condition)
        std::fprintf(stderr, "FAIL: %s\n", label);
    return condition;
}

static bool waitFor(WindowsMediaControls& controls, Playback& player, auto predicate)
{
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    do {
        MSG message;
        while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
        if (FAILED(controls.drain(player)))
            return false;
        Frame frame;
        auto video = player.nextFrame(frame);
        if (FAILED(video))
            return false;
        if (video == S_OK) {
            Microsoft::WRL::ComPtr<IDXGIKeyedMutex> mutex;
            if (FAILED(frame.texture.As(&mutex)) || mutex->AcquireSync(1,100) != S_OK || mutex->ReleaseSync(0) != S_OK)
                return false;
        }
        if (predicate())
            return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    } while (std::chrono::steady_clock::now() < deadline);
    return false;
}

int wmain(int argc, wchar_t** argv)
{
    if (argc != 2)
        return 64;
    SetCurrentProcessExplicitAppUserModelID(L"Ranvier.NativeMedia.Tests");
    WNDCLASSW type { };
    type.lpfnWndProc = DefWindowProcW;
    type.hInstance = GetModuleHandleW(nullptr);
    type.lpszClassName = L"RanvierNativeMediaTestWindow";
    if (!RegisterClassW(&type))
        return 1;
    struct Window {
        HWND value;
        ~Window() { if (value) DestroyWindow(value); }
    } window { CreateWindowExW(0, type.lpszClassName, L"Native media test", WS_OVERLAPPEDWINDOW,
        0,0,320,200,nullptr,nullptr,type.hInstance,nullptr) };
    if (!require(!!window.value, "owned top-level native window created without global input injection"))
        return 1;
    Playback player;
    WindowsMediaControls controls;
    if (!require(SUCCEEDED(player.initialize()) && SUCCEEDED(player.openFile(argv[1])), "actual local media provider opens"))
        return 1;
    auto status = controls.initialize(window.value, L"Ranvier generated media fixture");
    std::printf("SMTC_INITIALIZE_HRESULT=%08lx\n", static_cast<unsigned long>(status));
    if (!require(SUCCEEDED(status), "actual HWND-scoped OS transport adapter registered"))
        return 1;
    if (!require(SUCCEEDED(player.play()) && waitFor(controls,player,[&] { return player.snapshot().state == State::Playing; }), "actual playback state published to OS controls"))
        return 1;
    try {
        auto manager = GlobalSystemMediaTransportControlsSessionManager::RequestAsync().get();
        GlobalSystemMediaTransportControlsSession session { nullptr };
        if (!require(waitFor(controls,player,[&] {
            for (auto candidate : manager.GetSessions()) {
                if (candidate.SourceAppUserModelId() == L"Ranvier.NativeMedia.Tests") {
                    session = candidate;
                    return true;
                }
            }
            return false;
        }), "real OS media-session manager discovers only this explicit application session"))
            return 1;
        if (!require(session.TryPauseAsync().get() && waitFor(controls,player,[&] { return player.snapshot().state == State::Paused; }), "OS pause action reaches the same native provider"))
            return 1;
        auto capabilities = session.GetPlaybackInfo().Controls();
        bool seekAccepted = session.TryChangePlaybackPositionAsync(10000000).get();
        bool seekCompleted = seekAccepted && waitFor(controls,player,[&] { auto s=player.snapshot(); return !s.seeking && std::abs(s.position-1)<.05; });
        auto seekResult = player.snapshot();
        std::printf("SMTC_SEEK_CAPABILITY=%d ACCEPTED=%d COMPLETED=%d POSITION=%.6f SEEKING=%d STATE=%d\n",
            capabilities.IsPlaybackPositionEnabled(),seekAccepted,seekCompleted,seekResult.position,seekResult.seeking,static_cast<int>(seekResult.state));
        if (!require(seekCompleted, "OS seek action reaches actual provider clock"))
            return 1;
        if (!require(session.TryPlayAsync().get() && waitFor(controls,player,[&] { return player.snapshot().state == State::Playing; }), "OS play action resumes same provider"))
            return 1;
        if (!require(session.TryStopAsync().get() && waitFor(controls,player,[&] { auto s=player.snapshot(); return s.state == State::Stopped && !s.seeking && s.position < .05; }), "OS stop action stops same provider at start"))
            return 1;
        controls.close();
        controls.close();
        bool accepted = false;
        try { accepted = session.TryPlayAsync().get(); } catch (const winrt::hresult_error&) { }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        std::printf("SMTC_AFTER_CLOSE_OS_ACCEPTED=%d\n", accepted);
        if (!require(FAILED(controls.drain(player)) && player.snapshot().state == State::Stopped, "revoked handlers cannot restart playback after adapter close"))
            return 1;
    } catch (const winrt::hresult_error& error) {
        std::fprintf(stderr, "SMTC_ACTUAL_OS_HRESULT=%08lx\n", static_cast<unsigned long>(error.code().value));
        return 1;
    }
    player.close();
    std::printf("MEDIA_OS_CONTROLS_ASSERTIONS=%u\n", assertions);
    return 0;
}
