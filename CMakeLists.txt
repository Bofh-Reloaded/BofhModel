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

function(create_test test_name)
    add_executable(${test_name} ${ARGN})
    target_link_libraries(${test_name} test_utils)
    add_test(${test_name} ${test_name})
endfunction()

create_test(0_graph_make_and_destroy test/0_graph_make_and_destroy.cpp)
#create_test(1_elective_inverse_collimation test/1_elective_inverse_collimation.cpp)
