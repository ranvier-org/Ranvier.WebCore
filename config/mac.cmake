# macOS: WebKit's Cocoa port, which draws with CoreGraphics and CoreText where the Windows and Linux builds
# use Skia, so its pixels differ from theirs. config/common.cmake includes this file for osx-* runtime
# identifiers. The package links the system's frameworks and its ICU (libicucore) and does not carry them.
#
# The patch series hooks only the Windows and Linux platform files, so the USE_*_STUB options do nothing
# here; what presentation does not need is cut with WebKit's own switches, as far as they go on this port.

set(PORT "Mac" CACHE STRING "")
if (RANVIER_RID MATCHES "^osx-(.+)$")
    set(CMAKE_OSX_ARCHITECTURES "${CMAKE_MATCH_1}" CACHE STRING "")
endif ()

# The slim flavor's feature switches, for both flavors: the Mac port builds no Windows-only reference to
# compare against.
set(ENABLE_WEBGL OFF CACHE BOOL "")
set(ENABLE_VIDEO OFF CACHE BOOL "")
set(ENABLE_XSLT OFF CACHE BOOL "")
set(ENABLE_REMOTE_INSPECTOR OFF CACHE BOOL "")
set(ENABLE_WEBDRIVER OFF CACHE BOOL "")

# Cocoa features that build further libraries into or beside WebCore: WebGPU.framework, the dav1d AV1
# decoder and WebRTC. With ENABLE_VIDEO off WebKit also turns off the media features that depend on it.
set(ENABLE_WEBGPU OFF CACHE BOOL "")
set(ENABLE_AV1 OFF CACHE BOOL "")
set(ENABLE_WEB_RTC OFF CACHE BOOL "")
set(ENABLE_MEDIA_STREAM OFF CACHE BOOL "")
