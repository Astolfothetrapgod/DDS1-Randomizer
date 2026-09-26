#!/usr/bin/env python3
"""Test: does a copy of a unit record in a free slot work in game?

Copies unit SRC_UNIT into the free slot DST_UNIT, in every block indexed by unit number
(384 rows; evidence: NOTES.md, "Record copy"):
  - UNIT.TBL block 3 (record) and block 4 (affinities);
  - VISUAL.TBL block 1 (model, scale…), EFFECT.TBL block 2, SOUND.TBL block 1;
  - AICALC.TBL block 0 (AI);
  - MSG.TBL block 3 (name, 17-byte slot);
then the DDT entries of model/devil/%03X.PB, _ms.LB, _ms.ls and sobed/%03X.BED of DST_UNIT point to
the data of SRC_UNIT; encounter ENC only contains DST_UNIT, and zone ZONE only offers encounter ENC.
Everything is read again from the original ISO.

Usage: python scripts/test_clone.py iso/dds1_us.iso work/dds1_test.iso
"""
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from randomizer.iso import GameISO  # noqa: E402
from randomizer.tables import Encounters, tbl_blocks  # noqa: E402

SRC_UNIT, DST_UNIT = 24, 112        # Macha -> "Reserve" slot (344+: placeholder model)
ENC, ZONE = 14, 2                   # "1 Onmoraki", zone at the start of the first dungeon
NAME_SIZE = 17
# (file, block) of the 384-row tables indexed by unit number
UNIT_ROWS = [("battle/UNIT.TBL", 3), ("battle/UNIT.TBL", 4), ("battle/VISUAL.TBL", 1),
             ("battle/EFFECT.TBL", 2), ("battle/SOUND.TBL", 1), ("battle/AICALC.TBL", 0)]


def main(src: str, dst: str) -> None:
    game = GameISO(src)
    files = {name: bytearray(game.read(name)) for name, _ in UNIT_ROWS}
    msg = bytearray(game.read("battle/MSG.TBL"))
    enc = Encounters(game.read("battle/ENCOUNT.TBL"))

    # Safety: the target slot must be reserved (name "Reserve") and unused
    names_off = tbl_blocks(msg)[3][0]
    dst_name = bytes(msg[names_off + DST_UNIT * NAME_SIZE:names_off + (DST_UNIT + 1) * NAME_SIZE]).split(b"\0")[0]
    if dst_name not in (b"Reserve", b"(Reserve)"):
        sys.exit(f"refused: slot {DST_UNIT} is named {dst_name!r}, not \"Reserve\"")
    if any(DST_UNIT in enc.enemies(n) for n in range(enc.count)):
        sys.exit(f"refused: slot {DST_UNIT} is used by an encounter")

    for name, b in UNIT_ROWS:
        data = files[name]
        off, length = tbl_blocks(data)[b]
        row = length // 384
        s, d = off + SRC_UNIT * row, off + DST_UNIT * row
        data[d:d + row] = data[s:s + row]
        print(f"{name} block {b}: row {SRC_UNIT} -> {DST_UNIT} ({row} bytes)")

    names = tbl_blocks(msg)[3][0]
    s, d = names + SRC_UNIT * NAME_SIZE, names + DST_UNIT * NAME_SIZE
    print(f"name: {bytes(msg[d:d + NAME_SIZE])!r} -> {bytes(msg[s:s + NAME_SIZE])!r}")
    msg[d:d + NAME_SIZE] = msg[s:s + NAME_SIZE]

    print(f"encounter {ENC}: {enc.enemies(ENC)} -> [{DST_UNIT}]")
    enc.set_enemies(ENC, [DST_UNIT] + [0] * 6)
    zone_base = tbl_blocks(enc.data)[2][0] + ZONE * 0x20C + 0x1C
    for l in range(4):
        lst = zone_base + l * 0x7C + 4
        if any(struct.unpack_from("<3H", enc.data, lst)):
            struct.pack_into("<3H", enc.data, lst, ENC, 1000, 3)
            for i in range(1, 20):
                struct.pack_into("<3H", enc.data, lst + 6 * i, 0, 0, 0)
            print(f"zone {ZONE}, list {l} -> encounter {ENC} only")

    shutil.copyfile(src, dst)
    out = GameISO(dst)
    for name, data in files.items():
        out.write(name, bytes(data))
    out.write("battle/MSG.TBL", bytes(msg))
    out.write("battle/ENCOUNT.TBL", bytes(enc.data))
    # Files named after the unit number in hexadecimal: model, sounds, sobed (animations?)
    for pattern in ("model/devil/{:03X}.PB", "model/devil/{:03X}_ms.LB", "model/devil/{:03X}_ms.ls",
                    "sobed/{:03X}.BED"):
        dst_file, src_file = pattern.format(DST_UNIT), pattern.format(SRC_UNIT)
        out.alias(dst_file, src_file)
        print(f"DDT: {dst_file} -> data of {src_file}")
    out.write_ddt()
    print(f"-> {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
