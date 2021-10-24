cmake_minimum_required(VERSION 3.10)

project(finder LANGUAGES C CXX)

if(MSYS OR MINGW)
    # cut out toolchain dlls
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -static -static-libgcc -static-libstdc++")
endif()

set(CMAKE_CXX_STANDARD 20)

include_directories(.)
add_library(model finder_model.cpp finder_model.hpp finder_common.hpp)
add_library(test_utils test/test_utils.cpp test/test_utils.hpp)
target_link_libraries(test_utils model)

enable_testing()

add_executable(0_graph_make_and_destroy test/0_graph_make_and_destroy.cpp)
target_link_libraries(0_graph_make_and_destroy test_utils)
add_test(0_graph_make_and_destroy 0_graph_make_and_destroy)
