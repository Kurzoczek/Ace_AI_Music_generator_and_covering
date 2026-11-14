# Patches applied to a COPY of acestep.cpp (the submodule itself is never modified).
#
# 1. acestep.cpp hard-codes "half of the cores" for the CPU backend. The app sets the thread count itself
#    (Settings -> Processor), so the expression is replaced by a function that reads the ACE_THREADS variable.
# 2. acestep.cpp's CMakeLists.txt is written as a top-level project (${CMAKE_SOURCE_DIR}, ${CMAKE_BINARY_DIR}).
#    The app includes it with add_subdirectory(), so those are rewritten to the CURRENT_ variants.
function(ace_patch_threads dir)
    set(cmakelists "${dir}/CMakeLists.txt")
    file(READ "${cmakelists}" cm)
    string(REPLACE "\${CMAKE_SOURCE_DIR}" "\${CMAKE_CURRENT_SOURCE_DIR}" cm "${cm}")
    string(REPLACE "\${CMAKE_BINARY_DIR}" "\${CMAKE_CURRENT_BINARY_DIR}" cm "${cm}")
    file(WRITE "${cmakelists}" "${cm}")

    set(header "${dir}/src/backend.h")
    if(NOT EXISTS "${header}")
        message(WARNING "acestep.cpp: src/backend.h not found - thread patch skipped (the engine uses half of the cores)")
        return()
    endif()
    file(READ "${header}" content)
    string(FIND "${content}" "std::thread::hardware_concurrency() / 2" pos)
    if(pos EQUAL -1)
        message(WARNING "acestep.cpp: thread expression not found - thread patch skipped (ACE_THREADS ignored)")
        return()
    endif()
    string(REPLACE "std::thread::hardware_concurrency() / 2" "ace_android_threads()" content "${content}")
    set(helper "#ifndef ACE_ANDROID_THREADS_DEFINED\n#define ACE_ANDROID_THREADS_DEFINED\n#include <cstdlib>\n#include <thread>\nstatic inline unsigned ace_android_threads() {\n    const char * e = std::getenv(\"ACE_THREADS\");\n    int n = e ? std::atoi(e) : 0;\n    if (n > 0) return (unsigned) n;\n    unsigned h = std::thread::hardware_concurrency();\n    return h > 1 ? h / 2 : 1;\n}\n#endif\n")
    file(WRITE "${header}" "${helper}${content}")
    message(STATUS "acestep.cpp: thread count patched (ACE_THREADS)")
endfunction()
