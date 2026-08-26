#!/usr/bin/env python3
"""Tests for the zone render helper.

Runs under pytest or standalone: `python skills/zone-render/test_render.py`.

Covers everything up to the browser: repo discovery, zone name resolution, and every
input mistake that would otherwise surface as a 120 second wait for a mesh that is
never going to load. The render call itself needs a checkout and is exercised by hand.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import render

ZONES = {"west ronfaure": 100, "east ronfaure": 101, "pashhow marshlands": 105}


def point(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {"zone": 100, "x": 1.0, "y": -2.0, "z": 3.0}
    base.update(overrides)
    return base


def fails(points: object, fragment: str) -> None:
    try:
        render.resolve(points, ZONES)  # type: ignore[arg-type]
    except render.RenderError as error:
        assert fragment in str(error), f"expected {fragment!r} in {error}"
        return

    raise AssertionError(f"expected RenderError containing {fragment!r}")


def test_resolves_a_zone_name_to_its_id() -> None:
    out = render.resolve([point(zone="West Ronfaure")], ZONES)
    assert out[0]["zone"] == 100


def test_zone_name_match_is_case_insensitive() -> None:
    assert render.resolve([point(zone="wEsT rOnFaUrE")], ZONES)[0]["zone"] == 100


def test_accepts_a_numeric_zone_id() -> None:
    assert render.resolve([point(zone=105)], ZONES)[0]["zone"] == 105


def test_keeps_group_and_kind_untouched() -> None:
    out = render.resolve([point(group="chests", kind="Cursed Chest")], ZONES)
    assert out[0]["group"] == "chests"
    assert out[0]["kind"] == "Cursed Chest"


def test_rejects_an_unknown_zone_name() -> None:
    fails([point(zone="Nowhere")], "unknown zone name")


def test_rejects_a_zone_id_not_in_the_table() -> None:
    """A bad id renders an empty page for 120s rather than failing, so catch it here."""
    fails([point(zone=9999)], "not in the zone table")


def test_rejects_missing_or_non_numeric_coordinates() -> None:
    fails([{"zone": 100, "x": 1.0, "y": 2.0}], "no numeric z")
    fails([{"zone": 100, "x": "west", "y": 2.0, "z": 3.0}], "no numeric x")


def test_rejects_a_missing_zone() -> None:
    fails([{"x": 1.0, "y": 2.0, "z": 3.0}], "zone must be")


def test_rejects_empty_or_non_list_input() -> None:
    fails([], "non-empty JSON list")
    fails({"zone": 100}, "non-empty JSON list")
    fails(["not an object"], "not an object")


def test_rejects_a_group_spanning_two_zones() -> None:
    """shot.mjs loads only the first point's zone, so the rest land on the wrong map."""
    fails(
        [point(zone=100, group="mixed"), point(zone=101, group="mixed")],
        "spans zones",
    )


def test_groups_may_differ_in_zone_from_each_other() -> None:
    out = render.resolve(
        [point(zone=100, group="a"), point(zone=101, group="b")], ZONES
    )
    assert [p["zone"] for p in out] == [100, 101]


def test_ungrouped_points_group_by_zone() -> None:
    out = render.resolve([point(zone=100), point(zone=101)], ZONES)
    assert len(out) == 2


def test_finds_a_repo_by_explicit_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "scripts").mkdir()
        (root / "scripts" / "shot.mjs").write_text("", encoding="utf-8")

        assert render.find_repo(str(root)) == root.resolve()


def test_finds_a_repo_from_the_environment() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "scripts").mkdir()
        (root / "scripts" / "shot.mjs").write_text("", encoding="utf-8")

        os.environ["XI_VISUALIZER"] = str(root)
        try:
            assert render.find_repo(None) == root.resolve()
        finally:
            del os.environ["XI_VISUALIZER"]


def test_missing_repo_explains_how_to_get_one() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            render.find_repo(tmp)
        except render.RenderError as error:
            assert "submodule update --init" in str(error), "must name the 150MB prerequisite"
            return

        raise AssertionError("expected RenderError")


def test_uninitialised_submodule_is_reported_before_the_browser_starts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "public" / "ximeshes").mkdir(parents=True)
        try:
            render.check_prerequisites(root)
        except render.RenderError as error:
            assert "submodule" in str(error)
            return

        raise AssertionError("expected RenderError")


def test_zone_table_is_read_from_the_checkout() -> None:
    """The table must come from the visualizer, so ids can never disagree with it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src" / "data").mkdir(parents=True)
        (root / "src" / "data" / "zones.json").write_text(
            json.dumps([{"id": 100, "name": "West Ronfaure"}]), encoding="utf-8"
        )

        assert render.load_zones(root) == {"west ronfaure": 100}


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
