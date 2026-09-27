"""Shuffle of the enemies of random battles, with optional rescaling.

Principle: a species A becomes a species B everywhere (like the Nocturne randomizer). The zones
(ENCOUNT.TBL block 2) tell which encounters are active random battles.

"Noisy sort" shuffle: species are sorted by level, then by level + uniform noise in
[-spread, +spread], and the species of rank i in the first order is replaced by the species of
rank i in the second. The level gap between A and B never exceeds 2 × spread (+ the largest level
gap between two neighbouring species when identity is forbidden).

Rescaling: a species that appears nowhere but in random battles (active or unused) may have its
record rewritten at the level of the species it replaces, without affecting scripted battles.
These species are shuffled freely among themselves; the others keep the spread constraint.

Skills: a replacement (old -> new) is applied to the record (Analyze), to the AI lists and to the
unit's AI script if it has one (skills cast directly and "do I have this skill" checks). A script
shared with a unit outside the shuffle is detached (the unit then follows its lists). Units summoned
by a script are replaced by a shuffled species of a level proportional to the summoner's.
"""
import random
from dataclasses import dataclass, field

from .flowscript import Procedure
from .options import Enemies
from .scaling import Exponents, fit, scale
from .skills import adapt, families, mp_needed, random_skill_map, usage_levels
from .tables import AiTable, Encounters, Skill, Unit, UnitTable

# Excluded zones: Omoikane alone (level 99, 999 MP), special encounters (NOTES.md §4 bis).
EXCLUDED_ZONES = frozenset({47, 48, 49, 50, 51, 52, 53, 72})

# Ranges of ordinary random encounters (+0x00 = 0). 255: units 94–97 (level 1,
# 300–600 HP, 999 MP); 256–383: scripted battles and bosses; 768+: special.
RANDOM_RANGES = (range(0, 255), range(512, 768))

# Species left in place, with the reason.
EXCLUDED_UNITS = {
    57: "Pixie level 1 (300 HP) in zones of median level 35: special encounter?",
    325: "Pixie level 1 (777 HP) in zones of median level 56: special encounter?",
}
MAX_LEVEL = 99      # level 99 = placeholder records (32767 HP) or Omoikane
FREE = 1000         # "infinite" spread: free shuffle of the rescaled species


@dataclass
class Result:
    seed: int
    options: Enemies
    mapping: dict[int, int]                         # original species -> replacement
    encounters: list[int]                           # encounters that may be modified
    changed: int                                    # encounters actually modified
    scaled: dict[int, Unit] = field(default_factory=dict)   # replacement -> new record
    exponents: Exponents | None = None
    skill_changes: dict[int, list[tuple[int, int]]] = field(default_factory=dict)  # replacement -> [(old, new)]
    ai_skill_changes: dict[int, dict[int, int]] = field(default_factory=dict)   # unit -> {old: new} (AI lists, script)
    ai_changes: int = 0                                     # AI actions replaced
    mp_raised: dict[int, tuple[int, int]] = field(default_factory=dict)  # unit -> (MP before, after)
    script_changes: int = 0                                 # script arguments rewritten (casts, checks)
    detached: list[int] = field(default_factory=list)       # units whose shared script was detached
    summons: dict[int, list[tuple[int, int]]] = field(default_factory=dict)  # summoner -> [(old, new)]


def _in_ranges(n: int) -> bool:
    return any(n in r for r in RANDOM_RANGES)


def random_encounters(enc: Encounters) -> list[int]:
    """Encounters listed by a non-excluded zone, in the ordinary ranges, flag 0."""
    cited = {e for z in range(enc.zone_count) if z not in EXCLUDED_ZONES
             for lst in enc.zone_lists(z) for e, _w in lst}
    return sorted(e for e in cited if _in_ranges(e) and enc.flag(e) == 0)


def species_pool(enc: Encounters, encounters: list[int], units: list[Unit]) -> list[Unit]:
    ids = {x for e in encounters for x in enc.enemies(e) if x}
    return [units[i] for i in sorted(ids)
            if i not in EXCLUDED_UNITS and units[i].name and units[i].level < MAX_LEVEL]


def scalable(enc: Encounters, pool: list[Unit]) -> set[int]:
    """Species absent from scripted (256–383) and special (768+) battles and from encounter 255:
    rewriting their record only affects random battles (active or never used)."""
    elsewhere = {x for n in range(enc.count) if not (_in_ranges(n) and enc.flag(n) == 0)
                 for x in enc.enemies(n) if x}
    return {u.id for u in pool if u.id not in elsewhere}


def build_mapping(pool: list[Unit], rng: random.Random, spread: float,
                  no_identity: bool = True) -> dict[int, int]:
    ordered = sorted(pool, key=lambda u: (u.level, u.id))
    noise = {u.id: u.level + rng.uniform(-spread, spread) for u in ordered}
    noisy = sorted(pool, key=lambda u: (noise[u.id], u.id))
    if no_identity and len(pool) > 1:
        # A species that landed on itself swaps its replacement with its neighbour
        # (next rank, or previous for the last one). No new fixed point can appear:
        # noisy is a permutation of ordered.
        for i in range(len(noisy)):
            if noisy[i] is ordered[i]:
                j = i + 1 if i + 1 < len(noisy) else i - 1
                noisy[i], noisy[j] = noisy[j], noisy[i]
    return {a.id: b.id for a, b in zip(ordered, noisy)}


def randomize(enc: Encounters, table: UnitTable, units: list[Unit], seed: int,
              opts: Enemies | None = None, skills: list[Skill] | None = None,
              ai: AiTable | None = None, skill_mode: str = "adapt") -> Result:
    """Modifies `enc` (encounters), `table` (records) and `ai` (AI) in place.
    If `skills` is given: skill_mode "adapt" = damage spells of rescaled species brought to their rank;
    "random" = skills of every shuffled species drawn at random (same type, same rank). Always in the
    record (Analyze) AND in the AI (what is actually cast)."""
    opts = opts or Enemies()
    rng = random.Random(seed)
    encounters = random_encounters(enc)
    result = Result(seed, opts, {}, encounters, 0)
    if not opts.shuffle:
        return result

    pool = species_pool(enc, encounters, units)
    pool_ids = {u.id for u in pool}
    no_identity = not opts.allow_identity
    if opts.scaling:
        free = scalable(enc, pool)
        result.mapping = build_mapping([u for u in pool if u.id in free], rng, FREE, no_identity)
        result.mapping |= build_mapping([u for u in pool if u.id not in free], rng, opts.level_spread, no_identity)
        result.exponents = fit(pool)
        fam = families(skills) if skills else {}
        lo, hi = min(u.level for u in pool), max(u.level for u in pool)
        for a, b in result.mapping.items():
            if a in free:
                A = units[a]
                rescale_unit(table, ai, units[b], A.level, A.karma, A.macca, result,
                             fam if skill_mode == "adapt" else None, lo, hi, pool_ids)
    else:
        result.mapping = build_mapping(pool, rng, opts.level_spread, no_identity)

    if skills and ai and skill_mode == "random":
        _random_skills(result, table, ai, units, pool, skills, seed)
    if ai and result.scaled:
        _summons(result, table, ai, units, pool, seed)
    if skills:
        # MP budget for every record we rewrote (level or skills)
        for u in sorted(set(result.scaled) | set(result.skill_changes)):
            raise_mp(table, ai, u, skills, result, pool_ids)

    for e in encounters:
        old = enc.enemies(e)
        new = [result.mapping.get(x, x) for x in old]
        if new != old:
            enc.set_enemies(e, new)
            result.changed += 1
    return result


def own_script(ai: AiTable, unit: int, allowed: set[int] | None = None) -> Procedure | None:
    """The unit's script if it casts or summons and is only run by units of `allowed` (default: the
    unit alone). A script shared with another unit must not be rewritten for this one (e.g. AI_Zin:
    shuffled Jinn 48 and Jinn 338 of a scripted battle)."""
    proc = ai.script(unit)
    if not proc:
        return None
    p = ai.flow.procedures[proc]
    users = ai.script_users()[proc]
    return p if set(users) <= ((allowed or set()) | {unit}) else None


def actions(ai: AiTable, unit: int, allowed: set[int] | None = None) -> list[int]:
    """Actions the unit can use: AI lists + skills cast by its own script."""
    acts = [a for *_x, a in ai.entries(unit)]
    if p := own_script(ai, unit, allowed):
        acts += [ai.flow.arg(k) for k in p.casts]
    return acts


def rewrite_skills(table: UnitTable, ai: AiTable | None, unit: int, f, result: Result,
                   allowed: set[int] | None = None) -> list[tuple[int, int]]:
    """Applies the skill replacement `f` (old -> new) to the record, the AI lists and the unit's
    script. Returns the record changes [(old, new)]."""
    old = table.skills(unit)
    new = [f(s) for s in old]
    if new != old:
        table.set_skills(unit, new)
    if ai is None:
        return [(x, y) for x, y in zip(old, new) if x != y]
    seen = result.ai_skill_changes.setdefault(unit, {})
    for l, k, _prob, action in ai.entries(unit):
        if (adapted := f(action)) != action:
            ai.set_action(unit, l, k, adapted)
            result.ai_changes += 1
            seen[action] = adapted
    proc = ai.script(unit)
    if proc and (p := own_script(ai, unit, allowed)):
        # several shuffled units share this script (AllEscape_MeriBeru: no casts):
        # the first rewrite wins, the next ones find already replaced skills
        for k in p.casts + p.checks:
            if (adapted := f(ai.flow.arg(k))) != ai.flow.arg(k):
                seen[ai.flow.arg(k)] = adapted
                ai.flow.set_arg(k, adapted)
                result.script_changes += 1
    elif proc and (ai.flow.procedures[proc].casts or ai.flow.procedures[proc].summons):
        ai.set_script(unit, 0)
        result.detached.append(unit)
    if not seen:
        del result.ai_skill_changes[unit]
    return [(x, y) for x, y in zip(old, new) if x != y]


def skill_changes_text(result: Result, unit: int, skills: list[Skill]) -> str:
    """Record changes (what Analyze shows), then AI-only changes (lists, script). * = special version."""
    def name(i: int) -> str:
        return skills[i].name + ("*" if skills[i].element >= 256 else "") if i < len(skills) else hex(i)
    record = result.skill_changes.get(unit, [])
    parts = [", ".join(f"{name(x)} → {name(y)}" for x, y in record)] if record else []
    done = set(record)
    ai_only = [(x, y) for x, y in sorted(result.ai_skill_changes.get(unit, {}).items()) if (x, y) not in done]
    if ai_only:
        parts.append("AI: " + ", ".join(f"{name(x)} → {name(y)}" for x, y in ai_only))
    return "  | ".join(parts)


def rescale_unit(table: UnitTable, ai: AiTable | None, unit: Unit, level: int, karma: int, macca: int,
                 result: Result, fam: dict | None = None, lo: int = 0, hi: int = 0,
                 allowed: set[int] | None = None) -> None:
    """Rewrites the record of `unit` at level `level` (HP/MP/stats ≈ c × level^k, given rewards);
    if `fam` is given, its damage spells are brought to their rank (record, AI lists, script).
    `unit` = original record (starting level of the rescaling)."""
    hp, mp, stats = scale(unit, level, result.exponents)
    table.set(unit.id, level, hp, mp, stats, karma, macca)
    result.scaled[unit.id] = table.get(unit.id, unit.name)
    if fam:
        changes = rewrite_skills(table, ai, unit.id, lambda s: adapt(s, unit.level, level, fam, lo, hi),
                                 result, allowed)
        if changes:
            result.skill_changes[unit.id] = changes


def raise_mp(table: UnitTable, ai: AiTable | None, unit: int, skills: list[Skill], result: Result,
             allowed: set[int] | None = None) -> None:
    """MP budget: enough to cast the most expensive spell MP_FACTOR times (record, lists, script)."""
    cur = table.get(unit)
    need = mp_needed(table.skills(unit) + (actions(ai, unit, allowed) if ai else []), skills)
    if cur.mp < need:
        table.set(unit, cur.level, cur.hp, need, cur.stats, cur.karma, cur.macca)
        result.mp_raised[unit] = (cur.mp, need)


def _summons(result: Result, table: UnitTable, ai: AiTable, units: list[Unit], pool: list[Unit],
             seed: int) -> None:
    """Units summoned by the script of a shuffled species: if the summoned unit is itself a shuffled
    species (other than the summoner), it is replaced by a species of level
    summoner_level × summoned_level / summoner_level (original levels), picked among the closest.
    E.g. Hanuman (level 48) summons Sati (45) and Purski (42); rescaled to level 10, it summons ~9."""
    rng = random.Random(f"{seed}-invocations")      # stream name frozen: changing it would change every seed
    pool_ids = {u.id for u in pool}
    for u in sorted(pool_ids):
        p = own_script(ai, u, pool_ids)
        if p is None or not p.summons:
            continue
        level = table.get(u).level
        for k in p.summons:
            x = ai.flow.arg(k)
            if x == u or x not in pool_ids:
                continue
            target = max(1, round(level * units[x].level / units[u].level))
            dist = {y: abs(table.get(y).level - target) for y in sorted(pool_ids) if y != u}
            best = min(dist.values())
            y = rng.choice([y for y, d in dist.items() if d <= best + 1])
            ai.flow.set_arg(k, y)
            result.summons.setdefault(u, []).append((x, y))


def _random_skills(result: Result, table: UnitTable, ai: AiTable, units: list[Unit],
                   pool: list[Unit], skills: list[Skill], seed: int) -> None:
    """Random skills for every shuffled species, at the level it has in game.
    Separate random stream: enemy placement does not depend on this option."""
    rng = random.Random(f"{seed}-competences")      # stream name frozen: changing it would change every seed
    usage = usage_levels(units, ai, skills)
    pool_ids = {u.id for u in pool}
    for u in sorted(pool, key=lambda x: x.id):
        level = table.get(u.id).level                    # level after any rescaling
        mapping = random_skill_map(table.skills(u.id) + actions(ai, u.id, pool_ids), level, usage, skills, rng)
        if mapping:
            rewrite_skills(table, ai, u.id, lambda s: mapping.get(s, s), result, pool_ids)
            result.skill_changes[u.id] = sorted(mapping.items())


def spoiler(result: Result, units: list[Unit], skills: list[Skill] | None = None,
            options_text: str | None = None) -> str:
    def label(i: int) -> str:
        u = units[i]
        return f"{u.name:<16} (id {i:3d}, lv {u.level:2d})"

    options_text = options_text or "\n".join(f"  enemies.{k} = {v}" for k, v in vars(result.options).items())
    lines = [f"DDS1 Randomizer — seed {result.seed}", "Options:", options_text,
        f"{len(result.mapping)} species shuffled ({len(result.scaled)} rescaled), "
        f"{result.changed} encounters modified out of {len(result.encounters)} random battles", ""]
    if result.exponents:
        e = result.exponents
        lines.append("Measured exponents (value ≈ c × level^k): HP %.2f, MP %.2f, " % (e.hp, e.mp)
                     + ", ".join(f"{s} {k:.2f}" for s, k in zip(("St", "Vi", "Ma", "Ag", "Lu"), e.stats)))
        lines.append("")
    lines.append("Skills: record changes (shown by Analyze), then \"AI:\" = changes only in the AI lists or script;"
                 " * = special (boosted) version of a spell")
    lines.append("Original species                    -> Replacement                           Δlv   Rescaling")
    for a in sorted(result.mapping, key=lambda i: (units[i].level, i)):
        b = result.mapping[a]
        line = f"{label(a)} -> {label(b)}  {units[b].level - units[a].level:+3d}"
        if b in result.scaled:
            s = result.scaled[b]
            line += f"  -> lv {s.level}, HP {s.hp}, MP {s.mp}, stats {'/'.join(map(str, s.stats))}"
        if b in result.mp_raised:
            line += "  | MP %d → %d" % result.mp_raised[b]
        if skills and (text := skill_changes_text(result, b, skills)):
            line += "  | " + text
        lines.append(line)
    lines += ["", f"AI scripts: {result.script_changes} arguments rewritten (cast skills, skill checks)"]
    lines += [f"  {label(u)}: script shared with a scripted battle, detached (follows its AI lists)"
              for u in result.detached]
    for u, pairs in sorted(result.summons.items()):
        lines.append(f"  {label(u)} summons: " + ", ".join(f"{units[x].name} → {units[y].name}" for x, y in pairs))
    lines += ["", "Species left in place:"]
    lines += [f"  {label(i)}: {why}" for i, why in EXCLUDED_UNITS.items()]
    return "\n".join(lines) + "\n"
