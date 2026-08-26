#!/usr/bin/env python3
"""Build a LandSandBoat target, handling the MSVC environment on Windows for you.

  python build.py xi_test
  python build.py xi_map --repo /path/to/lsb
  python build.py --list

On Windows this removes a specific pain: cmake invoked from a plain bash or MSYS shell
fails with C1083 "cannot open include file" (algorithm, cstddef, windows.h) because
MSVC's environment was never loaded. This finds vcvars64.bat via vswhere, sources it,
and only then builds, so the compiler can see its own standard headers.

On Linux and macOS the compiler environment is already set up, so it is plain cmake
configure-and-build; the same command works.

It does the setup itself. It never hands back a command line for you to run, and it
never installs Visual Studio, a compiler, or CMake: those are prerequisites it detects
and reports.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# LSB checkout markers: a top-level CMakeLists plus the map server source tree.
IS_WINDOWS = sys.platform == "win32"

REPO_MARKERS = ("CMakeLists.txt", "src/map")

# Layout-agnostic only: the current dir, a checkout beside or below it. Anywhere else, pass
# --repo or set LSB_ROOT; do not guess the author's home directory.
SEARCH_PATHS = (
    ".",
    "lsb",
    "../lsb",
    "server",
)

# Build dirs to prefer when several are already configured, most-wanted first. A dir
# already built is a fast incremental; a fresh configure is 10+ minutes.
BUILD_DIR_PREFERENCE = (
    "cmake-build-debug-visual-studio",
    "build",
    "cmake-build-releasevs",
)

# System headers whose absence is the vcvars-not-loaded signature, not a code bug.
SYSTEM_HEADERS = ("algorithm", "cstddef", "cstdint", "windows.h", "vector", "string", "iostream")


class BuildError(Exception):
    """Anything the caller can fix, reported without a stack trace."""


def find_repo(explicit: str | None) -> Path:
    """Locate an LSB checkout. An explicit path that is wrong is an error, never a
    reason to go looking elsewhere.
    """
    if explicit:
        root = Path(explicit).expanduser()
        if not is_repo(root):
            raise BuildError(f"{root} is not a LandSandBoat checkout (no CMakeLists.txt + src/map)")

        return root.resolve()

    candidates = list(SEARCH_PATHS)
    if os.environ.get("LSB_ROOT"):
        candidates.insert(0, os.environ["LSB_ROOT"])

    for candidate in candidates:
        root = Path(candidate).expanduser()
        if is_repo(root):
            return root.resolve()

    raise BuildError(
        "no LandSandBoat checkout found. Pass --repo <path> or set $LSB_ROOT.\n"
        "This skill builds an existing checkout; it does not clone the server."
    )


def is_repo(root: Path) -> bool:
    return all((root / marker).exists() for marker in REPO_MARKERS)


def vswhere_path() -> Path:
    """Standard vswhere location under the VS Installer."""
    base = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    return Path(base) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"


def find_vcvars(explicit: str | None = None) -> Path:
    """Find vcvars64.bat. $VCVARS64 or --vcvars wins; otherwise ask vswhere, including
    prerelease so a Preview/Insiders VS install is found too.
    """
    override = explicit or os.environ.get("VCVARS64")
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise BuildError(f"vcvars64.bat not found at {path}")

        return path.resolve()

    vswhere = vswhere_path()
    if not vswhere.is_file():
        raise BuildError(
            f"vswhere.exe not found at {vswhere}.\n"
            "Visual Studio (with the C++ workload) must be installed."
        )

    relative = "VC/Auxiliary/Build/vcvars64.bat"
    result = subprocess.run(
        [str(vswhere), "-latest", "-prerelease", "-find", relative],
        capture_output=True,
        text=True,
    )
    found = result.stdout.strip().splitlines()
    if not found:
        raise BuildError(
            "vswhere found no Visual Studio install with vcvars64.bat.\n"
            "Install the 'Desktop development with C++' workload."
        )

    path = Path(found[0])
    if not path.is_file():
        raise BuildError(f"vswhere reported {path}, but it does not exist")

    return path.resolve()


def find_cmake() -> str:
    """cmake on PATH, else fail clearly. We do not install it."""
    from shutil import which

    cmake = which("cmake")
    if not cmake:
        raise BuildError("cmake not found on PATH. Install CMake 3.21+ (https://cmake.org/download).")

    return cmake


def discover_targets(root: Path) -> list[str]:
    """Buildable executable targets, read from the source CMakeLists so the list can
    never drift from what actually exists.
    """
    pattern = re.compile(r"add_executable\(\s*([A-Za-z_][A-Za-z0-9_]*)")
    targets: set[str] = set()
    for cmakelists in (root / "src").rglob("CMakeLists.txt"):
        text = cmakelists.read_text(encoding="utf-8", errors="replace")
        targets.update(pattern.findall(text))

    return sorted(targets)


def pick_build_dir(root: Path, explicit: str | None) -> tuple[Path, bool]:
    """Choose where to build and report whether it is already configured.

    An explicit --build-dir is used as given. Otherwise reuse an already configured
    directory (preferring a debug one, whose objects make the incremental fast); if
    none exists, fall back to the repo's own preset dir, which will need configuring.
    """
    if explicit:
        path = (root / explicit) if not Path(explicit).is_absolute() else Path(explicit)
        return path, is_configured(path)

    configured = [root / name for name in BUILD_DIR_PREFERENCE if is_configured(root / name)]
    if configured:
        return configured[0], True

    others = sorted(
        directory for directory in root.iterdir() if directory.is_dir() and is_configured(directory)
    )
    if others:
        return others[0], True

    return root / "build", False


def is_configured(build_dir: Path) -> bool:
    return (build_dir / "CMakeCache.txt").is_file()


def diagnose_c1083(output: str) -> str | None:
    """If the build failed for lack of a system header, name the real cause. A C1083 on
    a standard header means the MSVC environment was not active, not that code is broken.
    """
    if "C1083" not in output:
        return None

    hit = next((h for h in SYSTEM_HEADERS if re.search(rf"C1083.*['\"]{re.escape(h)}['\"]", output)), None)
    if hit is None:
        return None

    return (
        f"C1083 cannot open '{hit}': the MSVC environment was not loaded, so INCLUDE is\n"
        "unset and the compiler cannot see its own standard headers. This is an\n"
        "environment problem, not a code problem. cmake must be invoked from a shell\n"
        "that has sourced vcvars64.bat. This skill does that; if you saw this from a\n"
        "plain bash/MSYS build, that is why. Re-run through build.py."
    )


def write_build_script(
    vcvars: Path, cmake: str, build_dir: Path, target: str, jobs: int, configure: bool, root: Path
) -> str:
    """A temp .bat that loads MSVC, optionally configures, then builds. Baking every
    value in avoids nested-quote grief when cmd.exe runs it.
    """
    lines = [
        "@echo off",
        f'call "{vcvars}" >nul || (echo [lsb-build] vcvars64.bat failed & exit /b 1)',
    ]
    if configure:
        lines.append(
            f'"{cmake}" -S "{root}" -B "{build_dir}" -DCMAKE_BUILD_TYPE=RelWithDebInfo '
            f"|| exit /b %errorlevel%"
        )

    lines.append(f'"{cmake}" --build "{build_dir}" --target {target} -j {jobs}')
    lines.append("exit /b %errorlevel%")
    return "\r\n".join(lines) + "\r\n"


def stream(argv: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Run a command, streaming its output live and capturing it for diagnosis."""
    captured: list[str] = []
    process = subprocess.Popen(
        argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        captured.append(line)

    return process.wait(), "".join(captured)


def run_build(script: str) -> tuple[int, str]:
    """Run the Windows .bat through cmd.exe (it has sourced vcvars first)."""
    handle = tempfile.NamedTemporaryFile("w", suffix=".bat", delete=False, encoding="utf-8")
    handle.write(script)
    handle.close()
    try:
        return stream(["cmd", "/c", handle.name])
    finally:
        os.unlink(handle.name)


def build(
    root: Path, target: str, build_dir_arg: str | None, jobs: int, vcvars_arg: str | None
) -> int:
    targets = discover_targets(root)
    if target not in targets:
        listed = ", ".join(targets) or "(none found)"
        raise BuildError(f"unknown target {target!r}. Available targets: {listed}")

    cmake = find_cmake()
    build_dir, configured = pick_build_dir(root, build_dir_arg)

    print(f"repo:      {root}", file=sys.stderr)
    print(f"build dir: {build_dir}{'' if configured else '  (configuring, first build is slow)'}", file=sys.stderr)
    print(f"target:    {target}", file=sys.stderr)

    if IS_WINDOWS:
        # MSVC needs its environment; source vcvars in a .bat before cmake runs.
        vcvars = find_vcvars(vcvars_arg)
        print(f"vcvars:    {vcvars}", file=sys.stderr)
        script = write_build_script(vcvars, cmake, build_dir, target, jobs, not configured, root)
        code, output = run_build(script)
    else:
        # Linux and macOS: the compiler environment is already set up, so it is plain cmake.
        code, output = 0, ""
        if not configured:
            code, output = stream([cmake, "-S", str(root), "-B", str(build_dir),
                                   "-DCMAKE_BUILD_TYPE=RelWithDebInfo"])

        if code == 0:
            code, output = stream([cmake, "--build", str(build_dir), "--target", target,
                                   "-j", str(jobs)])

    if code != 0:
        diagnosis = diagnose_c1083(output)
        if diagnosis:
            print(f"\n[lsb-build] {diagnosis}", file=sys.stderr)

        print(f"\n[lsb-build] build failed (exit {code})", file=sys.stderr)

    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", help="target to build, e.g. xi_test, xi_map")
    parser.add_argument("--repo", help="LSB checkout (else $LSB_ROOT, else searched)")
    parser.add_argument("--build-dir", help="build directory (else an existing one, else ./build)")
    parser.add_argument("--vcvars", help="path to vcvars64.bat (else $VCVARS64, else vswhere)")
    parser.add_argument("--jobs", "-j", type=int, default=os.cpu_count() or 8, help="parallel jobs")
    parser.add_argument("--list", action="store_true", help="list buildable targets and exit")
    args = parser.parse_args()

    try:
        root = find_repo(args.repo)
        if args.list:
            for target in discover_targets(root):
                print(target)

            return 0

        if not args.target:
            parser.error("a target is required (or use --list). Try: xi_test")

        return build(root, args.target, args.build_dir, args.jobs, args.vcvars)
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
