#!/usr/bin/env python3
"""Tests for the edit-time C++ check.

Runs under pytest or standalone: `python hooks/test_lsb_cpp_check.py`.

The end-to-end tests build a throwaway directory that looks like a LandSandBoat checkout
and drive the hook through its real entry point, because the two bugs this script has
already had (a leaking GPL header, an unresolvable path) were both invisible to the
line-level unit tests.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from lsb_cpp_check import (
    ALT_OPERATOR,
    LSB_MARKERS,
    TERNARY,
    blank_block_comments,
    find_lsb_root,
    parse_hunks,
    run,
    strip_noise,
)

VIOLATING_SOURCE = """/*
  redistribute it and/or modify, either version 3 or later
*/
#include <cstdint>

int compute(bool isCritical, int base)
{
    const auto damage = isCritical ? base * 2 : base;
    if (base > 0 and damage > 0)
    {
        return damage;
    }

    return 0;
}
"""

CLEAN_SOURCE = """/*
  redistribute it and/or modify, either version 3 or later
*/
#include <cstdint>

int compute(bool isCritical, int base)
{
    const auto damage = [&]() -> int
    {
        if (isCritical)
        {
            return base * 2;
        }

        return base;
    }();

    if (base > 0 && damage > 0)
    {
        return damage;
    }

    return 0;
}
"""


def hits(line: str) -> int:
    stripped = strip_noise(blank_block_comments(line))
    return bool(TERNARY.search(stripped.replace("::", ""))) + bool(
        ALT_OPERATOR.search(stripped)
    )


def test_flags_ternary_and_alternative_operators() -> None:
    assert hits("const auto x = a ? b : c;") == 1
    assert hits("if (a and b)") == 1
    assert hits("if (not ready)") == 1


def test_ignores_conforming_code() -> None:
    assert hits("const auto y = value;") == 0
    assert hits("if (a && b)") == 0
    assert hits("if (!ready)") == 0


def test_ignores_literals_and_comments() -> None:
    assert hits('const auto s = "a ? b : c";') == 0
    assert hits("// use a ? b : c here") == 0


def test_does_not_confuse_colons_for_ternaries() -> None:
    assert hits("case Foo::Bar:") == 0
    assert hits("xi::ZoneId id;") == 0
    assert hits("int x : 3;") == 0


def test_does_not_match_operators_inside_identifiers() -> None:
    assert hits("const auto n = expand(random);") == 0
    assert hits("const auto b = borland;") == 0


def test_multiline_block_comment_does_not_leak() -> None:
    """Regression: this leaked the GPL header in every file, 2794 false positives."""
    header = "/*\n  redistribute it and/or modify\n  either version 3, or\n*/\nint x = 1;"
    blanked = blank_block_comments(header)
    assert not [line for line in blanked.splitlines() if ALT_OPERATOR.search(line)]
    assert len(blanked.splitlines()) == 5, "line numbering must be preserved"


def test_parses_diff_hunks() -> None:
    diff = (
        "@@ -1,2 +1,2 @@\n-old\n+new\n"
        "@@ -40,0 +41,3 @@\n+a\n+b\n+c\n"
        "@@ -90 +90 @@\n-x\n+y\n"
    )
    assert parse_hunks(diff) == {1, 2, 41, 42, 43, 90}


def make_lsb_tree(root: str) -> None:
    for marker in LSB_MARKERS:
        os.makedirs(os.path.join(root, marker), exist_ok=True)


def test_gate_ignores_files_outside_a_checkout() -> None:
    with tempfile.TemporaryDirectory() as plain:
        source = os.path.join(plain, "unrelated.cpp")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write(VIOLATING_SOURCE)

        assert find_lsb_root(source) is None
        assert run({"tool_input": {"file_path": source}}) == (0, "")


def test_end_to_end_reports_violations_inside_a_checkout() -> None:
    with tempfile.TemporaryDirectory() as root:
        make_lsb_tree(root)
        source = os.path.join(root, "src", "map", "example.cpp")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write(VIOLATING_SOURCE)

        code, message = run({"tool_input": {"file_path": source}})

        assert code == 2
        assert "example.cpp:8" in message, "ternary line"
        assert "example.cpp:9" in message, "alternative operator line"
        assert "'and': use &&" in message
        assert "and/or modify" not in message, "GPL header must not be reported"


def test_end_to_end_stays_quiet_on_conforming_code() -> None:
    with tempfile.TemporaryDirectory() as root:
        make_lsb_tree(root)
        source = os.path.join(root, "src", "map", "example.cpp")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write(CLEAN_SOURCE)

        assert run({"tool_input": {"file_path": source}}) == (0, "")


def init_repo(root: str) -> bool:
    """Commit VIOLATING_SOURCE as src/map/example.cpp. False if git is unavailable."""
    make_lsb_tree(root)
    source = os.path.join(root, "src", "map", "example.cpp")
    with open(source, "w", encoding="utf-8") as handle:
        handle.write(VIOLATING_SOURCE)

    commands = [
        ["git", "init", "-q"],
        ["git", "config", "user.email", "test@example.invalid"],
        ["git", "config", "user.name", "test"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "seed"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True)
        if result.returncode != 0:
            return False

    return True


def test_tracked_unmodified_file_reports_nothing() -> None:
    """Regression: an empty diff meant 'check everything', flooding untouched files."""
    with tempfile.TemporaryDirectory() as root:
        if not init_repo(root):
            print("SKIP tracked_unmodified: git unavailable")
            return

        source = os.path.join(root, "src", "map", "example.cpp")
        assert run({"tool_input": {"file_path": source}}) == (0, "")


def test_reports_only_the_lines_actually_edited() -> None:
    with tempfile.TemporaryDirectory() as root:
        if not init_repo(root):
            print("SKIP only_edited_lines: git unavailable")
            return

        source = os.path.join(root, "src", "map", "example.cpp")
        with open(source, "r", encoding="utf-8") as handle:
            lines = handle.readlines()

        # introduce one new violation; the pre-existing ones must stay silent
        lines.insert(4, "static int flags = a ? 1 : 2;\n")
        with open(source, "w", encoding="utf-8") as handle:
            handle.writelines(lines)

        code, message = run({"tool_input": {"file_path": source}})

        assert code == 2
        assert "example.cpp:5" in message, "the edited line"
        assert message.count("ternary") == 1, f"legacy lines leaked:\n{message}"


def test_untracked_file_is_checked_in_full() -> None:
    with tempfile.TemporaryDirectory() as root:
        if not init_repo(root):
            print("SKIP untracked_file: git unavailable")
            return

        source = os.path.join(root, "src", "map", "brand_new.cpp")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write(VIOLATING_SOURCE)

        code, message = run({"tool_input": {"file_path": source}})

        assert code == 2
        assert "brand_new.cpp:8" in message


def test_ignores_non_cpp_and_malformed_payloads() -> None:
    with tempfile.TemporaryDirectory() as root:
        make_lsb_tree(root)
        source = os.path.join(root, "src", "map", "notes.md")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write("a ? b : c and d")

        assert run({"tool_input": {"file_path": source}}) == (0, "")

    assert run({}) == (0, "")
    assert run({"tool_input": None}) == (0, "")
    assert run({"tool_input": {"file_path": 42}}) == (0, "")
    assert run({"tool_input": {"file_path": "/does/not/exist.cpp"}}) == (0, "")


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
        except AssertionError as error:
            print(f"FAIL {test.__name__}: {error}")
            failures += 1

    print(f"{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
