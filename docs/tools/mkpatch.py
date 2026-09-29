#!/usr/bin/env python3
"""mkpatch.py -- turn (VA, orig, new) into a byte patch, resolving the file
offset from the PE section table.

    file_off = VA - image_base - section.VirtualAddress + section.PointerToRawData

image_base is read from the PE optional header and cross-checked against the
expected 0x180000000 (a mismatch is reported, not silently tolerated).

The disc-resident original byte is verified against the `orig` you passed. If
they differ the tool exits non-zero WITHOUT emitting a patch, because a patch
built on a wrong original silently corrupts whatever it lands on.

Output is the exact `--patch` argument format try_patch.py consumes:

    0xBF1ACE:0x75:0xEB

Usage
-----
    # by virtual address (the usual case)
    python3 mkpatch.py --dll D:/ks_debug/harness/main.dll --va 0x180BF1ACE:0x75:0xEB

    # by file offset (still verified against the on-disk byte)
    python3 mkpatch.py --dll D:/ks_debug/harness/main.dll --off 0xBF1ACE:0x75:0xEB

    # inspect only: VA -> file offset, no patch emitted
    python3 mkpatch.py --dll D:/ks_debug/harness/main.dll --resolve 0x180BF1ACE

    # machine readable
    python3 mkpatch.py --dll ... --va ... --json
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

DEFAULT_DLL = "D:/ks_debug/harness/main.dll"
EXPECTED_IMAGE_BASE = 0x180000000
PE32_PLUS_MAGIC = 0x20B


class PatchError(Exception):
    """Any condition that must stop the tool before it emits a patch."""


def to_win_path(p: str) -> str:
    """Accept a WSL /mnt/<drive>/... path as well as a native Windows one."""
    if p.startswith("/mnt/") and len(p) > 6 and p[6] == "/":
        drive = p[5].upper()
        return f"{drive}:\\" + p[7:].replace("/", "\\")
    return p


def to_posix_path(p: str) -> str:
    """Accept a native Windows path on the Linux side."""
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[2:].replace("\\", "/").lstrip("/")
        return f"/mnt/{drive}/{rest}"
    return p


def read_at(fh, off: int, n: int) -> bytes:
    fh.seek(off)
    b = fh.read(n)
    if len(b) != n:
        raise PatchError(f"short read at file offset 0x{off:X}: wanted {n} bytes, got {len(b)}")
    return b


def parse_pe(path: Path) -> dict:
    """Minimal PE32+ section table + image base. No third-party dependency."""
    with path.open("rb") as fh:
        if read_at(fh, 0, 2) != b"MZ":
            raise PatchError(f"{path} is not a PE file (no MZ signature)")

        e_lfanew = struct.unpack("<I", read_at(fh, 0x3C, 4))[0]
        if read_at(fh, e_lfanew, 4) != b"PE\0\0":
            raise PatchError(f"{path} has no PE signature at 0x{e_lfanew:X}")

        coff = e_lfanew + 4
        machine, n_sections = struct.unpack("<HH", read_at(fh, coff, 4))
        size_opt = struct.unpack("<H", read_at(fh, coff + 16, 2))[0]

        opt = coff + 20
        magic = struct.unpack("<H", read_at(fh, opt, 2))[0]
        if magic != PE32_PLUS_MAGIC:
            raise PatchError(f"{path} is not PE32+ (optional header magic 0x{magic:X})")

        image_base = struct.unpack("<Q", read_at(fh, opt + 24, 8))[0]

        sec_table = opt + size_opt
        sections = []
        for i in range(n_sections):
            base = sec_table + i * 40
            raw = read_at(fh, base, 40)
            name = raw[0:8].rstrip(b"\0").decode("ascii", "replace")
            vsize, vaddr, rawsize, rawptr = struct.unpack("<IIII", raw[8:24])
            sections.append(
                {
                    "index": i,
                    "name": name,
                    "virtual_size": vsize,
                    "virtual_address": vaddr,
                    "size_of_raw_data": rawsize,
                    "pointer_to_raw_data": rawptr,
                    "raw_end": rawptr + rawsize,
                }
            )

        return {
            "path": str(path),
            "machine": machine,
            "image_base": image_base,
            "sections": sections,
        }


def resolve_va(pe: dict, va: int) -> dict:
    """VA -> file offset using the section table. Raises if the VA is unmapped."""
    image_base = pe["image_base"]
    if va < image_base:
        raise PatchError(
            f"VA 0x{va:X} is below image base 0x{image_base:X}; pass an absolute VA"
        )
    rva = va - image_base
    for s in pe["sections"]:
        span = max(s["virtual_size"], s["size_of_raw_data"])
        if s["virtual_address"] <= rva < s["virtual_address"] + span:
            if rva - s["virtual_address"] >= s["size_of_raw_data"]:
                raise PatchError(
                    f"RVA 0x{rva:X} falls in section {s['name']!r} beyond its raw data "
                    f"(size_of_raw_data=0x{s['size_of_raw_data']:X}); "
                    f"this is an uninitialised/BSS address with no file byte to patch"
                )
            off = rva - s["virtual_address"] + s["pointer_to_raw_data"]
            return {
                "va": va,
                "rva": rva,
                "file_off": off,
                "section": s["name"],
                "section_index": s["index"],
            }
    raise PatchError(f"RVA 0x{rva:X} is not covered by any section")


def resolve_off(pe: dict, off: int) -> dict:
    """File offset -> the section that owns it (verification only)."""
    for s in pe["sections"]:
        if s["pointer_to_raw_data"] <= off < s["raw_end"]:
            rva = off - s["pointer_to_raw_data"] + s["virtual_address"]
            return {
                "va": pe["image_base"] + rva,
                "rva": rva,
                "file_off": off,
                "section": s["name"],
                "section_index": s["index"],
            }
    raise PatchError(f"file offset 0x{off:X} is not inside any section's raw data")


def parse_byte_triplet(text: str) -> tuple[int, int, int]:
    """Parse 'KEY:ORIG:NEW' where ORIG/NEW are one-byte hex and KEY is an int."""
    parts = text.split(":")
    if len(parts) != 3:
        raise PatchError(f"expected KEY:ORIG:NEW, got {text!r}")
    try:
        key = int(parts[0], 0)
    except ValueError:
        raise PatchError(f"bad address {parts[0]!r} (use 0x... or decimal)")
    try:
        orig = int(parts[1], 0)
        new = int(parts[2], 0)
    except ValueError:
        raise PatchError(f"bad byte value in {text!r} (use hex like 0x75)")
    for label, v in (("orig", orig), ("new", new)):
        if not 0 <= v <= 0xFF:
            raise PatchError(f"{label} byte 0x{v:X} is out of range 0..0xFF")
    return key, orig, new


def verify_on_disk(fh, off: int, expected: int, label: str) -> int:
    actual = read_at(fh, off, 1)[0]
    if actual != expected:
        raise PatchError(
            f"{label} mismatch at file offset 0x{off:X}: "
            f"disk has 0x{actual:02X}, you declared 0x{expected:02X} "
            f"-- refusing to emit a patch built on a stale original"
        )
    return actual


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="VA -> file offset byte patch generator for main.dll",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--dll", default=DEFAULT_DLL, help=f"PE file to read sections from (default {DEFAULT_DLL})")
    ap.add_argument("--va", action="append", default=[], metavar="VA:ORIG:NEW",
                    help="absolute virtual address triplet, e.g. 0x180BF1ACE:0x75:0xEB (repeatable)")
    ap.add_argument("--off", action="append", default=[], metavar="OFF:ORIG:NEW",
                    help="raw file offset triplet (repeatable)")
    ap.add_argument("--resolve", action="append", default=[], metavar="ADDR",
                    help="print the section mapping for a VA or file offset and exit (repeatable)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of the plain patch list")
    args = ap.parse_args(argv)

    try:
        dll_posix = Path(to_posix_path(to_win_path(args.dll)))
        if not dll_posix.is_file():
            raise PatchError(f"dll not found: {dll_posix}")

        pe = parse_pe(dll_posix)

        if args.resolve:
            out = []
            for a in args.resolve:
                v = int(a, 0)
                info = resolve_va(pe, v) if v >= pe["image_base"] else resolve_off(pe, v)
                out.append(info)
                if not args.json:
                    print(
                        f"0x{v:X} -> file 0x{info['file_off']:X}  "
                        f"section {info['section']}  RVA 0x{info['rva']:X}  VA 0x{info['va']:X}"
                    )
            if args.json:
                print(json.dumps({"image_base": pe["image_base"], "resolved": out}, indent=2))
            return 0

        if not args.va and not args.off:
            raise PatchError("nothing to do: pass --va or --off (or --resolve)")

        results = []
        with dll_posix.open("rb") as fh:
            for spec in args.va:
                key, orig, new = parse_byte_triplet(spec)
                info = resolve_va(pe, key)
                verify_on_disk(fh, info["file_off"], orig, "original byte")
                results.append({**info, "input": "va", "orig": orig, "new": new})

            for spec in args.off:
                key, orig, new = parse_byte_triplet(spec)
                info = resolve_off(pe, key)
                verify_on_disk(fh, info["file_off"], orig, "original byte")
                results.append({**info, "input": "off", "orig": orig, "new": new})

        patch_args = [f"0x{r['file_off']:X}:0x{r['orig']:02X}:0x{r['new']:02X}" for r in results]

        if args.json:
            print(json.dumps(
                {
                    "image_base": pe["image_base"],
                    "image_base_expected": EXPECTED_IMAGE_BASE,
                    "image_base_ok": pe["image_base"] == EXPECTED_IMAGE_BASE,
                    "dll": str(dll_posix),
                    "patches": results,
                    "patch_args": patch_args,
                },
                indent=2,
            ))
        else:
            if pe["image_base"] != EXPECTED_IMAGE_BASE:
                print(
                    f"WARN image base 0x{pe['image_base']:X} != expected "
                    f"0x{EXPECTED_IMAGE_BASE:X}; offsets were resolved with the ACTUAL base",
                    file=sys.stderr,
                )
            for r, pa in zip(results, patch_args):
                print(
                    f"{pa}    # VA 0x{r['va']:X} -> file 0x{r['file_off']:X} "
                    f"section {r['section']} ({r['orig']:02X}->{r['new']:02X})"
                )
        return 0

    except PatchError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
