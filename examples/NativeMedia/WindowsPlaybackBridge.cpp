#define RANVIER_MEDIA_BUILD
#include "WindowsPlaybackBridge.h"
#include "WindowsMediaControls.h"
#include <new>

using namespace RanvierNativeMedia;
using Microsoft::WRL::ComPtr;

namespace {
struct StateData {
    DWORD owner { GetCurrentThreadId() };
    Playback player;
    WindowsMediaControls controls;
    Frame lastFrame;
    ComPtr<ID3D11DeviceContext> context;
    bool controlsAttached { false };
    bool published { false };
    bool cancelled { false };
    bool closing { false };
    ~StateData() { controls.close(); lastFrame = { }; player.close(); }
};

template<typename F> HRESULT guarded(F&& function)
{
    try { return function(); }
    catch (const winrt::hresult_error& error) { return error.code().value; }
    catch (const std::bad_alloc&) { return E_OUTOFMEMORY; }
    catch (...) { return E_FAIL; }
}
HRESULT owner(const StateData& state) { return state.owner == GetCurrentThreadId() ? S_OK : RPC_E_WRONG_THREAD; }
HRESULT active(const StateData& state)
{
    auto status = owner(state);
    return FAILED(status) ? status : state.closing || state.cancelled ? MF_E_SHUTDOWN : S_OK;
}
HRESULT revoke(StateData& state)
{
    if (!state.controlsAttached)
        return S_OK;
    state.controlsAttached = false;
    return state.controls.close();
}
}

struct RmSession { std::shared_ptr<StateData> state; };
struct RmFrame { std::shared_ptr<StateData> state; Frame frame; };
static_assert(sizeof(RmSnapshot) == 32);
static_assert(sizeof(RmFrameInfo) == 32);

extern "C" int32_t ranvier_media_create(RmSession** output, int32_t* state)
{
    if (output) *output = nullptr;
    if (state) *state = static_cast<int32_t>(State::Closed);
    if (!output || !state) return E_POINTER;
    return guarded([&]() -> HRESULT {
        auto data = std::make_shared<StateData>();
        auto status = data->player.initialize();
        *state = static_cast<int32_t>(data->player.snapshot().state);
        if (FAILED(status)) return status;
        data->player.device()->GetImmediateContext(&data->context);
        *output = new RmSession { std::move(data) };
        return S_OK;
    });
}

#define RM_COMMAND(name, expression) \
extern "C" int32_t name(RmSession* session) { \
    if (!session) return E_POINTER; \
    auto status = active(*session->state); \
    if (FAILED(status)) return status; \
    return guarded([&]() -> HRESULT { return (expression); }); \
}
RM_COMMAND(ranvier_media_play, session->state->player.play())
RM_COMMAND(ranvier_media_pause, session->state->player.pause())
RM_COMMAND(ranvier_media_stop, session->state->player.stop())
RM_COMMAND(ranvier_media_controls_drain, session->state->controlsAttached ? session->state->controls.drain(session->state->player) : RO_E_CLOSED)
RM_COMMAND(ranvier_media_controls_detach, revoke(*session->state))
#undef RM_COMMAND

extern "C" int32_t ranvier_media_open(RmSession* session, const wchar_t* path)
{
    if (!session) return E_POINTER;
    auto status = active(*session->state);
    return FAILED(status) ? status : guarded([&] { return session->state->player.openFile(path); });
}
extern "C" int32_t ranvier_media_seek(RmSession* session, double seconds)
{
    if (!session) return E_POINTER;
    auto status = active(*session->state);
    return FAILED(status) ? status : guarded([&] { return session->state->player.seek(seconds); });
}
extern "C" int32_t ranvier_media_snapshot(RmSession* session, RmSnapshot* output)
{
    if (!session || !output) return E_POINTER;
    if (output->size != sizeof(RmSnapshot)) return E_INVALIDARG;
    auto status = owner(*session->state);
    if (FAILED(status)) return status;
    auto value = session->state->player.snapshot();
    if (session->state->cancelled) value.state = State::Cancelled;
    *output = { sizeof(RmSnapshot), static_cast<int32_t>(value.state), value.error,
        (value.ready ? 1u : 0u) | (value.seeking ? 2u : 0u) | (value.hasAudio ? 4u : 0u) | (value.hasVideo ? 8u : 0u),
        value.position, value.duration };
    return S_OK;
}
extern "C" int32_t ranvier_media_cancel(RmSession* session)
{
    if (!session) return E_POINTER;
    auto& data = *session->state;
    auto status = owner(data);
    if (FAILED(status)) return status;
    data.cancelled = true;
    return guarded([&]() -> HRESULT {
        auto controlsStatus = revoke(data);
        auto playbackStatus = data.published ? data.player.pause() : data.player.cancel();
        if (!data.published) data.lastFrame = { };
        return FAILED(controlsStatus) ? controlsStatus : playbackStatus;
    });
}

namespace {
HRESULT publish(RmSession* session, RmFrame** output, bool repeat)
{
    if (output) *output = nullptr;
    if (!session || !output) return E_POINTER;
    auto& data = *session->state;
    auto status = active(data);
    if (FAILED(status)) return status;
    if (data.published) return MF_E_INVALIDREQUEST;
    return guarded([&]() -> HRESULT {
        auto frame = std::make_unique<RmFrame>();
        if (repeat) {
            if (!data.lastFrame.texture) return S_FALSE;
            ComPtr<IDXGIKeyedMutex> mutex;
            if (FAILED(status = data.lastFrame.texture.As(&mutex))) return status;
            status = mutex->AcquireSync(0, 0);
            if (status != S_OK) return status == WAIT_TIMEOUT ? HRESULT_FROM_WIN32(WAIT_TIMEOUT) : status;
            data.context->Flush();
            if (FAILED(status = mutex->ReleaseSync(1))) return status;
        } else {
            Frame next;
            status = data.player.nextFrame(next);
            if (status != S_OK) return status;
            data.lastFrame = std::move(next);
        }
        frame->state = session->state;
        frame->frame = data.lastFrame;
        data.published = true;
        *output = frame.release();
        return S_OK;
    });
}
}
extern "C" int32_t ranvier_media_next_frame(RmSession* session, RmFrame** output) { return publish(session, output, false); }
extern "C" int32_t ranvier_media_republish(RmSession* session, RmFrame** output) { return publish(session, output, true); }
extern "C" int32_t ranvier_media_frame_info(RmFrame* frame, RmFrameInfo* output)
{
    if (!frame || !output) return E_POINTER;
    if (output->size != sizeof(RmFrameInfo)) return E_INVALIDARG;
    auto status = owner(*frame->state);
    if (FAILED(status)) return status;
    *output = { sizeof(RmFrameInfo), frame->frame.width, frame->frame.height, 0,
        frame->frame.texture.Get(), frame->frame.presentationTime };
    return S_OK;
}
extern "C" int32_t ranvier_media_frame_release(RmFrame** frame)
{
    if (!frame || !*frame) return S_OK;
    auto status = owner(*(*frame)->state);
    if (FAILED(status)) return status;
    std::unique_ptr<RmFrame> value(*frame);
    *frame = nullptr;
    return guarded([&]() -> HRESULT {
        auto& data = *value->state;
        data.published = false;
        ComPtr<IDXGIKeyedMutex> mutex;
        auto result = value->frame.texture.As(&mutex);
        if (SUCCEEDED(result)) {
            auto acquired = mutex->AcquireSync(1, 0);
            result = acquired == S_OK ? mutex->ReleaseSync(0) : acquired == WAIT_TIMEOUT ? S_OK : acquired;
        }
        if (data.cancelled && !data.closing) {
            auto cancelled = data.player.cancel();
            data.lastFrame = { };
            if (SUCCEEDED(result)) result = cancelled;
        }
        return result;
    });
}
extern "C" int32_t ranvier_media_controls_attach(RmSession* session, void* window, const wchar_t* title)
{
    if (!session) return E_POINTER;
    auto& data = *session->state;
    auto status = active(data);
    if (FAILED(status)) return status;
    return guarded([&]() -> HRESULT {
        auto result = data.controls.initialize(static_cast<HWND>(window), title);
        data.controlsAttached = SUCCEEDED(result);
        return result;
    });
}
extern "C" int32_t ranvier_media_release(RmSession** session)
{
    if (!session || !*session) return S_OK;
    auto status = owner(*(*session)->state);
    if (FAILED(status)) return status;
    std::unique_ptr<RmSession> value(*session);
    *session = nullptr;
    auto& data = *value->state;
    data.closing = true;
    return guarded([&]() -> HRESULT {
        auto controlsStatus = revoke(data);
        auto playbackStatus = data.published ? data.player.pause() : S_OK;
        return FAILED(controlsStatus) ? controlsStatus : playbackStatus;
    });
}
