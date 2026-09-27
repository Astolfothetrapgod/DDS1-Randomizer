"""Shuffle of single-unit bosses (scripted battles).

Each boss place (scripted encounter) receives another boss, rescaled to the level of the place:
HP/MP/stats on the level curve (value ≈ c × level^k, like ordinary enemies), Karma and Macca of the
place, damage and percentage spells brought to their rank in the record, the AI lists and the script.
Unique skills (Seraph Lore…) do not change (tester's choice, boss test 2).
HP: on the level curve by default (a sturdy boss stays sturdy); option hp = "place": the new boss takes
the HP of the boss it replaces (level, stats, skills and rewards unchanged; no random draw, so the rest of
the seed is identical).
Unique skills: kept by default; option unique_skills = "power": the power of a damage or percentage
skill that only this boss uses (and no mantra) follows the level change on a continuous curve,
power × (new level / old level)^k, k measured on the ordinary species' skills (see UNIQUE_K). The boss battle number
(+0x26) stays the one of the place: the story continues from it (validated in game, boss test 2).

Reinforcements: a summoned unit reserved to the boss (in no encounter, summoned by it alone) is
rescaled with it, with the same level ratio (same id: original model and sounds). A summoned unit
that is a shuffled enemy species is replaced by a shuffled species of proportional level; any other
summoned unit makes the boss ineligible.
"""
import random
from dataclasses import dataclass, field

from .enemies import (Result, actions, own_script, raise_mp, random_encounters, rescale_unit, species_pool)
from .scaling import fit
from .skills import families
from .tables import AiTable, Encounters, Skill, SkillTable, Unit, UnitTable

MIN_HP = 1000            # without a boss number (+0x26), threshold telling a boss from an event battle
SPECIAL = 0xFF           # UNIT +0x16: special unit (boss, NPC)
PLACEHOLDER_HP = 32767   # placeholder HP (battle that cannot be won)
# Exponent k of "power ≈ c × level^k", log-log fit on the (species level, skill power) pairs of the 90
# ordinary species' AI (original game; NOTES "Unique boss skills"): magic on all targets 0.71 (R² 0.52),
# on one target 0.39 (R² 0.49), percentage 0.24 (R² 0.50), physical 0.21 (R² 0.11: weak, powers also
# depend on hits and HP cost).
UNIQUE_K = {"all": 0.71, "one": 0.39, "percent": 0.24, "physical": 0.21}
DAMAGE, PERCENT = 1, 8

# Places left untouched, with the reason (encounter -> reason).
EXCLUDED_ENCOUNTERS = {
    263: "Agni 905: 32767 HP, probably a battle meant to be lost",
    269: "Harihara 911: 999 HP at level 68, first phase of battle 912 (Harihara + Cores)",
}


@dataclass
class BossResult:
    places: list[tuple[int, int]] = field(default_factory=list)       # (encounter, original boss)
    mapping: dict[int, int] = field(default_factory=dict)             # encounter -> new boss
    reinforcements: dict[int, list[tuple[int, int]]] = field(default_factory=dict)  # boss -> [(summoned, level)]
    summons: dict[int, list[tuple[int, int]]] = field(default_factory=dict)         # boss -> [(old, new)]
    units: Result | None = None                                        # rewritten records (spoiler)
    unique: dict[int, tuple[int, int, int]] = field(default_factory=dict)  # skill -> (boss, old power, new)


def _summoned(ai: AiTable, unit: int) -> set[int]:
    p = own_script(ai, unit)
    return {ai.flow.arg(k) for k in p.summons} - {unit} if p else set()


def _reserved(x: int, caller: int, ai: AiTable, everywhere: set[int]) -> bool:
    """Reserved summon: in no encounter, summoned by `caller` alone (itself aside), any script of
    its own."""
    if x in everywhere or (ai.script(x) and own_script(ai, x) is None):
        return False
    callers = {u for p, users in ai.script_users().items() for u in users
               if x in {ai.flow.arg(k) for k in ai.flow.procedures[p].summons}}
    return callers - {x} == {caller}


def boss_places(enc: Encounters, table: UnitTable, ai: AiTable, units: list[Unit],
                pool_ids: set[int]) -> list[tuple[int, int]]:
    """(encounter, boss) of the shufflable places: scripted encounter with a single enemy, special
    unit found only in this encounter, boss number or at least MIN_HP HP, unshared script, summons
    that are reserved or shuffled species."""
    randoms = set(random_encounters(enc))
    where: dict[int, set[int]] = {}
    for n in range(enc.count):
        for x in enc.enemies(n):
            if x:
                where.setdefault(x, set()).add(n)
    everywhere = set(where)
    out = []
    for n in range(enc.count):
        ids = [x for x in enc.enemies(n) if x]
        if n in randoms or n in EXCLUDED_ENCOUNTERS or len(ids) != 1 or enc.flag(n) != 1:
            continue
        u = ids[0]
        U = units[u]
        if where[u] != {n} or table.special(u) != SPECIAL or U.hp >= PLACEHOLDER_HP:
            continue
        if not (enc.boss_number(n) or U.hp >= MIN_HP):
            continue
        if ai.script(u) and own_script(ai, u) is None:
            continue
        if all(x in pool_ids or _reserved(x, u, ai, everywhere - {x}) for x in _summoned(ai, u)):
            out.append((n, u))
    return out


def randomize_bosses(enc: Encounters, table: UnitTable, ai: AiTable, units: list[Unit],
                     skills: list[Skill] | None, seed: int, hp: str = "curve") -> BossResult:
    """Modifies `enc`, `table` and `ai` in place. Call after the enemy shuffle: summons of shuffled
    species target their level after rescaling. `units` = original records (read before any change)."""
    rng = random.Random(f"{seed}-boss")             # stream name frozen: changing it would change every seed
    pool = species_pool(enc, random_encounters(enc), units)
    pool_ids = {u.id for u in pool}
    res = BossResult()
    res.places = boss_places(enc, table, ai, units, pool_ids)
    if len(res.places) < 2:
        return res
    bosses = [u for _n, u in res.places]
    order = bosses[:]
    while any(a == b for a, b in zip(bosses, order)):       # no boss stays in its place
        rng.shuffle(order)
    result = Result(seed, None, {}, [], 0, exponents=fit(pool))
    res.units = result
    fam = families(skills) if skills else None
    lo, hi = min(u.level for u in pool), max(u.level for u in pool)
    everywhere = {x for n in range(enc.count) for x in enc.enemies(n) if x}

    for (n, a), b in zip(res.places, order):
        A, B = units[a], units[b]
        res.mapping[n] = b
        rescale_unit(table, ai, B, A.level, A.karma, A.macca, result, fam, lo, hi)
        if hp == "place":                                    # HP of the old boss, the rest on the curve
            s = table.get(b)
            table.set(b, s.level, A.hp, s.mp, s.stats, s.karma, s.macca)
            result.scaled[b] = table.get(b, B.name)
        for x in sorted(_summoned(ai, b)):
            X = units[x]
            if _reserved(x, b, ai, everywhere - {x}):
                level = max(1, round(A.level * X.level / B.level))
                rescale_unit(table, ai, X, level, round(X.karma * A.karma / max(1, B.karma)),
                             round(X.macca * A.macca / max(1, B.macca)), result, fam, lo, hi)
                res.reinforcements.setdefault(b, []).append((x, level))
            else:                                            # shuffled species: proportional level
                target = max(1, round(A.level * X.level / B.level))
                dist = {y: abs(table.get(y).level - target) for y in sorted(pool_ids)}
                best = min(dist.values())
                y = rng.choice([y for y, d in dist.items() if d <= best + 1])
                p = own_script(ai, b)
                for k in p.summons:
                    if ai.flow.arg(k) == x:
                        ai.flow.set_arg(k, y)
                res.summons.setdefault(b, []).append((x, y))
        # same slot as the old boss (Camazotz 259 is in slot 1, not 0)
        enc.set_enemies(n, [b if x == a else x for x in enc.enemies(n)])
    if skills:
        for u in sorted(result.scaled):
            raise_mp(table, ai, u, skills, result)
    return res


def _uses(ai: AiTable, unit: int) -> set[int]:
    """Skills a unit can cast: its AI lists and its own script."""
    p = own_script(ai, unit)
    return set(actions(ai, unit)) | ({ai.flow.arg(k) for k in p.casts} if p else set())


def _k(s: Skill) -> float:
    base = s.element - 256 if s.element >= 256 else s.element      # 256 + element: special versions
    if s.nature == PERCENT:
        return UNIQUE_K["percent"]
    if base == 0:
        return UNIQUE_K["physical"]
    return UNIQUE_K["all" if s.target else "one"]


def unique_power(s: Skill, old_level: int, new_level: int) -> int:
    """Power of a unique skill whose boss moves from old_level to new_level. A percentage never goes
    up (it already grows with the target's HP)."""
    value = round(s.power * (new_level / old_level) ** _k(s))
    if s.nature == PERCENT:
        value = min(value, s.power)
    return max(1, min(value, 0xFFFF))


def scale_unique_skills(res: BossResult, skill_table: SkillTable, ai: AiTable, units: list[Unit],
                        skills: list[Skill], protected: set[int]) -> None:
    """Option unique_skills = "power". Modifies `skill_table` in place. A skill is rescaled only if it
    is a damage or percentage skill outside the adaptable families, cast by this boss and by no other
    unit, and absent from the mantras (`protected`: the party would be affected too)."""
    fam = families(skills)
    users: dict[int, set[int]] = {}
    for u in range(len(units)):
        for s in _uses(ai, u):
            users.setdefault(s, set()).add(u)
    for n, a in res.places:
        b = res.mapping.get(n)
        if b is None:
            continue
        old, new = units[b].level, units[a].level
        for s in sorted(_uses(ai, b)):
            if s >= len(skills) or s in fam or s in protected or users[s] != {b}:
                continue
            S = skills[s]
            if not S.name or S.nature not in (DAMAGE, PERCENT) or S.power <= 0:
                continue
            value = unique_power(S, old, new)
            skill_table.set_power(s, value)
            res.unique[s] = (b, S.power, value)


def spoiler(res: BossResult, units: list[Unit], table: UnitTable, skills: list[Skill] | None = None) -> str:
    lines = ["", f"Bosses: {len(res.mapping)} places shuffled"]
    for n, a in res.places:
        b = res.mapping.get(n)
        if b is None:
            continue
        s = table.get(b)
        line = (f"  encounter {n:3d}: {units[a].name:<14} (lv {units[a].level:2d}) -> {units[b].name:<14} "
                f"(lv {units[b].level:2d} → {s.level}, HP {units[b].hp} → {s.hp}, MP {s.mp})")
        if b in res.reinforcements:
            line += " | reinforcements " + ", ".join(f"{units[x].name} {x} lv {units[x].level} → {lv}"
                                                   for x, lv in res.reinforcements[b])
        if b in res.summons:
            line += " | summons " + ", ".join(f"{units[x].name} → {units[y].name}" for x, y in res.summons[b])
        lines.append(line)
    if res.unique and skills:
        lines.append("Unique skills (power follows the level of the new place):")
        for s, (b, p, v) in sorted(res.unique.items(), key=lambda x: (x[1][0], x[0])):
            unit = " %" if skills[s].nature == PERCENT else ""
            lines.append(f"  {skills[s].name:<14} {units[b].name:<12} power {p}{unit} → {v}{unit}")
    lines += ["Places left untouched:"] + [f"  encounter {n}: {why}" for n, why in EXCLUDED_ENCOUNTERS.items()]
    return "\n".join(lines) + "\n"
