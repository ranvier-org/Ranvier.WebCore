#pragma once
#include "RanvierFramePipeline.h"
#include <deque>
#include <memory>
#include <algorithm>

// Surface readiness: 0 completed, 1 pending, -1 failed. A failed fence never proves safe reuse.
template<class Surface> struct RvPortablePipeline {
    RvFramePipeline state;
    std::array<std::shared_ptr<Surface>, RvFramePipeline::capacity> surfaces;
    std::array<uint64_t, RvFramePipeline::capacity> generations { };
    uint64_t generation { 1 };
    void* consumer { nullptr };
    bool failed { false };

    struct Retired { std::shared_ptr<Surface> surface; bool producing; };
    static std::deque<Retired>& retired()
    {
        // GL cleanup must not run on the CRT teardown thread.
        static auto* entries = new std::deque<Retired>;
        return *entries;
    }
    static void collect()
    {
        auto& entries = retired();
        auto count = std::min<size_t>(entries.size(), 64);
        while (count--) {
            auto entry = std::move(entries.front());
            entries.pop_front();
            auto ready = entry.producing ? entry.surface->producerReady() : entry.surface->retirementReady();
            if (ready != 0)
                entries.push_back(std::move(entry));
        }
    }
    ~RvPortablePipeline()
    {
        for (int i = 0; i < RvFramePipeline::capacity; ++i) {
            auto phase = state.slots[i].phase;
            assert(phase != RvFramePipeline::Phase::Leased); // Leases retain the pool.
            if (surfaces[i] && (phase == RvFramePipeline::Phase::Producing || phase == RvFramePipeline::Phase::Retiring))
                retired().push_back({ std::move(surfaces[i]), phase == RvFramePipeline::Phase::Producing });
        }
    }
    bool poll()
    {
        collect();
        for (int i = 0; i < RvFramePipeline::capacity; ++i) {
            auto phase = state.slots[i].phase;
            if (phase != RvFramePipeline::Phase::Producing && phase != RvFramePipeline::Phase::Retiring)
                continue;
            auto ready = phase == RvFramePipeline::Phase::Producing ? surfaces[i]->producerReady() : surfaces[i]->retirementReady();
            if (ready < 0)
                failed = true;
            else if (!ready) {
                if (phase == RvFramePipeline::Phase::Producing)
                    state.complete(i);
                else
                    state.recycle(i);
            }
        }
        return !failed;
    }
    void discard(int i)
    {
        assert(state.slots[i].phase == RvFramePipeline::Phase::Ready);
        surfaces[i]->discardReady();
        state.retire(i);
        state.recycle(i); // Producer completed; this frame was never given to a consumer.
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
