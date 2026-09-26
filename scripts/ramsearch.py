#!/usr/bin/env python3
"""Looks for the blocks of a .TBL file in an EE RAM dump (eeMemory.bin).

The .TBL is split according to its container (see NOTES.md §3: u32 size + data, 16-byte alignment).
For each block, it looks for:
  - the whole block (strong evidence that the game loaded it as is);
  - otherwise, its first 32 non-zero bytes (partial or modified load).
The offset in eeMemory.bin = the EE address seen in PCSX2's debugger.

Usage: python scripts/ramsearch.py work/ram/slot01/eeMemory.bin work/dds3/battle/UNIT.TBL [...]
"""
import struct
import sys
from pathlib import Path


def tbl_blocks(data: bytes):
    pos, blocks = 0, []
    while pos + 4 <= len(data):
        size = struct.unpack_from("<I", data, pos)[0]
        blocks.append((pos, data[pos + 4:pos + 4 + size]))
        pos = (pos + 4 + size + 15) // 16 * 16
    return blocks


def find_all(hay: bytes, needle: bytes, limit: int = 8):
    hits, i = [], hay.find(needle)
    while i != -1 and len(hits) < limit:
        hits.append(i)
        i = hay.find(needle, i + 1)
    return hits


def probe(block: bytes, n: int = 32) -> bytes | None:
    """First n-byte excerpt of the block that is not only zeros."""
    for off in range(0, max(len(block) - n, 0) + 1, 16):
        chunk = block[off:off + n]
        if chunk.count(0) < n // 2:
            return chunk
    return None


def main(ram_path: str, *tbl_paths: str) -> None:
    ram = Path(ram_path).read_bytes()
    print(f"RAM: {ram_path} ({len(ram)} bytes)")
    for tbl_path in tbl_paths:
        data = Path(tbl_path).read_bytes()
        print(f"\n== {tbl_path}")
        # The whole file, size headers included
        whole = find_all(ram, data)
        if whole:
            print(f"   whole file found at {', '.join(f'0x{h:08X}' for h in whole)}")
        for i, (off, block) in enumerate(tbl_blocks(data)):
            if not block:
                continue
            full = find_all(ram, block)
            line = f"   block {i} (file+0x{off:05X}, {len(block):6} bytes): "
            if full:
                line += "WHOLE at " + ", ".join(f"0x{h:08X}" for h in full)
            else:
                p = probe(block)
                part = find_all(ram, p) if p else []
                line += ("not whole; 32-byte excerpt found at "
                         + ", ".join(f"0x{h:08X}" for h in part)) if part else "missing"
            print(line)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
