"""Enemy affinities: shuffled or drawn, and the matching Analyze text.

UNIT.TBL block 4 (validated in game and against the Analyze texts, NOTES.md): 19 × u32 per
unit, column = SKILL.TBL element, u32 = flags (high 16 bits) + percentage.
The Analyze text (MSG.TBL block 2) is stored separately: it is rewritten on every change.

Values are only shuffled within groups: almost every demon nulls light or darkness; moving
those "null" flags onto physical would change the difficulty. Almighty (column 7, 100 % everywhere)
and column 15 (unknown) never move.
"""
import random
from collections import Counter

from .tables import AnalyzeText, UnitTable

NAMES = ("phys", "gun", "fire", "ice", "elec", "force", "earth", "almighty",
         "expel", "death", "charm", "poison", "mute", "panic", "nerve")
GROUPS = ((0, 1, 2, 3, 4, 5, 6), (8, 9), (10, 11, 12, 13, 14))   # damage, instant death, ailments
AILMENTS = GROUPS[2]
PHYS = 0
WEAK, NULL, REPEL, DRAIN = 0x8000_0000, 0x0001_0000, 0x0002_0000, 0x0004_0000
CATEGORIES = ("Strong", "Weak", "Repel", "Drain", "Null")          # order used by Atlus' texts
LINE_MAX = 62                                                     # 63 bytes including the \0


def category(value: int) -> str | None:
    if value & WEAK:
        return "Weak"
    if value & REPEL:
        return "Repel"
    if value & DRAIN:
        return "Drain"
    if value & NULL:
        return "Null"
    return "Strong" if (value & 0xFFFF) < 100 else None


def describe(values: list[int]) -> list[str]:
    """Analyze text in Atlus' format ("Strong: fire_Weak: ice/elec_Null: death"),
    split between two elements when a line would exceed 62 characters."""
    by_cat = {c: [] for c in CATEGORIES}
    for col, name in enumerate(NAMES):
        if col != 7 and (c := category(values[col])):
            by_cat[c].append(col)
    parts = []
    for c in CATEGORIES:
        cols = by_cat[c]
        if not cols:
            continue
        words = [NAMES[x] for x in cols if x not in AILMENTS]
        ail = [x for x in cols if x in AILMENTS]
        words += ["ailments"] if len(ail) == len(AILMENTS) else [NAMES[x] for x in ail]
        parts.append((c, words))
    lines, cur = [], ""
    for n, (c, words) in enumerate(parts):
        piece = ("_" if n else "") + f"{c}: "
        for k, w in enumerate(words):
            token = piece + w if k == 0 else "/" + w
            if len(cur) + len(token) > LINE_MAX:
                lines.append(cur)
                cur = token.lstrip("_/")
            else:
                cur += token
    if cur:
        lines.append(cur)
    return lines


def randomize_affinities(table: UnitTable, text: AnalyzeText, units: list[int], seed: int,
                         mode: str, protect_physical: bool = False) -> dict[int, tuple[list[str], list[str]]]:
    """Modifies `table` and `text` in place for each unit of `units`.
    Returns {unit: (text before, text after)}. Random stream independent from the enemy shuffle."""
    if mode == "original":
        return {}
    rng = random.Random(f"{seed}-affinites")        # stream name frozen: changing it would change every seed
    # value distribution of each group, measured on the units concerned
    dist = [Counter(table.affinities(u)[c] for u in units for c in g) for g in GROUPS]
    changes = {}
    for u in units:
        old = table.affinities(u)
        new = old[:]
        for gi, group in enumerate(GROUPS):
            if mode == "shuffle":
                values = [old[c] for c in group]
                rng.shuffle(values)
            else:  # "random"
                pool, weights = zip(*dist[gi].items())
                values = rng.choices(pool, weights, k=len(group))
            for c, v in zip(group, values):
                new[c] = v
        if protect_physical and new[PHYS] & (NULL | REPEL | DRAIN):
            # swap with a damage column without those flags, if there is one
            safe = [c for c in GROUPS[0] if not new[c] & (NULL | REPEL | DRAIN)]
            if safe:
                c = rng.choice(safe)
                new[PHYS], new[c] = new[c], new[PHYS]
        if new != old:
            before = text.lines(u)
            table.set_affinities(u, new)
            text.set_lines(u, describe(new))
            changes[u] = (before, text.lines(u))
    return changes
