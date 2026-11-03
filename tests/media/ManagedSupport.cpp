#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <mmdeviceapi.h>
#include <audiopolicy.h>
#include <endpointvolume.h>
#include <shobjidl.h>
#include <winrt/Windows.Media.Control.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <string>
#include <cstring>
#include <bit>
#include <cstdint>
#include <cstdio>

using Microsoft::WRL::ComPtr;
static std::wstring applicationId() { return L"Ranvier.NativeMedia.Managed." + std::to_wstring(GetCurrentProcessId()); }

extern "C" __declspec(dllexport) HRESULT media_test_identity()
{
    return SetCurrentProcessExplicitAppUserModelID(applicationId().c_str());
}
extern "C" __declspec(dllexport) HRESULT media_test_os_action(int action, double seconds)
{
    try {
        using namespace winrt::Windows::Media::Control;
        auto manager = GlobalSystemMediaTransportControlsSessionManager::RequestAsync().get();
        for (auto session : manager.GetSessions()) {
            if (session.SourceAppUserModelId() != applicationId()) continue;
            bool accepted = action == 0 ? session.TryPlayAsync().get() :
                action == 1 ? session.TryPauseAsync().get() :
                action == 2 ? session.TryStopAsync().get() :
                action == 3 ? session.TryChangePlaybackPositionAsync(static_cast<int64_t>(seconds * 10000000)).get() : false;
            return accepted ? S_OK : S_FALSE;
        }
        return HRESULT_FROM_WIN32(ERROR_NOT_FOUND);
    } catch (const winrt::hresult_error& error) { return error.code().value; }
}
extern "C" __declspec(dllexport) HRESULT media_test_audio(float* peak, int* active)
{
    if (!peak || !active) return E_POINTER;
    *peak = 0; *active = 0;
    ComPtr<IMMDeviceEnumerator> devices;
    auto status = CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&devices));
    ComPtr<IMMDevice> endpoint;
    if (SUCCEEDED(status)) status = devices->GetDefaultAudioEndpoint(eRender, eMultimedia, &endpoint);
    if (FAILED(status)) return status;
    ComPtr<IAudioSessionManager2> sessions;
    if (FAILED(status = endpoint->Activate(__uuidof(IAudioSessionManager2), CLSCTX_ALL, nullptr, &sessions))) return status;
    ComPtr<IAudioSessionEnumerator> enumeration;
    if (FAILED(status = sessions->GetSessionEnumerator(&enumeration))) return status;
    int count = 0;
    if (FAILED(status = enumeration->GetCount(&count))) return status;
    for (int index = 0; index < count; ++index) {
        ComPtr<IAudioSessionControl> control;
        ComPtr<IAudioSessionControl2> own;
        DWORD process = 0;
        if (FAILED(enumeration->GetSession(index, &control)) || FAILED(control.As(&own))
            || FAILED(own->GetProcessId(&process)) || process != GetCurrentProcessId()) continue;
        AudioSessionState state;
        ComPtr<IAudioMeterInformation> meter;
        if (FAILED(status = own->GetState(&state)) || FAILED(status = own.As(&meter))) return status;
        float current = 0;
        if (FAILED(status = meter->GetPeakValue(&current))) return status;
        *peak = (std::max)(*peak, current);
        *active |= state == AudioSessionStateActive;
    }
    return S_OK;
}

extern "C" __declspec(dllexport) HRESULT media_test_render(void* host, void* inputTexture,
    unsigned char* output, uint32_t capacity, int32_t* width, int32_t* height)
{
    if (!host || !inputTexture || !output || !width || !height) return E_POINTER;
    auto module = GetModuleHandleW(L"RanvierWebCoreHost.dll");
    if (!module) return HRESULT_FROM_WIN32(ERROR_MOD_NOT_FOUND);
    using Acquire = int32_t(*)(void*, void*, void**);
    using Info = int32_t(*)(void*, void**, int32_t*, int32_t*, int32_t*);
    using Release = int32_t(*)(void*);
    auto acquire = std::bit_cast<Acquire>(GetProcAddress(module, "rv_host_acquire_d3d11_frame"));
    auto info = std::bit_cast<Info>(GetProcAddress(module, "rv_gpu_frame_info"));
    auto release = std::bit_cast<Release>(GetProcAddress(module, "rv_gpu_frame_release"));
    if (!acquire || !info || !release) return HRESULT_FROM_WIN32(ERROR_PROC_NOT_FOUND);
    ComPtr<ID3D11Device> device;
    static_cast<ID3D11Texture2D*>(inputTexture)->GetDevice(&device);
    void* frame = nullptr;
    auto code = acquire(host, device.Get(), &frame);
    if (code || !frame) {
        std::fprintf(stderr, "MEDIA_READBACK_ACQUIRE_STATUS=%d FRAME=%p CONSUMER_DEVICE=%p\n", code, frame, device.Get());
        return E_FAIL;
    }
    struct Lease { void* frame; Release release; ~Lease() { release(frame); } } lease { frame, release };
    void* texture = nullptr;
    int32_t format = 0;
    if (info(frame, &texture, width, height, &format) || !texture || *width <= 0 || *height <= 0
        || static_cast<uint64_t>(*width) * *height * 4 != capacity) return E_INVALIDARG;
    auto source = static_cast<ID3D11Texture2D*>(texture);
    D3D11_TEXTURE2D_DESC description;
    source->GetDesc(&description);
    bool bgra = description.Format == DXGI_FORMAT_B8G8R8A8_UNORM;
    if (!bgra && description.Format != DXGI_FORMAT_R8G8B8A8_UNORM) return E_INVALIDARG;
    description.Usage = D3D11_USAGE_STAGING;
    description.BindFlags = description.MiscFlags = 0;
    description.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    ComPtr<ID3D11Texture2D> staging;
    auto status = device->CreateTexture2D(&description, nullptr, &staging);
    if (FAILED(status)) return status;
    ComPtr<ID3D11DeviceContext> context;
    device->GetImmediateContext(&context);
    context->CopyResource(staging.Get(), source);
    D3D11_MAPPED_SUBRESOURCE mapped;
    if (FAILED(status = context->Map(staging.Get(), 0, D3D11_MAP_READ, 0, &mapped))) return status;
    for (int32_t y = 0; y < *height; ++y) {
        auto row = static_cast<const uint8_t*>(mapped.pData) + static_cast<size_t>(y) * mapped.RowPitch;
        auto destination = output + static_cast<size_t>(y) * *width * 4;
        for (int32_t x = 0; x < *width; ++x) {
            destination[x * 4] = row[x * 4 + (bgra ? 2 : 0)];
            destination[x * 4 + 1] = row[x * 4 + 1];
            destination[x * 4 + 2] = row[x * 4 + (bgra ? 0 : 2)];
            destination[x * 4 + 3] = row[x * 4 + 3];
        }
    }
    context->Unmap(staging.Get(), 0);
    return S_OK;
}
