#pragma once

#include "RanvierWebCoreAbi.h"

typedef struct RvMacSpikeFrame RvMacSpikeFrame;

#ifdef __cplusplus
extern "C" {
#endif

/* Experimental exports exist only in the opt-in Mac GPU spike. No shipping ABI guarantee.
 * Each frame owns an independent surface. Acquisition waits for producer completion.
 * Keep the frame alive until the consumer's GPU work has completed, including after host destruction. */
RV_EXPORT int32_t rv_mac_spike_acquire_frame(RvHost*, RvMacSpikeFrame**);
/* iosurface is borrowed until frame release. Dimensions are backing pixels; format is premultiplied BGRA8. */
RV_EXPORT int32_t rv_mac_spike_frame_info(RvMacSpikeFrame*, void** iosurface, int32_t* width, int32_t* height);
RV_EXPORT int32_t rv_mac_spike_frame_release(RvMacSpikeFrame*);
/* Borrowed process-lifetime EGL/GL renderer identity; NULL indicates an uninitialized producer. */
RV_EXPORT const char* rv_mac_spike_identity(void);
RV_EXPORT int32_t rv_mac_spike_counters(RvHost*, uint64_t* gpu_frames, uint64_t* readback_frames, uint64_t* base_paints);
/* Opt-in input: a valid nonplanar premultiplied BGRA8 IOSurfaceRef, retained until replacement/unbind (NULL),
 * document/host destruction, or next-frame target removal. Complete producer GPU work before binding/notifying;
 * do not write during acquire. Acquire finishes the input GPU read. flipY is 0 or 1; failed replacement keeps the old binding.
 * Contract fixture: tests/gpu/mac/texture_input.mm. */
RV_EXPORT int32_t rv_mac_spike_bind_iosurface(RvHost*, RvNode* target, void* iosurface, int32_t flipY);

#ifdef __cplusplus
}

#if defined(RANVIER_MAC_GPU_SPIKE) && RANVIER_MAC_GPU_SPIKE
#include <memory>

void* rvMacSpikeDisplay();
const char* rvMacSpikeIdentity();

class RvMacSpikeSurface {
public:
    static std::unique_ptr<RvMacSpikeSurface> create(int width, int height, bool (*makeCurrent)(), bool bounded = false);
    static bool supportsPipeline();
    ~RvMacSpikeSurface();
    unsigned framebuffer() const;
    bool finishProducer();
    bool beginProducer();
    bool submitProducer(void*);
    int producerReady();
    int retirementReady() { return 0; } // Caller releases only after its Metal completion proof.
    void discardReady() { }
    bool matches(int width, int height) const;
    void* surface() const;
    int width() const;
    int height() const;
private:
    struct State;
    explicit RvMacSpikeSurface(std::unique_ptr<State>);
    std::unique_ptr<State> state;
};

class RvMacSpikeInputSurface {
public:
    static std::unique_ptr<RvMacSpikeInputSurface> create(void* iosurface, bool (*makeCurrent)());
    ~RvMacSpikeInputSurface();
    bool begin();
    bool end();
    unsigned texture() const;
private:
    struct State;
    explicit RvMacSpikeInputSurface(std::unique_ptr<State>);
    std::unique_ptr<State> state;
};
#endif
#endif
