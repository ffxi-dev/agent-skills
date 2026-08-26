#!/usr/bin/env python3
"""Standalone tests for build.py. Run: python test_build.py -> "N/N passed".

No pytest, no network, no real compile. Fixtures stand in for an LSB checkout and for
vswhere output so the logic is exercised without a 10-minute build.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable

import build


def make_repo(tmp: Path, targets: tuple[str, ...] = ("xi_test", "xi_map")) -> Path:
    """Minimal on-disk shape that find_repo/discover_targets accept."""
    (tmp / "CMakeLists.txt").write_text("project(xi)\n", encoding="utf-8")
    src = tmp / "src" / "map"
    src.mkdir(parents=True)
    for target in targets:
        sub = tmp / "src" / target
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "CMakeLists.txt").write_text(f"add_executable({target}\n  main.cpp)\n", encoding="utf-8")

    return tmp


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_raises(func: Callable[[], object], needle: str) -> None:
    try:
        func()
    except build.BuildError as error:
        expect(needle.lower() in str(error).lower(), f"expected {needle!r} in: {error}")
        return

    raise AssertionError(f"expected BuildError containing {needle!r}, none raised")


def test_find_repo_explicit_valid() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = make_repo(Path(raw))
        expect(build.find_repo(str(root)) == root.resolve(), "explicit valid repo should resolve")


def test_find_repo_explicit_invalid() -> None:
    with tempfile.TemporaryDirectory() as raw:
        expect_raises(lambda: build.find_repo(raw), "not a landsandboat checkout")


def test_find_repo_env(monkey: dict[str, str]) -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = make_repo(Path(raw))
        monkey["LSB_ROOT"] = str(root)
        expect(build.find_repo(None) == root.resolve(), "LSB_ROOT should be honoured")


def test_find_repo_missing() -> None:
    expect_raises(lambda: build.find_repo(r"Z:\definitely\not\here"), "not a landsandboat")


def test_discover_targets() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = make_repo(Path(raw), ("xi_test", "xi_map", "xi_world"))
        found = build.discover_targets(root)
        expect(found == ["xi_map", "xi_test", "xi_world"], f"sorted target list, got {found}")


def test_unknown_target_rejected() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = make_repo(Path(raw))
        # build() validates target before touching cmake/vcvars, so no real tools needed.
        expect_raises(
            lambda: build.build(root, "xi_nope", None, 4, None),
            "unknown target",
        )


def test_pick_build_dir_prefers_existing_debug() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = make_repo(Path(raw))
        for name in ("build", "cmake-build-debug-visual-studio"):
            directory = root / name
            directory.mkdir()
            (directory / "CMakeCache.txt").write_text("x\n", encoding="utf-8")

        chosen, configured = build.pick_build_dir(root, None)
        expect(chosen.name == "cmake-build-debug-visual-studio", f"debug dir preferred, got {chosen}")
        expect(configured, "existing dir reports configured")


def test_pick_build_dir_falls_back_to_build() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = make_repo(Path(raw))
        chosen, configured = build.pick_build_dir(root, None)
        expect(chosen == root / "build", f"fallback is ./build, got {chosen}")
        expect(not configured, "unconfigured fallback reports not configured")


def test_pick_build_dir_explicit() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = make_repo(Path(raw))
        chosen, configured = build.pick_build_dir(root, "mydir")
        expect(chosen == root / "mydir", "relative explicit dir is under root")
        expect(not configured, "explicit unconfigured dir is not configured")


def test_diagnose_c1083_system_header() -> None:
    output = "foo.cpp\nC:\\x\\foo.cpp(1): fatal error C1083: Cannot open include file: 'algorithm': No such file"
    diagnosis = build.diagnose_c1083(output)
    expect(diagnosis is not None, "system-header C1083 should be diagnosed")
    assert diagnosis is not None
    expect("vcvars" in diagnosis.lower(), "diagnosis names the real cause")


def test_diagnose_c1083_project_header_not_flagged() -> None:
    output = "C1083: Cannot open include file: 'my_project_header.h': No such file"
    expect(build.diagnose_c1083(output) is None, "a project header is a real bug, not the vcvars trap")


def test_diagnose_no_c1083() -> None:
    expect(build.diagnose_c1083("LINK : fatal error LNK1104") is None, "non-C1083 output not diagnosed")


def test_find_vcvars_explicit_missing() -> None:
    expect_raises(lambda: build.find_vcvars(r"Z:\no\vcvars64.bat"), "not found")


def test_find_vcvars_explicit_valid() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".bat", delete=False) as handle:
        handle.write("@echo off\n")
        name = handle.name

    try:
        expect(build.find_vcvars(name) == Path(name).resolve(), "valid explicit vcvars accepted")
    finally:
        os.unlink(name)


def test_find_vcvars_env(monkey: dict[str, str]) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".bat", delete=False) as handle:
        name = handle.name

    try:
        monkey["VCVARS64"] = name
        expect(build.find_vcvars(None) == Path(name).resolve(), "VCVARS64 env honoured")
    finally:
        os.unlink(name)


def test_find_vcvars_no_vswhere(monkey: dict[str, str]) -> None:
    # Point ProgramFiles(x86) at an empty dir so vswhere.exe cannot be found.
    with tempfile.TemporaryDirectory() as raw:
        monkey["ProgramFiles(x86)"] = raw
        monkey.pop("VCVARS64", None)
        expect_raises(lambda: build.find_vcvars(None), "vswhere.exe not found")


def test_write_build_script_configure_toggle() -> None:
    vcvars = Path("C:/vs/vcvars64.bat")
    flags = build.configure_args(build.DEFAULT_BUILD_TYPE, False)
    with_configure = build.write_build_script(vcvars, "cmake", Path("C:/b"), "xi_test", 8, flags, Path("C:/r"))
    without = build.write_build_script(vcvars, "cmake", Path("C:/b"), "xi_test", 8, [], Path("C:/r"))
    expect(vcvars.as_posix() in with_configure.replace("\\", "/"), "vcvars baked into script")
    expect("--target xi_test" in with_configure, "target baked in")
    expect("-B" in with_configure, "configure step present when unconfigured")
    expect("-B" not in without, "no configure step when already configured")


def test_configure_args_and_flavor() -> None:
    expect(build.configure_args("RelWithDebInfo", False) == ["-DCMAKE_BUILD_TYPE=RelWithDebInfo"],
           "plain build type only")
    expect("-DTRACY_ENABLE=ON" in build.configure_args("RelWithDebInfo", True), "tracy flag added")
    expect(build.configure_args("ASAN", False) == ["-DCMAKE_BUILD_TYPE=ASAN"], "sanitizer build type")
    expect(build.flavor_name("RelWithDebInfo", False) is None, "plain build has no flavor dir")
    expect(build.flavor_name("ASAN", False) == "asan", "sanitizer flavor is its lowercase name")
    expect(build.flavor_name("RelWithDebInfo", True) == "tracy", "tracy flavor when enabled")


def test_pick_build_dir_isolates_a_flavor() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = make_repo(Path(raw))
        (root / "build").mkdir()
        (root / "build" / "CMakeCache.txt").write_text("x\n", encoding="utf-8")

        chosen, configured = build.pick_build_dir(root, None, "asan")
        expect(chosen == root / "build-asan", f"sanitizer gets its own dir, got {chosen}")
        expect(not configured, "fresh flavor dir is not configured")


def _stub_unix(build_dir_configured: bool, calls: list[list[str]], targets: list[str]) -> None:
    """Point build() at recorders for an off-Windows run. Caller restores from build's dict."""
    build.IS_WINDOWS = False
    build.find_cmake = lambda: "cmake"
    build.discover_targets = lambda root: targets

    def pick(root: Path, explicit: str | None, flavor: str | None = None) -> tuple[Path, bool]:
        return Path("/b"), build_dir_configured

    def record(argv: list[str], cwd: Path | None = None) -> tuple[int, str]:
        calls.append(argv)
        return 0, ""

    build.pick_build_dir = pick
    build.stream = record


def test_unix_build_calls_cmake_directly_without_vcvars() -> None:
    """On Linux and macOS the build is plain cmake, and vcvars must never be touched."""
    calls: list[list[str]] = []
    saved = {k: getattr(build, k) for k in
             ("IS_WINDOWS", "find_cmake", "discover_targets", "pick_build_dir", "stream", "find_vcvars")}
    try:
        _stub_unix(True, calls, ["xi_test"])

        def boom(explicit: str | None = None) -> Path:
            raise AssertionError("find_vcvars must not run off Windows")

        build.find_vcvars = boom
        code = build.build(Path("/r"), "xi_test", None, 4, None)
    finally:
        for key, value in saved.items():
            setattr(build, key, value)

    expect(code == 0, "unix build succeeds")
    expect(len(calls) == 1, "configured dir builds without a configure step")
    argv = calls[0]
    expect(argv[0] == "cmake" and "--build" in argv, "invokes cmake --build")
    expect("--target" in argv and "xi_test" in argv, "passes the target")


def test_unix_build_configures_first_when_needed() -> None:
    calls: list[list[str]] = []
    saved = {k: getattr(build, k) for k in
             ("IS_WINDOWS", "find_cmake", "discover_targets", "pick_build_dir", "stream")}
    try:
        _stub_unix(False, calls, ["xi_map"])
        build.build(Path("/r"), "xi_map", None, 4, None)
    finally:
        for key, value in saved.items():
            setattr(build, key, value)

    expect(len(calls) == 2, "unconfigured dir runs configure then build")
    expect("-B" in calls[0], "first call configures")
    expect("--build" in calls[1], "second call builds")


def main() -> int:
    passed = 0
    failed = 0
    for name, func in sorted(globals().items()):
        if not name.startswith("test_") or not callable(func):
            continue

        saved = dict(os.environ)
        try:
            if "monkey" in func.__code__.co_varnames[: func.__code__.co_argcount]:
                func(os.environ)
            else:
                func()

            passed += 1
        except AssertionError as error:
            failed += 1
            print(f"FAIL {name}: {error}")
        except Exception as error:  # noqa: BLE001
            failed += 1
            print(f"ERROR {name}: {type(error).__name__}: {error}")
        finally:
            os.environ.clear()
            os.environ.update(saved)

    total = passed + failed
    print(f"{passed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
