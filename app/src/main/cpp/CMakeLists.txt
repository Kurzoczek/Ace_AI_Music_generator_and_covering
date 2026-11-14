# Native engine of the app: acestep.cpp (MIT, https://github.com/ServeurpersoCom/acestep.cpp) built for Android.
#
# The two programs the app needs (ace-synth, ace-lm) are built as normal executables, but named libacesynth.so /
# libacelm.so and written to the library output directory, so the Android Gradle plugin packages them into the APK
# (jniLibs). At runtime they are executed from nativeLibraryDir - the only app location Android allows to execute
# (files downloaded at runtime can never be executed: W^X rule since Android 10). Nothing executable is downloaded.
#
# Source of acestep.cpp, in this order:
#   1. app/src/main/cpp/acestep.cpp  (git submodule of this repository, pinned version;
#        clone with --recurse-submodules or run:
#        git submodule update --init --recursive)
#   2. otherwise downloaded at configure time with FetchContent (branch ACE_GIT_TAG).
cmake_minimum_required(VERSION 3.22.1)
project(acemusicgen_native C CXX)

set(ACE_GIT_TAG "master" CACHE STRING "acestep.cpp git branch / tag / commit used when there is no submodule")
set(ACE_ARM_ARCH "armv8.2-a+dotprod+fp16" CACHE STRING "ARM architecture level for ggml (-march)")

set(ACE_SRC "${CMAKE_CURRENT_SOURCE_DIR}/acestep.cpp")
if(NOT EXISTS "${ACE_SRC}/CMakeLists.txt")
    include(FetchContent)
    FetchContent_Declare(acestep_cpp
        GIT_REPOSITORY https://github.com/ServeurpersoCom/acestep.cpp.git
        GIT_TAG ${ACE_GIT_TAG}
        GIT_SUBMODULES_RECURSE TRUE
        GIT_SHALLOW TRUE)
    FetchContent_GetProperties(acestep_cpp)
    if(NOT acestep_cpp_POPULATED)
        FetchContent_Populate(acestep_cpp)
    endif()
    set(ACE_SRC "${acestep_cpp_SOURCE_DIR}")
endif()

# Work on a copy, so the thread patch never touches the submodule / download cache.
set(ACE_PATCHED "${CMAKE_CURRENT_BINARY_DIR}/acestep_patched")
file(REMOVE_RECURSE "${ACE_PATCHED}")
file(COPY "${ACE_SRC}/" DESTINATION "${ACE_PATCHED}" PATTERN ".git" EXCLUDE)
include("${CMAKE_CURRENT_SOURCE_DIR}/patch_threads.cmake")
ace_patch_threads("${ACE_PATCHED}")

# ggml options for phones: CPU backend only, no BLAS/OpenMP/GPU, static everything (one self-contained binary each)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
set(GGML_BLAS OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
set(GGML_VULKAN OFF CACHE BOOL "" FORCE)
set(GGML_CUDA OFF CACHE BOOL "" FORCE)
set(GGML_METAL OFF CACHE BOOL "" FORCE)
if(ANDROID_ABI STREQUAL "arm64-v8a")
    set(GGML_CPU_ARM_ARCH "${ACE_ARM_ARCH}" CACHE STRING "" FORCE)
endif()

set(GGML_SOURCE_DIR "${ACE_PATCHED}/ggml" CACHE PATH "" FORCE)
add_subdirectory("${ACE_PATCHED}" acestep EXCLUDE_FROM_ALL)

foreach(pair "ace-synth;acesynth" "ace-lm;acelm")
    list(GET pair 0 tgt)
    list(GET pair 1 out)
    if(NOT TARGET ${tgt})
        message(FATAL_ERROR "acestep.cpp has no target '${tgt}' - check the ACE_GIT_TAG version")
    endif()
    set_target_properties(${tgt} PROPERTIES
        OUTPUT_NAME "lib${out}"
        SUFFIX ".so"
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}")
    # 16 KB page alignment (required for apps on Android 15+ devices with 16 KB pages)
    target_link_options(${tgt} PRIVATE "-Wl,-z,max-page-size=16384")
endforeach()
