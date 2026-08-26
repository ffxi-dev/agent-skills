#!/usr/bin/env python3
"""Tests for the FFXI wiki lookup.

Runs under pytest or standalone: `python skills/ffxi-wiki/test_wiki.py`.

Builds a real SQLite index from synthetic JSONL in the documented release schema, then
drives every query path over it. No download, no network. The fixtures deliberately
mirror the corpus's awkward parts: `wikitext` on MediaWiki against `text` on FFO, the
`Category:` prefix that article category lists drop, redirect files that hold only
{from, to}, and pages carrying a verification flag.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import sqlite3
import tempfile
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import Iterator

import wiki

BG = [
    {"title": "Joyeuse", "pageid": 12345, "ns": 0,
     "url": "https://www.bg-wiki.com/ffxi/Joyeuse", "revid": 696666,
     "timestamp": "2024-03-11T17:20:37Z", "categories": ["Sword", "Item"],
     "wikitext": "{{item\n|description=Occasionally attacks twice.\n}} A famed sword."},
    {"title": "Acrolith", "pageid": 222, "ns": 0,
     "url": "https://www.bg-wiki.com/ffxi/Acrolith", "categories": ["Bestiary"],
     "wikitext": "{{Bestiary Description 2|An animated statue.}} {{verification}}"},
]

FFO = [
    {"title": "デッドエイム", "pageid": 23695, "ns": 0,
     "url": "https://wiki.ffo.jp/html/23695.html",
     "reading": "でっどえいむ/Dead Aim", "categories": ["ジョブ", "ジョブ特性"],
     "text": "[狩人](/html/255.html)のジョブ特性の一つ。"},
    {"title": "ジョワユーズ", "pageid": 999, "ns": 0,
     "url": "https://wiki.ffo.jp/html/999.html", "reading": "じょわゆーず/Joyeuse",
     "categories": ["武器"], "text": "片手剣の一つ。追加効果ダブルアタック。"},
]

CLOPEDIA = [
    {"title": "Joyeuse", "pageid": 77, "ns": 0,
     "url": "https://ffxiclopedia.fandom.com/wiki/Joyeuse",
     "categories": ["Information Needed"], "wikitext": "An old page about Joyeuse."},
]

BG_CATEGORIES = [
    {"title": "Category:Sword", "pageid": 5, "ns": 14,
     "url": "https://www.bg-wiki.com/ffxi/Category:Sword", "categories": [],
     "wikitext": "Swords of Vana'diel."},
]

BG_REDIRECTS: list[dict[str, object]] = [{"from": "13 Knot Quipus", "to": "Joyeuse"}]


def corpus(root: Path) -> Path:
    """Write the fixtures out as the release would lay them on disk."""
    files: dict[str, list[dict[str, object]]] = {
        "bg-wiki.jsonl": BG,
        "bg-wiki-categories.jsonl": BG_CATEGORIES,
        "bg-wiki-redirects.jsonl": BG_REDIRECTS,
        "ffo-wiki.jsonl": FFO,
        "ffxiclopedia.jsonl": CLOPEDIA,
    }
    for name, records in files.items():
        with open(root / name, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    (root / "manifest.json").write_text(
        json.dumps({"corpus": "ffxi-wiki-dumps", "generated": "2026-08-26T00:00:00Z",
                    "files": []}), encoding="utf-8")
    return root


@contextmanager
def indexed(root: Path) -> Iterator[sqlite3.Connection]:
    """Windows will not delete the temp dir while the sqlite handle is open."""
    wiki.build_index(corpus(root), root / "wiki.db")
    connection = sqlite3.connect(root / "wiki.db")
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def query(connection: sqlite3.Connection, command: str, text: str) -> str:
    """Run a command the way the CLI does and give back what the user would see."""
    args = type("Args", (), {"query": text, "limit": 20, "source": None})()
    handlers = {"title": wiki.cmd_title, "search": wiki.cmd_search, "body": wiki.cmd_body,
                "category": wiki.cmd_category, "name": wiki.cmd_name}
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        handlers[command](connection, args)
    return buffer.getvalue()


def test_indexes_both_body_fields() -> None:
    """MediaWiki carries `wikitext`, FFO carries `text`; neither carries both."""
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        # keyed by source too: BG and FFXIclopedia both have a page called Joyeuse
        bodies = {
            (str(row["source"]), str(row["title"])): str(row["body"])
            for row in connection.execute("SELECT source, title, body FROM pages")
        }
        assert "Occasionally attacks twice" in bodies[("bg-wiki", "Joyeuse")]
        assert "ジョブ特性" in bodies[("ffo-wiki", "デッドエイム")]


def test_redirect_rows_do_not_become_pages() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        titles = [r["title"] for r in connection.execute("SELECT title FROM pages")]
        assert "13 Knot Quipus" not in titles
        assert connection.execute("SELECT COUNT(*) c FROM redirects").fetchone()["c"] == 1


def test_title_lookup_is_case_insensitive_and_ordered_by_trust() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "title", "joyeuse")

    assert "BG Wiki" in out and "FFXIclopedia" in out
    assert out.index("BG Wiki") < out.index("FFXIclopedia"), "BG outranks FFXIclopedia"


def test_title_bridges_an_english_name_to_the_japanese_ffo_page() -> None:
    """FFO pages are titled in Japanese; an English title must still surface them via reading."""
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "title", "Joyeuse")

    assert "FFO Wiki (JP)" in out, "the JP page must appear for an English title query"
    assert "ジョワユーズ" in out
    assert out.index("FFO Wiki (JP)") < out.index("BG Wiki"), "JP outranks the English wikis"
    assert "confidence: high" in out, "JP plus another wiki is high confidence"


def test_japanese_reading_renders_without_error() -> None:
    """Guards the data path that crashed on a real cp1252 console (see the utf-8 reconfigure)."""
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "title", "Dead Aim")

    assert "でっどえいむ/Dead Aim" in out


def test_redirect_alias_resolves_to_the_real_page() -> None:
    """Acceptance check 2."""
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "title", "13 Knot Quipus")

    assert "redirect to 'Joyeuse'" in out
    assert "bg-wiki.com/ffxi/Joyeuse" in out


def test_every_result_carries_source_and_url() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "title", "Joyeuse")

    assert "https://www.bg-wiki.com/ffxi/Joyeuse" in out
    assert "https://ffxiclopedia.fandom.com/wiki/Joyeuse" in out


def test_verification_flag_is_surfaced() -> None:
    """Acceptance check 5: never pass a flagged claim through silently."""
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "title", "Acrolith")

    assert "unverified" in out


def test_incomplete_category_is_surfaced() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "title", "Joyeuse")

    assert "incomplete" in out


def test_a_claim_with_no_jp_entry_is_reported_as_such() -> None:
    """Acceptance check 6: a BG-only claim must not read as settled fact."""
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "title", "Acrolith")

    assert "confidence: low" in out
    assert "No JP entry" in out


def test_jp_agreement_raises_confidence() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        connection.execute(
            "INSERT INTO pages(source, rank, title, url, categories, body)"
            " VALUES ('ffo-wiki', 1, 'Joyeuse', 'https://wiki.ffo.jp/html/1.html', '[]', 'x')")
        connection.commit()
        out = query(connection, "title", "Joyeuse")

    assert "confidence: high" in out


def test_category_lookup_ignores_the_prefix_mismatch() -> None:
    """Category: page titles keep the prefix; article category lists drop it."""
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        bare = query(connection, "category", "Sword")
        prefixed = query(connection, "category", "Category:Sword")

    assert "Joyeuse" in bare
    assert "Joyeuse" in prefixed


def test_japanese_name_lookup_via_reading() -> None:
    """Acceptance check 4: Dead Aim -> デッドエイム through the FFO reading field."""
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "name", "Dead Aim")

    assert "デッドエイム" in out
    assert "でっどえいむ/Dead Aim" in out


def test_name_lookup_works_from_japanese_too() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "name", "ジョワユーズ")

    assert "Joyeuse" in out


def test_body_search_finds_text_and_shows_context() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "body", "Occasionally")

    assert "Joyeuse" in out
    assert "attacks twice" in out, "must show surrounding context, not just the hit"


def test_title_substring_search() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "search", "oyeus")

    assert "Joyeuse" in out


def test_missing_title_says_so_rather_than_guessing() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = query(connection, "title", "Excalipoor")

    assert "no match" in out


def test_checksum_mismatch_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "bg-wiki.jsonl.gz"
        with gzip.open(archive, "wb") as handle:
            handle.write(b'{"title": "x"}\n')

        wiki.verify(archive, hashlib.sha256(archive.read_bytes()).hexdigest())
        try:
            wiki.verify(archive, "0" * 64)
        except wiki.WikiError as error:
            assert "failed its checksum" in str(error)
            return

        raise AssertionError("a bad checksum must be refused")


def test_index_rebuilds_without_a_download() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # 5 pages across three wikis, plus one redirect row
        counts = wiki.build_index(corpus(root), root / "wiki.db")
        assert sum(counts.values()) == 7, counts

        again = wiki.build_index(root, root / "wiki.db")
        assert again == counts, "rebuild must be idempotent"


def test_empty_corpus_directory_is_an_error() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            wiki.build_index(Path(tmp), Path(tmp) / "wiki.db")
        except wiki.WikiError as error:
            assert "no .jsonl files" in str(error)
            return

        raise AssertionError("expected WikiError")


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
