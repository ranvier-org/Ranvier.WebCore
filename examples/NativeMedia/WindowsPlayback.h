#pragma once

#include <windows.h>
#include <d3d11.h>
#include <d3d10.h>
#include <dxgi1_2.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfmediaengine.h>
#include <mferror.h>
#include <wrl/client.h>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <memory>
#include <utility>

namespace RanvierNativeMedia {

enum class State { Closed, Ready, Loading, Playing, Paused, Ended, Cancelled, Failed, Unavailable };

struct Snapshot {
    State state { State::Closed };
    HRESULT error { S_OK };
    double position { 0 };
    double duration { 0 };
    bool ready { false };
    bool seeking { false };
    bool hasAudio { false };
    bool hasVideo { false };
};

namespace Detail {
struct Events {
    std::atomic_bool active { true };
    std::atomic<HRESULT> error { S_OK };
};

class Notify final : public IMFMediaEngineNotify {
public:
    explicit Notify(std::shared_ptr<Events> events) : m_events(std::move(events)) { }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void** output) override
    {
        if (!output)
            return E_POINTER;
        *output = nullptr;
        if (id != __uuidof(IUnknown) && id != __uuidof(IMFMediaEngineNotify))
            return E_NOINTERFACE;
        *output = static_cast<IMFMediaEngineNotify*>(this);
        AddRef();
        return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++m_references; }
    ULONG STDMETHODCALLTYPE Release() override
    {
        auto references = --m_references;
        if (!references)
            delete this;
        return references;
    }
    HRESULT STDMETHODCALLTYPE EventNotify(DWORD event, DWORD_PTR, DWORD second) override
    {
        if (m_events->active.load(std::memory_order_acquire) && event == MF_MEDIA_ENGINE_EVENT_ERROR) {
            auto error = static_cast<HRESULT>(second);
            m_events->error.store(FAILED(error) ? error : E_FAIL, std::memory_order_release);
        }
        return S_OK;
    }
private:
    std::atomic<ULONG> m_references { 1 };
    std::shared_ptr<Events> m_events;
};
}

// Owner-thread application adapter. It owns OS playback; callbacks retain only detached event state.
// Unbind the application texture from the native host before closing this playback session.
class Playback final {
public:
    Playback() = default;
    Playback(const Playback&) = delete;
    Playback& operator=(const Playback&) = delete;
    ~Playback() { close(); }

    HRESULT initialize()
    {
        if (m_owner && m_owner != GetCurrentThreadId())
            return RPC_E_WRONG_THREAD;
        close();
        m_owner = GetCurrentThreadId();
        auto status = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        if (FAILED(status) && status != RPC_E_CHANGED_MODE)
            return failedInitialization(status);
        m_ownsCom = SUCCEEDED(status);
        if (FAILED(status = MFStartup(MF_VERSION)))
            return failedInitialization(status);
        m_ownsMf = true;
        D3D_FEATURE_LEVEL level;
        status = D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
            D3D11_CREATE_DEVICE_VIDEO_SUPPORT | D3D11_CREATE_DEVICE_BGRA_SUPPORT,
            nullptr, 0, D3D11_SDK_VERSION, &m_device, &level, &m_context);
        if (FAILED(status))
            return failedInitialization(status);
        Microsoft::WRL::ComPtr<ID3D10Multithread> multithread;
        if (FAILED(status = m_context.As(&multithread)))
            return failedInitialization(status);
        multithread->SetMultithreadProtected(TRUE);
        UINT token = 0;
        if (FAILED(status = MFCreateDXGIDeviceManager(&token, &m_manager))
            || FAILED(status = m_manager->ResetDevice(m_device.Get(), token)))
            return failedInitialization(status);
        Microsoft::WRL::ComPtr<IMFAttributes> attributes;
        if (FAILED(status = MFCreateAttributes(&attributes, 4)))
            return failedInitialization(status);
        m_events = std::make_shared<Detail::Events>();
        m_notify.Attach(new Detail::Notify(m_events));
        if (FAILED(status = attributes->SetUnknown(MF_MEDIA_ENGINE_CALLBACK, m_notify.Get()))
            || FAILED(status = attributes->SetUINT32(MF_MEDIA_ENGINE_VIDEO_OUTPUT_FORMAT, DXGI_FORMAT_R8G8B8A8_UNORM))
            || FAILED(status = attributes->SetUnknown(MF_MEDIA_ENGINE_DXGI_MANAGER, m_manager.Get())))
            return failedInitialization(status);
        Microsoft::WRL::ComPtr<IMFMediaEngineClassFactory> factory;
        status = CoCreateInstance(CLSID_MFMediaEngineClassFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&factory));
        if (FAILED(status) || FAILED(status = factory->CreateInstance(0, attributes.Get(), &m_engine)))
            return failedInitialization(status);
        m_closedState = State::Ready;
        m_failure = S_OK;
        return S_OK;
    }

    HRESULT openFile(const wchar_t* path)
    {
        auto status = admitted();
        if (FAILED(status))
            return status;
        if (!path || !*path)
            return E_INVALIDARG;
        Microsoft::WRL::ComPtr<IMFByteStream> stream;
        status = MFCreateFile(MF_ACCESSMODE_READ, MF_OPENMODE_FAIL_IF_NOT_EXIST, MF_FILEFLAGS_NONE, path, &stream);
        if (FAILED(status))
            return fail(status);
        Microsoft::WRL::ComPtr<IMFMediaEngineEx> extended;
        if (FAILED(status = m_engine.As(&extended)))
            return fail(status);
        auto name = SysAllocString(path);
        if (!name)
            return fail(E_OUTOFMEMORY);
        status = extended->SetSourceFromByteStream(stream.Get(), name);
        SysFreeString(name);
        if (FAILED(status))
            return fail(status);
        m_stream = std::move(stream);
        m_opened = true;
        return FAILED(status = m_engine->Load()) ? fail(status) : status;
    }

    HRESULT play() { auto status = admitted(); return FAILED(status) ? status : m_engine->Play(); }
    HRESULT pause() { auto status = admitted(); return FAILED(status) ? status : m_engine->Pause(); }
    HRESULT seek(double seconds)
    {
        auto status = admitted();
        if (FAILED(status))
            return status;
        if (!std::isfinite(seconds) || seconds < 0)
            return E_INVALIDARG;
        return m_engine->SetCurrentTime(seconds);
    }

    Snapshot snapshot() const
    {
        Snapshot value;
        value.state = m_closedState;
        value.error = m_failure;
        if (!m_engine)
            return value;
        if (m_owner != GetCurrentThreadId()) {
            value.state = State::Failed;
            value.error = RPC_E_WRONG_THREAD;
            return value;
        }
        value.error = m_events->error.load(std::memory_order_acquire);
        if (FAILED(value.error) || FAILED(m_failure)) {
            value.state = State::Failed;
            if (SUCCEEDED(value.error))
                value.error = m_failure;
            return value;
        }
        value.position = m_engine->GetCurrentTime();
        value.duration = m_engine->GetDuration();
        value.ready = m_engine->GetReadyState() >= MF_MEDIA_ENGINE_READY_HAVE_CURRENT_DATA;
        value.seeking = !!m_engine->IsSeeking();
        value.hasAudio = !!m_engine->HasAudio();
        value.hasVideo = !!m_engine->HasVideo();
        value.state = !m_opened ? State::Ready : !value.ready ? State::Loading :
            m_engine->IsEnded() ? State::Ended : m_engine->IsPaused() ? State::Paused : State::Playing;
        return value;
    }

    HRESULT close()
    {
        if (m_owner && m_owner != GetCurrentThreadId())
            return RPC_E_WRONG_THREAD;
        if (m_events)
            m_events->active.store(false, std::memory_order_release);
        auto status = m_engine ? m_engine->Shutdown() : S_OK;
        m_engine.Reset();
        m_stream.Reset();
        m_notify.Reset();
        m_events.reset();
        m_manager.Reset();
        m_context.Reset();
        m_device.Reset();
        if (m_ownsMf)
            MFShutdown();
        if (m_ownsCom)
            CoUninitialize();
        m_ownsMf = false;
        m_ownsCom = false;
        m_opened = false;
        m_closedState = State::Closed;
        m_failure = S_OK;
        return status;
    }
    HRESULT cancel() { auto status = close(); if (SUCCEEDED(status)) m_closedState = State::Cancelled; return status; }

private:
    HRESULT admitted() const
    {
        if (m_owner && m_owner != GetCurrentThreadId())
            return RPC_E_WRONG_THREAD;
        return m_engine ? S_OK : MF_E_SHUTDOWN;
    }
    HRESULT fail(HRESULT value) { m_failure = value; return value; }
    HRESULT failedInitialization(HRESULT value) { close(); m_closedState = State::Unavailable; m_failure = value; return value; }
    DWORD m_owner { 0 };
    bool m_ownsCom { false };
    bool m_ownsMf { false };
    bool m_opened { false };
    State m_closedState { State::Closed };
    HRESULT m_failure { S_OK };
    std::shared_ptr<Detail::Events> m_events;
    Microsoft::WRL::ComPtr<Detail::Notify> m_notify;
    Microsoft::WRL::ComPtr<IMFMediaEngine> m_engine;
    Microsoft::WRL::ComPtr<IMFByteStream> m_stream;
    Microsoft::WRL::ComPtr<IMFDXGIDeviceManager> m_manager;
    Microsoft::WRL::ComPtr<ID3D11Device> m_device;
    Microsoft::WRL::ComPtr<ID3D11DeviceContext> m_context;
};
}
