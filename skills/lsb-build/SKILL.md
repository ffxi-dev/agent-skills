---
name: lsb-build
description: >
  Build LandSandBoat on Windows, Linux, or macOS. Use whenever the task is to build LSB, build a
  specific target (xi_map, xi_connect, xi_world, xi_test, xi_search, xi_data_schema),
  "compile the server", rebuild after a code change, set up the MSVC build environment, or
  diagnose a C1083 "cannot open include file" error on a standard header (algorithm,
  cstddef, windows.h) that appears when cmake is run from a plain bash or MSYS shell. It
  loads vcvars64.bat for you on Windows and then builds, so the compiler can find its own
  headers; on Linux and macOS it is plain cmake.
license: MIT
compatibility: >
  CMake 3.21+ on PATH, plus a C++ compiler. On Windows that is Visual Studio (MSVC, the
  "Desktop development with C++" workload), which the skill locates via vswhere. On Linux and
  macOS the system gcc or clang. Prerequisites are detected and reported, never installed.
---

# Build LandSandBoat

Give it a target, get a build. The same command works on every platform:

```bash
python build.py xi_test
python build.py xi_map --repo /path/to/lsb
python build.py --list
```

On **Windows** it finds vcvars64.bat, sources it, and only then invokes cmake, which is the
whole point: a build from a shell that never loaded the MSVC environment fails on the first
standard header. On **Linux and macOS** the compiler environment is already present, so it
is a plain cmake configure-and-build, no vcvars involved.

Either way, do not hand the user a command to run or tell them to open a "Developer Command
Prompt". This skill does the setup itself.

## The pain it removes

cmake invoked from bash/MSYS (or any shell without the MSVC environment) fails like this:

```
fatal error C1083: Cannot open include file: 'algorithm': No such file or directory
```

`cl.exe` finds its standard headers through the `INCLUDE` variable, which only
`vcvars64.bat` sets. Nothing is wrong with the code. `build.py` locates vcvars64.bat
through `vswhere`, sources it inside the build shell, then runs cmake, so `INCLUDE` is set
and the headers resolve. If a build still ends in C1083 on a system header, the helper says
so plainly rather than letting it read as a compile error.

## Targets

Discovered from the source `CMakeLists.txt` files, so the list never drifts from reality.
`python build.py --list` prints the current set. On a normal checkout:

| target | what it is |
|---|---|
| `xi_map` | the map server |
| `xi_connect` | the login/connect server |
| `xi_world` | the world server |
| `xi_search` | the search server |
| `xi_test` | the test harness |
| `xi_data_schema` | data schema tool |

An unknown target is rejected up front with the available list, before cmake or vcvars are
touched.

## Options

- `--repo PATH` the LSB checkout. Otherwise `$LSB_ROOT`, otherwise the current directory or a
  sibling `lsb`/`server` checkout (no home-directory guessing). An
  explicit `--repo` that is not a checkout is an error, not a reason to search elsewhere.
  The skill builds an existing checkout and does not clone the server.
- `--build-dir PATH` where to build. Otherwise it reuses an already configured directory
  (preferring a debug one, whose object files make the incremental fast); if none exists it
  configures `./build` from scratch, which is the slow first build.
- `--vcvars PATH` an explicit vcvars64.bat. Otherwise `$VCVARS64`, otherwise `vswhere`.
- `--jobs N` / `-j N` parallel jobs, default the CPU count.

## How discovery works

- **vcvars64.bat** comes from `vswhere.exe` under the VS Installer, queried with
  `-latest -prerelease -find VC/Auxiliary/Build/vcvars64.bat`. The `-prerelease` matters:
  a Preview or Insiders VS install is invisible without it.
- **cmake** must be on PATH (3.21+). It is not installed for you.
- **The build directory** is an existing configured one when present (a fresh configure is
  ten minutes and more), else `./build` configured via the repo's own layout.

Visual Studio and CMake are prerequisites, detected and named clearly if absent, the same
way a missing runtime is reported rather than installed.

## When it fails

- **C1083 on a standard header** after the skill ran means vcvars did not take effect. The
  helper prints that diagnosis. This is an environment problem, never a code problem.
- **vswhere or vcvars not found** means no C++ Visual Studio install was located. Install
  the "Desktop development with C++" workload, or pass `--vcvars`.
- **A missing library on Linux or macOS** shows as a normal cmake error naming the package.
  Install it with the system package manager; the LSB build docs under `documentation/` list
  what the server needs. The skill does not install system packages.
- **A real compile error** in LSB source is exactly that; the build output is streamed live
  so the first error is visible as it happens.

```bash
python test_build.py   # standalone, no checkout or compiler needed
```
