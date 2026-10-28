# The slim flavor with the GPU code kept: ANGLE, Skia's Ganesh backend, TextureMapper and WebGL. The host
# composites accelerated layers only when asked to (RanvierWebCoreSettings.acceleratedCompositing); with
# it off, frames are painted on the CPU as in the slim flavor. Every other cut of the slim flavor stays.
#
# This file comes before slim.cmake, so these values win over its stubs.
set(USE_ANGLE_STUB OFF CACHE BOOL "")
set(USE_GPU_STUB OFF CACHE BOOL "")
set(ENABLE_WEBGL ON CACHE BOOL "")

include("${CMAKE_CURRENT_LIST_DIR}/slim.cmake")
