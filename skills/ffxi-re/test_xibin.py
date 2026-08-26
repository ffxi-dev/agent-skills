#!/usr/bin/env python3
"""Standalone tests for xibin's byte/VA logic. No pytest, no game files.

Run: `python skills/ffxi-re/test_xibin.py` (CI runs it from this directory).

These exercise the same internals `xibin.py --selftest` does, by calling them
directly: section/VA resolution, the cross-section symbol guard that stops a stray
call byte in .data from inventing a symbol, and the POL1 `lzss_pol1` decompressor
including an overlapping back-reference and the out-of-range guard.
"""

from __future__ import annotations

import os

import xibin
from xibin import Img


def make_img(secs: list[xibin.Section], arch: str = "x86") -> Img:
    """An Img with hand-placed sections, bypassing file parsing (as --selftest does)."""
    img = Img.__new__(Img)
    img.arch = arch
    img.secs = secs
    img.starts = [s[1] for s in secs]
    img._syms = None
    img.path = os.path.join(os.path.dirname(__file__), "_no_such_binary")
    return img


def test_sec_of_resolves_within_a_section() -> None:
    img = make_img([(".text", 0x10001000, b"\x90" * 0x100)])
    first = img.sec_of(0x10001000)
    last = img.sec_of(0x100010FF)
    assert first and first[0] == ".text"
    assert last and last[0] == ".text"


def test_sec_of_rejects_gaps_and_below_base() -> None:
    img = make_img(
        [(".text", 0x10001000, b"\x90" * 0x100), (".data", 0x10002000, b"\x01" * 0x80)]
    )
    assert img.sec_of(0x10001100) is None, "gap between sections must not resolve"
    assert img.sec_of(0x0FFFFFFF) is None, "below the first section must not resolve"
    data = img.sec_of(0x10002001)
    assert data and data[0] == ".data"


def test_read_returns_bytes_at_va() -> None:
    img = make_img(
        [(".text", 0x10001000, b"\x90" * 0x100), (".data", 0x10002000, b"\x01" * 0x80)]
    )
    assert img.read(0x10002000, 2) == b"\x01\x01"
    assert img.read(0x10001100, 4) == b"", "an unmapped VA reads empty"


def _guard_img() -> Img:
    """.text with two E8 calls: one into .text (a real function start), one into .data."""
    code = bytearray(b"\x90" * 0x100)
    code[0x10] = 0xE8
    code[0x11:0x15] = (0x40 - 0x15).to_bytes(4, "little", signed=True)
    code[0x20] = 0xE8
    code[0x21:0x25] = (0x1000 - 0x25).to_bytes(4, "little", signed=True)  # -> .data
    return make_img(
        [(".text", 0x10001000, bytes(code)), (".data", 0x10002000, b"\x01" * 0x80)]
    )


def test_derive_finds_intra_section_call_target_only() -> None:
    img = _guard_img()
    assert img.syms() == [(0x10001040, "sub_10001040")], img.syms()
    assert img.symsrc == "derived from call targets"


def test_sym_offsets_within_a_function() -> None:
    img = _guard_img()
    assert img.sym(0x10001048) == "sub_10001040+0x8"
    assert img.sym(0x10001040) == "sub_10001040", "exact match carries no +0x offset"


def test_cross_section_symbol_guard() -> None:
    img = _guard_img()
    assert img.sym(0x10002010) is None, "a .data address must not borrow a .text symbol"


def test_lzss_overlapping_backreference() -> None:
    # flags 0b1100_0000: literal 'A', literal 'B', backref(off=2,len=3), terminator.
    # the back-reference reads bytes it is itself still emitting.
    assert lzss("C0 41 42 00 02 00 00") == b"ABABA"


def test_lzss_immediate_terminator() -> None:
    assert lzss("00 00 00") == b"", "a zero offset ends the stream immediately"


def test_lzss_out_of_range_backreference_raises() -> None:
    try:
        xibin.lzss_pol1(bytes([0x00, 0x0F, 0xFF]))  # back-reference before start of output
    except ValueError:
        return

    raise AssertionError("a back-reference before the start of output must raise")


def lzss(hexbytes: str) -> bytes:
    return xibin.lzss_pol1(bytes(int(b, 16) for b in hexbytes.split()))


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
