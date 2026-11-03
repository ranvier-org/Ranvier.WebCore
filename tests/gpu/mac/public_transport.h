#pragma once

#if defined(RANVIER_MAC_PUBLIC_TRANSPORT) && RANVIER_MAC_PUBLIC_TRANSPORT
inline int32_t macPublicFrameInfo(RvGpuFrame* frame, void** surface, int32_t* width, int32_t* height)
{
    int32_t format = 0;
    auto result = rv_gpu_frame_info(frame, surface, width, height, &format);
    return result != RV_OK || format == RV_GPU_BGRA8_PREMULTIPLIED ? result : RV_ERR_UNSUPPORTED;
}

#define RvMacSpikeFrame RvGpuFrame
#define rv_mac_spike_acquire_frame rv_host_acquire_iosurface_frame
#define rv_mac_spike_frame_info macPublicFrameInfo
#define rv_mac_spike_frame_release rv_gpu_frame_release
#define rv_mac_spike_bind_iosurface rv_host_bind_iosurface
#endif
