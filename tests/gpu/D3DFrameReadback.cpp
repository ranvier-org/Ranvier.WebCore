#define NOMINMAX
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <cstdint>

using Microsoft::WRL::ComPtr;
#define TEST_EXPORT extern "C" __declspec(dllexport)

TEST_EXPORT int32_t gpu_readback_create(void** output)
{
    if (!output)
        return E_POINTER;
    *output = nullptr;
    ComPtr<ID3D11Device> device;
    auto result = D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
        D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, D3D11_SDK_VERSION, &device, nullptr, nullptr);
    if (FAILED(result))
        return result;
    ComPtr<IDXGIDevice> dxgi;
    ComPtr<IDXGIAdapter> adapter;
    ComPtr<IDXGIAdapter1> adapter1;
    DXGI_ADAPTER_DESC1 description {};
    if (FAILED(result = device.As(&dxgi)) || FAILED(result = dxgi->GetAdapter(&adapter))
        || FAILED(result = adapter.As(&adapter1)) || FAILED(result = adapter1->GetDesc1(&description)))
        return result;
    if (description.Flags & DXGI_ADAPTER_FLAG_SOFTWARE)
        return DXGI_ERROR_UNSUPPORTED;
    *output = device.Detach();
    return S_OK;
}

TEST_EXPORT void gpu_readback_destroy(void* device)
{
    if (device)
        static_cast<ID3D11Device*>(device)->Release();
}

TEST_EXPORT int32_t gpu_readback_rgba(void* devicePointer, void* texturePointer, uint8_t* output,
    uint64_t capacity, uint32_t width, uint32_t height)
{
    if (!devicePointer || !texturePointer || !output || !width || !height
        || capacity < uint64_t(width) * height * 4)
        return E_INVALIDARG;
    auto* device = static_cast<ID3D11Device*>(devicePointer);
    auto* texture = static_cast<ID3D11Texture2D*>(texturePointer);
    ComPtr<ID3D11Device> owner;
    texture->GetDevice(&owner);
    if (owner.Get() != device)
        return E_INVALIDARG;
    D3D11_TEXTURE2D_DESC description {};
    texture->GetDesc(&description);
    if (description.Width != width || description.Height != height || description.ArraySize != 1
        || description.MipLevels != 1 || description.SampleDesc.Count != 1
        || (description.Format != DXGI_FORMAT_R8G8B8A8_UNORM && description.Format != DXGI_FORMAT_B8G8R8A8_UNORM))
        return E_INVALIDARG;
    bool bgra = description.Format == DXGI_FORMAT_B8G8R8A8_UNORM;
    description.Usage = D3D11_USAGE_STAGING;
    description.BindFlags = 0;
    description.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    description.MiscFlags = 0;
    ComPtr<ID3D11Texture2D> staging;
    auto result = device->CreateTexture2D(&description, nullptr, &staging);
    if (FAILED(result))
        return result;
    ComPtr<ID3D11DeviceContext> context;
    device->GetImmediateContext(&context);
    context->CopyResource(staging.Get(), texture);
    D3D11_MAPPED_SUBRESOURCE mapped {};
    result = context->Map(staging.Get(), 0, D3D11_MAP_READ, 0, &mapped);
    if (FAILED(result))
        return result;
    for (uint32_t y = 0; y < height; ++y) {
        auto* row = static_cast<const uint8_t*>(mapped.pData) + size_t(y) * mapped.RowPitch;
        for (uint32_t x = 0; x < width; ++x) {
            auto* target = output + (size_t(y) * width + x) * 4;
            auto* pixel = row + size_t(x) * 4;
            target[0] = pixel[bgra ? 2 : 0];
            target[1] = pixel[1];
            target[2] = pixel[bgra ? 0 : 2];
            target[3] = pixel[3];
        }
    }
    context->Unmap(staging.Get(), 0);
    return S_OK;
}
