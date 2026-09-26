#!/usr/bin/env python3
"""Affinity test (UNIT.TBL block 4: 384 rows of 19 × u32; hypothesis since validated ✅).

Hypothesis: column = SKILL.TBL element (0 physical, 1 gun, 2 fire, 3 ice…), u32 = flags (high 16 bits)
+ percentage (low 16 bits); 0x8000 = weak, 0x0001 = null, 0x0002 = repel, 0x0004 = drain.

Preta (102): physical -> null (0x00010000), ice -> weak 150 % (0x80000096).
Zone 2 only offers encounter 518 (2 Preta). Everything is read again from the original ISO.

Usage: python scripts/test_affinity.py iso/dds1_us.iso work/dds1_test.iso
"""
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from randomizer.iso import GameISO  # noqa: E402
from randomizer.tables import Encounters, tbl_blocks  # noqa: E402

UNIT, COLS = 102, {0: 0x00010000, 3: 0x80000096}   # Preta: physical nulled, weak to ice
ZONE, ENC = 2, 518                                  # 518 = 2 Preta


def main(src: str, dst: str) -> None:
    game = GameISO(src)
    unit = bytearray(game.read("battle/UNIT.TBL"))
    off = tbl_blocks(unit)[4][0] + UNIT * 0x4C
    for col, value in COLS.items():
        old = struct.unpack_from("<I", unit, off + 4 * col)[0]
        struct.pack_into("<I", unit, off + 4 * col, value)
        print(f"unit {UNIT}, column {col}: {old:08X} -> {value:08X}")

    enc = Encounters(game.read("battle/ENCOUNT.TBL"))
    print(f"encounter {ENC}: {enc.enemies(ENC)}")
    zone = tbl_blocks(enc.data)[2][0] + ZONE * 0x20C + 0x1C
    for l in range(4):
        lst = zone + l * 0x7C + 4
        if any(struct.unpack_from("<3H", enc.data, lst)):
            struct.pack_into("<3H", enc.data, lst, ENC, 1000, 3)
            for i in range(1, 20):
                struct.pack_into("<3H", enc.data, lst + 6 * i, 0, 0, 0)

    shutil.copyfile(src, dst)
    out = GameISO(dst)
    out.write("battle/UNIT.TBL", bytes(unit))
    out.write("battle/ENCOUNT.TBL", bytes(enc.data))
    print(f"-> {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
