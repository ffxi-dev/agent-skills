#!/usr/bin/env python
"""xibin - read-only inspection of FFXI game binaries you already own.

Handles the retail x86 PE (an *unpacked* FFXiMain.dll) and the PS2 MIPS ELF
(SCUS_972.66). Everything is addressed by virtual address.

POL1-packed files (the protection on FFXiMain.dll, pol.exe, polcore.dll and friends)
are unpacked transparently in memory - every command below just works on them.

  xibin.py doctor                          what's available on this machine
  xibin.py <target> unpack [OUT]           write a normal PE for IDA/Ghidra/BN
  xibin.py <target> info                   sections, imagebase, symbol source
  xibin.py <target> dis    VA [LEN]        disassemble (LEN default 0x200)
  xibin.py <target> xref   VA | "text"     call sites + pointer refs
  xibin.py <target> str    [REGEX] [SEC]   ascii strings with their VAs
  xibin.py <target> imm    VALUE           instructions using an immediate
  xibin.py <target> sym    VA              nearest symbol

<target> is a path, or the alias `retail` / `ps2`. Aliases resolve from, in order:
an env var (FFXI_DLL / FFXI_PS2), ~/.ffxi-re.json, then a guess at common install
paths. `doctor` prints what each resolved to.

Ships no game data. Reads only files already on your disk.
"""
from __future__ import annotations

import bisect
import json
import os
import re
import struct
import sys
from typing import Any, Callable, cast

HOME = os.path.expanduser("~")
CONFIG = os.path.join(HOME, ".ffxi-re.json")

Section = tuple[str, int, bytes]
Symbol = tuple[int, str]

KNOWN: dict[str, dict[str, Any]] = {
    "retail": dict(
        env="FFXI_DLL",
        what="FFXiMain.dll (packed is fine)",
        globs=[
            os.path.join(HOME, "*", "FFXiMain*unpacked*.dll"),
            r"C:\Program Files (x86)\PlayOnline*\SquareEnix\FINAL FANTASY XI\FFXiMain.dll",
            r"C:\Program Files\PlayOnline*\SquareEnix\FINAL FANTASY XI\FFXiMain.dll",
        ],
        hint=(
            "Point FFXI_DLL at FFXiMain.dll from your game install. SE's POL1 packing is\n"
            "     unpacked in memory automatically, so the file works as-is; `unpack` writes a\n"
            "     normal PE if you want one for IDA/Ghidra. A dump of the module from a live\n"
            "     process works too. Note: a file starting with 'XEX2' is the Xbox 360 build."
        ),
    ),
    "ps2": dict(
        env="FFXI_PS2",
        what="PS2 ELF SCUS_972.66",
        globs=[os.path.join(HOME, "*", "SCUS_972.66"), r"?:\SCUS_972.66"],
        hint=(
            "Optional. Point FFXI_PS2 at SCUS_972.66 extracted from a PS2 disc you own.\n"
            "     Most questions are answerable from the decomp without it."
        ),
    ),
    "decomp": dict(
        env="FFXI_DECOMP",
        what="FFXI-PS2 decompilation checkout",
        globs=[
            os.path.join(HOME, "Documents", "GitHub", "FFXI-PS2"),
            os.path.join(HOME, "src", "FFXI-PS2"),
            os.path.join(HOME, "FFXI-PS2"),
        ],
        marker="index.md",
        hint="git clone https://github.com/sruon/FFXI-PS2 (public, MIT), then set FFXI_DECOMP.",
    ),
}


def config() -> dict[str, str]:
    try:
        return cast("dict[str, str]", json.load(open(CONFIG, encoding="utf-8")))
    except OSError:
        return {}


def resolve(target: str) -> str | None:
    """Path for an alias, or the target itself if it is already a path."""
    if target not in KNOWN:
        return target
    spec = KNOWN[target]

    def usable(p: str | None) -> bool:
        if not p:
            return False
        if "marker" in spec:
            return os.path.isfile(os.path.join(p, spec["marker"]))
        return os.path.isfile(p)

    for cand in (os.environ.get(cast(str, spec["env"])), config().get(target)):
        if usable(cand):
            return cand
    import glob as _glob

    for pat in cast("list[str]", spec["globs"]):
        for hit in sorted(_glob.glob(pat)):
            if usable(hit):
                return hit
    return None


def cmd_doctor(_img: Img | None, _args: list[str]) -> None:
    print("xibin - available sources\n")
    for name, spec in KNOWN.items():
        path = resolve(name)
        if path:
            note = ""
            if "marker" not in spec:
                try:
                    head = open(path, "rb").read(4)
                except OSError as e:
                    head, note = b"", "  !! unreadable: %s" % e.strerror
                if head[:4] == b"XEX2":
                    note = "  !! Xbox 360 build (XEX/PowerPC), not the PC DLL"
                elif head and head[:2] != b"MZ" and head[:4] != b"\x7fELF":
                    note = "  !! %r, not a PE/ELF" % head
            print("  [%s] %-8s %s%s" % ("ok" if not note else "??", name, path, note))
            if note:
                print("     " + spec["hint"])
        else:
            print("  [--] %-8s missing (%s)" % (name, spec["what"]))
            print("     " + spec["hint"])
    try:
        import capstone  # type: ignore

        print("\n  [ok] capstone %s" % capstone.__version__)
    except ImportError:
        print("\n  [--] capstone missing - pip install capstone (needed for dis/imm)")
    print("\n  config file: %s%s" % (CONFIG, "" if os.path.exists(CONFIG) else " (absent)"))


def lzss_pol1(src: bytes) -> bytes:
    """SE's POL1 packer: LZSS with an 8-bit flag byte, 12-bit offset, 4-bit length.

    Flag bits are consumed MSB first; a set bit is a literal, a clear bit a
    back-reference. A zero offset terminates the stream.

    Written from the observable behaviour of the loader's own unpack stub and
    validated byte-exact against known packed/unpacked pairs. The protection was
    first described publicly by atom0s ("Unpacking FFXi Files For Static Analysis",
    2015), whose write-up is the clearest description of the format.
    """
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        flags = src[i]
        i += 1
        for _ in range(8):
            carry = flags & 0x80
            flags = (flags << 1) & 0xFF
            if carry:  # literal
                if i >= n:
                    return bytes(out)
                out.append(src[i])
                i += 1
                continue
            if i + 1 >= n:
                return bytes(out)
            b0, b1 = src[i], src[i + 1]
            off = ((b0 << 8) | b1) & 0xFFF
            if off == 0:
                return bytes(out)
            i += 2
            start = len(out) - off
            if start < 0:
                raise ValueError("POL1 stream: back-reference before start of output")
            for k in range((b0 >> 4) + 3):
                out.append(out[start + k])
    return bytes(out)


def unpack_pol1(img: Img) -> dict[str, Any] | None:
    """If this PE is POL1-packed, return {'text', 'oep'}; else None.

    SE moves .text into a section named POL1, zeroes .text's raw size, and points
    the entry point at a stub that unpacks it at load time. Nothing is hidden, so
    we just do what the stub does.
    """
    byname = {s["name"]: s for s in img.rawsecs}
    text, pol = byname.get(".text"), byname.get("POL1")
    if not text or not pol or text["rsz"] != 0:
        return None
    body = lzss_pol1(img.data[pol["ro"] : pol["ro"] + pol["rsz"]])
    if len(body) < text["vsz"]:
        body += b"\0" * (text["vsz"] - len(body))
    return {"text": body[: text["vsz"]], "oep": _find_oep(img, text, pol)}


def _find_oep(img: Img, text: dict[str, Any], pol: dict[str, Any]) -> int | None:
    """The stub ends by jumping to the real entry point. Find that jump.

    atom0s' writeup hardcodes stub-relative constants; those are right for his
    FFXiMain.dll but wrong for e.g. polboot.exe. Reading the last JMP rel32 whose
    target lands inside .text works for both.
    """
    data = img.data[pol["ro"] : pol["ro"] + pol["rsz"]]
    lo, hi = text["va"], text["va"] + text["vsz"]
    for off in range(min(len(data), pol["vsz"]) - 5, -1, -1):
        if data[off] != 0xE9:
            continue
        rel = struct.unpack_from("<i", data, off + 1)[0]
        tgt = (pol["va"] + off + 5 + rel) & 0xFFFFFFFF
        if lo <= tgt < hi:
            return cast(int, tgt)
    return None


class Img:
    def __init__(self, target: str) -> None:
        path = resolve(target)
        if not path:
            sys.exit("cannot resolve %r - run `xibin.py doctor`" % target)
        self.path = path
        self.data = open(path, "rb").read()
        self.secs: list[Section] = []  # (name, va, data)
        self.symsrc = "none"
        if self.data[:2] == b"MZ":
            self._pe()
        elif self.data[:4] == b"\x7fELF":
            self._elf()
        else:
            what = (
                "the Xbox 360 build (XEX/PowerPC)"
                if self.data[:4] == b"XEX2"
                else "%r" % self.data[:4]
            )
            sys.exit("%s is %s, not a PE/ELF.\n     %s" % (path, what, KNOWN["retail"]["hint"]))
        self.starts = [s[1] for s in self.secs]
        self._syms: list[Symbol] | None = None

    def cs(self) -> Any:
        import capstone

        if self.arch == "x86":
            return capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        return capstone.Cs(
            capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 | capstone.CS_MODE_LITTLE_ENDIAN
        )

    def _pe(self) -> None:
        d = self.data
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        if pe + 24 > len(d) or d[pe : pe + 4] != b"PE\0\0":
            sys.exit("%s has an MZ header but no PE signature - packed or truncated." % self.path)
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        optsz = struct.unpack_from("<H", d, pe + 20)[0]
        self.pe = pe
        self.base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
        self.file_align = struct.unpack_from("<I", d, pe + 24 + 36)[0] or 0x200
        self.size_of_headers = struct.unpack_from("<I", d, pe + 24 + 60)[0]
        self.oep = struct.unpack_from("<I", d, pe + 24 + 16)[0]
        size_of_image = struct.unpack_from("<I", d, pe + 24 + 56)[0]
        self.arch = "x86"
        # A dump of the loaded module is already section-aligned in memory, so raw
        # pointers do not apply - VirtualAddress is the file offset.
        self.mapped = bool(os.environ.get("XIBIN_MAPPED")) or len(d) >= size_of_image * 0.9

        self.rawsecs: list[dict[str, Any]] = []
        for i in range(nsec):
            o = pe + 24 + optsz + i * 40
            name = d[o : o + 8].rstrip(b"\0").decode("latin1")
            vsz, va, rsz, ro = struct.unpack_from("<IIII", d, o + 8)
            self.rawsecs.append(dict(name=name, vsz=vsz, va=va, rsz=rsz, ro=ro))

        self.packed = unpack_pol1(self) if not self.mapped else None
        for s in self.rawsecs:
            ro, rsz = (s["va"], s["vsz"]) if self.mapped else (s["ro"], s["rsz"])
            body = d[ro : ro + min(rsz, s["vsz"] or rsz)]
            if self.packed and s["name"] == ".text":
                body = self.packed["text"]
            self.secs.append((s["name"], self.base + s["va"], body))

    def _elf(self) -> None:
        d = self.data
        self.arch = "mips"
        phoff = struct.unpack_from("<I", d, 0x1C)[0]
        phentsize, phnum = struct.unpack_from("<HH", d, 0x2A)
        for i in range(phnum):
            o = phoff + i * phentsize
            ptype, poff, pvaddr, _, pfilesz = struct.unpack_from("<IIIII", d, o)
            if ptype == 1 and pfilesz:
                self.secs.append(("LOAD%d" % i, pvaddr, d[poff : poff + pfilesz]))
        if not self.secs:
            sys.exit("%s has no loadable segments" % self.path)
        self.base = min(s[1] for s in self.secs)

    def exec_secs(self) -> list[Section]:
        return [s for s in self.secs if s[0] in (".text", "CODE") or s[0].startswith("LOAD")]

    def sec_of(self, va: int) -> Section | None:
        i = bisect.bisect_right(self.starts, va) - 1
        if i < 0:
            return None
        _, sva, data = self.secs[i]
        return self.secs[i] if sva <= va < sva + len(data) else None

    def read(self, va: int, n: int) -> bytes:
        s = self.sec_of(va)
        return s[2][va - s[1] : va - s[1] + n] if s else b""

    # --- symbols: IDA .map, else a plain "<hexva> <name>" .sym, else derived ---
    def syms(self) -> list[Symbol]:
        if self._syms is None:
            got = self._from_map()
            if got:
                self._syms = sorted(got)
                self.symsrc = os.path.basename(self.sidecar(".map") or "") + " (IDA)"
            elif self._from_sym():
                self._syms = sorted(self._from_sym())
                self.symsrc = os.path.basename(self.sidecar(".sym") or "")
            else:
                self._syms = sorted(self._derive())
                self.symsrc = "derived from call targets"
        return self._syms

    def sidecar(self, ext: str) -> str | None:
        """Find a symbol file for this binary.

        Checks `<file>.ext`, `<stem>.ext`, and the packed/unpacked sibling both ways -
        a .map is usually saved next to the unpacked copy while analysis may be pointed
        at the packed original. XIBIN_MAP / XIBIN_SYM override outright.
        """
        override = os.environ.get("XIBIN_" + ext.lstrip(".").upper())
        if override:
            return override if os.path.isfile(override) else None
        root, e = os.path.splitext(self.path)
        twin = root[: -len("_unpacked")] if root.endswith("_unpacked") else root + "_unpacked"
        for c in (self.path + ext, root + ext, twin + e + ext, twin + ext):
            if os.path.isfile(c):
                return c
        return None

    def _from_map(self) -> list[Symbol]:
        path = self.sidecar(".map")
        if not path:
            return []
        try:
            txt = open(path, encoding="latin1").read()
        except OSError:
            return []
        auto = re.compile(r"^(?:sub|loc|locret|off|dword|word|byte|unk|flt|dbl|asc|j)_([0-9A-F]{6,8})$")
        seg_base: dict[int, int] = {}
        rows: list[tuple[int, int, str]] = []
        for m in re.finditer(r"^\s([0-9A-F]{4}):([0-9A-F]{8})\s+(\S+)", txt, re.M):
            seg, off, name = int(m.group(1), 16), int(m.group(2), 16), m.group(3)
            rows.append((seg, off, name))
            a = auto.match(name)
            if a and seg not in seg_base:
                seg_base[seg] = int(a.group(1), 16) - off
        return [(seg_base[s] + o, n) for s, o, n in rows if s in seg_base]

    def _from_sym(self) -> list[Symbol]:
        """Bring-your-own names: one `<hex va> <name>` per line. Ghidra/BN export easily."""
        path = self.sidecar(".sym")
        if not path:
            return []
        try:
            txt = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            return []
        out: list[Symbol] = []
        for line in txt.splitlines():
            m = re.match(r"\s*(?:0x)?([0-9A-Fa-f]{6,16})\s+(\S+)", line)
            if m:
                out.append((int(m.group(1), 16), m.group(2)))
        return out

    def _derive(self) -> list[Symbol]:
        """No symbol file: every call target is a function start. Cheap byte scan."""
        out: set[int] = set()
        for _, sva, data in self.exec_secs():
            if self.arch == "x86":
                for m in re.finditer(rb"\xe8", data):
                    o = m.start()
                    if o + 5 <= len(data):
                        rel = int.from_bytes(data[o + 1 : o + 5], "little", signed=True)
                        out.add(sva + o + 5 + rel)
            else:
                for o in range(0, len(data) - 3, 4):
                    w = struct.unpack_from("<I", data, o)[0]
                    if w >> 26 == 0x03:  # jal
                        out.add(((sva + o) & 0xF0000000) | ((w & 0x03FFFFFF) << 2))
        code = {s[1] for s in self.exec_secs()}
        return [
            (va, "sub_%08X" % va)
            for va in out
            if (sec := self.sec_of(va)) and sec[1] in code
        ]

    def sym(self, va: int) -> str | None:
        s = self.syms()
        if not s:
            return None
        i = bisect.bisect_right(s, (va, "\xff")) - 1
        if i < 0 or va - s[i][0] > 0x4000:
            return None
        here, there = self.sec_of(va), self.sec_of(s[i][0])
        if not here or not there or here[1] != there[1]:
            return None  # nearest symbol lives in another section - not a real match
        return s[i][1] + ("+0x%x" % (va - s[i][0]) if va != s[i][0] else "")


def cmd_info(img: Img, _args: list[str]) -> None:
    layout = " (memory-mapped dump)" if getattr(img, "mapped", False) else ""
    print("%s  %s  base=0x%08x%s" % (img.path, img.arch, img.base, layout))
    for name, va, data in img.secs:
        print("  %-10s 0x%08x  0x%06x bytes" % (name, va, len(data)))
    n = len(img.syms())
    print("  symbols: %d from %s" % (n, img.symsrc) if n else "  symbols: none")


def cmd_dis(img: Img, args: list[str]) -> None:
    va = int(args[0], 0)
    n = int(args[1], 0) if len(args) > 1 else 0x200
    for i in img.cs().disasm(img.read(va, n), va):
        line = "%08x  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str)
        m = re.search(r"0x[0-9a-f]{6,8}", i.op_str)
        if m and i.mnemonic in ("call", "jmp", "jal", "j", "bal"):
            s = img.sym(int(m.group(0), 16))
            if s:
                line += "   ; " + s
        print(line)


def cmd_xref(img: Img, args: list[str]) -> None:
    tok = args[0]
    try:
        targets = [int(tok, 16 if tok.lower().startswith("0x") else 0)]
    except ValueError:
        targets = [va for va, _ in find_str(img, re.escape(tok))]
        print("string %r -> %s" % (tok, [hex(t) for t in targets] or "not found"))
    for target in targets:
        print("xrefs to 0x%08x:" % target)
        for name, sva, data in img.secs:
            if img.arch == "x86":
                for m in re.finditer(rb"\xe8", data):
                    o = m.start()
                    if o + 5 <= len(data):
                        rel = int.from_bytes(data[o + 1 : o + 5], "little", signed=True)
                        if sva + o + 5 + rel == target:
                            report(img, sva + o, "call")
            else:
                pat = struct.pack("<I", 0x0C000000 | ((target >> 2) & 0x03FFFFFF))
                o = data.find(pat)
                while o != -1:
                    if o % 4 == 0:
                        report(img, sva + o, "jal")
                    o = data.find(pat, o + 1)
            tb = target.to_bytes(4, "little")
            o = data.find(tb)
            while o != -1:
                report(img, sva + o, "ptr in " + name)
                o = data.find(tb, o + 1)


def report(img: Img, va: int, kind: str) -> None:
    print("   0x%08x  %-14s %s" % (va, kind, img.sym(va) or ""))


def find_str(img: Img, pattern: str | bytes, sec: str | None = None) -> list[Symbol]:
    rx = re.compile(pattern.encode("latin1") if isinstance(pattern, str) else pattern)
    out: list[Symbol] = []
    for name, sva, data in img.secs:
        if sec and name != sec:
            continue
        for m in re.finditer(rb"[\x20-\x7e]{4,}", data):
            if rx.search(m.group()):
                out.append((sva + m.start(), m.group().decode("latin1")))
    return out


def cmd_str(img: Img, args: list[str]) -> None:
    for va, s in find_str(img, args[0] if args else ".", args[1] if len(args) > 1 else None):
        print("0x%08x  %s" % (va, s))


def cmd_imm(img: Img, args: list[str]) -> None:
    """Linear sweep of executable sections for a literal immediate. Slow (~10s)."""
    val = int(args[0], 0)
    needles = {hex(val), str(val)}
    cs = img.cs()
    for _, sva, data in img.exec_secs():
        for i in cs.disasm(data, sva):
            if any(n in i.op_str for n in needles):
                print("0x%08x  %s %s   ; %s" % (i.address, i.mnemonic, i.op_str, img.sym(i.address) or ""))


def cmd_sym(img: Img, args: list[str]) -> None:
    print(img.sym(int(args[0], 0)) or "no symbol")


def cmd_unpack(img: Img, args: list[str]) -> None:
    """Write a normal PE with .text restored, for loading in IDA/Ghidra/BN."""
    if not getattr(img, "packed", None):
        sys.exit("%s is not POL1-packed - nothing to do." % img.path)
    assert img.packed is not None
    out = args[0] if args else re.sub(r"(\.\w+)$", r"_unpacked\1", img.path)
    d, align = img.data, img.file_align

    def up(n: int) -> int:
        return (n + align - 1) // align * align

    blob = bytearray(d[: img.size_of_headers])
    cursor = up(img.size_of_headers)
    for i, s in enumerate(img.rawsecs):
        body = img.packed["text"] if s["name"] == ".text" else d[s["ro"] : s["ro"] + s["rsz"]]
        hdr = img.pe + 24 + struct.unpack_from("<H", d, img.pe + 20)[0] + i * 40
        if not body:
            struct.pack_into("<II", blob, hdr + 16, 0, 0)
            continue
        struct.pack_into("<II", blob, hdr + 16, up(len(body)), cursor)
        blob[cursor : cursor + len(body)] = body
        blob.extend(b"\0" * max(0, cursor + up(len(body)) - len(blob)))
        cursor += up(len(body))
    if img.packed["oep"]:
        struct.pack_into("<I", blob, img.pe + 24 + 16, img.packed["oep"])
    open(out, "wb").write(blob)
    print(
        "%s\n  .text 0x%x bytes restored from POL1\n  entry point 0x%08x -> 0x%08x\n  %d bytes"
        % (out, len(img.packed["text"]), img.oep, img.packed["oep"] or img.oep, len(blob))
    )


CMDS: dict[str, Callable[[Img, list[str]], None]] = {
    "info": cmd_info,
    "dis": cmd_dis,
    "xref": cmd_xref,
    "str": cmd_str,
    "imm": cmd_imm,
    "sym": cmd_sym,
    "unpack": cmd_unpack,
}


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        return cmd_doctor(None, [])
    if len(sys.argv) < 3 or sys.argv[2] not in CMDS:
        sys.exit(__doc__)
    CMDS[sys.argv[2]](Img(sys.argv[1]), sys.argv[3:])


def _selftest() -> None:
    img = Img.__new__(Img)
    img.arch = "x86"
    img.secs = [(".text", 0x10001000, b"\x90" * 0x100), (".data", 0x10002000, b"\x01" * 0x80)]
    img.starts = [s[1] for s in img.secs]
    img._syms = None
    text_sec = img.sec_of(0x10001000)
    assert text_sec and text_sec[0] == ".text"
    text_end = img.sec_of(0x100010FF)
    assert text_end and text_end[0] == ".text"
    assert img.sec_of(0x10001100) is None, "gap between sections must not resolve"
    data_sec = img.sec_of(0x10002001)
    assert data_sec and data_sec[0] == ".data"
    assert img.sec_of(0x0FFFFFFF) is None
    assert img.read(0x10002000, 2) == b"\x01\x01"

    # a call at .text+0x10 to .text+0x40 must be derivable as a function start;
    # one aimed into .data must not become a symbol at all
    code = bytearray(b"\x90" * 0x100)
    code[0x10] = 0xE8
    code[0x11:0x15] = (0x40 - 0x15).to_bytes(4, "little", signed=True)
    code[0x20] = 0xE8
    code[0x21:0x25] = (0x1000 - 0x25).to_bytes(4, "little", signed=True)  # -> .data
    img.secs[0] = (".text", 0x10001000, bytes(code))
    img.path = os.path.join(os.path.dirname(__file__), "_no_such_binary")
    assert img.syms() == [(0x10001040, "sub_10001040")], img.syms()
    assert img.sym(0x10001048) == "sub_10001040+0x8"
    assert img.sym(0x10002010) is None, "must not name a .data address after a .text symbol"
    assert img.symsrc == "derived from call targets"

    # POL1 stream: flags 0b1100_0000 = literal 'A', literal 'B', backref(off=2,len=3),
    # terminator. The backref must read bytes it is still emitting.
    assert lzss_pol1(bytes([0xC0, 0x41, 0x42, 0x00, 0x02, 0x00, 0x00])) == b"ABABA"
    assert lzss_pol1(bytes([0x00, 0x00, 0x00])) == b""  # immediate terminator
    try:
        lzss_pol1(bytes([0x00, 0x0F, 0xFF]))  # backref before start of output
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-range back-reference must raise")
    print("ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        main()
