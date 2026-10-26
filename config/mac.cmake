# macOS: WebKit's Cocoa port, which draws with CoreGraphics and CoreText where the Windows and Linux builds
# use Skia, so its pixels differ from theirs. config/common.cmake includes this file for osx-* runtime
# identifiers. The package links the system's frameworks and its ICU (libicucore) and does not carry them.
#
# The Cocoa sources compile only in configurations close to the port's defaults: with video, WebGPU or
# WebRTC off, or WebAssembly off, WebCore fails to compile (docs/SETTINGS.md lists the errors). So this
# file turns off only what builds without editing WebKit's C++, and the rest stays as the port has it.
# It runs before slim.cmake's and common.cmake's own settings, and a cache entry set first is kept, so
# the ON values below override theirs.

set(PORT "Mac" CACHE STRING "")
if (RANVIER_RID MATCHES "^osx-(.+)$")
    set(CMAKE_OSX_ARCHITECTURES "${CMAKE_MATCH_1}" CACHE STRING "")
endif ()

# Off, as in the slim flavor.
set(ENABLE_WEBGL OFF CACHE BOOL "")
set(ENABLE_XSLT OFF CACHE BOOL "")
set(ENABLE_WEBDRIVER OFF CACHE BOOL "")

# On, unlike the slim flavor and common.cmake:
# - video: the Cocoa media, WebCodecs, media session and picture-in-picture sources assume it;
# - the remote inspector: API/JSRemoteInspector.cpp calls RemoteInspector::singleton() under PLATFORM(COCOA);
# - WebAssembly: bindings/js/BindingsJSTZoneImpls.cpp names its source providers unconditionally. It runs
#   on the in-place interpreter, since the JIT tiers stay off (common.cmake).
set(ENABLE_VIDEO ON CACHE BOOL "")
set(ENABLE_REMOTE_INSPECTOR ON CACHE BOOL "")
set(ENABLE_WEBASSEMBLY ON CACHE BOOL "")
