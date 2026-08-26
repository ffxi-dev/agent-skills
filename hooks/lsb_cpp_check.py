#!/usr/bin/env python3
"""Edit-time C++ style check for LandSandBoat.

Covers only the rules no linter enforces. Formatting is clang-format's job and the
enabled clang-tidy checks are CI's job; duplicating either here would just make every
edit slow without catching anything new.

Reports on changed lines only. The codebase predates these rules, so checking whole
files would bury real findings under legacy noise.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

CPP_SUFFIXES: tuple[str, ...] = (".cpp", ".h", ".hpp", ".cc", ".cxx")

# Present together only in a LandSandBoat checkout or a fork of one. The plugin can be
# installed globally, so without this the hook would fire on every C++ file you edit
# anywhere.
LSB_MARKERS: tuple[str, ...] = (
    os.path.join("src", "map"),
    os.path.join("scripts", "globals"),
)

STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')
CHAR_LITERAL = re.compile(r"'(?:\\.|[^'\\])*'")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"//.*")
HUNK_HEADER = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", re.M)

TERNARY = re.compile(r"\?[^;{}]*:")
ALT_OPERATOR = re.compile(r"(?<![\w:])(and|or|not)(?![\w:])")
ALT_REPLACEMENT: dict[str, str] = {"and": "&&", "or": "||", "not": "!"}

Finding = tuple[int, str]


def blank_block_comments(text: str) -> str:
    """Blank /* */ comments across the whole file, preserving line numbering.

    Every LSB source file opens with a multi-line GPL header, so stripping block
    comments line by line leaks the entire license into the checks.
    """
    return BLOCK_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def strip_noise(line: str) -> str:
    """Blank out literals and line comments so they can't trigger a match."""
    line = STRING_LITERAL.sub('""', line)
    line = CHAR_LITERAL.sub("''", line)
    line = LINE_COMMENT.sub("", line)
    return line


def find_lsb_root(path: str) -> str | None:
    """Nearest ancestor directory that looks like a LandSandBoat checkout, else None."""
    current = os.path.dirname(os.path.abspath(path))
    while True:
        if all(os.path.isdir(os.path.join(current, marker)) for marker in LSB_MARKERS):
            return current

        parent = os.path.dirname(current)
        if parent == current:
            return None

        current = parent


def parse_hunks(diff: str) -> set[int]:
    """Post-image line numbers touched by a unified diff."""
    lines: set[int] = set()
    for hunk in HUNK_HEADER.finditer(diff):
        start = int(hunk.group(1))
        count = int(hunk.group(2) or 1)
        lines.update(range(start, start + count))
    return lines


def git(root: str, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def changed_lines(path: str, root: str) -> set[int] | None:
    """Line numbers touched relative to HEAD.

    None means check the whole file, which is correct for a new or untracked file. An
    empty set means the file is tracked and unmodified, so there is nothing to report:
    conflating that with None floods every legacy file the hook is pointed at.
    """
    tracked = git(root, "ls-files", "--error-unmatch", "--", path)
    if tracked is None or tracked.returncode != 0:
        return None

    diff = git(root, "diff", "-U0", "HEAD", "--", path)
    if diff is None or diff.returncode != 0:
        return None

    return parse_hunks(diff.stdout)


def check(path: str, root: str) -> list[Finding]:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        source = blank_block_comments(handle.read()).splitlines()

    touched = changed_lines(path, root)
    findings: list[Finding] = []

    for number, raw in enumerate(source, 1):
        if touched is not None and number not in touched:
            continue

        line = strip_noise(raw)

        if TERNARY.search(line.replace("::", "")):
            findings.append((number, "ternary: use an IILE instead"))

        alternative = ALT_OPERATOR.search(line)
        if alternative:
            keyword = alternative.group(1)
            findings.append((number, f"'{keyword}': use {ALT_REPLACEMENT[keyword]}"))

    return findings


def format_report(path: str, findings: list[Finding]) -> str:
    name = os.path.basename(path)
    body = "\n".join(f"  {name}:{number}  {message}" for number, message in findings)
    return (
        f"lsb-cpp-style violations on lines you changed:\n{body}\n"
        "See the lsb-cpp-style skill. Fix these before continuing."
    )


def run(payload: dict[str, object]) -> tuple[int, str]:
    """Core hook logic. Returns (exit code, message) so it can be tested directly."""
    tool_input = payload.get("tool_input")
    path = tool_input.get("file_path", "") if isinstance(tool_input, dict) else ""
    if not isinstance(path, str):
        return 0, ""

    if not path.endswith(CPP_SUFFIXES) or not os.path.isfile(path):
        return 0, ""

    root = find_lsb_root(path)
    if root is None:
        return 0, ""

    findings = check(path, root)
    if not findings:
        return 0, ""

    return 2, format_report(path, findings)


def main() -> int:
    try:
        raw = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if not isinstance(raw, dict):
        return 0

    code, message = run(raw)
    if message:
        print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
