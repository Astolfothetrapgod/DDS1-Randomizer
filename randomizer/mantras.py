"""Mantras (the party's skills): table of the executable SLUS_209.74.

Format (NOTES "Mantras"):
- names: MSG.TBL block 1, 98 slots of 19 bytes (1 Devourer … 88 Earth Temple, 89–97 Reserve);
- table: ELF at 0x2917B4 (RAM 0x3907B4, loaded as is), 98 entries of 28 bytes, same order:
  +0x00 u8 ✅ difficulty (stars), +0x01 u8 ❓ (equal to +0x00 except King: 5 / 9),
  +0x02 u16 🟡 required level, +0x04 u32 ✅ AP to earn (❌ not the price: the price is in another table),
  +0x08 10 × u16 skills (0 = empty; ids of MSG.TBL block 7; 512–601 = passives).
✅ skills checked on 4 mantras noted in game; ✅ shuffle validated in game (mantra test 4: a shuffled
mantra, once mastered, teaches its new skills).
"""
import random
import struct
from dataclasses import dataclass

ELF = "SLUS_209.74"
MANTRA_TABLE, MANTRA_SIZE, N_MANTRAS, N_MANTRA_SKILLS = 0x2917B4, 28, 98, 10
MSG_MANTRA_NAMES, NAME_SIZE = 1, 19
# Safety check: (difficulty, required level) of known entries, never touched by the shuffle
# (otherwise this is not the right executable): Devourer, Demon Beast, Ice Demon, Destroyer, Godly Spirit
KNOWN = {1: (1, 1), 2: (2, 15), 26: (2, 5), 19: (8, 55), 78: (9, 60)}


@dataclass
class Mantra:
    id: int
    name: str
    difficulty: int
    b: int          # ❓
    level: int      # 🟡 required level
    ap: int         # ✅ AP to earn
    skills: list[int]


class MantraTable:
    """Mantra table in the executable (bytearray of the same size as the original)."""

    FIELDS = {"difficulty": (0, "<B"), "b": (1, "<B"), "level": (2, "<H"), "ap": (4, "<I")}

    def __init__(self, elf: bytes, names: list[str] | None = None):
        self.data = bytearray(elf)
        self.names = names or [""] * N_MANTRAS
        for m, (difficulty, level) in KNOWN.items():
            if (self.get(m).difficulty, self.get(m).level) != (difficulty, level):
                raise ValueError("mantra table not found: unexpected executable")
        if any(self.data[self._pos(96):self._pos(N_MANTRAS)]):
            raise ValueError("mantra table not found: entries 96–97 are not empty")

    def _pos(self, m: int) -> int:
        return MANTRA_TABLE + m * MANTRA_SIZE

    def get(self, m: int) -> Mantra:
        difficulty, b, level, ap = struct.unpack_from("<BBHI", self.data, self._pos(m))
        skills = [s for s in struct.unpack_from(f"<{N_MANTRA_SKILLS}H", self.data, self._pos(m) + 8) if s]
        return Mantra(m, self.names[m] if m < len(self.names) else "", difficulty, b, level, ap, skills)

    def set_skills(self, m: int, skills: list[int]) -> None:
        if len(skills) > N_MANTRA_SKILLS:
            raise ValueError(f"at most {N_MANTRA_SKILLS} skills per mantra")
        padded = skills + [0] * (N_MANTRA_SKILLS - len(skills))
        struct.pack_into(f"<{N_MANTRA_SKILLS}H", self.data, self._pos(m) + 8, *padded)

    def set_field(self, m: int, field: str, value: int) -> None:
        off, fmt = self.FIELDS[field]
        struct.pack_into(fmt, self.data, self._pos(m) + off, value)


def read_mantra_names(msg: bytes) -> list[str]:
    from .tables import tbl_blocks
    off, size = tbl_blocks(msg)[MSG_MANTRA_NAMES]
    return [msg[off + k:off + k + NAME_SIZE].split(b"\0")[0].decode("ascii", "replace")
            for k in range(0, size, NAME_SIZE)]


# --- Mantra skill shuffle ---
# Shuffled mantras: 1–88 (89–97 = Reserve). Godly Spirit (78) is handled separately by the code
# (0x253100 compares the id with 0x4E): left in place to be safe.
SHUFFLED = [m for m in range(1, 89) if m != 78]
HEAL, GROUP_HEAL = "Dia", "Media"
GROUP_HEAL_MAX_LEVEL = 15


@dataclass
class MantraResult:
    mode: str
    before: dict[int, list[int]]
    after: dict[int, list[int]]
    moved_for_guarantee: list[str]


def _slots(table: MantraTable) -> list[tuple[int, int]]:
    """(mantra, rank within the mantra) of every shufflable skill."""
    return [(m, k) for m in SHUFFLED for k in range(len(table.get(m).skills))]


def _fix_duplicates(assign: dict, slots: list, rng) -> None:
    """A skill cannot appear twice in a mantra (Agi is in two mantras): swap with another place
    until no duplicate remains."""
    for _ in range(1000):
        seen, dup = {}, None
        for s in slots:
            key = (s[0], assign[s])
            if key in seen:
                dup = s
                break
            seen[key] = s
        if dup is None:
            return
        i = slots.index(dup)
        j = (i + rng.randrange(1, len(slots))) % len(slots)
        assign[slots[i]], assign[slots[j]] = assign[slots[j]], assign[slots[i]]
    raise RuntimeError("duplicates could not be resolved")


def _guarantee(table: MantraTable, assign: dict, slots: list, skill: int, max_level: int, rng,
               locked: set[int]) -> bool:
    """Puts `skill` in a mantra of required level ≤ max_level (swap with a skill of such a mantra,
    never with an already guaranteed skill of `locked`). True if it had to be moved."""
    where = next(s for s in slots if assign[s] == skill)
    if table.get(where[0]).level <= max_level:
        return False
    targets = [s for s in slots if table.get(s[0]).level <= max_level and assign[s] not in locked
               and skill not in {assign[t] for t in slots if t[0] == s[0]}
               and assign[s] not in {assign[t] for t in slots if t[0] == where[0]}]
    t = rng.choice(targets)
    assign[where], assign[t] = assign[t], assign[where]
    return True


def randomize_mantras(table: MantraTable, skill_names: list[str], seed: int, mode: str = "tiered",
                      level_spread: float = 5, guarantee_heal: bool = True,
                      guarantee_group_heal: bool = True) -> MantraResult:
    """Redistributes the mantras' skills (number of skills, price, AP, level and place of each mantra
    unchanged). "tiered": noisy sort on the required level (±level_spread, like the enemies);
    "random": anywhere; "original": nothing. Modifies `table` in place."""
    rng = random.Random(f"{seed}-mantras")
    before = {m: table.get(m).skills for m in SHUFFLED}
    res = MantraResult(mode, before, dict(before), [])
    if mode == "original":
        return res
    slots = _slots(table)
    skills = [before[m][k] for m, k in slots]
    if mode == "tiered":
        level = {s: table.get(s[0]).level for s in slots}
        noisy = sorted(range(len(slots)), key=lambda i: level[slots[i]] + rng.uniform(-level_spread, level_spread))
        order = sorted(range(len(slots)), key=lambda i: level[slots[i]])
        assign = {slots[o]: skills[n] for o, n in zip(order, noisy)}
    elif mode == "random":
        rng.shuffle(skills)
        assign = dict(zip(slots, skills))
    else:
        raise ValueError(f"unknown mantra mode: {mode!r}")
    _fix_duplicates(assign, slots, rng)
    by_name = {skill_names[x]: x for x in set(skills)}
    locked: set[int] = set()
    for wanted, name, max_level in ((guarantee_heal, HEAL, 1), (guarantee_group_heal, GROUP_HEAL, GROUP_HEAL_MAX_LEVEL)):
        if wanted and name in by_name:
            if _guarantee(table, assign, slots, by_name[name], max_level, rng, locked):
                res.moved_for_guarantee.append(name)
            locked.add(by_name[name])
    for m in SHUFFLED:
        new = [assign[(m, k)] for k in range(len(before[m]))]
        table.set_skills(m, new)
        res.after[m] = new
    return res


def spoiler(res: MantraResult, table: MantraTable, skill_names: list[str]) -> str:
    lines = ["", f"Mantras ({res.mode}):"]
    if res.moved_for_guarantee:
        lines.append("  guarantees applied: " + ", ".join(res.moved_for_guarantee))
    for m in sorted(res.after, key=lambda m: (table.get(m).level, m)):
        t = table.get(m)
        lines.append(f"  {t.name:<14} lv {t.level:2d}: " + ", ".join(skill_names[x] for x in res.after[m])
                     + "   (was: " + ", ".join(skill_names[x] for x in res.before[m]) + ")")
    return "\n".join(lines) + "\n"
