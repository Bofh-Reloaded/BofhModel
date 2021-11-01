cmake_minimum_required(VERSION 3.10)

project(finder LANGUAGES C CXX)

if(MSYS OR MINGW)
    # cut out toolchain dlls
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -static -static-libgcc -static-libstdc++")
endif()

set(CMAKE_CXX_STANDARD 20)

if (NOT DEVELOPMENT)
    # This is production: all dependencies are available. Look for them

    # Find libboost
    if(NOT BOOST_ROOT)
        set(Boost_NO_SYSTEM_PATHS ON)
        set(BOOST_ROOT boost)
    endif()
    find_package(Boost REQUIRED)
    message("Using boost headers at ${Boost_INCLUDE_DIRS}")
    include_directories(${Boost_INCLUDE_DIRS})

    # find CPython interpreter and libs
    find_package(Python COMPONENTS Interpreter Development)
    if (NOT Python_Development_FOUND)
        message(FATAL_ERROR "Python headers and lib not found")
    endif()
    if (Python_VERSION_MAJOR LESS 3 OR Python_VERSION_MINOR LESS 8)
    #    message(FATAL_ERROR "At least Python3.8+ is required (found: ${Python_VERSION_MAJOR}.${Python_VERSION_MINOR}.${Python_VERSION_PATCH})")
    endif()
    message("Targeting Python ${Python_VERSION_MAJOR}.${Python_VERSION_MINOR}.${Python_VERSION_PATCH} at ${Python_EXECUTABLE} (headers ${Python_INCLUDE_DIR}, libs ${Python_LIBRARY})")
    if(Python_INCLUDE_DIR)
        include_directories(${Python_INCLUDE_DIR})
    endif()

else()
    # This branch is only here to appease CLion/QTCreator/VStudio or other editor
    # that look into CMake project metadata.
    # Otherwise the missing dependencies would drive me mad.

    include_directories(${CMAKE_CURRENT_PROJECT_DIR}/boost)
endif()



add_library(model
    model/finder_model.cpp
    model/finder_model.hpp
    model/finder_model_python.cpp
    model/finder_model_python.hpp
    model/finder_model_fwd.hpp
    model/finder_common.hpp
    model/main_index.cpp
    model/main_index.hpp
    model/main_index_fwd.hpp
    )
target_include_directories(model PUBLIC model)


add_library(test_utils test/test_utils.cpp test/test_utils.hpp)
target_link_libraries(test_utils model)
target_include_directories(test_utils PUBLIC test)

enable_testing()

function(create_test test_name)
    add_executable(${test_name} ${ARGN})
    target_link_libraries(${test_name} test_utils)
    add_test(${test_name} ${test_name})
endfunction()

create_test(0_graph_make_and_destroy test/0_graph_make_and_destroy.cpp)

#create_test(1_elective_inverse_collimation test/1_elective_inverse_collimation.cpp)
#set_target_properties(1_elective_inverse_collimation PROPERTIES EXCLUDE_FROM_ALL 1 EXCLUDE_FROM_DEFAULT_BUILD 1)

#create_test(2_balance_estimator test/2_balance_estimator.cpp)
