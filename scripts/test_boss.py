#!/usr/bin/env python3
"""Test: replace a boss with another one, rescaled (risk: event scripts).

Encounter 258 (Hayagriva, level 8, boss battle 901): Hayagriva -> Usas (261, level 20), brought to level 8
with the randomizer's pipeline: stats (value ≈ c × level^k), Hayagriva's Karma and Macca, damage spells
adapted in the record, the AI lists and the script (AI_Ushasu: Hamaon, Whirlwind, Seraph Lore), MP budget.
Reinforcements: units summoned by the script and reserved to it (Unicorn 301: in no encounter, summoned by
Usas alone) are rescaled with the same ratio (20/20 -> 8/8).
The boss battle number (+0x26 = 901) is not touched. Read again from the original ISO.

Usage: python scripts/test_boss.py iso/dds1_us.iso work/dds1_test.iso
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from randomizer.enemies import Result, own_script, raise_mp, random_encounters, rescale_unit, species_pool  # noqa: E402
from randomizer.iso import GameISO  # noqa: E402
from randomizer.options import Enemies  # noqa: E402
from randomizer.scaling import fit  # noqa: E402
from randomizer.skills import families  # noqa: E402
from randomizer.tables import AiTable, Encounters, UnitTable, read_skills, read_units  # noqa: E402

ENC, OLD, NEW = 258, 257, 261        # Hayagriva's encounter; Hayagriva; Usas


def main(src: str, dst: str) -> None:
    game = GameISO(src)
    msg, unit_data = game.read("battle/MSG.TBL"), game.read("battle/UNIT.TBL")
    units, skills = read_units(unit_data, msg), read_skills(game.read("battle/SKILL.TBL"), msg)
    enc, table, ai = Encounters(game.read("battle/ENCOUNT.TBL")), UnitTable(unit_data), AiTable(game.read("battle/AICALC.TBL"))
    before = AiTable(game.read("battle/AICALC.TBL"))

    if enc.enemies(ENC) != [OLD, 0, 0, 0, 0, 0, 0]:
        sys.exit(f"refused: encounter {ENC} = {enc.enemies(ENC)}")
    pool = species_pool(enc, random_encounters(enc), units)
    result = Result(0, Enemies(), {}, [], 0, exponents=fit(pool))
    fam, lo, hi = families(skills), min(u.level for u in pool), max(u.level for u in pool)
    A, B = units[OLD], units[NEW]

    rescale_unit(table, ai, B, A.level, A.karma, A.macca, result, fam, lo, hi)
    raise_mp(table, ai, NEW, skills, result)

    # reinforcements reserved to the boss: same level ratio, rewards in the same ratio
    script = own_script(ai, NEW)
    everywhere = {x for n in range(enc.count) for x in enc.enemies(n) if x}
    for x in sorted({ai.flow.arg(k) for k in script.summons} if script else set()):
        callers = [p.name for p in ai.flow.procedures if x in {ai.flow.arg(k) for k in p.summons}]
        if x == NEW or x in everywhere or ai.script(x) or len(callers) > 1:
            sys.exit(f"refused: summoned unit {x} ({units[x].name}) is not reserved to this boss")
        X, level = units[x], max(1, round(A.level * units[x].level / B.level))
        rescale_unit(table, ai, X, level, round(X.karma * A.karma / B.karma), round(X.macca * A.macca / B.macca),
                     result, fam, lo, hi)
        raise_mp(table, ai, x, skills, result)
    enc.set_enemies(ENC, [NEW, 0, 0, 0, 0, 0, 0])

    name = lambda x: "Attack" if x == 0x8000 else (skills[x].name if x < len(skills) else hex(x))  # noqa: E731
    for u in result.scaled:
        s = table.get(u)
        print(f"{units[u].name} {u} (lv {units[u].level}, HP {units[u].hp}) -> lv {s.level}, HP {s.hp}, "
              f"MP {s.mp}, stats {s.stats}, Karma {s.karma}, Macca {s.macca}")
        print("   record:", [name(x) for x in table.skills(u) if x])
        print("   AI:", [(p, name(a)) for _l, _k, p, a in ai.entries(u)])
    if script:
        print(f"   script {script.name}:", [f"{name(before.flow.arg(k))} -> {name(ai.flow.arg(k))}"
                                             for k in script.casts + script.checks])
    print(f"{result.ai_changes} AI actions, {result.script_changes} script arguments rewritten")

    shutil.copyfile(src, dst)
    out = GameISO(dst)
    for f, data in (("battle/UNIT.TBL", table.data), ("battle/AICALC.TBL", ai.data), ("battle/ENCOUNT.TBL", enc.data)):
        out.write(f, bytes(data))
    print(f"-> {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
