# Included after WebKit's project() on Linux (CMAKE_PROJECT_WebKit_INCLUDE, config/wpe.cmake).
#
# Links the pinned static ICU archives and HarfBuzz-ICU adapter built by scripts/linux_icu.py instead of a
# distribution's versioned libicu*.so.<major> and libharfbuzz-icu.so.0. Debian and Ubuntu development packages
# (libharfbuzz-dev, libxml2-dev) pull in libicu-dev under /usr/include/unicode and pkg-config flags can add
# -I/usr/include, so the static ICU include directory goes first as a normal -I directory while Clang treats
# unicode/ and hb-icu.h as system headers for diagnostics.
if (NOT RANVIER_ICU_ROOT)
    message(FATAL_ERROR "config/wpe-project.cmake: RANVIER_ICU_ROOT is required on Linux")
endif ()

set(ICU_ROOT "${RANVIER_ICU_ROOT}" CACHE PATH "" FORCE)
set(ICU_INCLUDE_DIR "${RANVIER_ICU_ROOT}/include" CACHE PATH "" FORCE)
set(ICU_DATA_LIBRARY_RELEASE "${RANVIER_ICU_ROOT}/lib/libicudata.a" CACHE FILEPATH "" FORCE)
set(ICU_UC_LIBRARY_RELEASE "${RANVIER_ICU_ROOT}/lib/libicuuc.a" CACHE FILEPATH "" FORCE)
set(ICU_I18N_LIBRARY_RELEASE "${RANVIER_ICU_ROOT}/lib/libicui18n.a" CACHE FILEPATH "" FORCE)
set(HarfBuzz_ICU_INCLUDE_DIR "${RANVIER_ICU_ROOT}/include" CACHE PATH "" FORCE)
set(HarfBuzz_ICU_LIBRARY "${RANVIER_ICU_ROOT}/lib/libharfbuzz-icu.a" CACHE FILEPATH "" FORCE)

include_directories(BEFORE "${RANVIER_ICU_ROOT}/include")
add_compile_definitions(U_STATIC_IMPLEMENTATION)
if (CMAKE_C_COMPILER_ID MATCHES "Clang" OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    add_compile_options(
        "$<$<COMPILE_LANGUAGE:C,CXX>:--system-header-prefix=unicode/>"
        "$<$<COMPILE_LANGUAGE:C,CXX>:--system-header-prefix=hb-icu.h>"
    )
endif ()

find_package(Threads REQUIRED)

if (NOT TARGET ICU::data)
    add_library(ICU::data STATIC IMPORTED GLOBAL)
    set_target_properties(ICU::data PROPERTIES
        IMPORTED_LOCATION "${RANVIER_ICU_ROOT}/lib/libicudata.a"
        IMPORTED_NO_SYSTEM ON
        INTERFACE_COMPILE_DEFINITIONS "U_STATIC_IMPLEMENTATION"
    )
endif ()

if (NOT TARGET ICU::uc)
    add_library(ICU::uc STATIC IMPORTED GLOBAL)
    set_target_properties(ICU::uc PROPERTIES
        IMPORTED_LOCATION "${RANVIER_ICU_ROOT}/lib/libicuuc.a"
        IMPORTED_NO_SYSTEM ON
        INTERFACE_COMPILE_DEFINITIONS "U_STATIC_IMPLEMENTATION"
        INTERFACE_LINK_LIBRARIES "ICU::data;${CMAKE_DL_LIBS};Threads::Threads"
    )
endif ()

if (NOT TARGET ICU::i18n)
    add_library(ICU::i18n STATIC IMPORTED GLOBAL)
    set_target_properties(ICU::i18n PROPERTIES
        IMPORTED_LOCATION "${RANVIER_ICU_ROOT}/lib/libicui18n.a"
        IMPORTED_NO_SYSTEM ON
        INTERFACE_COMPILE_DEFINITIONS "U_STATIC_IMPLEMENTATION"
        INTERFACE_LINK_LIBRARIES "ICU::uc;ICU::data"
    )
endif ()

if (NOT TARGET HarfBuzz::ICU)
    add_library(HarfBuzz::ICU STATIC IMPORTED GLOBAL)
    set_target_properties(HarfBuzz::ICU PROPERTIES
        IMPORTED_LOCATION "${RANVIER_ICU_ROOT}/lib/libharfbuzz-icu.a"
        IMPORTED_NO_SYSTEM ON
        INTERFACE_COMPILE_DEFINITIONS "U_STATIC_IMPLEMENTATION"
        INTERFACE_LINK_LIBRARIES "ICU::uc;ICU::data"
    )
endif ()
