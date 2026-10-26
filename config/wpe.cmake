# Linux: WebKit's WPE port, made for embedding, with Skia's CPU raster as on Windows. config/common.cmake
# includes this file for linux-* runtime identifiers. The package links the distribution's libraries
# (GLib, ICU, HarfBuzz, FreeType, fontconfig and the image codecs) and does not carry them.
#
# The host builds only WebCore and JavaScriptCore under TestWebKitAPI, so WPE's own embedding layers and
# their dependencies are off: the WPE platform backends, the libwpe API, and the integrations a browser
# needs. The port requires the WPE platform library or libwpe; the library stays, without backends, and
# the host does not link it.

set(PORT "WPE" CACHE STRING "")

set(ENABLE_WPE_PLATFORM ON CACHE BOOL "")
set(ENABLE_WPE_PLATFORM_DRM OFF CACHE BOOL "")
set(ENABLE_WPE_PLATFORM_HEADLESS OFF CACHE BOOL "")
set(ENABLE_WPE_PLATFORM_WAYLAND OFF CACHE BOOL "")
set(ENABLE_WPE_LEGACY_API OFF CACHE BOOL "")
set(ENABLE_WPE_QT_API OFF CACHE BOOL "")
set(ENABLE_DOCUMENTATION OFF CACHE BOOL "")
set(ENABLE_INTROSPECTION OFF CACHE BOOL "")
set(ENABLE_JOURNALD_LOG OFF CACHE BOOL "")
set(ENABLE_BUBBLEWRAP_SANDBOX OFF CACHE BOOL "")
set(ENABLE_LAYOUT_TESTS OFF CACHE BOOL "")
set(ENABLE_COG OFF CACHE BOOL "")

# 0004 takes Ganesh out of Skia, and WPE's WebCore, unlike the Windows port's, links it whatever the
# compositing setting (texmap/coordinated, PlatformDisplaySkia). This file comes before the flavor's
# settings, so this value wins.
set(USE_GPU_STUB OFF CACHE BOOL "")

# Libraries the port links for browser features: accessibility over AT-SPI, speech, hyphenation
# dictionaries, GPU buffers, crash backtraces and profiler capture. libdrm stays: the API test tree's WPE
# platform mock links it, and the host does not.
set(USE_ATK OFF CACHE BOOL "")
set(USE_FLITE OFF CACHE BOOL "")
set(USE_LIBHYPHEN OFF CACHE BOOL "")
set(USE_GBM OFF CACHE BOOL "")
set(USE_LIBBACKTRACE OFF CACHE BOOL "")
set(USE_SYSPROF_CAPTURE OFF CACHE BOOL "")
set(USE_VULKAN OFF CACHE BOOL "")

# Media and device features, which need GStreamer or device libraries, and browser features the Windows
# port does not have.
set(USE_GSTREAMER OFF CACHE BOOL "")
set(ENABLE_WEB_AUDIO OFF CACHE BOOL "")
set(ENABLE_MEDIA_STREAM OFF CACHE BOOL "")
set(ENABLE_MEDIA_RECORDER OFF CACHE BOOL "")
set(ENABLE_WEB_CODECS OFF CACHE BOOL "")
set(ENABLE_ENCRYPTED_MEDIA OFF CACHE BOOL "")
set(ENABLE_SPEECH_SYNTHESIS OFF CACHE BOOL "")
set(ENABLE_GAMEPAD OFF CACHE BOOL "")
set(ENABLE_SPELLCHECK OFF CACHE BOOL "")
set(ENABLE_PDFJS OFF CACHE BOOL "")
set(ENABLE_WEBXR OFF CACHE BOOL "")
set(ENABLE_WK_WEB_EXTENSIONS OFF CACHE BOOL "")
