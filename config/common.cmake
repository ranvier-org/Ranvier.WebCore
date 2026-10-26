# Settings every flavor shares. Loaded with `cmake -C` before WebKit's own CMakeLists, so each value
# here takes the place of a `-D` on the command line. scripts/build.py adds the paths that depend on the
# machine: the compilers, the vcpkg toolchain file and VCPKG_INSTALLED_DIR.

set(PORT "Win" CACHE STRING "")
set(CMAKE_BUILD_TYPE "Release" CACHE STRING "")

# WebKit's overlay triplet (WebKitLibraries/triplets): x64, dynamic libraries, release only.
set(VCPKG_TARGET_TRIPLET "x64-windows-webkit" CACHE STRING "")

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

# bmalloc and libpas stay: the system malloc fails to compile on Windows (bmalloc.h calls aligned_alloc,
# which the CRT lacks).
set(USE_SYSTEM_MALLOC OFF CACHE BOOL "")
