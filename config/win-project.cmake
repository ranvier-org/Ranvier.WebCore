# Included after WebKit's project() on Windows (CMAKE_PROJECT_WebKit_INCLUDE, config/common.cmake).
#
# clang-cl records each input's modification time in a precompiled header and rejects the header when a time
# differs, including the Visual Studio headers, whose times differ between runner images. Without the times, a
# reused build tree (docs/CI.md, "Build tree") keeps its precompiled headers valid; a precompiled header is still
# rejected when an input's size changes, and the build tree's key names the compiler and its headers.
add_compile_options("$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-Xclang -fno-pch-timestamp>")
