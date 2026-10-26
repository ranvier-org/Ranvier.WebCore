
# Ranvier native WebCore C ABI experiment: a shared library over the TestWebCore host and frameworks.
if (ENABLE_WEBCORE)
    set(RanvierWebCoreHost_SOURCES
        RanvierAbi/RanvierWebCoreAbi.cpp
    )
    set(RanvierWebCoreHost_LIBRARIES ${TestWebCore_LIBRARIES})
    list(REMOVE_ITEM RanvierWebCoreHost_LIBRARIES WebKit::gtest)
    list(REMOVE_ITEM RanvierWebCoreHost_LIBRARIES WebKit::WebCoreTestSupport)
    set(RanvierWebCoreHost_FRAMEWORKS ${TestWebCore_FRAMEWORKS})
    set(RanvierWebCoreHost_PRIVATE_INCLUDE_DIRECTORIES
        ${CMAKE_BINARY_DIR}
        ${TESTWEBKITAPI_DIR}
        ${TESTWEBKITAPI_DIR}/RanvierAbi
    )
    set(RanvierWebCoreHost_DEFINITIONS BUILDING_TestWebCore NO_GTEST_USAGE)

    add_library(RanvierWebCoreHost SHARED "${CMAKE_BINARY_DIR}/cmakeconfig.h")
    _WEBKIT_TARGET_LINK_FRAMEWORK(RanvierWebCoreHost)
    _WEBKIT_TARGET(RanvierWebCoreHost)
    set_target_properties(RanvierWebCoreHost PROPERTIES LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib/ranvier)
    if (APPLE)
        # WebCore.framework lets only the clients it names (-allowable_client) link it; the host links as
        # TestWebCore, one of them.
        target_link_options(RanvierWebCoreHost PRIVATE "LINKER:-client_name,TestWebCore")
    endif ()
endif ()
