#define NOMINMAX
#include <windows.h>
#include <d3d11.h>
#include <wrl/client.h>
#include <array>
#include <cstdint>
#include <cstdio>
#include <stdexcept>

extern "C" int32_t gpu_readback_create(void**);
extern "C" void gpu_readback_destroy(void*);
extern "C" int32_t gpu_readback_rgba(void*, void*, uint8_t*, uint64_t, uint32_t, uint32_t);
using Microsoft::WRL::ComPtr;

static void require(bool condition, const char* label)
{
    if (!condition)
        throw std::runtime_error(label);
}

int main() try
{
    void* pointer = nullptr;
    require(gpu_readback_create(&pointer) == S_OK && pointer, "hardware device");
    ComPtr<ID3D11Device> device;
    device.Attach(static_cast<ID3D11Device*>(pointer));
    const std::array<uint8_t, 24> expected {
        255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255,
        17, 34, 51, 255, 64, 32, 16, 128, 1, 2, 3, 4
    };
    for (bool bgra : { false, true }) {
        std::array<uint8_t, 40> initial {};
        for (size_t y = 0; y < 2; ++y) {
            for (size_t x = 0; x < 3; ++x) {
                auto* input = initial.data() + y * 20 + x * 4;
                const auto* rgba = expected.data() + (y * 3 + x) * 4;
                input[0] = rgba[bgra ? 2 : 0];
                input[1] = rgba[1];
                input[2] = rgba[bgra ? 0 : 2];
                input[3] = rgba[3];
            }
        }
        D3D11_TEXTURE2D_DESC description {};
        description.Width = 3;
        description.Height = 2;
        description.MipLevels = 1;
        description.ArraySize = 1;
        description.Format = bgra ? DXGI_FORMAT_B8G8R8A8_UNORM : DXGI_FORMAT_R8G8B8A8_UNORM;
        description.SampleDesc.Count = 1;
        description.Usage = D3D11_USAGE_DEFAULT;
        description.BindFlags = D3D11_BIND_SHADER_RESOURCE;
        D3D11_SUBRESOURCE_DATA data { initial.data(), 20, 0 };
        ComPtr<ID3D11Texture2D> texture;
        require(SUCCEEDED(device->CreateTexture2D(&description, &data, &texture)), "known texture");
        std::array<uint8_t, 24> output {};
        require(gpu_readback_rgba(device.Get(), texture.Get(), output.data(), output.size(), 3, 2) == S_OK,
            "padded rows read back");
        require(output == expected, "all RGBA channels, both rows and alpha preserved");
        require(gpu_readback_rgba(device.Get(), texture.Get(), output.data(), 23, 3, 2) == E_INVALIDARG,
            "short output rejected");
        require(gpu_readback_rgba(device.Get(), texture.Get(), output.data(), output.size(), 2, 2) == E_INVALIDARG,
            "wrong dimensions rejected");
        void* other = nullptr;
        require(gpu_readback_create(&other) == S_OK && other, "second hardware device");
        auto status = gpu_readback_rgba(other, texture.Get(), output.data(), output.size(), 3, 2);
        gpu_readback_destroy(other);
        require(status == E_INVALIDARG, "texture from another device rejected");
    }
    std::puts("PASS hardware D3D readback: RGBA/BGRA, padded rows, alpha, size and device ownership");
    return 0;
} catch (const std::exception& error) {
    std::fprintf(stderr, "FAIL D3D readback: %s\n", error.what());
    return 1;
}
