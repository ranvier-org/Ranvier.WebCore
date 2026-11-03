#include "../../examples/NativeMedia/WindowsPlayback.h"
#include <memory>

using namespace RanvierNativeMedia;
using Microsoft::WRL::ComPtr;
struct Probe {
    Playback player;
    Frame frame;
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> context;
};
struct ProbeSnapshot {
    int32_t state;
    HRESULT error;
    double position;
    double duration;
    int32_t ready;
    int32_t seeking;
    int32_t audio;
    int32_t video;
};
static_assert(sizeof(ProbeSnapshot) == 40);

extern "C" {
__declspec(dllexport) HRESULT media_create(const wchar_t* path, Probe** output)
{
    if (!output)
        return E_POINTER;
    *output = nullptr;
    auto probe = std::make_unique<Probe>();
    auto status = probe->player.initialize();
    if (FAILED(status) || FAILED(status = probe->player.openFile(path)))
        return status;
    probe->device = probe->player.device();
    probe->device->GetImmediateContext(&probe->context);
    *output = probe.release();
    return S_OK;
}
__declspec(dllexport) void media_destroy(Probe* probe) { delete probe; }
__declspec(dllexport) HRESULT media_close(Probe* probe) { return probe ? probe->player.close() : E_POINTER; }
__declspec(dllexport) HRESULT media_play(Probe* probe) { return probe ? probe->player.play() : E_POINTER; }
__declspec(dllexport) HRESULT media_pause(Probe* probe) { return probe ? probe->player.pause() : E_POINTER; }
__declspec(dllexport) HRESULT media_seek(Probe* probe, double position) { return probe ? probe->player.seek(position) : E_POINTER; }
__declspec(dllexport) ID3D11Device* media_device(Probe* probe) { return probe ? probe->device.Get() : nullptr; }
__declspec(dllexport) HRESULT media_snapshot(Probe* probe, ProbeSnapshot* output)
{
    if (!probe || !output)
        return E_POINTER;
    auto value = probe->player.snapshot();
    *output = { static_cast<int32_t>(value.state), value.error, value.position, value.duration,
        value.ready, value.seeking, value.hasAudio, value.hasVideo };
    return S_OK;
}
__declspec(dllexport) HRESULT media_next(Probe* probe, ID3D11Texture2D** texture, LONGLONG* time)
{
    if (!probe || !texture || !time)
        return E_POINTER;
    *texture = nullptr;
    *time = 0;
    Frame frame;
    auto status = probe->player.nextFrame(frame);
    if (status == S_OK) {
        probe->frame = std::move(frame);
        *texture = probe->frame.texture.Get();
        *time = probe->frame.presentationTime;
    }
    return status;
}
__declspec(dllexport) HRESULT media_republish(Probe* probe)
{
    if (!probe || !probe->frame.texture)
        return E_POINTER;
    ComPtr<IDXGIKeyedMutex> mutex;
    auto status = probe->frame.texture.As(&mutex);
    if (FAILED(status))
        return status;
    status = mutex->AcquireSync(0, 100);
    if (status != S_OK)
        return status == WAIT_TIMEOUT ? HRESULT_FROM_WIN32(WAIT_TIMEOUT) : status;
    probe->context->Flush();
    return mutex->ReleaseSync(1);
}
__declspec(dllexport) HRESULT media_readback(Probe* probe, ID3D11Texture2D* texture, unsigned char* output, uint32_t capacity, uint32_t width, uint32_t height)
{
    if (!probe || !texture || !output || !width || !height || width > 16384 || height > 16384 || capacity != static_cast<uint64_t>(width) * height * 4)
        return E_INVALIDARG;
    D3D11_TEXTURE2D_DESC description;
    texture->GetDesc(&description);
    if (description.Width != width || description.Height != height
        || (description.Format != DXGI_FORMAT_R8G8B8A8_UNORM && description.Format != DXGI_FORMAT_B8G8R8A8_UNORM))
        return E_INVALIDARG;
    bool bgra = description.Format == DXGI_FORMAT_B8G8R8A8_UNORM;
    description.Usage = D3D11_USAGE_STAGING;
    description.BindFlags = 0;
    description.MiscFlags = 0;
    description.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    ComPtr<ID3D11Texture2D> staging;
    auto status = probe->device->CreateTexture2D(&description, nullptr, &staging);
    if (FAILED(status))
        return status;
    probe->context->CopyResource(staging.Get(), texture);
    D3D11_MAPPED_SUBRESOURCE mapped;
    if (FAILED(status = probe->context->Map(staging.Get(), 0, D3D11_MAP_READ, 0, &mapped)))
        return status;
    for (uint32_t row = 0; row < height; ++row) {
        auto input = static_cast<unsigned char*>(mapped.pData) + static_cast<size_t>(row) * mapped.RowPitch;
        auto destination = output + static_cast<size_t>(row) * width * 4;
        for (uint32_t column = 0; column < width; ++column) {
            destination[column * 4] = input[column * 4 + (bgra ? 2 : 0)];
            destination[column * 4 + 1] = input[column * 4 + 1];
            destination[column * 4 + 2] = input[column * 4 + (bgra ? 0 : 2)];
            destination[column * 4 + 3] = input[column * 4 + 3];
        }
    }
    probe->context->Unmap(staging.Get(), 0);
    probe->context->Flush();
    return S_OK;
}
}
