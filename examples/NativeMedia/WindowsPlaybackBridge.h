#pragma once
#include <stdint.h>
#include <stddef.h>

#ifdef RANVIER_MEDIA_BUILD
#define RM_API __declspec(dllexport)
#else
#define RM_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif
typedef struct RmSession RmSession;
typedef struct RmFrame RmFrame;
typedef struct RmSnapshot {
    uint32_t size;
    int32_t state;
    int32_t error;
    uint32_t flags;
    double position_seconds;
    double duration_seconds;
} RmSnapshot;
typedef struct RmFrameInfo {
    uint32_t size;
    uint32_t width;
    uint32_t height;
    uint32_t reserved;
    void* texture;
    int64_t presentation_time_100ns;
} RmFrameInfo;

/* Optional application DLL, independent of the renderer ABI. All calls use the creating thread.
 * HRESULTs are preserved; create reports the provider state even on failure (Unavailable=8).
 * Snapshot flags: ready=1, seeking=2, audio=4, video=8. State values match WindowsPlayback.h. */
RM_API int32_t ranvier_media_create(RmSession** output, int32_t* state);
RM_API int32_t ranvier_media_open(RmSession*, const wchar_t* local_path);
RM_API int32_t ranvier_media_play(RmSession*);
RM_API int32_t ranvier_media_pause(RmSession*);
RM_API int32_t ranvier_media_stop(RmSession*);
RM_API int32_t ranvier_media_seek(RmSession*, double seconds);
RM_API int32_t ranvier_media_cancel(RmSession*);
RM_API int32_t ranvier_media_snapshot(RmSession*, RmSnapshot* output);
/* A frame owns the provider/texture through composition. Only one publication may be outstanding.
 * Bind and notify using the existing View API, finish/release the composition lease, then unbind
 * before releasing this frame. S_FALSE means no decoded frame. Release reclaims an unused key1. */
RM_API int32_t ranvier_media_next_frame(RmSession*, RmFrame** output);
RM_API int32_t ranvier_media_republish(RmSession*, RmFrame** output);
RM_API int32_t ranvier_media_frame_info(RmFrame*, RmFrameInfo* output);
RM_API int32_t ranvier_media_frame_release(RmFrame** frame);
RM_API int32_t ranvier_media_controls_attach(RmSession*, void* own_window, const wchar_t* title);
RM_API int32_t ranvier_media_controls_drain(RmSession*);
RM_API int32_t ranvier_media_controls_detach(RmSession*);
/* Idempotent for a null handle. Revokes OS actions and pauses immediately; an outstanding frame
 * retains the provider until frame release. Wrong-thread release leaves the handle unchanged. */
RM_API int32_t ranvier_media_release(RmSession** session);
#ifdef __cplusplus
}
#endif
