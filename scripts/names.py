#!/usr/bin/env python3
"""Name tables of battle/MSG.TBL (blocks 0 to 9: ASCII, fixed-size slots).

Each slot = ASCII text terminated by \\0, padded with zeros. Slot size found by score (100 % of the
slots valid), meaning validated in game (NOTES.md §5). Empty slots read "Reserved" or "0x000…": they
are returned as "".

Usage: python scripts/names.py work/dds3/battle/MSG.TBL work/dds3/battle/UNIT.TBL
       -> writes work/units.tsv, work/skills.tsv, work/items.tsv
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ramsearch import tbl_blocks  # noqa: E402

# MSG.TBL block -> (name, slot size)
NAME_BLOCKS = {
    0: ("descriptions", 45),  # "Strong:ice_Weak:fire" (party characters)
    1: ("mantras", 19),       # "Devourer", "Holy Beast"
    3: ("units", 17),         # index = unit id (UNIT.TBL block 3)
    4: ("items", 25),
    5: ("characters", 17),    # index = id of the party members in battle
    6: ("races", 7),
    7: ("skills", 17),        # index = skill id
}


def read_names(block: bytes, size: int) -> list[str]:
    out = []
    for k in range(len(block) // size):
        text = block[k * size:(k + 1) * size].split(b"\0")[0].decode("ascii")
        out.append("" if text == "Reserved" or text.startswith("0x") else text)
    return out


def load(msg_tbl: bytes) -> dict[str, list[str]]:
    blocks = tbl_blocks(msg_tbl)
    return {name: read_names(blocks[i][1], size) for i, (name, size) in NAME_BLOCKS.items()}


def main(msg_path: str, unit_path: str) -> None:
    n = load(Path(msg_path).read_bytes())
    units = tbl_blocks(Path(unit_path).read_bytes())[3][1]
    out = Path("work")
    with open(out / "units.tsv", "w") as f:
        f.write("id\tname\tlevel\tHP\tMP\tSt\tVi\tMa\tAg\tLu\tmodel\tskills\n")
        for i in range(len(units) // 0x4C):
            e = units[i * 0x4C:(i + 1) * 0x4C]
            lv, hp, mp, model = e[5], *struct.unpack_from("<H", e, 6), *struct.unpack_from("<H", e, 0xA), \
                *struct.unpack_from("<H", e, 0xE)
            skills = [s for s in struct.unpack_from("<8H", e, 0x18) if s]
            f.write(f"{i}\t{n['units'][i]}\t{lv}\t{hp}\t{mp}\t" + "\t".join(map(str, e[0x10:0x15]))
                    + f"\t{model}\t" + ", ".join(n["skills"][s] if s < len(n["skills"]) else hex(s)
                                                 for s in skills) + "\n")
    for key, fname in (("skills", "skills.tsv"), ("items", "items.tsv")):
        with open(out / fname, "w") as f:
            f.write("id\tname\n")
            f.writelines(f"{i}\t{x}\n" for i, x in enumerate(n[key]) if x)
    print("work/units.tsv, work/skills.tsv, work/items.tsv written")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
