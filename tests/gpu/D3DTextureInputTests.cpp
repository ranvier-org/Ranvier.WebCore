#include "D3DFrameReadback.cpp"
#include <d3d11_1.h>
#include <d3d11on12.h>
#include <d3d12.h>

TEST_EXPORT int32_t native_input_create(void* devicePointer, uint32_t width, uint32_t height, int shared, void** output)
{
    if (!devicePointer || !output) return E_POINTER;
    *output = nullptr;
    auto* device = static_cast<ID3D11Device*>(devicePointer);
    D3D11_TEXTURE2D_DESC desc { };
    desc.Width = width; desc.Height = height; desc.MipLevels = 1; desc.ArraySize = 1;
    desc.Format = DXGI_FORMAT_R8G8B8A8_UNORM; desc.SampleDesc.Count = 1;
    desc.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
    desc.MiscFlags = shared ? D3D11_RESOURCE_MISC_SHARED_NTHANDLE | D3D11_RESOURCE_MISC_SHARED_KEYEDMUTEX : 0;
    ComPtr<ID3D11Texture2D> texture;
    auto result = device->CreateTexture2D(&desc, nullptr, &texture);
    if (SUCCEEDED(result)) *output = texture.Detach();
    return result;
}

TEST_EXPORT int32_t native_input_publish(void* texturePointer, float r, float g, float b, float alpha)
{
    auto* texture = static_cast<ID3D11Texture2D*>(texturePointer);
    ComPtr<ID3D11Device> device; texture->GetDevice(&device);
    ComPtr<ID3D11DeviceContext> context; device->GetImmediateContext(&context);
    ComPtr<IDXGIKeyedMutex> mutex;
    auto result = texture->QueryInterface(IID_PPV_ARGS(&mutex));
    if (FAILED(result)) return result;
    result = mutex->AcquireSync(0, 16);
    if (result != S_OK) return result;
    ComPtr<ID3D11RenderTargetView> view;
    result = device->CreateRenderTargetView(texture, nullptr, &view);
    if (SUCCEEDED(result)) {
        float color[] { r, g, b, alpha };
        context->ClearRenderTargetView(view.Get(), color);
        context->Flush();
    }
    auto released = mutex->ReleaseSync(1);
    return FAILED(result) ? result : released;
}

TEST_EXPORT void native_input_release(void* texturePointer)
{
    if (texturePointer) static_cast<ID3D11Texture2D*>(texturePointer)->Release();
}

TEST_EXPORT int32_t native_input_hold(void* texturePointer)
{
    ComPtr<IDXGIKeyedMutex> mutex;
    auto result = static_cast<ID3D11Texture2D*>(texturePointer)->QueryInterface(IID_PPV_ARGS(&mutex));
    return FAILED(result) ? result : mutex->AcquireSync(0, 0);
}

TEST_EXPORT int32_t native_input_unhold(void* texturePointer)
{
    ComPtr<IDXGIKeyedMutex> mutex;
    auto result = static_cast<ID3D11Texture2D*>(texturePointer)->QueryInterface(IID_PPV_ARGS(&mutex));
    return FAILED(result) ? result : mutex->ReleaseSync(0);
}

TEST_EXPORT int32_t native_input_quadrants(void* texturePointer)
{
    auto* texture = static_cast<ID3D11Texture2D*>(texturePointer);
    ComPtr<ID3D11Device> device; texture->GetDevice(&device);
    ComPtr<ID3D11DeviceContext> context; device->GetImmediateContext(&context);
    ComPtr<ID3D11DeviceContext1> context1;
    ComPtr<IDXGIKeyedMutex> mutex;
    auto result = context.As(&context1);
    if (FAILED(result) || FAILED(result = texture->QueryInterface(IID_PPV_ARGS(&mutex)))) return result;
    result = mutex->AcquireSync(0, 16);
    if (result != S_OK) return result;
    ComPtr<ID3D11RenderTargetView> view;
    result = device->CreateRenderTargetView(texture, nullptr, &view);
    if (SUCCEEDED(result)) {
        D3D11_TEXTURE2D_DESC desc { }; texture->GetDesc(&desc);
        const float colors[][4] { {1,0,0,1}, {0,1,0,1}, {0,0,1,1}, {1,1,0,1} };
        for (int y = 0; y < 2; ++y) for (int x = 0; x < 2; ++x) {
            D3D11_RECT rect { LONG(x*desc.Width/2), LONG(y*desc.Height/2), LONG((x+1)*desc.Width/2), LONG((y+1)*desc.Height/2) };
            context1->ClearView(view.Get(), colors[y*2+x], &rect, 1);
        }
        context->Flush();
    }
    auto released = mutex->ReleaseSync(1);
    return FAILED(result) ? result : released;
}

TEST_EXPORT int32_t native_input_removable(void* devicePointer, void** textureOutput, void** removalOutput)
{
    *textureOutput = nullptr; *removalOutput = nullptr;
    auto* device = static_cast<ID3D11Device*>(devicePointer);
    ComPtr<IDXGIDevice> dxgi; ComPtr<IDXGIAdapter> adapter;
    auto result = device->QueryInterface(IID_PPV_ARGS(&dxgi));
    if (FAILED(result) || FAILED(result = dxgi->GetAdapter(&adapter))) return result;
    ComPtr<ID3D12Device5> device12;
    result = D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_11_0, IID_PPV_ARGS(&device12));
    if (FAILED(result)) return result;
    D3D12_COMMAND_QUEUE_DESC desc { }; desc.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
    ComPtr<ID3D12CommandQueue> queue;
    result = device12->CreateCommandQueue(&desc, IID_PPV_ARGS(&queue));
    if (FAILED(result)) return result;
    IUnknown* queues[] { queue.Get() };
    ComPtr<ID3D11Device> device11; ComPtr<ID3D11DeviceContext> context;
    result = D3D11On12CreateDevice(device12.Get(), D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, queues, 1, 0, &device11, &context, nullptr);
    if (FAILED(result)) return result;
    result = native_input_create(device11.Get(), 32, 24, 1, textureOutput);
    if (SUCCEEDED(result)) *removalOutput = device12.Detach();
    return result;
}

TEST_EXPORT int32_t native_input_remove(void* removalPointer, void* texturePointer, int32_t* reasons)
{
    auto* device12 = static_cast<ID3D12Device5*>(removalPointer);
    ComPtr<ID3D11Device> device11; static_cast<ID3D11Texture2D*>(texturePointer)->GetDevice(&device11);
    reasons[0] = device12->GetDeviceRemovedReason(); reasons[1] = device11->GetDeviceRemovedReason();
    device12->RemoveDevice();
    reasons[2] = device12->GetDeviceRemovedReason(); reasons[3] = device11->GetDeviceRemovedReason();
    return S_OK;
}

TEST_EXPORT void native_input_removal_release(void* pointer)
{
    if (pointer) static_cast<ID3D12Device5*>(pointer)->Release();
}

TEST_EXPORT void* native_input_device(void* texturePointer)
{
    ID3D11Device* device = nullptr;
    static_cast<ID3D11Texture2D*>(texturePointer)->GetDevice(&device);
    return device;
}
