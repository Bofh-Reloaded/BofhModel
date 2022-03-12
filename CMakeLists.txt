cmake_minimum_required(VERSION 3.17)

project(finder LANGUAGES C CXX)

if(MSYS OR MINGW)
    # cut out toolchain dlls
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -static -static-libgcc -static-libstdc++")
endif()
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fdiagnostics-color=always")

set(CMAKE_CXX_STANDARD 20)

# Find libboost
if(BOOST_ROOT)
    set(Boost_NO_SYSTEM_PATHS ON)
endif()
find_package(Boost COMPONENTS python REQUIRED)
message("Using boost headers at ${Boost_INCLUDE_DIRS}")
include_directories(${Boost_INCLUDE_DIRS})


# find CPython interpreter and libs
if(PYTHON_ROOT)
    set(Python_ROOT_DIR "${PYTHON_ROOT}")
    set(Python_FIND_STRATEGY LOCATION)
endif()
find_package(Python 3.8 COMPONENTS Interpreter Development REQUIRED)
message("**** Targeting Python ${Python_VERSION_MAJOR}.${Python_VERSION_MINOR}.${Python_VERSION_PATCH} at ${Python_EXECUTABLE}")
message("**** Python_Development_FOUND=${Python_Development_FOUND}")
message("**** Python_INCLUDE_DIRS=${Python_INCLUDE_DIRS}")
message("**** Python_LIBRARIES=${Python_LIBRARIES}")
message("**** Python_EXECUTABLE=${Python_EXECUTABLE}")
message("**** Python_LINK_OPTIONS=${Python_LINK_OPTIONS}")
message("**** Python_RUNTIME_LIBRARY_DIRS=${Python_RUNTIME_LIBRARY_DIRS}")
message("**** Python_SITELIB=${Python_SITELIB}")
if (NOT Python_Development_FOUND OR NOT Python_LIBRARIES OR NOT Python_EXECUTABLE OR NOT Python_INCLUDE_DIRS OR NOT Python_SITELIB)
    message(FATAL_ERROR "Necessary Python headers and/or lib not found")
endif()
include_directories(${Python_INCLUDE_DIR})


set(MODEL_SRC
    src/bofh/model/bofh_common.hpp
    src/bofh/model/bofh_entity.hpp
    src/bofh/model/bofh_entity.cpp
    src/bofh/model/bofh_entity_idx_fwd.hpp
    src/bofh/model/bofh_entity_idx.hpp
    src/bofh/model/bofh_entity_idx.cpp
    src/bofh/model/bofh_types.cpp
    src/bofh/model/bofh_types.hpp
    src/bofh/model/bofh_fees.cpp
    src/bofh/model/bofh_fees.hpp
    src/bofh/model/bofh_model.cpp
    src/bofh/model/bofh_model.hpp
    src/bofh/model/bofh_model_fwd.hpp
    src/bofh/model/bofh_amm_estimation.hpp
    src/bofh/model/bofh_amm_estimation.cpp
    src/bofh/pathfinder/finder_3way.hpp
    src/bofh/pathfinder/finder_3way.cpp
    src/bofh/pathfinder/swaps_idx.hpp
    src/bofh/pathfinder/swaps_idx.cpp
    src/bofh/commons/bofh_log.hpp
    src/bofh/commons/bofh_log.cpp
    src/bofh/pathfinder/paths.hpp
    src/bofh/pathfinder/paths.cpp
    src/3rd-party/hash-library/crc32.cpp
    src/3rd-party/hash-library/crc32.h
    src/3rd-party/hash-library/digest.cpp
    src/3rd-party/hash-library/hash.h
    src/3rd-party/hash-library/hmac.h
    src/3rd-party/hash-library/keccak.cpp
    src/3rd-party/hash-library/keccak.h
    src/3rd-party/hash-library/md5.cpp
    src/3rd-party/hash-library/md5.h
    src/3rd-party/hash-library/sha1.cpp
    src/3rd-party/hash-library/sha1.h
    src/3rd-party/hash-library/sha256.cpp
    src/3rd-party/hash-library/sha256.h
    src/3rd-party/hash-library/sha3.cpp
    src/3rd-party/hash-library/sha3.h
    )
include_directories(src)

# # Build library as a Python module. (Using Boost.Python)
# add_library(bofh_model SHARED
#     )
# target_include_directories(bofh_model PUBLIC src)
# target_link_libraries(bofh_model ${Boost_LIBRARIES})
#install(TARGETS bofh_model LIBRARY DESTINATION lib)

# Build library as a Python module. (Using Boost.Python)
add_library(bofh_model_ext MODULE
    ${MODEL_SRC}
    src/bofh/model/bofh_model_py_ext.cpp
    )

add_library(bofh_model STATIC EXCLUDE_FROM_ALL ${MODEL_SRC})
target_compile_definitions(bofh_model PUBLIC -DNOPYTHON=1)
#target_link_libraries(bofh_model_ext bofh_model)
target_include_directories(bofh_model_ext PRIVATE ${Python_INCLUDE_DIRS})
set_target_properties(bofh_model_ext PROPERTIES PREFIX "") # build library without "lib{x}" name
target_link_libraries(bofh_model_ext ${Boost_LIBRARIES})
install(TARGETS bofh_model_ext DESTINATION ${Python_SITELIB})


target_include_directories(bofh_model PRIVATE ${Python_INCLUDE_DIRS})
target_link_libraries(bofh_model ${Boost_LIBRARIES})

enable_testing()


function(create_test test_name)
    add_executable(${test_name} EXCLUDE_FROM_ALL ${ARGN})
    target_link_libraries(${test_name} bofh_model)
    add_test(${test_name} ${test_name})
endfunction()

create_test(test_address test/test_address.cpp)
create_test(test_multiindex test/test_multiindex.cpp)

