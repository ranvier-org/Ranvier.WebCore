
# Ranvier native WebCore C ABI experiment: a shared library over the TestWebCore host and frameworks.
if (ENABLE_WEBCORE)
    set(RanvierWebCoreHost_SOURCES
        RanvierAbi/RanvierWebCoreAbi.cpp
        RanvierAbi/RanvierWebCoreDom.cpp
        RanvierAbi/RanvierWebCoreUia.cpp
    )
    set(RanvierWebCoreHost_LIBRARIES ${TestWebCore_LIBRARIES})
    if (WIN32)
        list(APPEND RanvierWebCoreHost_LIBRARIES Uiautomationcore Ole32 OleAut32 Comctl32)
    endif ()
    list(REMOVE_ITEM RanvierWebCoreHost_LIBRARIES WebKit::gtest)
    list(REMOVE_ITEM RanvierWebCoreHost_LIBRARIES WebKit::WebCoreTestSupport)
    set(RanvierWebCoreHost_FRAMEWORKS ${TestWebCore_FRAMEWORKS})
    set(RanvierWebCoreHost_PRIVATE_INCLUDE_DIRECTORIES
        ${CMAKE_BINARY_DIR}
        ${TESTWEBKITAPI_DIR}
        ${TESTWEBKITAPI_DIR}/RanvierAbi
    )
    set(RanvierWebCoreHost_DEFINITIONS BUILDING_TestWebCore NO_GTEST_USAGE)
    # Accelerated compositing (rv_host_set_accelerated_compositing) needs GraphicsLayerTextureMapper, which
    # coordinated graphics replaces, and the GPU code that patch 0004's USE_GPU_STUB removes.
    if (USE_GRAPHICS_LAYER_TEXTURE_MAPPER AND NOT USE_GPU_STUB)
        list(APPEND RanvierWebCoreHost_DEFINITIONS RANVIER_COMPOSITING=1)
        list(APPEND RanvierWebCoreHost_LIBRARIES ANGLE::GLES)
    endif ()

    add_library(RanvierWebCoreHost SHARED "${CMAKE_BINARY_DIR}/cmakeconfig.h")
    _WEBKIT_TARGET_LINK_FRAMEWORK(RanvierWebCoreHost)
    _WEBKIT_TARGET(RanvierWebCoreHost)
    set_target_properties(RanvierWebCoreHost PROPERTIES LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib/ranvier)
    if (APPLE)
        # WebCore.framework lets only the clients it names (-allowable_client) link it, and the linker takes
        # a library's client name from its install name. The host links as libTestWebCore.dylib, TestWebCore
        # being one of those clients; build.py package sets the install name back to its file name. The
        # option goes with the libraries because they follow CMake's own -install_name, and the last wins.
        target_link_libraries(RanvierWebCoreHost PRIVATE "-Wl,-install_name,@rpath/libTestWebCore.dylib")
    endif ()
endif ()
