#!/usr/bin/env python3
"""Boss test 3 without travelling: Metatron (rescaled to level 15 by seed 2523) in every random battle,
and a PCSX2 cheat putting the party at an approximate level 15.

1. ISO: starts from the randomized ISO (seed 2523) and modifies it **in place**: one random encounter
   gets Metatron alone, and every non-empty list of the ordinary zones points to it (like
   patch_zones.py). Random battle (+0x00 = 0): no story flag is touched; the story continuing after a
   boss victory was already validated (boss test 2).
2. Cheat: permanent party records in RAM (✅ NOTES "Party records in RAM"): array of 0x1A4 bytes, Serph at
   0x01141D60; +0x04 id, +0x06 HP, +0x08 max HP, +0x0A MP, +0x0C max MP, +0x10 total Karma (u32),
   +0x14 level (u16), +0x16 St Vi Ma Ag Lu (5 × u8).
   Level-15 values = estimate from what was measured (level 6 → 7): +3 stat points, +4 max HP, +4 max
   MP per level; points are distributed like the tester's current build. (The game recomputes max HP /
   MP at the start of each battle: HP max = level × 4 + Vi × 4 + 10, MP max = level × 4 + Ma × 4 + 8.)

Usage: python scripts/test_boss3.py work/dds1_test.iso work/SLUS-20974_D7273511.pnach
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from randomizer.enemies import EXCLUDED_ZONES, random_encounters  # noqa: E402
from randomizer.iso import GameISO  # noqa: E402
from randomizer.tables import (LIST_LEN, ZONE_HEAD, ZONE_LIST, ZONE_LISTS, ZONE_SIZE, Encounters,  # noqa: E402
                               UnitTable)

BOSS, LEVEL = 265, 15                    # Metatron, place of Camazotz 1
PARTY, STRIDE = 0x01141D60, 0x1A4
# state after boss test 2 (savestate slot 3 = memory card save after Hayagriva)
CURRENT = {                              # name: (index, level, max HP, max MP, stats)
    "Serph": (0, 7, 54, 48, (22, 4, 3, 4, 3)),
    "Heat": (1, 7, 74, 56, (11, 9, 5, 6, 7)),
    "Argilla": (2, 6, 58, 68, (5, 6, 9, 6, 7)),
}
POINTS, HP_STEP, MP_STEP = 3, 4, 4


def spread(stats: tuple[int, ...], extra: int) -> list[int]:
    """Adds `extra` points proportionally to the current stats (largest remainders)."""
    total = sum(stats)
    shares = [s * extra / total for s in stats]
    out = [s + int(x) for s, x in zip(stats, shares)]
    for i in sorted(range(5), key=lambda i: shares[i] - int(shares[i]), reverse=True)[:extra - sum(map(int, shares))]:
        out[i] += 1
    return out


def patch_iso(path: str) -> int:
    game = GameISO(path)
    enc = Encounters(game.read("battle/ENCOUNT.TBL"))
    table = UnitTable(game.read("battle/UNIT.TBL"))
    lvl = table.get(BOSS).level
    if lvl != LEVEL:
        sys.exit(f"refused: Metatron is level {lvl} in this ISO (expected {LEVEL}: seed 2523 with bosses shuffled)")
    target = random_encounters(enc)[0]
    enc.set_enemies(target, [BOSS, 0, 0, 0, 0, 0, 0])
    lists = 0
    for z in range(enc.zone_count):
        if z in EXCLUDED_ZONES:
            continue
        for l in range(ZONE_LISTS):
            pos = enc._zones + z * ZONE_SIZE + ZONE_HEAD + l * ZONE_LIST + 4
            first = struct.unpack_from("<3H", enc.data, pos)
            if any(first):
                struct.pack_into("<3H", enc.data, pos, target, 1000, first[2])
                for i in range(1, LIST_LEN):
                    struct.pack_into("<3H", enc.data, pos + 6 * i, 0, 0, 0)
                lists += 1
    game.write("battle/ENCOUNT.TBL", bytes(enc.data))
    print(f"encounter {target} = Metatron alone; {lists} zone lists redirected")
    return target


def pnach(path: str) -> None:
    lines = ["gametitle=Shin Megami Tensei: Digital Devil Saga (SLUS-20974)",
             "", "[Boss test 3: party level 15]",
             "description=Approximate level-15 level, HP/MP and stats (randomizer test)"]
    for name, (k, level, hp, mp, stats) in CURRENT.items():
        base, n = PARTY + k * STRIDE, LEVEL - level
        new = spread(stats, POINTS * n)
        hp, mp = hp + HP_STEP * n, mp + MP_STEP * n
        print(f"{name:8s} lv {level} -> {LEVEL}: HP {hp}, MP {mp}, stats {stats} -> {tuple(new)}")
        lines.append(f"// {name}")
        for off, typ, value in ((0x14, "short", LEVEL), (0x06, "short", hp), (0x08, "short", hp),
                                (0x0A, "short", mp), (0x0C, "short", mp)):
            lines.append(f"patch=1,EE,{base + off:08X},{typ},{value:04X}")
        for i, v in enumerate(new):
            lines.append(f"patch=1,EE,{base + 0x16 + i:08X},byte,{v:02X}")
    Path(path).write_text("\n".join(lines) + "\n")
    print(f"-> {path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    patch_iso(sys.argv[1])
    pnach(sys.argv[2])
