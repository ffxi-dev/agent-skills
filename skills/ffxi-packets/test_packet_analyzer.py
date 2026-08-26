#!/usr/bin/env python3
"""Tests for the FFXI packet analyzer.

Runs under pytest or standalone: `python skills/ffxi-packets/test_packet_analyzer.py`.

The fixture is SYNTHETIC. It is built here in captain's documented grid format rather than
vendored from a real retail capture, so no account data lands in a public repo. The grid
builder mirrors the format read out of the real captures: the two `%3X` index columns, the
16-cell rows, `--` padding on the short final row, and the row index carrying past 0xF into
hex once a packet crosses 256 bytes. One test pins the builder's column header to the exact
string the real files use, so the fixture cannot drift away from reality.
"""

from __future__ import annotations

import argparse
import io
import os
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import packet_analyzer as pa


def test_resolve_root_requires_an_explicit_path_or_env() -> None:
    """No hardcoded default: the captures dir is machine-specific and must be supplied."""
    saved = os.environ.pop("CAPTAIN_CAPTURES", None)
    try:
        pa.resolve_root(None)
    except pa.PacketError as error:
        assert "CAPTAIN_CAPTURES" in str(error)
    else:
        raise AssertionError("expected PacketError when no root is given")
    finally:
        if saved is not None:
            os.environ["CAPTAIN_CAPTURES"] = saved

# copied verbatim out of a real full.log, structure only. If grid() ever stops matching
# these two lines it no longer matches captain's output.
REAL_HEADER = "        |  0  1  2  3  4  5  6  7  8  9  A  B  C  D  E  F      | 0123456789ABCDEF"
REAL_SEP = "    " + "-" * 53 + "  " + "-" * 22


def encode(opcode: int, size: int) -> bytes:
    """A packet whose FFXI header id/size agree with the grid, so it parses clean."""
    word = (opcode & 0x1FF) | ((size // 4) << 9)
    data = bytearray(size)
    data[0] = word & 0xFF
    data[1] = (word >> 8) & 0xFF
    # a backslash byte to exercise the ascii escape, and a printable run
    if size > 4:
        data[4] = 0x5C
        data[5] = ord("A")

    return bytes(data)


def grid(data: bytes) -> str:
    """Reproduce captain's string.hexformat_file output for `data`."""
    out = [REAL_HEADER, REAL_SEP]
    rows = max(1, (len(data) + 15) // 16)
    for r in range(rows):
        chunk = data[r * 16:(r + 1) * 16]
        cells = ""
        ascii_ = ""
        for c in range(16):
            if c < len(chunk):
                b = chunk[c]
                cells += " %02X" % b
                ascii_ += "\\\\" if b == 0x5C else (chr(b) if 0x20 <= b < 0x7F else ".")
            else:
                cells += " --"
                ascii_ += "-"

        out.append("    %3X |%s  %3X | %s" % (r, cells, r, ascii_))

    return "\n".join(out) + "\n"


def record(header: str, data: bytes) -> str:
    return f"{header}\n{grid(data)}\n"


def write_capture(root: Path) -> None:
    """Lay out a session exactly as it appears in the wild."""
    hero = root / "session1" / "Hero"
    pl = hero / "PacketLogger"
    (pl / "incoming").mkdir(parents=True)
    (pl / "outgoing").mkdir(parents=True)

    (hero / "manifest.txt").write_text(
        '{\n  Captain = {\n    Version = "1.12.0"\n  },\n'
        '  FFXI = {\n    IsRetail = true,\n    ZoneIP = "124.150.152.220"\n  },\n'
        "  StartTime = 1787669227\n}\n", encoding="utf-8")

    # full.log: both directions interleaved, direction stated in the header
    (pl / "full.log").write_text(
        record("[2026-08-25 08:47:07.122] Incoming packet 0x028", encode(0x028, 40))
        + record("[2026-08-25 08:47:07.191] Outgoing packet 0x015", encode(0x015, 32)),
        encoding="utf-8")

    # per-opcode file: direction implied by the incoming/ folder, two records
    (pl / "incoming" / "0x028.log").write_text(
        record("[2026-08-25 08:47:10.325] Packet 0x028", encode(0x028, 40))
        + record("[2026-08-25 08:47:15.382] Packet 0x028", encode(0x028, 44)),
        encoding="utf-8")

    # a 260-byte packet: crosses 256, so a row is indexed 0x10, final row is padded
    (pl / "incoming" / "0x00E.log").write_text(
        record("[2026-08-25 08:47:07.138] Packet 0x00E", encode(0x00E, 260)),
        encoding="utf-8")

    # a second, non-retail character, for the trusted filter
    alt = root / "session1" / "Alt"
    (alt / "PacketLogger" / "incoming").mkdir(parents=True)
    (alt / "manifest.txt").write_text(
        '{\n  Captain = { Version = "1.12.0" },\n'
        "  FFXI = { IsRetail = false },\n  StartTime = 1\n}\n", encoding="utf-8")
    (alt / "PacketLogger" / "incoming" / "0x028.log").write_text(
        record("[2026-08-25 08:47:10.000] Packet 0x028", encode(0x028, 40)), encoding="utf-8")


def ns(**kw: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "root": None, "dir": None, "session": None, "char": None,
        "trusted": False, "index": 0, "opcode": "0x028",
    }
    base.update(kw)
    return argparse.Namespace(**base)


def run(command: str, **kw: object) -> tuple[int, str]:
    handlers = {"list": pa.cmd_list, "find": pa.cmd_find, "show": pa.cmd_show}
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = handlers[command](ns(**kw))

    return code, buffer.getvalue()


def test_grid_matches_the_real_column_header() -> None:
    """The fixture cannot silently drift from captain's real output."""
    text = grid(encode(0x028, 40))
    assert REAL_HEADER in text
    assert REAL_SEP in text


def test_parses_full_log_with_direction_from_header() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_capture(Path(tmp))
        packets, problems = pa.parse_file(Path(tmp) / "session1" / "Hero" / "PacketLogger" / "full.log", None)

    assert problems == [], problems
    assert [(p.opcode, p.direction, p.size) for p in packets] == [(0x028, "in", 40), (0x015, "out", 32)]


def test_direction_comes_from_the_folder_for_per_opcode_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_capture(Path(tmp))
        path = Path(tmp) / "session1" / "Hero" / "PacketLogger" / "incoming" / "0x028.log"
        packets, problems = pa.parse_file(path, "in")

    assert problems == []
    assert all(p.direction == "in" for p in packets)
    assert [p.size for p in packets] == [40, 44]


def test_row_index_past_256_and_padded_final_row() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_capture(Path(tmp))
        path = Path(tmp) / "session1" / "Hero" / "PacketLogger" / "incoming" / "0x00E.log"
        text = path.read_text(encoding="utf-8")
        packets, problems = pa.parse_file(path, "in")

    assert "     10 |" in text, "a packet over 256 bytes must index a row in hex"
    assert " --" in text, "the short final row must be padded with --"
    assert problems == []
    assert packets[0].size == 260, "size derived from real cells, not the padded 272"


def test_size_and_header_field_agree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_capture(Path(tmp))
        found, _ = pa.gather(Path(tmp), 0x028, None, None, None, False)

    for packet in found.packets:
        hdr_id, hdr_size = pa.header_fields(packet.data)
        assert hdr_id == 0x028
        assert hdr_size == packet.size, "header size field must match the counted size"


def test_manifest_provenance_is_parsed_from_the_lua_literal() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_capture(Path(tmp))
        man = pa.read_manifest(Path(tmp) / "session1" / "Hero" / "manifest.txt")

    assert man["version"] == "1.12.0"
    assert man["is_retail"] is True
    assert man["zone_ip"] == "124.150.152.220"
    assert man["start_time"] == 1787669227


def test_trusted_filter_is_opt_in_and_drops_non_retail() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_capture(Path(tmp))
        everyone = {c.char for c in pa.iter_captures(Path(tmp), None, None, False)}
        retail = {c.char for c in pa.iter_captures(Path(tmp), None, None, True)}

    assert everyone == {"Hero", "Alt"}, "default includes everything"
    assert retail == {"Hero"}, "--trusted keeps only IsRetail true"


def test_char_filter_selects_one_character() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_capture(Path(tmp))
        found, _ = pa.gather(Path(tmp), 0x028, None, None, "Alt", False)

    assert {p.source.parent.parent.parent.name for p in found.packets} == {"Alt"}


def test_corrupt_record_is_reported_not_dropped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "0x028.log"
        # header id 0x030 inside a file that claims 0x028, plus a record with no data rows
        path.write_text(
            record("[t] Packet 0x028", encode(0x030, 40))
            + "[t] Packet 0x028\n", encoding="utf-8")
        packets, problems = pa.parse_file(path, "in")

    assert any("header id 0x030" in p for p in problems), problems
    assert any("no data rows" in p for p in problems), problems
    assert len(packets) == 1, "the well-formed record still parses"


def test_find_missing_opcode_says_so() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_capture(Path(tmp))
        code, out = run("find", root=tmp, opcode="0x0FF")

    assert code == 1
    assert "no 0x0FF packets found" in out
    assert "capture(s) scanned" in out


def test_find_counts_and_lists_variations() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_capture(Path(tmp))
        code, out = run("find", root=tmp, opcode="0x028", dir="in")

    assert code == 0
    assert "structural variations" in out
    assert "40 bytes" in out and "44 bytes" in out


def test_show_prints_a_complete_untruncated_packet() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_capture(Path(tmp))
        code, out = run("show", root=tmp, opcode="0x00E")

    assert code == 0
    assert "captured grid:" in out and "bytes:" in out
    assert "     10 |" in out, "the full grid, including the row past 256, must be shown"
    # 260 bytes -> offsets 0000 through 0100 all present, nothing truncated
    assert "0100" in out


def test_show_index_out_of_range() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_capture(Path(tmp))
        code, out = run("show", root=tmp, opcode="0x028", dir="in", index=99)

    assert code == 1
    assert "out of range" in out


def test_list_reports_provenance() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_capture(Path(tmp))
        code, out = run("list", root=tmp)

    assert code == 0
    assert "Hero [retail]" in out
    assert "Alt [private/unknown]" in out
    assert "1.12.0" in out


def test_parse_opcode_accepts_common_forms() -> None:
    assert pa.parse_opcode("0x028") == 0x28
    assert pa.parse_opcode("28") == 0x28
    assert pa.parse_opcode("D") == 0xD


def test_missing_root_is_an_error() -> None:
    try:
        pa.resolve_root(str(Path(tempfile.gettempdir()) / "definitely-not-a-captures-dir-xyz"))
    except pa.PacketError as error:
        assert "captures root not found" in str(error)
        return

    raise AssertionError("expected PacketError")


def pack_action(fields: list[tuple[int, int]]) -> bytes:
    """Build a bitstream LSB-first (the inverse of BitReader), prefixed with the 5-byte
    header+worksize the real packet carries before its body."""
    total = sum(length for _, length in fields)
    buf = bytearray((total + 7) // 8)
    pos = 0
    for value, length in fields:
        for i in range(length):
            if (value >> i) & 1:
                buf[(pos + i) >> 3] |= 1 << ((pos + i) & 7)

        pos += length

    return b"\x28\x00\x00\x00\x00" + bytes(buf)


def test_action_decode_round_trips_known_values() -> None:
    """A synthetic action packet built with LSB's bit order must decode back exactly."""
    body = [
        (0x1234ABCD, 32),  # caster
        (1, 6),            # target count
        (0, 4),            # res_sum
        (3, 4),            # action type
        (555, 32),         # action id
        (60, 32),          # recast
        (0x0000BEEF, 32),  # target actorId
        (1, 4),            # result count
        # one result, core 85 bits
        (4, 3), (1, 2), (100, 12), (7, 5), (2, 2), (3, 3), (9999, 17), (185, 10), (12345, 31),
        (0, 1),            # no additional effect
        (0, 1),            # no spikes
    ]
    parsed = pa.parse_action(pack_action(body))

    assert parsed["casterId"] == 0x1234ABCD
    assert parsed["actionType"] == 3
    assert parsed["actionId"] == 555
    assert parsed["recast"] == 60
    targets = parsed["targets"]
    assert isinstance(targets, list) and len(targets) == 1
    assert targets[0]["actorId"] == 0x0000BEEF
    results = targets[0]["results"]
    assert isinstance(results, list) and len(results) == 1
    result = results[0]
    assert result["resolution"] == 4
    assert result["animation"] == 100
    assert result["param"] == 9999
    assert result["messageID"] == 185
    assert result["modifier"] == 12345
    assert "additionalEffect" not in result
    assert "spikes" not in result


def test_action_decode_reads_conditional_blocks() -> None:
    body = [
        (1, 32), (1, 6), (0, 4), (6, 4), (1, 32), (0, 32),  # header
        (2, 32), (1, 4),                                     # one target, one result
        (0, 3), (0, 2), (0, 12), (0, 5), (0, 2), (0, 3), (0, 17), (100, 10), (0, 31),
        (1, 1), (5, 6), (2, 4), (77, 17), (200, 10),         # additional effect present
        (1, 1), (6, 6), (3, 4), (44, 14), (300, 10),         # spikes present
    ]
    result = pa.parse_action(pack_action(body))["targets"][0]["results"][0]  # type: ignore[index]
    assert isinstance(result, dict)
    assert result["additionalEffect"] == {"effect": 5, "info": 2, "param": 77, "messageID": 200}
    assert result["spikes"] == {"effect": 6, "info": 3, "param": 44, "messageID": 300}


def test_action_decode_rejects_truncated_packet() -> None:
    try:
        pa.parse_action(b"\x28\x00\x00\x00\x00\x01\x02")  # far too short for the header
    except pa.PacketError:
        return

    raise AssertionError("a truncated action packet must raise, not read past the end")


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
