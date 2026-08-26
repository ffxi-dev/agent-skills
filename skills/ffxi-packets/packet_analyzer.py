#!/usr/bin/env python3
"""Analyze FFXI packet captures made by the captain (Ashita v4) PacketLogger addon.

  python packet_analyzer.py list [root]
  python packet_analyzer.py find 0x028 [root] [--dir in|out] [--session S] [--char C] [--trusted]
  python packet_analyzer.py show 0x028 [root] [--dir in|out] [--index N] ...

Captures are a TEXT HEX GRID, not binary or pcap. Layout in the wild:

  <root>/<session>/<CharacterName>/PacketLogger/{full.log, incoming/, outgoing/}

full.log interleaves both directions, each record headed
`[ts] Incoming packet 0xNNN` / `[ts] Outgoing packet 0xNNN`. The per-opcode files
`incoming/0xNNN.log` and `outgoing/0xNNN.log` head each record `[ts] Packet 0xNNN`
with the direction IMPLIED BY THE FOLDER. find/show read the per-opcode files
(direct and fast); the parser also handles full.log for whole-session work.

The captures live outside this skill. Point at them with the `root` argument, the
$CAPTAIN_CAPTURES env var, or fall back to the documented Ashita default. Nothing here
is hardcoded to one machine.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Documented last-resort default. Overridden by the `root` argument or $CAPTAIN_CAPTURES,
# so this is never the only option, just where a stock Ashita install keeps them.

# full.log: direction is in the line. per-opcode file: direction comes from the folder.
FULL_HEADER = re.compile(r"^\[(?P<ts>[^\]]+)\] (?P<dir>Incoming|Outgoing) packet (?P<op>0x[0-9A-Fa-f]+)\s*$")
PERID_HEADER = re.compile(r"^\[(?P<ts>[^\]]+)\] Packet (?P<op>0x[0-9A-Fa-f]+)\s*$")

# a data row: `   0 | 0D 32 .. 00    0 | ascii`, 16 cells, short rows padded with `--`,
# row index in hex so byte 256+ indexes 10, 11, ... The trailing second index column
# tells this apart from the column-header and separator lines.
ROW = re.compile(r"^ *[0-9A-Fa-f]{1,3} \|((?: (?:[0-9A-Fa-f]{2}|--)){16})  +[0-9A-Fa-f]{1,3} \|")


class PacketError(Exception):
    """Anything the caller can act on, reported without a stack trace."""


@dataclass
class Packet:
    opcode: int
    direction: str  # "in" or "out"
    timestamp: str
    data: bytes
    source: Path
    raw: str  # the record's original grid text, for verbatim display

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass
class Capture:
    session: str
    char: str
    pl_dir: Path  # the PacketLogger directory
    manifest: dict[str, object]

    def label(self) -> str:
        tag = "retail" if self.manifest.get("is_retail") is True else "private/unknown"
        return f"{self.session}/{self.char} [{tag}]"


def header_fields(data: bytes) -> tuple[int, int]:
    """FFXI header: LE uint16 at [0], low 9 bits = id, high 7 bits = size in 4-byte words.

    Same convention both directions (verified against real incoming and outgoing packets).
    Returns (id, size_in_bytes). The size is a cross-check on the counted cell size.
    """
    if len(data) < 2:
        return (data[0] if data else 0, len(data))

    word = data[0] | (data[1] << 8)
    return (word & 0x1FF, (word >> 9) * 4)


def parse_file(path: Path, direction: str | None) -> tuple[list[Packet], list[str]]:
    """Parse one capture .log into packets. direction None => full.log (dir from header);
    "in"/"out" => per-opcode file (dir from the caller, i.e. the folder).

    Corrupt records are reported in the returned problem list, never dropped silently.
    """
    header_re = FULL_HEADER if direction is None else PERID_HEADER
    packets: list[Packet] = []
    problems: list[str] = []

    ts = ""
    op = -1
    dir_ = direction or ""
    data = bytearray()
    raw: list[str] = []
    open_record = False

    def flush() -> None:
        if not open_record:
            return

        if not data:
            problems.append(f"{path.name}: record 0x{op:03X} @ {ts} has no data rows")
            return

        hdr_id, _ = header_fields(bytes(data))
        if hdr_id != op:
            problems.append(
                f"{path.name}: record labelled 0x{op:03X} @ {ts} carries header id 0x{hdr_id:03X}")

        packets.append(Packet(op, dir_, ts, bytes(data), path, "\n".join(raw)))

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.rstrip("\n")
            head = header_re.match(line)
            if head:
                flush()
                ts = head.group("ts")
                op = int(head.group("op"), 16)
                if direction is None:
                    dir_ = "in" if head.group("dir") == "Incoming" else "out"

                data = bytearray()
                raw = [line]
                open_record = True
                continue

            if not open_record:
                continue

            raw.append(line)
            row = ROW.match(line)
            if row:
                for cell in row.group(1).split():
                    if cell != "--":
                        data.append(int(cell, 16))

    flush()
    return packets, problems


def resolve_root(explicit: str | None) -> Path:
    """Captures root from the argument or $CAPTAIN_CAPTURES. No hardcoded default: the path
    is an Ashita install location that varies per machine, so it must be supplied."""
    candidate = explicit or os.environ.get("CAPTAIN_CAPTURES")
    if not candidate:
        raise PacketError(
            "no captures root given. Pass it as an argument or set $CAPTAIN_CAPTURES to your\n"
            "captain captures directory (<Ashita>/addons/captain/captures).")

    root = Path(candidate).expanduser()
    if not root.is_dir():
        raise PacketError(f"captures root not found: {root}")

    return root


_MANIFEST_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("version", r'Version\s*=\s*"([^"]*)"', "str"),
    ("zone_ip", r'ZoneIP\s*=\s*"([^"]*)"', "str"),
    ("is_retail", r"IsRetail\s*=\s*(true|false)", "bool"),
    ("start_time", r"StartTime\s*=\s*(\d+)", "int"),
)


def read_manifest(path: Path) -> dict[str, object]:
    """The sibling manifest.txt is a Lua table literal, not JSON. Pull the provenance
    fields out by pattern rather than pretending to parse Lua."""
    out: dict[str, object] = {}
    if not path.is_file():
        return out

    text = path.read_text(encoding="utf-8", errors="replace")
    for key, pattern, kind in _MANIFEST_FIELDS:
        match = re.search(pattern, text)
        if not match:
            continue

        value = match.group(1)
        out[key] = value == "true" if kind == "bool" else int(value) if kind == "int" else value

    return out


def iter_captures(root: Path, session: str | None, char: str | None,
                  trusted: bool) -> Iterator[Capture]:
    """Yield every <session>/<char> that has a PacketLogger dir, applying the opt-in
    filters. `trusted` keeps only manifests whose FFXI.IsRetail is true; it is off by
    default, so nothing is silently excluded."""
    for pl_dir in sorted(root.glob("*/*/PacketLogger")):
        char_dir = pl_dir.parent
        sess = char_dir.parent.name
        name = char_dir.name
        if session and session.lower() not in sess.lower():
            continue

        if char and char.lower() != name.lower():
            continue

        manifest = read_manifest(char_dir / "manifest.txt")
        if trusted and manifest.get("is_retail") is not True:
            continue

        yield Capture(sess, name, pl_dir, manifest)


def parse_opcode(text: str) -> int:
    """Accept 0x028, 0x28, 028, 28, D, etc. Opcodes are hex."""
    try:
        return int(text, 16)
    except ValueError:
        raise PacketError(f"not a hex opcode: {text!r} (try 0x028)")


def perid_files(pl_dir: Path, opcode: int, direction: str | None) -> list[tuple[Path, str]]:
    """The per-opcode files for this opcode that exist, as (path, direction)."""
    wanted = f"0x{opcode:03X}.log"
    out: list[tuple[Path, str]] = []
    for folder, dir_ in (("incoming", "in"), ("outgoing", "out")):
        if direction and dir_ != direction:
            continue

        path = pl_dir / folder / wanted
        if path.is_file():
            out.append((path, dir_))

    return out


@dataclass
class Found:
    packets: list[Packet] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    scanned: int = 0


def gather(root: Path, opcode: int, direction: str | None, session: str | None,
           char: str | None, trusted: bool) -> tuple[Found, list[Capture]]:
    """Collect every packet of `opcode` across the matching captures."""
    found = Found()
    hit_captures: list[Capture] = []
    for capture in iter_captures(root, session, char, trusted):
        found.scanned += 1
        got = False
        for path, dir_ in perid_files(capture.pl_dir, opcode, direction):
            packets, problems = parse_file(path, dir_)
            found.packets.extend(packets)
            found.problems.extend(problems)
            if packets:
                got = True

        if got:
            hit_captures.append(capture)

    return found, hit_captures


def cmd_list(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    captures = list(iter_captures(root, args.session, args.char, args.trusted))
    if not captures:
        print(f"no captures with a PacketLogger dir under {root}")
        return 1

    print(f"{len(captures)} capture(s) under {root}\n")
    for capture in captures:
        man = capture.manifest
        incoming = len(list((capture.pl_dir / "incoming").glob("0x*.log")))
        outgoing = len(list((capture.pl_dir / "outgoing").glob("0x*.log")))
        print(capture.label())
        print(f"    captain {man.get('version', '?')}  zone {man.get('zone_ip', '?')}"
              f"  start {man.get('start_time', '?')}")
        print(f"    opcodes: {incoming} incoming, {outgoing} outgoing  ({capture.pl_dir})")

    return 0


def cmd_find(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    opcode = parse_opcode(args.opcode)
    found, captures = gather(root, opcode, args.dir, args.session, args.char, args.trusted)

    if not found.packets:
        print(f"no 0x{opcode:03X} packets found across {found.scanned} capture(s) scanned")
        for problem in found.problems:
            print(f"  ! {problem}")

        return 1

    sizes: dict[tuple[str, int], int] = {}
    for packet in found.packets:
        sizes[(packet.direction, packet.size)] = sizes.get((packet.direction, packet.size), 0) + 1

    print(f"0x{opcode:03X}: {len(found.packets)} packet(s) in {len(captures)} capture(s)"
          f" of {found.scanned} scanned")
    print(f"structural variations ({len(sizes)}):")
    for (direction, size), count in sorted(sizes.items()):
        print(f"    {direction:<3} {size:>4} bytes  x{count}")

    print("by capture:")
    for capture in captures:
        counts: dict[str, int] = {}
        for packet in found.packets:
            if packet.source.parent.parent == capture.pl_dir:
                counts[packet.direction] = counts.get(packet.direction, 0) + 1

        breakdown = ", ".join(f"{d}:{n}" for d, n in sorted(counts.items()))
        print(f"    {capture.label()}  {breakdown}")

    for problem in found.problems:
        print(f"  ! {problem}")

    return 0


def dump(data: bytes) -> str:
    """A byte/offset table straight from the parsed bytes, never truncated. Offsets in
    hex and decimal, then 16 hex cells, then ASCII."""
    lines = ["  off (hex/dec)  " + " ".join(f"{i:02X}" for i in range(16)) + "  ascii"]
    for base in range(0, len(data), 16):
        chunk = data[base:base + 16]
        cells = " ".join(f"{b:02X}" for b in chunk).ljust(16 * 3 - 1)
        ascii_ = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in chunk)
        lines.append(f"  {base:04X} {base:>6}   {cells}  {ascii_}")

    return "\n".join(lines)


ACTION_OPCODE = 0x028

# The action (BATTLE2) packet is bit-packed. Bits are read LSB-first from a little-endian
# byte stream (LSB's unpackBitsBE: value = little-endian bytes, (value >> intra) & mask),
# starting after the 4-byte header and the 1-byte WorkSize, i.e. at bit 40. The field order
# and widths mirror src/map/packets/s2c/0x028_battle2.cpp, which follows atom0s's actionparse.
ACTION_BODY_BIT = 8 * 5


class BitReader:
    """Read fields LSB-first from a little-endian bitstream, matching LSB's unpackBitsBE."""

    def __init__(self, data: bytes, bit_offset: int = 0) -> None:
        self.data = data
        self.pos = bit_offset

    def remaining(self) -> int:
        return len(self.data) * 8 - self.pos

    def read(self, length: int) -> int:
        if self.remaining() < length:
            raise PacketError("packet ends mid-field; not a valid action packet or it is truncated")

        byte_index = self.pos >> 3
        intra = self.pos & 7
        span = (intra + length + 7) // 8
        value = int.from_bytes(self.data[byte_index:byte_index + span], "little")
        self.pos += length
        return (value >> intra) & ((1 << length) - 1)


def parse_action(data: bytes) -> dict[str, object]:
    """Decode a 0x028 action packet into a structured dict. Field names follow LSB."""
    reader = BitReader(data, ACTION_BODY_BIT)
    caster = reader.read(32)
    target_count = reader.read(6)
    reader.read(4)  # res_sum, always 0
    action_type = reader.read(4)
    action_id = reader.read(32)
    recast = reader.read(32)

    targets: list[dict[str, object]] = []
    for _ in range(min(target_count, 15)):
        target_id = reader.read(32)
        result_count = reader.read(4)
        results: list[dict[str, object]] = []
        for _ in range(min(result_count, 8)):
            result: dict[str, object] = {
                "resolution": reader.read(3),
                "kind": reader.read(2),
                "animation": reader.read(12),
                "info": reader.read(5),
                "hitDistortion": reader.read(2),
                "knockback": reader.read(3),
                "param": reader.read(17),
                "messageID": reader.read(10),
                "modifier": reader.read(31),
            }
            if reader.read(1):
                result["additionalEffect"] = {
                    "effect": reader.read(6), "info": reader.read(4),
                    "param": reader.read(17), "messageID": reader.read(10),
                }

            if reader.read(1):
                result["spikes"] = {
                    "effect": reader.read(6), "info": reader.read(4),
                    "param": reader.read(14), "messageID": reader.read(10),
                }

            results.append(result)

        targets.append({"actorId": target_id, "results": results})

    return {
        "casterId": caster, "actionType": action_type, "actionId": action_id,
        "recast": recast, "targetCount": target_count, "targets": targets,
    }


def format_action(parsed: dict[str, object]) -> str:
    lines = [
        "decoded action (0x028), field names from LSB src/map/packets/s2c/0x028_battle2.cpp:",
        f"  caster {parsed['casterId']}  actionType {parsed['actionType']}"
        f"  actionId {parsed['actionId']}  recast {parsed['recast']}s",
    ]
    targets = parsed["targets"]
    assert isinstance(targets, list)
    for target in targets:
        lines.append(f"  target {target['actorId']}:")
        results = target["results"]
        assert isinstance(results, list)
        for result in results:
            lines.append(
                f"    resolution {result['resolution']} kind {result['kind']}"
                f" animation {result['animation']} param {result['param']}"
                f" messageID {result['messageID']} modifier {result['modifier']}")
            if "additionalEffect" in result:
                lines.append(f"      additionalEffect {result['additionalEffect']}")

            if "spikes" in result:
                lines.append(f"      spikes {result['spikes']}")

    lines.append("  messageID values resolve against the `ffxi-resources` strings dataset.")
    return "\n".join(lines)


def cmd_show(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    opcode = parse_opcode(args.opcode)
    found, _ = gather(root, opcode, args.dir, args.session, args.char, args.trusted)

    if not found.packets:
        print(f"no 0x{opcode:03X} packets found across {found.scanned} capture(s) scanned")
        return 1

    if args.index >= len(found.packets):
        print(f"only {len(found.packets)} packet(s); index {args.index} out of range")
        return 1

    packet = found.packets[args.index]
    hdr_id, hdr_size = header_fields(packet.data)
    print(f"0x{opcode:03X}  direction {packet.direction}  {packet.size} bytes"
          f"  (header id 0x{hdr_id:03X}, header size {hdr_size})")
    print(f"example {args.index + 1} of {len(found.packets)}  @ {packet.timestamp}")
    print(f"source: {packet.source}\n")
    print("captured grid:")
    print(packet.raw)
    print("\nbytes:")
    print(dump(packet.data))

    if opcode == ACTION_OPCODE:
        print()
        try:
            print(format_action(parse_action(packet.data)))
        except PacketError as error:
            print(f"(could not decode as an action packet: {error})")

    return 0


def cmd_action(args: argparse.Namespace) -> int:
    """Find and decode action (0x028) packets first-class, since it is bit-packed."""
    root = resolve_root(args.root)
    found, _ = gather(root, ACTION_OPCODE, args.dir, args.session, args.char, args.trusted)
    if not found.packets:
        print(f"no 0x028 action packets across {found.scanned} capture(s) scanned")
        return 1

    if args.index >= len(found.packets):
        print(f"only {len(found.packets)} action packet(s); index {args.index} out of range")
        return 1

    packet = found.packets[args.index]
    print(f"action {args.index + 1} of {len(found.packets)}  @ {packet.timestamp}")
    print(f"source: {packet.source}\n")
    print(format_action(parse_action(packet.data)))
    return 0


def add_filters(node: argparse.ArgumentParser) -> None:
    node.add_argument("root", nargs="?", help="captures root (else $CAPTAIN_CAPTURES, else default)")
    node.add_argument("--dir", choices=["in", "out"], help="restrict to one direction")
    node.add_argument("--session", help="only sessions whose name contains this")
    node.add_argument("--char", help="only this character name (exact, case-insensitive)")
    node.add_argument("--trusted", action="store_true",
                      help="only manifests with FFXI.IsRetail true (opt-in)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    lister = sub.add_parser("list", help="enumerate captures and their provenance")
    add_filters(lister)

    finder = sub.add_parser("find", help="count an opcode across captures, with size variations")
    finder.add_argument("opcode")
    add_filters(finder)

    shower = sub.add_parser("show", help="print one complete example packet")
    shower.add_argument("opcode")
    shower.add_argument("--index", type=int, default=0, help="which matching packet (default 0)")
    add_filters(shower)

    actioner = sub.add_parser("action", help="decode the bit-packed 0x028 action packet")
    actioner.add_argument("--index", type=int, default=0, help="which matching packet (default 0)")
    add_filters(actioner)

    args = parser.parse_args()
    handlers = {"list": cmd_list, "find": cmd_find, "show": cmd_show, "action": cmd_action}

    try:
        return handlers[args.command](args)
    except PacketError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
