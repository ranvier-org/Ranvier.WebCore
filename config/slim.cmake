# The slim flavor, the one this repository ships: the lean build with every feature cut that
# presentation does not need. docs/SETTINGS.md gives the reason and the measured size of each setting.
#
# scripts/build.py also sets, for this flavor only:
#   _LINK_=/OPT:SAFEICF dwrite.lib   lld-link folds identical functions whose address is not taken, and
#                                    links dwrite.lib, which WebCore otherwise receives only through the
#                                    MediaFoundation target that ENABLE_VIDEO=OFF removes.
# and after the build writes a filtered ICU data DLL (scripts/icu_data.py).

include("${CMAKE_CURRENT_LIST_DIR}/common.cmake")

# vcpkg: no LCMS. The "web" feature installs curl, libpsl, OpenSSL and SQLite; only the Windows
# cryptography backend links OpenSSL. The dependency closure packages the libraries actually linked.
set(VCPKG_MANIFEST_FEATURES "web;skia;woff2" CACHE STRING "")
set(USE_LCMS OFF CACHE BOOL "")

# WebKit's own feature switches.
set(ENABLE_WEBGL OFF CACHE BOOL "")
set(ENABLE_VIDEO OFF CACHE BOOL "")
set(ENABLE_XSLT OFF CACHE BOOL "")
set(ENABLE_REMOTE_INSPECTOR OFF CACHE BOOL "")
set(ENABLE_WEBDRIVER OFF CACHE BOOL "")

# The patch series (patches/). Each option defaults to OFF upstream of this file.
set(USE_ANGLE_STUB ON CACHE BOOL "")          # 0001: ANGLE replaced by EGL/GLES entry points that fail
set(USE_NETWORK_STUB ON CACHE BOOL "")        # 0002: no curl, libpsl; no network loads
if (RANVIER_RID MATCHES "^win-")
    set(USE_CRYPTO_STUB OFF CACHE BOOL "")
else ()
    set(USE_CRYPTO_STUB ON CACHE BOOL "")
endif ()
set(USE_GPU_STUB ON CACHE BOOL "")            # 0004: no GPU code in WebCore or Skia
set(USE_WEB_API_STUB ON CACHE BOOL "")        # 0005: no IndexedDB, caches, service/shared workers, push, WebSocket
set(USE_SQLITE_STUB ON CACHE BOOL "")         # 0006: no SQLite (requires USE_WEB_API_STUB)
set(USE_BROWSER_API_STUB ON CACHE BOOL "")    # 0007: no WebGPU, WebXR, File System, WebTransport (requires USE_WEB_API_STUB)
set(USE_INSPECTOR_STUB ON CACHE BOOL "")      # 0008: no WebCore inspector
set(USE_JSC_INSPECTOR_STUB ON CACHE BOOL "")  # 0009: no JavaScriptCore inspector (requires USE_INSPECTOR_STUB)
set(USE_AX_EMBEDDER_NOTIFICATIONS ON CACHE BOOL "")  # 0011: accessibility notifications reach the host
