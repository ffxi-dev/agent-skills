#!/usr/bin/env python3
"""Tests for the FFXI resources lookup.

Runs under pytest or standalone: `python skills/ffxi-resources/test_resources.py`.

Builds a real SQLite index from synthetic NDJSON in the documented release schema, then
drives every query path over it. No download, no network. The fixtures mirror the awkward
parts of the real data: items carry `name` as a nested object plus a base64 `icon` to strip,
strings and events key on a composite (zone_id, string_id)/(zone_id, event_id), events carry
byte_code + lua, and spells key on `index` (not `id`, which collides).
"""

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import Iterator

import resources

TAG = "30260805_0"

ITEMS: list[dict[str, object]] = [
    {"id": 18, "resource_id": 65018, "name": {"english": "Excalibur",
     "english_log_single": "Excalibur", "english_log_plural": "Excaliburs",
     "japanese": "エクスカリバー"}, "description": {"english": "A holy sword.", "japanese": "聖剣。"},
     "type": "Weapon", "stack_size": 1, "flags": ["Rare", "Exclusive"], "targets": [],
     "icon": "iVBORw0KGgoAAAANSUhEUgAA_base64_should_be_stripped", "category": "weapon"},
]

STRINGS: list[dict[str, object]] = [
    {"zone_id": 1, "block": 0, "string_id": 0, "layer": None,
     "content": "A mog tablet has been discovered in [West Ronfaure]!"},
    {"zone_id": 1, "block": 0, "string_id": 5, "layer": None,
     "content": "ラ・テーヌ高原"},
]

EVENTS: list[dict[str, object]] = [
    {"zone_id": 1, "actor_id": 16781340, "block": 0, "layer": None, "idx": 0,
     "event_id": 100, "entrypoint": 0, "byte_code": "0a1b2c", "lua": "function onZoneIn()\nend",
     "params": [], "imed": {}},
    {"zone_id": 1, "actor_id": 16781340, "block": 0, "layer": None, "idx": 1,
     "event_id": -1, "entrypoint": 0, "byte_code": "00", "lua": None, "params": [], "imed": {}},
]

SPELLS: list[dict[str, object]] = [
    {"id": 0, "index": 1, "name": "Cure", "description": "Restores HP.", "type": "WhiteMagic",
     "mp_cost": 8, "icon_id": 3, "valid_targets": ["Self", "Player"]},
    {"id": 0, "index": 2, "name": "Cure II", "description": "Restores more HP.",
     "type": "WhiteMagic", "mp_cost": 24, "icon_id": 3, "valid_targets": ["Self", "Player"]},
]

ENTITIES: list[dict[str, object]] = [
    {"zone_id": 1, "block": 0, "entity_id": 16781313, "layer": None, "name": "Snipper"},
]

ZONES: list[dict[str, object]] = [
    {"id": 100, "name": "Bastok Mines", "name_alt": "Bastok Mines", "name_short": "bastok_mines"},
]


def corpus(root: Path) -> Path:
    files: dict[str, list[dict[str, object]]] = {
        "items.ndjson": ITEMS,
        "strings.ndjson": STRINGS,
        "events.ndjson": EVENTS,
        "spells.ndjson": SPELLS,
        "entities.ndjson": ENTITIES,
        "zones.ndjson": ZONES,
    }
    for name, records in files.items():
        with open(root / name, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    (root / "release.json").write_text(json.dumps({"tag": TAG}), encoding="utf-8")
    return root


@contextmanager
def indexed(root: Path) -> Iterator[sqlite3.Connection]:
    """Windows will not delete the temp dir while the sqlite handle is open."""
    resources.build_index(corpus(root), root / "resources.db")
    connection = sqlite3.connect(root / "resources.db")
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def run(connection: sqlite3.Connection, command: str, **fields: object) -> str:
    args = type("Args", (), {"limit": 20, "command": command, **fields})()
    handlers = {
        "get": resources.cmd_get, "search": resources.cmd_search,
        "string": resources.cmd_string, "event": resources.cmd_event,
        "item": resources.cmd_convenience, "spell": resources.cmd_convenience,
        "ability": resources.cmd_convenience, "status": resources.cmd_convenience,
        "keyitem": resources.cmd_convenience, "entity": resources.cmd_convenience,
        "zone": resources.cmd_convenience,
    }
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        handlers[command](connection, args)
    return buffer.getvalue()


def test_item_name_english_is_indexed_and_icon_is_stripped() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        row = connection.execute(
            "SELECT name, body FROM records WHERE dataset='items' AND pk='18'").fetchone()
        assert row["name"] == "Excalibur", "item name.english must be the searchable name"
        assert "base64_should_be_stripped" not in row["body"], "icon must be stripped"
        assert '"icon"' not in row["body"]


def test_strings_key_on_zone_and_string_id() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = run(connection, "string", zone_id="1", string_id="0")

    assert "mog tablet" in out
    assert f"{resources.SITE}/v/{TAG}/strings/1-0" in out


def test_events_key_on_zone_and_event_id_and_show_byte_code_and_lua() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = run(connection, "event", zone_id="1", event_id="100")

    assert "byte_code: 0a1b2c" in out
    assert "onZoneIn" in out
    assert f"{resources.SITE}/v/{TAG}/events/1-100" in out


def test_signed_negative_event_id_keys_correctly() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = run(connection, "event", zone_id="1", event_id="-1")

    assert "byte_code: 00" in out
    assert "lua: None" in out


def test_spells_key_on_index_not_id() -> None:
    """Every spell has id=0; the unique key is `index`."""
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        both = connection.execute(
            "SELECT pk FROM records WHERE dataset='spells' ORDER BY pk").fetchall()
        assert [r["pk"] for r in both] == ["1", "2"], "spells must key on index, not colliding id"

        out = run(connection, "get", dataset="spells", id="2")

    assert "Cure II" in out
    assert f"{resources.SITE}/v/{TAG}/spells/2" in out


def test_convenience_item_by_id_and_by_name() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        by_id = run(connection, "item", query="18")
        by_name = run(connection, "item", query="Excalibur")

    assert "Excalibur" in by_id
    assert "Excalibur" in by_name
    assert f"{resources.SITE}/v/{TAG}/items/18" in by_id


def test_convenience_spell_by_index_and_name() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        by_index = run(connection, "spell", query="1")
        by_name = run(connection, "spell", query="Cure")

    assert "Cure" in by_index
    assert "Cure" in by_name


def test_convenience_zone_by_id_and_name() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = run(connection, "zone", query="Bastok")

    assert "Bastok Mines" in out
    assert f"{resources.SITE}/v/{TAG}/zones/100" in out


def test_entity_by_composite_pk() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = run(connection, "entity", query="1-16781313")

    assert "Snipper" in out
    assert f"{resources.SITE}/v/{TAG}/entities/1-16781313" in out


def test_search_within_a_dataset() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = run(connection, "search", dataset="spells", query="Cure")

    assert "Cure" in out and "Cure II" in out


def test_trusted_line_is_stated_on_every_result() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = run(connection, "item", query="18")

    assert "trusted" in out and "retail FFXI" in out


def test_japanese_content_renders_without_error() -> None:
    """Guards the data path that crashed on a real cp1252 console (see the utf-8 reconfigure)."""
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = run(connection, "string", zone_id="1", string_id="5")

    assert "ラ・テーヌ高原" in out


def test_link_uses_the_recorded_tag_and_route() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        assert resources.tag_of(connection) == TAG
        link = resources.link_for("items", "18", TAG)
        assert link == f"{resources.SITE}/v/{TAG}/items/18"
        # datasets without a human page get no link
        assert resources.link_for("spells", "1", TAG) == f"{resources.SITE}/v/{TAG}/spells/1"
        assert resources.link_for("merits", "2", TAG) is None


def test_missing_record_says_no_match() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = run(connection, "get", dataset="items", id="99999")

    assert "no match" in out


def test_unknown_dataset_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp, indexed(Path(tmp)) as connection:
        out = run(connection, "get", dataset="nonsense", id="1")

    assert "unknown dataset" in out


def test_index_rebuilds_without_a_download() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        counts = resources.build_index(corpus(root), root / "resources.db")
        assert counts["items"] == 1
        assert counts["spells"] == 2
        assert counts["strings"] == 2

        again = resources.build_index(root, root / "resources.db")
        assert again == counts, "rebuild must be idempotent"


def test_empty_corpus_directory_is_an_error() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            resources.build_index(Path(tmp), Path(tmp) / "resources.db")
        except resources.ResourceError as error:
            assert "no .ndjson files" in str(error)
            return

        raise AssertionError("expected ResourceError")


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
