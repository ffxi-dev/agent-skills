# lsb-build

Build LandSandBoat on Windows, Linux, or macOS. Use whenever the task is to build LSB, build a specific target (xi_map, xi_connect, xi_world, xi_test, xi_search, xi_data_schema), "compile the server", rebuild after a code change, set up the MSVC build environment, or diagnose a C1083 "cannot open include file" error on a standard header (algorithm, cstddef, windows.h) that appears when cmake is run from a plain bash or MSYS shell. It loads vcvars64.bat for you on Windows and then builds, so the compiler can find its own headers; on Linux and macOS it is plain cmake.

See [SKILL.md](SKILL.md) for the full instructions, and the [repo README](../../README.md) for how skills are installed.

**Requirements:** CMake 3.21+ on PATH, plus a C++ compiler. On Windows that is Visual Studio (MSVC, the "Desktop development with C++" workload), which the skill locates via vswhere. On Linux and macOS the system gcc or clang. Prerequisites are detected and reported, never installed.

<!-- generated from SKILL.md by tools/gen_skill_readmes.py; do not edit -->
