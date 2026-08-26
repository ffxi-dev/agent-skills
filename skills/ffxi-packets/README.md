# ffxi-packets

Find, examine, and summarize FFXI network packets from captain (Ashita v4) PacketLogger captures. Use whenever a question is about the raw bytes of a packet: "show me the bytes of packet 0xNNN", "find all instances of opcode X", "how big is opcode 0x028 and does its size vary", "which captures contain this opcode", "dump a real example to compare against a struct". It parses the captain text hex grid directly and reports the real bytes with their offsets, always carrying opcode, size, direction, and source capture, so an answer is traced to a concrete captured packet rather than recalled. It reports the bytes; it does not know what an opcode is called or what its fields mean (see "Interpreting a packet" below).

See [SKILL.md](SKILL.md) for the full instructions, and the [repo README](../../README.md) for how skills are installed.

**Requirements:** Requires Python 3.9+ and a captain captures directory (external to this skill).

<!-- generated from SKILL.md by tools/gen_skill_readmes.py; do not edit -->
