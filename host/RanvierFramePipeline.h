#pragma once
#include <array>
#include <cassert>
#include <cstdint>

// GPU ownership/completion proofs stay in the transport; this ledger never treats retirement as reuse.
class RvFramePipeline {
public:
    enum class Phase { Free, Producing, Ready, Leased, Retiring };
    struct Slot { Phase phase { Phase::Free }; uint64_t id { 0 }; };
    static constexpr int capacity = 3;
    std::array<Slot, capacity> slots;

    int reserve(uint64_t id)
    {
        if (!id || id <= lastSubmitted)
            return -1;
        for (int i = 0; i < capacity; ++i) {
            if (slots[i].phase == Phase::Free) {
                slots[i] = { Phase::Producing, id };
                lastSubmitted = id;
                return i;
            }
        }
        return -1;
    }
    bool accepts(uint64_t id) const { return id && id > lastSubmitted; }
    int newestReady() const
    {
        int newest = -1;
        uint64_t id = lastDelivered;
        for (int i = 0; i < capacity; ++i) {
            if (slots[i].phase == Phase::Ready && slots[i].id > id) {
                newest = i;
                id = slots[i].id;
            }
        }
        return newest;
    }
    void complete(int i) { assert(slots[i].phase == Phase::Producing); slots[i].phase = Phase::Ready; }
    void lease(int i) { assert(slots[i].phase == Phase::Ready); lastDelivered = slots[i].id; slots[i].phase = Phase::Leased; }
    void retire(int i) { assert(slots[i].phase != Phase::Free); slots[i].phase = Phase::Retiring; }
    void recycle(int i) { assert(slots[i].phase == Phase::Retiring); slots[i].phase = Phase::Free; }
private:
    uint64_t lastSubmitted { 0 };
    uint64_t lastDelivered { 0 };
};
