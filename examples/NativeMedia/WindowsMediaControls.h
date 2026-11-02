#pragma once

#include "WindowsPlayback.h"
#include <SystemMediaTransportControlsInterop.h>
#include <roapi.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Media.h>
#include <algorithm>
#include <mutex>
#include <vector>

namespace RanvierNativeMedia {
namespace Detail {
enum class ActionKind { Play, Pause, Stop, Seek };
struct Action { ActionKind kind; double position { 0 }; };
struct Actions {
    std::mutex mutex;
    bool active { true };
    HRESULT error { S_OK };
    std::vector<Action> values;
    void push(Action action)
    {
        std::lock_guard guard(mutex);
        if (!active)
            return;
        if (values.size() == 32) {
            error = HRESULT_FROM_WIN32(ERROR_NOT_ENOUGH_QUOTA);
            return;
        }
        values.push_back(action);
    }
};
}

// OS callbacks enqueue commands. The application drains them on the playback/host owner thread.
class WindowsMediaControls final {
public:
    WindowsMediaControls() = default;
    WindowsMediaControls(const WindowsMediaControls&) = delete;
    WindowsMediaControls& operator=(const WindowsMediaControls&) = delete;
    ~WindowsMediaControls() { close(); }

    HRESULT initialize(HWND window, const wchar_t* title)
    {
        if (m_owner && m_owner != GetCurrentThreadId())
            return RPC_E_WRONG_THREAD;
        close();
        DWORD process = 0;
        if (!IsWindow(window) || !GetWindowThreadProcessId(window, &process) || process != GetCurrentProcessId()
            || GetAncestor(window, GA_ROOT) != window || !title || wcslen(title) > 4096)
            return E_INVALIDARG;
        m_owner = GetCurrentThreadId();
        APTTYPE apartment;
        APTTYPEQUALIFIER qualifier;
        auto apartmentStatus = CoGetApartmentType(&apartment, &qualifier);
        auto model = SUCCEEDED(apartmentStatus) && (apartment == APTTYPE_STA || apartment == APTTYPE_MAINSTA)
            ? RO_INIT_SINGLETHREADED : RO_INIT_MULTITHREADED;
        auto status = RoInitialize(model);
        if (FAILED(status))
            return status;
        m_ownsRo = true;
        try {
            using namespace winrt::Windows::Media;
            auto factory = winrt::get_activation_factory<SystemMediaTransportControls, ISystemMediaTransportControlsInterop>();
            winrt::check_hresult(factory->GetForWindow(window, winrt::guid_of<SystemMediaTransportControls>(), winrt::put_abi(m_controls)));
            m_actions = std::make_shared<Detail::Actions>();
            m_actions->values.reserve(32);
            auto actions = m_actions;
            m_button = m_controls.ButtonPressed([actions](auto const&, auto const& argument) {
                switch (argument.Button()) {
                case SystemMediaTransportControlsButton::Play: actions->push({ Detail::ActionKind::Play }); break;
                case SystemMediaTransportControlsButton::Pause: actions->push({ Detail::ActionKind::Pause }); break;
                case SystemMediaTransportControlsButton::Stop: actions->push({ Detail::ActionKind::Stop }); break;
                default: break;
                }
            });
            m_hasButton = true;
            m_seek = m_controls.PlaybackPositionChangeRequested([actions](auto const&, auto const& argument) {
                actions->push({ Detail::ActionKind::Seek, argument.RequestedPlaybackPosition().count() / 10000000.0 });
            });
            m_hasSeek = true;
            m_controls.IsPlayEnabled(true);
            m_controls.IsPauseEnabled(true);
            m_controls.IsStopEnabled(true);
            m_controls.IsEnabled(true);
            auto metadata = m_controls.DisplayUpdater();
            metadata.Type(MediaPlaybackType::Video);
            metadata.VideoProperties().Title(title);
            metadata.Update();
            return S_OK;
        } catch (const winrt::hresult_error& error) {
            auto result = error.code().value;
            close();
            return result;
        }
    }

    HRESULT publish(const Snapshot& value)
    {
        auto status = admitted();
        if (FAILED(status))
            return status;
        try {
            using namespace winrt::Windows::Media;
            auto state = value.state == State::Playing ? MediaPlaybackStatus::Playing :
                value.state == State::Paused ? MediaPlaybackStatus::Paused :
                value.state == State::Loading ? MediaPlaybackStatus::Changing :
                value.state == State::Closed || value.state == State::Cancelled ? MediaPlaybackStatus::Closed : MediaPlaybackStatus::Stopped;
            m_controls.PlaybackStatus(state);
            if (std::isfinite(value.duration) && value.duration > 0 && value.duration < 900000000000.0 && std::isfinite(value.position)) {
                SystemMediaTransportControlsTimelineProperties timeline;
                timeline.StartTime(winrt::Windows::Foundation::TimeSpan { 0 });
                timeline.EndTime(winrt::Windows::Foundation::TimeSpan { static_cast<int64_t>(value.duration * 10000000) });
                timeline.MinSeekTime(winrt::Windows::Foundation::TimeSpan { 0 });
                timeline.MaxSeekTime(timeline.EndTime());
                timeline.Position(winrt::Windows::Foundation::TimeSpan { static_cast<int64_t>(std::clamp(value.position, 0.0, value.duration) * 10000000) });
                m_controls.UpdateTimelineProperties(timeline);
            }
            return S_OK;
        } catch (const winrt::hresult_error& error) {
            return error.code().value;
        }
    }

    HRESULT drain(Playback& player)
    {
        auto status = admitted();
        if (FAILED(status))
            return status;
        std::vector<Detail::Action> actions;
        {
            std::lock_guard guard(m_actions->mutex);
            if (FAILED(m_actions->error))
                return m_actions->error;
            actions.swap(m_actions->values);
        }
        for (auto action : actions) {
            switch (action.kind) {
            case Detail::ActionKind::Play: status = player.play(); break;
            case Detail::ActionKind::Pause: status = player.pause(); break;
            case Detail::ActionKind::Stop: status = player.stop(); break;
            case Detail::ActionKind::Seek: status = player.seek(action.position); break;
            }
            if (FAILED(status)) {
                publish(player.snapshot());
                return status;
            }
        }
        return publish(player.snapshot());
    }

    HRESULT close()
    {
        if (m_owner && m_owner != GetCurrentThreadId())
            return RPC_E_WRONG_THREAD;
        if (m_actions) {
            std::lock_guard guard(m_actions->mutex);
            m_actions->active = false;
            m_actions->values.clear();
        }
        HRESULT result = S_OK;
        if (m_controls) {
            if (m_hasButton)
                m_controls.ButtonPressed(m_button);
            if (m_hasSeek)
                m_controls.PlaybackPositionChangeRequested(m_seek);
            try { m_controls.IsEnabled(false); } catch (const winrt::hresult_error& error) { result = error.code().value; }
        }
        m_controls = nullptr;
        m_actions.reset();
        m_hasButton = false;
        m_hasSeek = false;
        if (m_ownsRo)
            RoUninitialize();
        m_ownsRo = false;
        return result;
    }

private:
    HRESULT admitted() const { return m_owner && m_owner != GetCurrentThreadId() ? RPC_E_WRONG_THREAD : m_controls ? S_OK : RO_E_CLOSED; }
    DWORD m_owner { 0 };
    bool m_ownsRo { false };
    bool m_hasButton { false };
    bool m_hasSeek { false };
    std::shared_ptr<Detail::Actions> m_actions;
    winrt::Windows::Media::SystemMediaTransportControls m_controls { nullptr };
    winrt::event_token m_button { };
    winrt::event_token m_seek { };
};
}
