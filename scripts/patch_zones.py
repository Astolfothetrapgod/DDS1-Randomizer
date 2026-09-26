#!/usr/bin/env python3
"""Test of the per-zone encounter lists (ENCOUNT.TBL block 2).

Format tested (NOTES.md §4 bis, since validated ✅): 128 records of 0x20C bytes =
0x1C header + 4 lists of (u32 + 20 u16 triplets (encounter, weight, x)).

For each given zone, all its non-empty lists are replaced by a single triplet (encounter, 1000, 3).
ENCOUNT.TBL is read again from the original ISO, modified, then written whole into the copy:
previous tests are erased.

Usage: python scripts/patch_zones.py iso/dds1_us.iso work/dds1_test.iso 1=10 2=12 4=96
       (zone=encounter)
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from patch_unit import locate  # noqa: E402
from ramsearch import tbl_blocks  # noqa: E402

ENCOUNT_SIZE = 135136
ZONE_BLOCK, REC, HEAD, LIST, N = 2, 0x20C, 0x1C, 0x7C, 20
X_DEFAULT = 3


def main(src: str, dst: str, *pairs: str) -> None:
    if Path(src).resolve() == Path(dst).resolve():
        sys.exit("refused: src and dst must be two different files")
    off = locate(src, "battle/ENCOUNT.TBL")
    if locate(dst, "battle/ENCOUNT.TBL") != off:
        sys.exit("refused: ENCOUNT.TBL is not at the same place in src and dst")
    with open(src, "rb") as f:
        f.seek(off)
        tbl = bytearray(f.read(ENCOUNT_SIZE))
    block_off, block = tbl_blocks(bytes(tbl))[ZONE_BLOCK]
    base = block_off + 4

    for pair in pairs:
        zone, enc = map(int, pair.split("="))
        for l in range(4):
            lst = base + zone * REC + HEAD + l * LIST + 4
            triplets = [struct.unpack_from("<3H", tbl, lst + 6 * i) for i in range(N)]
            if sum(w for a, w, _ in triplets if a) == 0:
                continue                                   # unused list: left untouched
            struct.pack_into("<3H", tbl, lst, enc, 1000, X_DEFAULT)
            for i in range(1, N):
                struct.pack_into("<3H", tbl, lst + 6 * i, 0, 0, 0)
            print(f"zone {zone}, list {l}: {len([t for t in triplets if t[0]])} encounters -> encounter {enc} only")

    with open(dst, "r+b") as f:
        f.seek(off)
        f.write(tbl)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
