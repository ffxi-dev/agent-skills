#!/usr/bin/env python3
"""Tests for the skill-README generator.

Runs under pytest or standalone: `python tools/test_gen_skill_readmes.py`.

Covers the frontmatter parse (both the inline and folded styles this repo uses) and the
rendered output, plus a real check against the live skills so a format the parser cannot
read fails here rather than shipping a blank README.
"""

from __future__ import annotations

import gen_skill_readmes as gen

INLINE = """---
name: lsb-cpp-style
description: C++ style rules for LandSandBoat. Use when writing C++.
license: MIT
---

# body
"""

FOLDED = """---
name: ffxi-wiki
description: >
  Look up FFXI game data across three wikis. Use for any question about FFXI content:
  what does X do, where does Y drop.
license: MIT
compatibility: Requires Python 3.9+ and about 1GB of disk.
---

# body
"""

QUOTED = """---
name: thing
description: "A quoted one liner."
---
"""


def test_inline_description() -> None:
    fields = gen.parse_frontmatter(INLINE)
    assert fields["name"] == "lsb-cpp-style"
    assert fields["description"].startswith("C++ style rules")
    assert fields["license"] == "MIT"


def test_folded_description_joins_to_one_line() -> None:
    fields = gen.parse_frontmatter(FOLDED)
    desc = fields["description"]
    assert desc.startswith("Look up FFXI game data")
    assert "\n" not in desc, "a folded scalar must collapse to a single line"
    assert "where does Y drop." in desc
    # a later top-level key must not be swallowed into the folded value
    assert "Requires Python" not in desc
    assert fields["compatibility"].startswith("Requires Python")


def test_quoted_value_is_unwrapped() -> None:
    assert gen.parse_frontmatter(QUOTED)["description"] == "A quoted one liner."


def test_missing_frontmatter_is_an_error() -> None:
    for bad in ("# no frontmatter", "---\nname: x\n(never closed)"):
        try:
            gen.parse_frontmatter(bad)
        except gen.FrontmatterError:
            continue

        raise AssertionError(f"expected FrontmatterError for {bad!r}")


def test_render_has_title_description_and_marker() -> None:
    out = gen.render({"name": "ffxi-wiki", "description": "Look things up.",
                      "compatibility": "Needs disk."})
    assert out.startswith("# ffxi-wiki\n")
    assert "Look things up." in out
    assert "See [SKILL.md](SKILL.md)" in out
    assert "**Requirements:** Needs disk." in out
    assert gen.MARKER in out


def test_render_without_compatibility_omits_requirements() -> None:
    out = gen.render({"name": "x", "description": "d"})
    assert "Requirements" not in out


def test_render_rejects_incomplete_frontmatter() -> None:
    for bad in ({"name": "x"}, {"description": "d"}, {}):
        try:
            gen.render(bad)
        except gen.FrontmatterError:
            continue

        raise AssertionError(f"expected FrontmatterError for {bad!r}")


def test_every_live_skill_parses() -> None:
    """The real SKILL.md files must all parse and render, or the generator ships blanks."""
    skills = gen.skill_dirs()
    assert skills, "no skills found"
    for skill in skills:
        fields = gen.parse_frontmatter((skill / "SKILL.md").read_text(encoding="utf-8"))
        out = gen.render(fields)
        assert out.startswith(f"# {skill.name}\n"), skill.name


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
