---
name: ffxi-re
description: Reverse-engineer Final Fantasy XI client internals - the decompiled PS2 client (FFXI-PS2), the retail FFXiMain.dll, and the PS2 SCUS_972.66 ELF. Use when asked to find how the client implements something (animation/lock timers, event & cutscene flags, chat limits, movement/collision, packet handling, UI), to locate a byte signature to patch, to confirm a flag or field's meaning, or to compare PS2-era behavior against retail. Triggers on FFXI/FFXi/XI + client, decomp, FFXiMain.dll, SCUS_972.66, packet, opcode, signature, cutscene flag, or reconciling private-server (LSB) behavior with client code.
license: MIT
---

# FFXI reverse engineering

**Run `python xibin.py doctor` first.** It prints which of the three sources exist on
this machine and how to get the missing ones. Only the first is needed for most
questions, and it is a public repo.

| Source | What it is | How you get it |
|---|---|---|
| **Decomp** | `github.com/sruon/FFXI-PS2` - the 2003 PS2 client decompiled, ~11k functions with real class/field/function names recovered from the binary's DWARF. | `git clone`, MIT. Set `FFXI_DECOMP`. |
| Retail DLL | Your install's `FFXiMain.dll`. No symbols, but it's the build that actually runs. | Already on disk; `xibin.py` unpacks it itself. Set `FFXI_DLL`. |
| PS2 ELF | `SCUS_972.66` from a PS2 disc. Raw data the decomp dropped: string pools, enum name tables, jump tables. | Extract from a disc you own. Set `FFXI_PS2`. Optional. |

Two reimplementations are worth reading when the question is about **file formats or
assets** rather than client logic - they have a lot already decoded:

- `https://xim.pages.dev/source.zip` - browser reimplementation. Not the real game, but
  strong on `.DAT` parsing, animations and sounds.
- `https://gitlab.com/Aenge/XIClient` - C++ reimplementation.

Paths resolve from env var, then `~/.ffxi-re.json` (`{"retail": "...", "ps2": "...",
"decomp": "..."}`), then a guess at common install locations.

**This skill ships no game data and never will.** It reads only files already on your
disk. The retail DLL comes from your own install; the PS2 ELF and its debug symbols you
must source yourself from media you own - they are not redistributable and are not
bundled here. The decomp repo is the one source that is freely cloneable, which is why
it's the one to reach for first.

## Read the decomp first

It answers most questions on its own, costs nothing to search, and is the only source
with real names. Every `.cpp` is one original compile unit.

```bash
# list every function in a compile unit (name, mangled symbol, rva, size)
grep -n "^//   symbol:" src/main/actor/xievent.cpp

# then read a range - files run to 15k lines, never cat them
sed -n '8383,8784p' src/main/actor/xievent.cpp

# find callers: functions are referenced by their GCC 2.x mangled name
grep -rn "UseMagic__14XiControlActorFP12CXiSchStatus" src/

# class layout, with per-field provenance
cat include/XiControlActor.h
```

- `include/<Class>.h` - fields with offsets, sizes, access counts. Tags: no tag =
  DWARF (authoritative), `[llm]` = a rename pass guessed it, `[synth]` = offset known
  only, name is `field_0xNN`. **Never report an `[llm]` name as if it were a real
  symbol.**
- `include/_globals.h` (1,763 typed globals), `include/_types.h` (127 enums) - DWARF.
- `index.md` - function counts per compile unit; use it to pick where to look.
- `src/_unmapped.cpp` - 3,104 functions with no compile-unit info. Grep it when a
  symbol is nowhere else.

Directory map: `main/actor` (entity/battle/event logic), `main/miyagawa` (resource
system, sound, the `ymsch*` animation scheduler), `main/miyagawa/effect` (scheduler
bytecode interpreter `ymschdecript.cpp`), `main/net/game_cli` (packet handlers),
`ohno` (graphics + collision, `ko_*`), `kazumi` (animation, `Kz*`), `main/tk` +
`main/yk` (UI), `main/fshira` (config, text input), `main/zone`.

Caveat that matters: this is **client** code for the PS2 beta. Mob AI, battle math and
route decisions are server-side and simply absent. Client-side collision, movement,
timers, input and packet parsing are all genuinely there.

## The POL1 protection - handled for you

SE protects `FFXiMain.dll`, `pol.exe`, `polcore.dll`, `polboot.exe` and friends by
moving `.text` into a section named **POL1**, zeroing `.text`'s raw size, and pointing
the entry point at a stub that unpacks it at load time. Nothing is obfuscated; the
stub does a plain LZSS decompress (8-bit flag byte, 12-bit offset, 4-bit length).

**`xibin.py` unpacks these in memory automatically** - point any command at the file
straight out of your game install and it works. No dumping, no separate tool.

To get a normal PE on disk for IDA/Ghidra/Binary Ninja:

```bash
python xibin.py /path/to/FFXiMain.dll unpack        # -> FFXiMain_unpacked.dll
```

That restores `.text`, realigns every section's raw pointer, and recovers the original
entry point from the stub's final jump. (Don't hardcode stub offsets the way older
writeups do - the constants differ between `.dll` and `.exe` targets. Reading the last
`JMP rel32` whose target lands inside `.text` works for both.)

Also fine, if you'd rather: a dump of the module from a live process. `xibin.py` detects
a memory-mapped layout from `SizeOfImage` and uses virtual addresses as file offsets;
force it with `XIBIN_MAPPED=1`.

Beware: an `FFXiMain.dll` starting with `XEX2` is the **Xbox 360** build (PowerPC), an
unrelated artifact - not a packed PC DLL.

## Poking the binaries

`xibin.py` (next to this file) handles the x86 PE and the MIPS ELF with the same
commands. Target is a path or the alias `retail` / `ps2`.

```bash
S=<this skill dir>/xibin.py
python "$S" doctor                         # what's available, and hints for what isn't
python "$S" retail unpack                  # POL1 -> a normal PE on disk (only for other tools)
python "$S" retail info                    # sections, imagebase, where symbols came from
python "$S" retail dis 0x1009ff00 0x200    # disassemble; call targets annotated
python "$S" retail xref 0x100fbfb0         # call sites + pointer/vtable refs
python "$S" retail xref "SomeString"       # locate the string, then xref its VA
python "$S" retail str "Idle[A-Za-z]+"     # regex over ascii runs, with VAs
python "$S" retail imm 0x8000              # instructions using that immediate (slow sweep)
python "$S" ps2 dis 0x00405160 0x100       # same commands on the MIPS ELF
```

**Symbols, in priority order** - `xibin.py` uses the best available and `info` says which:

1. `<binary>.map` - IDA's export. Auto-names (`sub_`/`loc_`) tell you *which function*
   an address is in; any functions you named by hand come through properly.
2. `<binary>.sym` - bring your own, one `<hex va> <name>` per line. Any disassembler
   emits this in a couple of lines; use it to carry names forward.
3. Nothing: function starts are derived by scanning call targets. Recovers ~12k
   functions from a stock retail DLL, enough to orient `xref` output.

Both sidecars are looked up as `<file>.ext`, `<stem>.ext`, and the packed/unpacked
sibling both ways - a `.map` usually sits next to the *unpacked* copy while you may be
pointing at the packed original, and that still resolves. `XIBIN_MAP` / `XIBIN_SYM`
override the search outright.

Other notes:
- MIPS `xref` matches `jal` only. MIPS data addresses are built from `lui`+`addiu`
  pairs and will not show up; scan for the immediate halves by hand when it matters.
- `imm` linear-sweeps executable sections, ~10s on the retail DLL. Prefer `xref` on a
  string or a known function when you can.
- Needs `capstone` for `dis`/`imm` (`pip install capstone`); everything else is stdlib.

## The usual investigation shape

1. Guess the subsystem from the directory map, list its functions with the `symbol:`
   grep, read the plausible ones.
2. Follow fields through `include/*.h` and callers through mangled-name grep until the
   mechanism is concrete: which field, which constant, which packet byte.
3. If the answer is "the server decides", say so and stop.
4. Confirm in retail with `xref`/`str`/`dis` when the claim needs to hold today, and
   against an older build when you need to know whether something changed.
5. Cross-check wire formats against a private-server implementation (LandSandBoat's
   `src/map/packets/s2c/0xNNN_*.h`) and atom0s/XiPackets before naming a field.

Report what the code does, with `file:line` or a VA for every claim, and mark inference
as inference. A named-but-unverified constant is worse than an unnamed one.
