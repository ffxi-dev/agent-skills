#!/usr/bin/env python3
"""Tests for the corpus builder.

Runs under pytest or standalone: `python skills/ffxi-version-updates/test_build.py`.

Drives build() over synthetic upstream records, so the whole render path is covered:
category filtering, HTML flattening, filename shape, headers, machine translations,
slug fallback, collisions, and INDEX.md. No network, no archive needed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import build

FORUM_RECORD: dict[str, object] = {
    "id": "forum-49064",
    "source": "forum",
    "url": "https://forum.square-enix.com/ffxi/threads/49064",
    "date": "2015-11-10",
    "lang": "en",
    "category": "Version Update",
    "title": "(11/10/2015) Version Update",
    "body": "<div><p>The following adjustments were made:</p>"
            "<ul><li>Monster Rearing has been added.</li></ul>"
            "<script>tracking();</script><style>.x{}</style></div>",
}

NOISE_RECORD: dict[str, object] = {
    "id": "polnews-1", "source": "polnews", "url": "https://example.invalid/1",
    "date": "2015-11-11", "lang": "en", "category": "Maintenance",
    "title": "Server Maintenance", "body": "<p>Login servers are down.</p>",
}


def build_into(root: Path, records: list[dict[str, object]]) -> dict[str, str]:
    out = root / "notes"
    build.build(records, out)
    return {p.name: p.read_text(encoding="utf-8") for p in out.iterdir()}


def test_flattens_html_and_drops_script_and_style() -> None:
    text = build.to_text(str(FORUM_RECORD["body"]))
    assert "Monster Rearing has been added." in text
    assert "tracking()" not in text
    assert ".x{}" not in text
    assert "<" not in text


def test_crlf_does_not_defeat_the_blank_line_collapse() -> None:
    """Regression: legacy pages are CRLF, and a surviving \\r blocked the \\n{3,} collapse,
    leaving files that were 90% blank lines."""
    text = build.to_text("<p>one</p>\r\n\r\n\r\n\r\n\r\n<p>two</p>")
    assert "\n\n\n" not in text, repr(text)
    assert "one" in text and "two" in text


def test_keeps_only_version_update_categories() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        notes = build_into(Path(tmp), [FORUM_RECORD, NOISE_RECORD])

        assert "2015-11-10-en-11-10-2015-version-update.txt" in notes, sorted(notes)
        assert not any("maintenance" in n for n in notes)


def test_writes_the_expected_header() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        notes = build_into(Path(tmp), [FORUM_RECORD])
        body = notes["2015-11-10-en-11-10-2015-version-update.txt"]

        assert body.startswith("# (11/10/2015) Version Update\n")
        assert "# date: 2015-11-10" in body
        assert "# lang: en" in body
        assert "# category: Version Update" in body
        assert "# source: https://forum.square-enix.com/ffxi/threads/49064" in body


def test_japanese_title_falls_back_to_the_record_id_for_the_slug() -> None:
    record = dict(FORUM_RECORD, id="forum-49065", lang="ja",
                  title="2015.11.10 バージョンアップ情報")
    with tempfile.TemporaryDirectory() as tmp:
        notes = build_into(Path(tmp), [record])

        assert "2015-11-10-ja-forum-49065.txt" in notes, sorted(notes)


def test_machine_translation_is_appended_and_labelled() -> None:
    record = dict(FORUM_RECORD, translation={"body": "<p>Warrior adjustments.</p>"})
    with tempfile.TemporaryDirectory() as tmp:
        notes = build_into(Path(tmp), [record])
        body = next(v for k, v in notes.items() if k.endswith(".txt"))

        assert "Warrior adjustments." in body
        assert "machine translation" in body, "must be marked as unofficial"


def test_same_date_and_slug_do_not_overwrite_each_other() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        notes = build_into(Path(tmp), [FORUM_RECORD, dict(FORUM_RECORD, id="forum-2")])

        assert len([n for n in notes if n.endswith(".txt")]) == 2, sorted(notes)


def test_index_reports_the_count_and_date_range() -> None:
    later = dict(FORUM_RECORD, id="forum-3", date="2020-10-12",
                 title="(10/12/2020) Version Update")
    with tempfile.TemporaryDirectory() as tmp:
        notes = build_into(Path(tmp), [FORUM_RECORD, later, NOISE_RECORD])

        index = notes["INDEX.md"]
        assert index.splitlines()[0] == "2 notes, oldest 2015-11-10, newest 2020-10-12", (
            index.splitlines()[0]
        )
        assert "| 2015-11-10 | en |" in index


def test_rebuild_clears_notes_that_no_longer_exist() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_into(root, [FORUM_RECORD, dict(FORUM_RECORD, id="forum-9", date="2019-01-01",
                                             title="(01/01/2019) Version Update")])
        notes = build_into(root, [FORUM_RECORD])

        assert not any("2019-01-01" in n for n in notes), sorted(notes)


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
