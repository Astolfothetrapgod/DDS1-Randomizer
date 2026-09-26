#!/usr/bin/env python3
"""Step 1 test: change the HP of a UNIT.TBL unit in a copy of the ISO.

Address chain (all validated in NOTES.md):
  ISO    : DDS3.IMG starts at the LBA given by ISO9660   (x 2048)
  IMG    : battle/UNIT.TBL at the sector given by the DDT (x 0x800)
  TBL    : block 3 = units, data after the u32 header
  block  : entry n at n * 0x4C, current HP +0x06, max HP +0x08

The script reads the original bytes back and refuses to write if they are not the expected ones: a
wrong address cannot corrupt anything else.

Usage: python scripts/patch_unit.py work/dds1_test.iso 284 999
"""
import struct
import sys
from pathlib import Path

import pycdlib

sys.path.insert(0, str(Path(__file__).parent))
import ddt  # noqa: E402
from ramsearch import tbl_blocks  # noqa: E402

UNIT_SIZE = 0x4C
UNIT_BLOCK = 3
OFF_HP, OFF_HP_MAX = 0x06, 0x08


def locate(iso_path: str, dds3_path: str, ddt_path: str = "extracted/DDS3.DDT") -> int:
    """Absolute offset of a DDS3.IMG file (e.g. battle/UNIT.TBL) in the ISO."""
    iso = pycdlib.PyCdlib()
    iso.open(iso_path)
    img_lba = iso.get_record(iso_path="/DDS3.IMG;1").extent_location()
    iso.close()
    entry = [f for f in ddt.files(Path(ddt_path).read_bytes()) if f[0] == dds3_path][0]
    return img_lba * 2048 + entry[2] * ddt.SECTOR


def main(iso_path: str, unit_id: str, new_hp: str) -> None:
    unit_id, new_hp = int(unit_id), int(new_hp)
    tbl_off = locate(iso_path, "battle/UNIT.TBL")
    with open(iso_path, "r+b") as f:
        f.seek(tbl_off)
        tbl = f.read(67600)
        block_off, block = tbl_blocks(tbl)[UNIT_BLOCK]
        entry_off = tbl_off + block_off + 4 + unit_id * UNIT_SIZE
        entry = block[unit_id * UNIT_SIZE:(unit_id + 1) * UNIT_SIZE]
        hp, hp_max = struct.unpack_from("<HH", entry, OFF_HP)
        print(f"UNIT.TBL at 0x{tbl_off:X} in the ISO; unit {unit_id} at 0x{entry_off:X}")
        print(f"before: level {entry[5]}, HP {hp}/{hp_max}")
        if hp != hp_max:
            sys.exit("refused: HP != max HP, this is not an expected unit entry")
        f.seek(entry_off + OFF_HP)
        f.write(struct.pack("<HH", new_hp, new_hp))
        f.seek(entry_off + OFF_HP)
        print(f"after: HP {struct.unpack('<HH', f.read(4))}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
