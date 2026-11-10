#pragma once
#include "RanvierFramePipeline.h"
#include "RanvierWebCoreD3D11.h"
#include "RanvierGpuRetirement.h"
#if defined(_WIN32) && RANVIER_COMPOSITING
#include <d3d11.h>
#include <wrl/client.h>

struct RvD3D11Pipeline {
    RvFramePipeline state;
    std::array<std::shared_ptr<RvD3D11Surface>, RvFramePipeline::capacity> surfaces;
    Microsoft::WRL::ComPtr<ID3D11Device> device;
    uint64_t generation { 1 };
    std::array<uint64_t, RvFramePipeline::capacity> generations { };

    bool poll()
    {
        RvGpuRetirement::collect();
        bool healthy = device && device->GetDeviceRemovedReason() == S_OK;
        for (int i = 0; i < RvFramePipeline::capacity; ++i) {
            auto phase = state.slots[i].phase;
            if (phase != RvFramePipeline::Phase::Producing && phase != RvFramePipeline::Phase::Retiring)
                continue;
            auto ready = phase == RvFramePipeline::Phase::Producing
                ? surfaces[i]->tryAcquireConsumer() : surfaces[i]->tryRetire();
            if (ready == RvGpuReadiness::Ready) {
                if (phase == RvFramePipeline::Phase::Producing)
                    state.complete(i);
                else
                    state.recycle(i);
            } else if (ready == RvGpuReadiness::Failed) {
                healthy = false;
                state.retire(i);
                surfaces[i].reset();
                state.recycle(i);
            }
        }
        return healthy;
    }
    void discard(int i)
    {
        assert(state.slots[i].phase == RvFramePipeline::Phase::Ready);
        surfaces[i]->releaseConsumer(true);
        state.retire(i);
    }
    int freeSlot() const
    {
        for (int i = 0; i < RvFramePipeline::capacity; ++i) {
            if (state.slots[i].phase == RvFramePipeline::Phase::Free)
                return i;
        }
        return -1;
    }
};
#endif
