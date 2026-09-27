"""Skill adaptation for a rescaled enemy.

A skill itself is never modified (it is shared by enemies, bosses and party members): in the enemy's
record, a skill is replaced by a member of the same family (element, cost, target, hits, nature,
effect).

Only families of damage spells (nature 1), percentage spells (nature 8) and instant-death spells
(nature 0, darkness, death effect 0x4000: Mudo < Mudoon, Mamudo < Mamudoon, ranked by the chance of the
effect, +0x25) with at least two members of different strength are adapted; the rest is kept.

Special versions (element 256 + base element, e.g. Maragidyne 434 cast by Isis, Queen Mab, the Oni): boosted
copies of a normal spell of the same name (cheaper, more accurate, doubled effect chance, sometimes more
power; NOTES "Special versions"). They take the rank of their normal version; when the rank changes they
become the normal member of the new rank (cast by ordinary enemies: animation guaranteed), only if the
direction holds against the special's own strength; same rank: the special version is kept. Nature 8 = removes a percentage of HP (🟡, game
texts: Hama 50 "Reduce HP by half", Hamaon 66 "Reduce HP greatly", Seraph Lore 80 "Greatly reduces
HP"): the power is that percentage, so the rank is in it.

"Rank from level" rule: the species' level range is cut into as many slices as the family has
members (sorted by power); an enemy moving down in level never moves up in rank, and conversely.
Measured on the 146 damage spells of the original species: this rule finds Atlus' choice in 53 % of
cases, against 29 % for "typical power ≈ c × level^k".
"""
from collections import defaultdict

from .tables import Skill

DAMAGE, PERCENT = 1, 8
DARK, DEATH = 9, 0x4000         # element; effect mask (u16 +0x26: cured by Recarm, like the other masks)


class Families(dict):
    """Skill id -> members of its family sorted by strength (adaptable families only). A special version
    maps to the family of its normal version without being a member; `special[id]` = (normal id, skill)."""

    def __init__(self) -> None:
        super().__init__()
        self.special: dict[int, tuple[int, Skill]] = {}


def families(skills: list[Skill]) -> Families:
    """Skill -> members of its family sorted by strength (adaptable families only)."""
    groups = defaultdict(list)
    for s in skills:
        if not s.name or s.element >= 255:
            continue
        if (s.nature in (DAMAGE, PERCENT) and s.power > 0) or \
                (s.nature == 0 and s.element == DARK and s.ailment == (1, DEATH) and s.chance > 0):
            groups[s.family].append(s)
    out = Families()
    for members in groups.values():
        if len({m.strength for m in members}) >= 2:
            members = sorted(members, key=lambda m: (m.strength, m.id))
            out.update({m.id: members for m in members})
    normal = {}
    for s in skills:
        if s.name and s.id in out:
            normal.setdefault((s.name, s.element), s)
    for s in skills:
        if s.name and 256 <= s.element < 512:
            n = normal.get((s.name, s.element - 256))
            if n and (n.nature, n.target) == (s.nature, s.target):
                out[s.id] = out[n.id]
                out.special[s.id] = (n.id, s)
    return out


def adapt(sid: int, from_level: int, to_level: int, fam: dict[int, list[Skill]], lo: int, hi: int) -> int:
    """Member of the family of `sid` matching level `to_level` (range lo–hi), never against the
    direction of the level change: an enemy moving down never gets a stronger spell (Atlus sometimes
    gives a spell below the level's rank), and conversely."""
    if sid not in fam or from_level == to_level:
        return sid
    members = fam[sid]
    n = len(members)
    special = getattr(fam, "special", {}).get(sid)
    key = special[0] if special else sid
    current = members.index(next(m for m in members if m.id == key))
    target = min(n - 1, max(0, int(n * (to_level - lo) / max(1, hi - lo))))
    down = to_level < from_level
    pos = min(target, current) if down else max(target, current)
    if special:
        new, s = members[pos], special[1]
        if pos == current or (new.strength > s.strength if down else new.strength < s.strength):
            return sid                          # same rank, or the normal version would go against the direction
    return members[pos].id


# --- Random skills "same type, same rank" ---
# Skills are only drawn among those at least one ordinary enemy uses in its original AI: they
# necessarily have an enemy-side animation (a party-only skill could freeze the game, like the
# Macha copy without a model).

WINDOW = 10          # tolerated gap between the skill's usage level and the enemy's level
# MP budget: 90 % of ordinary enemies have at least 8 × the cost of their most expensive spell
# (median 19 ×). Atlus' AI does not check MP: without this budget, an enemy wastes its turns on
# "Insufficient MP" (seen in game, v2.4).
MP_FACTOR = 8
MP_MAX = 32767


def skill_class(s: Skill) -> tuple[str, int, int] | None:
    """Type of a skill (category, target, cost type); None = cannot be drawn (special skills,
    passives…). The cost type is kept: an HP-cost technique never becomes an MP spell (an enemy
    with little MP could no longer act)."""
    if s.element <= 7 and s.nature == DAMAGE:
        cat = "damage"
    elif s.element in (8, 9):
        cat = "death"
    elif 10 <= s.element <= 14:
        cat = "ailment"
    elif s.element == 16:
        cat = "heal"
    elif s.element == 17:
        cat = "support"
    else:
        return None
    return cat, s.target, s.cost_type


def mp_needed(skill_ids: list[int], skills: list[Skill]) -> int:
    """Minimum MP to cast the most expensive spell MP_FACTOR times (0 if no MP spell)."""
    costs = [skills[s].cost for s in skill_ids if 0 < s < len(skills) and skills[s].cost_type == 2]
    return min(MP_MAX, MP_FACTOR * max(costs)) if costs else 0


def usage_levels(units, ai, skills: list[Skill]) -> dict[int, float]:
    """Skill -> median level of the ordinary enemies using it in their AI."""
    levels = defaultdict(list)
    for u in units:
        if u.name and not u.name.startswith(("Reserve", "(Reserve")) and u.level < 99:
            for _l, _k, _p, act in ai.entries(u.id):
                if 0 < act < len(skills) and skills[act].name:
                    levels[act].append(u.level)
    return {s: sorted(v)[len(v) // 2] for s, v in levels.items()}


def random_skill_map(unit_skills: list[int], level: int, usage: dict[int, float],
                     skills: list[Skill], rng) -> dict[int, int]:
    """Replacement {old: new} for the drawable skills of a unit."""
    mapping, taken = {}, set()
    for sid in unit_skills:
        if sid in mapping or not (0 < sid < len(skills)) or sid not in usage:
            continue
        cls = skill_class(skills[sid])
        if cls is None:
            continue
        same = [s for s in usage if skill_class(skills[s]) == cls and s not in taken]
        window = WINDOW
        near = [s for s in same if abs(usage[s] - level) <= window]
        while not near and same:
            window *= 2
            near = [s for s in same if abs(usage[s] - level) <= window]
        if near:
            new = rng.choice(sorted(near))
            mapping[sid] = new
            taken.add(new)
    return mapping
