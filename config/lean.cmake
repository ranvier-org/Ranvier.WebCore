# The lean flavor: WebKit's Windows port with the JIT tiers off and every patch option at its default,
# so the build compiles WebKit's own sources (plus 0000-skia-strike-ref.patch). It is the reference the
# slim flavor is compared against, and it shows that the patches leave a default build unchanged.

include("${CMAKE_CURRENT_LIST_DIR}/common.cmake")

set(VCPKG_MANIFEST_FEATURES "web;lcms;skia;woff2" CACHE STRING "")
