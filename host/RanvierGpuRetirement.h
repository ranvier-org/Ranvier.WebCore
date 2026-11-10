#pragma once
#include "RanvierGpuMemoryBudget.h"
#if defined(_WIN32) && RANVIER_COMPOSITING
#include <d3d11.h>
#include <wrl/client.h>
#include <deque>

// Retain both storage and its budget charge until submitted GPU commands finish. Owner thread only.
class RvGpuRetirement {
    template<class T> using ComPtr = Microsoft::WRL::ComPtr<T>;
    struct Completion {
        ComPtr<ID3D11Device> device;
        ComPtr<ID3D11DeviceContext> context;
        ComPtr<ID3D11Query> query;
        void start(ID3D11Device* given)
        {
            if (!given)
                return;
            device = given;
            device->GetImmediateContext(&context);
            D3D11_QUERY_DESC desc { D3D11_QUERY_EVENT, 0 };
            if (SUCCEEDED(device->CreateQuery(&desc, &query))) {
                context->End(query.Get());
                context->Flush();
            }
        }
        bool ready() const
        {
            if (!device || device->GetDeviceRemovedReason() != S_OK)
                return true;
            return query && context->GetData(query.Get(), nullptr, 0, D3D11_ASYNC_GETDATA_DONOTFLUSH) == S_OK;
        }
    };
    struct Entry {
        size_t bytes;
        Completion producer;
        Completion consumer;
        ComPtr<IUnknown> first;
        ComPtr<IUnknown> second;
    };
    static std::deque<Entry>& pending()
    {
        // The process can end after its final owner thread exits. Do not run GL/D3D cleanup on a CRT teardown thread.
        static auto* queue = new std::deque<Entry>;
        return *queue;
    }
public:
    static void collect()
    {
        auto& queue = pending();
        auto count = std::min<size_t>(queue.size(), 64);
        for (size_t i = 0; i < count; ++i) {
            auto entry = std::move(queue.front());
            queue.pop_front();
            if (entry.producer.ready() && entry.consumer.ready())
                RvGpuMemoryBudget::release(entry.bytes);
            else
                queue.push_back(std::move(entry));
        }
    }
    static void retire(size_t bytes, ID3D11Device* producer, IUnknown* first,
        ID3D11Device* consumer = nullptr, IUnknown* second = nullptr)
    {
        if (!bytes)
            return;
        if (!first && !second) {
            RvGpuMemoryBudget::release(bytes);
            return;
        }
        Entry entry { };
        entry.bytes = bytes;
        entry.first = first;
        entry.second = second;
        entry.producer.start(producer);
        if (consumer != producer)
            entry.consumer.start(consumer);
        pending().push_back(std::move(entry));
        collect();
    }
};
#endif
