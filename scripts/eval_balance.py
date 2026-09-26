#!/usr/bin/env python3
"""Measures the effect of the enemy shuffle settings over many seeds.

First dungeon = zones 1, 2, 4, 5, 8 (validated in game, NOTES.md §4 bis).
Metrics:
  identity       % of species (whole game) replaced by themselves
  dungeon same   % of first-dungeon species that stay themselves
  dungeon lv     mean / max level of the species met in the first dungeon
                 (mean weighted by the zone list weights)
  |Δlv|          mean / max level gap, whole game
  new            (weighted) share of first-dungeon enemies that were not there originally

Usage: python scripts/eval_balance.py iso/dds1_us.iso
"""
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from randomizer.enemies import randomize  # noqa: E402
from randomizer.iso import GameISO  # noqa: E402
from randomizer.options import Enemies  # noqa: E402
from randomizer.tables import Encounters, UnitTable, read_units  # noqa: E402

DUNGEON = (1, 2, 4, 5, 8)
SEEDS = range(200)
# (level spread, no identity, rescaling)
CONFIGS = [(5, False, False), (5, True, False), (10, True, False), (5, True, True)]


def dungeon_species(enc: Encounters) -> dict[int, float]:
    """Species -> cumulative weight (probability × number of copies) in the first dungeon."""
    w = {}
    for z in DUNGEON:
        for lst in enc.zone_lists(z):
            for e, weight in lst:
                for x in enc.enemies(e):
                    if x:
                        w[x] = w.get(x, 0) + weight
    return w


def main(iso: str) -> None:
    g = GameISO(iso)
    original = g.read("battle/ENCOUNT.TBL")
    unit_data = g.read("battle/UNIT.TBL")
    units = read_units(unit_data, g.read("battle/MSG.TBL"))
    base = dungeon_species(Encounters(original))
    lvl0 = sum(units[x].level * w for x, w in base.items()) / sum(base.values())
    print(f"Original: first dungeon = {len(base)} species, mean level {lvl0:.1f}, "
          f"max {max(units[x].level for x in base)}\n")
    print("spread no_id scaling | identity | dungeon same | dungeon lv mean/max | |Δlv| mean/max | new")
    for spread, no_id, scaling in CONFIGS:
        ident, same, mean, mx, dmean, dmax, new = [], [], [], [], [], [], []
        for seed in SEEDS:
            enc, table = Encounters(original), UnitTable(unit_data)
            r = randomize(enc, table, units, seed,
                          Enemies(level_spread=spread, allow_identity=not no_id, scaling=scaling))
            lv = {i: table.get(i).level for i in range(table.count)}   # levels after rescaling
            m = r.mapping
            ident.append(sum(a == b for a, b in m.items()) / len(m))
            same.append(sum(m.get(x, x) == x for x in base) / len(base))
            after = dungeon_species(enc)
            mean.append(sum(lv[x] * w for x, w in after.items()) / sum(after.values()))
            mx.append(max(lv[x] for x in after))
            new.append(sum(w for x, w in after.items() if x not in base) / sum(after.values()))
            deltas = [abs(units[a].level - lv[b]) for a, b in m.items()]
            dmean.append(statistics.mean(deltas))
            dmax.append(max(deltas))
        print(f"±{spread:<5} {str(no_id):5} {str(scaling):7} | {100 * statistics.mean(ident):6.1f} % | "
              f"{100 * statistics.mean(same):10.1f} % | {statistics.mean(mean):8.1f} / {max(mx):3d}       | "
              f"{statistics.mean(dmean):4.1f} / {max(dmax):2d}     | {100 * statistics.mean(new):5.1f} %")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "iso/dds1_us.iso")
