#!/usr/bin/env python3
"""Generate a human-facing README.md in each skill folder from its SKILL.md.

  python tools/gen_skill_readmes.py            # write/update every skill README
  python tools/gen_skill_readmes.py --check    # fail if any is stale (CI uses this)

SKILL.md is the source of truth; the agent reads it. GitHub renders README.md when you
open a folder, so this gives a human browsing the repo the same one-line summary without a
second hand-maintained copy that can drift. The files are generated and marked as such;
edit SKILL.md and rerun, never edit the README by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"
MARKER = "<!-- generated from SKILL.md by tools/gen_skill_readmes.py; do not edit -->"


class FrontmatterError(Exception):
    pass


def parse_frontmatter(text: str) -> dict[str, str]:
    """Pull the top-level scalar keys out of a SKILL.md YAML frontmatter block.

    Handles the two styles in this repo: an inline `key: value`, and a folded
    `key: >` whose value is the more-indented lines that follow. Not a general YAML
    parser, just enough for these files, so it stays dependency-free and mypy-clean.
    """
    if not text.startswith("---"):
        raise FrontmatterError("no frontmatter block")

    end = text.find("\n---", 3)
    if end == -1:
        raise FrontmatterError("unterminated frontmatter")

    lines = text[3:end].splitlines()
    fields: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip() or line.startswith((" ", "\t")):
            continue

        if ":" not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if value in (">", "|", ">-", "|-"):
            folded: list[str] = []
            while index < len(lines) and (lines[index].startswith((" ", "\t")) or not lines[index].strip()):
                folded.append(lines[index].strip())
                index += 1

            value = " ".join(part for part in folded if part)
        elif value and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]

        fields[key] = value

    return fields


def render(fields: dict[str, str]) -> str:
    name = fields.get("name", "")
    description = fields.get("description", "").strip()
    if not name or not description:
        raise FrontmatterError("frontmatter is missing name or description")

    lines = [
        f"# {name}",
        "",
        description,
        "",
        "See [SKILL.md](SKILL.md) for the full instructions, and the "
        "[repo README](../../README.md) for how skills are installed.",
    ]

    compatibility = fields.get("compatibility", "").strip()
    if compatibility:
        lines += ["", f"**Requirements:** {compatibility}"]

    lines += ["", MARKER, ""]
    return "\n".join(lines)


def skill_dirs() -> list[Path]:
    return sorted(d for d in SKILLS.iterdir() if (d / "SKILL.md").is_file())


def main() -> int:
    check = "--check" in sys.argv
    stale: list[str] = []
    written = 0

    for skill in skill_dirs():
        try:
            fields = parse_frontmatter((skill / "SKILL.md").read_text(encoding="utf-8"))
            content = render(fields)
        except FrontmatterError as error:
            print(f"error: {skill.name}: {error}", file=sys.stderr)
            return 1

        readme = skill / "README.md"
        current = readme.read_text(encoding="utf-8") if readme.is_file() else ""
        if current == content:
            continue

        if check:
            stale.append(skill.name)
        else:
            readme.write_text(content, encoding="utf-8")
            written += 1

    if check:
        if stale:
            print("stale skill READMEs (run tools/gen_skill_readmes.py): " + ", ".join(stale),
                  file=sys.stderr)
            return 1

        print("all skill READMEs current")
        return 0

    print(f"wrote {written} README(s)" if written else "all skill READMEs already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
