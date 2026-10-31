# Settings every flavor shares. Loaded with `cmake -C` before WebKit's own CMakeLists, so each value
# here takes the place of a `-D` on the command line. scripts/build.py passes RANVIER_RID, the runtime
# identifier, before this file, and on Windows adds the paths that depend on the machine: the compilers,
# the vcpkg toolchain file and VCPKG_INSTALLED_DIR.

set(CMAKE_BUILD_TYPE "Release" CACHE STRING "")

if (RANVIER_RID MATCHES "^win-(.+)$")
    set(PORT "Win" CACHE STRING "")
    # WebKit's overlay triplet (WebKitLibraries/triplets): dynamic libraries, release only.
    set(VCPKG_TARGET_TRIPLET "${CMAKE_MATCH_1}-windows-webkit" CACHE STRING "")
elseif (RANVIER_RID MATCHES "^linux-")
    include("${CMAKE_CURRENT_LIST_DIR}/wpe.cmake")
elseif (RANVIER_RID MATCHES "^osx-")
    include("${CMAKE_CURRENT_LIST_DIR}/mac.cmake")
else ()
    message(FATAL_ERROR "config/common.cmake: no port for RANVIER_RID '${RANVIER_RID}'")
endif ()

# Pointer lock on every port. Touch events on Windows and Linux (WPE enables them by default); on macOS they pull
# in iOS-only touch paths, so the Mac port keeps them off and reports touch input unsupported. Both options are
# in cmakeconfig.h: a change to either recompiles every unit.
set(ENABLE_POINTER_LOCK ON CACHE BOOL "")
if (RANVIER_RID MATCHES "^(win|linux)-")
    set(ENABLE_TOUCH_EVENTS ON CACHE BOOL "")
endif ()

# Image formats WebKit's Windows port enables by default but presentation does not use.
set(USE_JPEGXL OFF CACHE BOOL "")
set(USE_AVIF OFF CACHE BOOL "")

# RanvierWebCoreHost is declared in Tools/TestWebKitAPI (host/RanvierWebCoreHost.cmake) and links
# TestWebCore's libraries, so the API test tree must be configured. Only RanvierWebCoreHost is built.
set(ENABLE_API_TESTS ON CACHE BOOL "")
set(ENABLE_MINIBROWSER OFF CACHE BOOL "")

# JavaScriptCore runs on its interpreter, as on WebKit's Linux build: the host evaluates no page script
# of its own.
set(ENABLE_JIT OFF CACHE BOOL "")
set(ENABLE_DFG_JIT OFF CACHE BOOL "")
set(ENABLE_FTL_JIT OFF CACHE BOOL "")
set(ENABLE_WEBASSEMBLY OFF CACHE BOOL "")
set(ENABLE_WEBASSEMBLY_BBQJIT OFF CACHE BOOL "")
set(ENABLE_WEBASSEMBLY_OMGJIT OFF CACHE BOOL "")

# bmalloc and libpas stay on every port: the system malloc fails to compile on Windows (bmalloc.h calls
# aligned_alloc, which the CRT lacks), and one allocator keeps the ports alike.
set(USE_SYSTEM_MALLOC OFF CACHE BOOL "")

# The glue of the generated DOM functions (gen/domgen.py) compiles into WebCore through patch 0012, where it
# reaches members WebCore does not export. The host re-exports each function under its rv_ name.
get_filename_component(_ranvier_root "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
set(WebCore_EMBEDDER_SOURCES "${_ranvier_root}/host/dom/RanvierDomGlue.cpp;${_ranvier_root}/host/RanvierSvgViewGlue.cpp;${_ranvier_root}/host/RanvierResourceGlue.cpp;${_ranvier_root}/host/RanvierEventGlue.cpp;${_ranvier_root}/host/RanvierViewportGlue.cpp;${_ranvier_root}/host/RanvierInspectGlue.cpp;${_ranvier_root}/host/RanvierCanvasGlue.cpp;${_ranvier_root}/host/RanvierWakeLockGlue.cpp;${_ranvier_root}/host/RanvierNotificationGlue.cpp;${_ranvier_root}/host/RanvierTransferGlue.cpp;${_ranvier_root}/host/RanvierPointerGlue.cpp" CACHE STRING "" FORCE)
# WebKit compiles the touch PointerEvent constructors (dom/glib/PointerEventGLib.cpp, port-neutral) only for GTK and
# WPE. The path is relative to Source/WebCore, where WebCore's CMakeLists adds the embedder sources.
if (RANVIER_RID MATCHES "^win-")
    set(WebCore_EMBEDDER_SOURCES "${WebCore_EMBEDDER_SOURCES};dom/glib/PointerEventGLib.cpp" CACHE STRING "" FORCE)
endif ()
