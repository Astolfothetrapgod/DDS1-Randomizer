#!/usr/bin/env python3
"""Step 2 test: replace the enemies of an ENCOUNT.TBL encounter.

ENCOUNT.TBL block 0 = 1024 entries of 0x28 bytes (see NOTES.md);
hypothesis tested here (since validated ✅): 7 u16 enemy slots from +0x06 to +0x12.

The script shows the encounter before/after and refuses to write if the current enemies are not the
expected ones (--expect).

Usage: python scripts/patch_encounter.py work/dds1_test.iso 257 --expect 284,284 --set 99,99,99
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from patch_unit import locate  # noqa: E402
from ramsearch import tbl_blocks  # noqa: E402

ENC_SIZE = 0x28
ENC_BLOCK = 0
OFF_ENEMIES, N_SLOTS = 0x06, 7


def ids(text: str) -> list[int]:
    return [int(x) for x in text.split(",") if x]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("iso")
    ap.add_argument("encounter", type=int)
    ap.add_argument("--expect", type=ids, required=True, help="current enemies, e.g. 284,284")
    ap.add_argument("--set", type=ids, required=True, help="new enemies, e.g. 99,99,99")
    a = ap.parse_args()
    if len(a.set) > N_SLOTS:
        sys.exit(f"at most {N_SLOTS} enemies")

    tbl_off = locate(a.iso, "battle/ENCOUNT.TBL")
    with open(a.iso, "r+b") as f:
        f.seek(tbl_off)
        tbl = f.read(135136)
        block_off, block = tbl_blocks(tbl)[ENC_BLOCK]
        entry_off = tbl_off + block_off + 4 + a.encounter * ENC_SIZE
        slots = list(struct.unpack_from(f"<{N_SLOTS}H", block, a.encounter * ENC_SIZE + OFF_ENEMIES))
        print(f"encounter {a.encounter} at 0x{entry_off:X}; before: {slots}")
        if [x for x in slots if x] != a.expect:
            sys.exit(f"refused: current enemies {slots} != expected {a.expect}")
        new = a.set + [0] * (N_SLOTS - len(a.set))
        f.seek(entry_off + OFF_ENEMIES)
        f.write(struct.pack(f"<{N_SLOTS}H", *new))
        f.seek(entry_off + OFF_ENEMIES)
        print(f"after: {list(struct.unpack(f'<{N_SLOTS}H', f.read(2 * N_SLOTS)))}")


if __name__ == "__main__":
    main()
