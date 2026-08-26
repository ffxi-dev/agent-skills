---
name: ffxi-packets
description: >
  Find, examine, and summarize FFXI network packets from captain (Ashita v4) PacketLogger
  captures. Use whenever a question is about the raw bytes of a packet: "show me the bytes of
  packet 0xNNN", "find all instances of opcode X", "how big is opcode 0x028 and does its size
  vary", "which captures contain this opcode", "dump a real example to compare against a
  struct". It parses the captain text hex grid directly and reports the real bytes with their
  offsets, always carrying opcode, size, direction, and source capture, so an answer is traced
  to a concrete captured packet rather than recalled. It reports the bytes; it does not know
  what an opcode is called or what its fields mean (see "Interpreting a packet" below).
license: MIT
compatibility: Requires Python 3.9+ and a captain captures directory (external to this skill).
---

# FFXI packet analyzer

captain's PacketLogger writes captures as a text hex grid, not binary or pcap. This reads
that format and answers packet questions from the real bytes.

## Use it

```bash
python packet_analyzer.py list                       # captures on disk and their provenance
python packet_analyzer.py find 0x028                 # count an opcode everywhere, with variations
python packet_analyzer.py find 0x028 --dir in        # incoming only
python packet_analyzer.py show 0x028                  # one complete example, full dump
python packet_analyzer.py show 0x00E --index 2        # the third matching packet
python packet_analyzer.py action                     # decode the bit-packed action packet
```

## The action packet (0x028)

The action packet is bit-packed and variable-length, the one packet that is miserable to read
as hex, so it gets a first-class decoder. `action` finds and decodes it; `show 0x028` appends
the decode after the byte dump. It unpacks the header (caster, action type, action id, recast),
each target, and each result (resolution, kind, animation, param, messageID, modifier, and the
optional additional-effect and spikes blocks).

Field names and bit widths follow LSB's `src/map/packets/s2c/0x028_battle2.cpp`, which is
built against atom0s's [XiPackets](https://github.com/atom0s/XiPackets) and actionparse addon. The bit order is LSB's `unpackBitsBE` exactly: LSB-first over a
little-endian stream, body starting at bit 40. Verified against real captures: melee results
carry the canonical combat message IDs (15 hit, 67 critical, 1 miss). Values are raw numbers
with their real field names; a `messageID` resolves against the `ffxi-resources` strings
dataset, and semantics for other opcodes come from LSB's packet code (see below).

`find` reports total count, which captures held it, and the distinct sizes seen (the
structural variations). `show` prints the whole captured grid plus a byte/offset table,
never truncated. If an opcode is absent, both say so and how many captures were scanned;
they never invent a packet.

Opcodes accept any hex form: `0x028`, `0x28`, `028`, `28`, `D`.

## Interpreting a packet

This tool gives you the bytes, not their meaning. It has no opcode-to-name table and does not
label fields: `show 0x028` prints a real action packet's bytes, not "this is the action packet
and byte 4 is the target id". To turn bytes into meaning, pair it with a source that defines the
structure:

- **atom0s's [XiPackets](https://github.com/atom0s/XiPackets)** is the canonical reverse
  engineered reference for FFXI packet structures, opcode by opcode, both directions. Start
  here for what an opcode is and how its fields lay out. LSB's own packet code is built against
  it.
- **LSB's own packet code** is the authoritative field map for server work. Server-to-client
  builders live in `src/map/packets/*.cpp` (e.g. `action.cpp`, `char_update.cpp`), and
  client-to-server handlers in `src/map/packets/c2s/`. They name every field and offset.
- **The `ffxi-re` skill** covers the decompiled client and `FFXiMain.dll`, where the client's
  own packet handling is implemented, for anything LSB does not model or where you need the
  retail client's view.

Use this tool to establish what the bytes actually are across real captures, then read the
structure from one of those. Do not infer a field's meaning from the bytes alone, and do not
recall a packet's layout from memory when a capture and a struct definition both exist.

## Where the captures are

They live outside this skill. Point at them, in order of precedence:

1. the `root` argument: `python packet_analyzer.py find 0x028 /path/to/captures`
2. the `$CAPTAIN_CAPTURES` environment variable

There is no built-in default: the captain captures directory lives inside an Ashita install
whose location varies, so one of the two above is required. It is usually
`<your Ashita>/addons/captain/captures`.

Layout in the wild:

```
<root>/<session>/<CharacterName>/PacketLogger/{full.log, incoming/, outgoing/}
                 <CharacterName>/manifest.txt
```

Sibling addon dirs (ActionView, HPTrack, NPCLogger, ...) are not packets; they are ignored.

## The format

- `full.log` interleaves both directions. Each record is headed
  `[YYYY-MM-DD HH:MM:SS.mmm] Incoming packet 0xNNN` or `Outgoing packet 0xNNN`.
- Per-opcode files `incoming/0xNNN.log` and `outgoing/0xNNN.log` head each record
  `[ts] Packet 0xNNN`. The direction is IMPLIED BY THE FOLDER, not the line; the parser
  carries it from the path. `find` and `show` read these because they are direct and fast.
- Body: 16 bytes per row. The row index is in hex (so byte 256+ indexes `10`, `11`, ...),
  a `|`, the hex cells, a second index column, a `|`, then ASCII. A short final row is
  padded with `--`. Records are separated by a blank line.
- The size is not written in the header. It is the count of real (non-`--`) cells, and it
  is cross-checked against the FFXI header field: the little-endian uint16 at offset 0 holds
  the id in its low 9 bits and the size in 4-byte words in its high 7 bits. When the two
  disagree the record is reported as corrupt.

## Provenance and trust

Each character has a sibling `manifest.txt`, a Lua table literal (not JSON), with
`Captain.Version`, the enabled addons, `FFXI.IsRetail`, `FFXI.ZoneIP`, and `StartTime`.
`list` reports it, and every packet result names its source capture.

`FFXI.IsRetail` is the trust signal: a retail capture is genuine game data, a private-server
one may not be. Filtering is opt-in, never assumed:

- `--trusted` keeps only captures whose manifest says `IsRetail = true`.
- `--char NAME` restricts to one character; `--session S` to sessions whose name contains S.

Nothing is silently excluded by default. When a result matters, say which capture and
whether it was retail.

## Discipline

- Never fabricate. If an opcode is not present, report that and the number of captures
  scanned, not a plausible-looking packet.
- Show complete packets. `show` never truncates; a large packet is printed in full.
- Carry direction, size, opcode, and source on every result. Direction for a per-opcode
  file comes from its folder, not from anything in the line.
- Report corrupt records rather than skipping them silently: a record with no data rows, or
  one whose header id does not match the opcode it is filed under, is surfaced as a problem.

## Test

```bash
python test_packet_analyzer.py   # synthetic fixture, no real capture needed
```

The fixture is hand-built in captain's grid format. Real retail packet bytes are never
vendored into this repo.
