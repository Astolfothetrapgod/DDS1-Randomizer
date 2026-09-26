"""Reading and writing the battle/*.TBL tables. Validated formats: NOTES.md §3 to §5."""
import struct
from dataclasses import dataclass

from .flowscript import FlowScript


def tbl_blocks(data: bytes) -> list[tuple[int, int]]:
    """.TBL container: sequence of (u32 size + data), aligned on 16.
    Returns (data offset, size) of each block."""
    pos, blocks = 0, []
    while pos + 4 <= len(data):
        size = struct.unpack_from("<I", data, pos)[0]
        blocks.append((pos + 4, size))
        pos = (pos + 4 + size + 15) // 16 * 16
    return blocks


# --- MSG.TBL: names (ASCII, fixed-size slots) ---

MSG_UNIT_NAMES = (3, 17)   # (block, slot size); index = unit id


def read_names(msg: bytes, block: int, size: int) -> list[str]:
    off, length = tbl_blocks(msg)[block]
    names = []
    for k in range(length // size):
        text = msg[off + k * size:off + (k + 1) * size].split(b"\0")[0].decode("ascii")
        names.append("" if text == "Reserved" or text.startswith("0x") else text)
    return names


# MSG.TBL block 2: Analyze text, 3 lines of 63 bytes per unit (line 1 = affinities)
MSG_ANALYZE_BLOCK, ANALYZE_LINE, ANALYZE_LINES = 2, 63, 3


class AnalyzeText:
    """Editable Analyze text (whole MSG.TBL in memory)."""

    def __init__(self, data: bytes):
        self.data = bytearray(data)
        self._off, _ = tbl_blocks(self.data)[MSG_ANALYZE_BLOCK]

    def _pos(self, unit: int, line: int) -> int:
        return self._off + (unit * ANALYZE_LINES + line) * ANALYZE_LINE

    def lines(self, unit: int) -> list[str]:
        return [bytes(self.data[self._pos(unit, k):self._pos(unit, k) + ANALYZE_LINE]).split(b"\0")[0]
                .decode("ascii") for k in range(ANALYZE_LINES)]

    def set_lines(self, unit: int, lines: list[str]) -> None:
        if len(lines) > ANALYZE_LINES or any(len(t) >= ANALYZE_LINE for t in lines):
            raise ValueError(f"Analyze text too long: {lines}")
        for k in range(ANALYZE_LINES):
            text = lines[k].encode("ascii") if k < len(lines) else b""
            p = self._pos(unit, k)
            self.data[p:p + ANALYZE_LINE] = text.ljust(ANALYZE_LINE, b"\0")


# --- UNIT.TBL block 3: unit records, 384 × 0x4C ---

UNIT_BLOCK, UNIT_SIZE = 3, 0x4C
# Fields validated in game (NOTES.md §3): offset in the record
OFF_LEVEL, OFF_HP, OFF_HP_MAX, OFF_MP, OFF_MP_MAX = 0x05, 0x06, 0x08, 0x0A, 0x0C
OFF_STATS = 0x10                     # 5 × u8 : St, Vi, Ma, Ag, Lu
OFF_MACCA, OFF_KARMA = 0x28, 0x2C    # u32 base Macca, u16 Karma
OFF_SKILLS, N_SKILLS = 0x18, 8       # 8 × u16: skills (0 = empty)
OFF_SPECIAL = 0x16                   # u8: 0xFF = special unit (boss, NPC…)
AFFINITY_BLOCK, N_AFFINITIES = 4, 19 # column = SKILL.TBL element (NOTES.md, "UNIT.TBL block 4")
STATS = ("St", "Vi", "Ma", "Ag", "Lu")


@dataclass(frozen=True)
class Unit:
    id: int
    name: str
    level: int
    hp: int
    mp: int
    stats: tuple[int, ...] = (0, 0, 0, 0, 0)
    karma: int = 0
    macca: int = 0


class UnitTable:
    """Editable UNIT.TBL in memory; records of block 3 (384 × 0x4C)."""

    def __init__(self, data: bytes):
        self.data = bytearray(data)
        blocks = tbl_blocks(self.data)
        self._off, length = blocks[UNIT_BLOCK]
        self._aff, _ = blocks[AFFINITY_BLOCK]
        self.count = length // UNIT_SIZE

    def _e(self, i: int) -> int:
        return self._off + i * UNIT_SIZE

    def special(self, i: int) -> int:
        """+0x16: 0xFF = special unit (boss, NPC, reserved copies); 0 = ordinary enemy."""
        return self.data[self._e(i) + OFF_SPECIAL]

    def get(self, i: int, name: str = "") -> Unit:
        e = self._e(i)
        return Unit(i, name, self.data[e + OFF_LEVEL],
                    struct.unpack_from("<H", self.data, e + OFF_HP)[0],
                    struct.unpack_from("<H", self.data, e + OFF_MP)[0],
                    tuple(self.data[e + OFF_STATS:e + OFF_STATS + 5]),
                    struct.unpack_from("<H", self.data, e + OFF_KARMA)[0],
                    struct.unpack_from("<I", self.data, e + OFF_MACCA)[0])

    def set(self, i: int, level: int, hp: int, mp: int, stats: tuple[int, ...], karma: int, macca: int) -> None:
        """Rewrites level, HP and max HP, MP and max MP, stats, Karma, Macca."""
        e = self._e(i)
        self.data[e + OFF_LEVEL] = level
        struct.pack_into("<HH", self.data, e + OFF_HP, hp, hp)
        struct.pack_into("<HH", self.data, e + OFF_MP, mp, mp)
        self.data[e + OFF_STATS:e + OFF_STATS + 5] = bytes(stats)
        struct.pack_into("<H", self.data, e + OFF_KARMA, karma)
        struct.pack_into("<I", self.data, e + OFF_MACCA, macca)

    # --- block 4: affinities, 19 × u32 per unit (flags in the high 16 bits + percentage in the low 16) ---

    def affinities(self, i: int) -> list[int]:
        off = self._aff + i * UNIT_SIZE
        return list(struct.unpack_from(f"<{N_AFFINITIES}I", self.data, off))

    def set_affinities(self, i: int, values: list[int]) -> None:
        struct.pack_into(f"<{N_AFFINITIES}I", self.data, self._aff + i * UNIT_SIZE, *values)

    def skills(self, i: int) -> list[int]:
        return list(struct.unpack_from(f"<{N_SKILLS}H", self.data, self._e(i) + OFF_SKILLS))

    def set_skills(self, i: int, skills: list[int]) -> None:
        struct.pack_into(f"<{N_SKILLS}H", self.data, self._e(i) + OFF_SKILLS, *skills)


def read_units(unit_tbl: bytes, msg_tbl: bytes) -> list[Unit]:
    table = UnitTable(unit_tbl)
    names = read_names(msg_tbl, *MSG_UNIT_NAMES)
    return [table.get(i, names[i]) for i in range(table.count)]


# --- SKILL.TBL: block 0 = element/category (u16), block 1 = records 512 × 0x38 (NOTES.md §5 bis) ---

MSG_SKILL_NAMES = (7, 17)
SKILL_ELEM_BLOCK, SKILL_BLOCK, SKILL_SIZE = 0, 1, 0x38


@dataclass(frozen=True)
class Skill:
    id: int
    name: str
    element: int        # 0 physical, 2 fire, 3 ice…; >= 255: items, variants, passives
    cost_type: int      # 2 = MP, 1 = % of max HP
    cost: int
    target: int         # 0 = one, 1 = all
    hits: tuple[int, int]
    nature: int         # 1 = damage, 8 = removes a percentage of HP (Hama family), 0 = ailment only
    power: int
    ailment: tuple[int, int]   # (active, mask); the chance is not part of the family

    @property
    def family(self) -> tuple:
        return (self.element, self.cost_type, self.target, self.hits, self.nature, self.ailment)


def read_skill_names(msg_tbl: bytes) -> list[str]:
    """Names of the 624 skills (MSG.TBL block 7), including the party's passives (512–601)."""
    return read_names(msg_tbl, *MSG_SKILL_NAMES)


def read_skills(skill_tbl: bytes, msg_tbl: bytes) -> list[Skill]:
    blocks = tbl_blocks(skill_tbl)
    elem_off, _ = blocks[SKILL_ELEM_BLOCK]
    off, length = blocks[SKILL_BLOCK]
    names = read_names(msg_tbl, *MSG_SKILL_NAMES)
    skills = []
    for i in range(length // SKILL_SIZE):
        e = off + i * SKILL_SIZE
        d = skill_tbl
        skills.append(Skill(i, names[i] if i < len(names) else "",
                            struct.unpack_from("<H", d, elem_off + 2 * i)[0],
                            d[e + 0x03], d[e + 0x04], d[e + 0x08], (d[e + 0x14], d[e + 0x15]), d[e + 0x16],
                            struct.unpack_from("<H", d, e + 0x18)[0], (d[e + 0x24], d[e + 0x26])))
    return skills


# --- AICALC.TBL block 0: AI, one 348-byte row per unit (NOTES.md, "AICALC") ---
# Row = 0x40 header + 7 lists of 0x28 bytes = 5 entries of 8 bytes:
# (u16 probability, u16 action, u16, u16); action = skill id, 0x8000 = attack,
# 0x8001 / 0x10xx = special actions. The probabilities of a list add up to 100.

AI_BLOCK, AI_ROW, AI_HEAD, AI_LIST, AI_LISTS, AI_ENTRY, AI_ENTRIES = 0, 348, 0x40, 0x28, 7, 8, 5
AI_OFF_SCRIPT = 0x02            # u16: block-2 procedure run by the unit (✅ names match)
AI_SCRIPT_BLOCK = 2


class AiTable:
    """AICALC.TBL: block 0 = action lists per unit, block 2 = scripts (`self.flow`, edited in place)."""

    def __init__(self, data: bytes):
        self.data = bytearray(data)
        blocks = tbl_blocks(self.data)
        self._off, size = blocks[AI_BLOCK]
        self.rows = size // AI_ROW
        self.flow = FlowScript(self.data, *blocks[AI_SCRIPT_BLOCK])

    def script(self, unit: int) -> int:
        """Index of the unit's script procedure (0 = none: the unit follows its lists)."""
        return struct.unpack_from("<H", self.data, self._off + unit * AI_ROW + AI_OFF_SCRIPT)[0]

    def set_script(self, unit: int, proc: int) -> None:
        struct.pack_into("<H", self.data, self._off + unit * AI_ROW + AI_OFF_SCRIPT, proc)

    def script_users(self) -> dict[int, list[int]]:
        """Procedure -> units running it."""
        users: dict[int, list[int]] = {}
        for u in range(self.rows):
            if p := self.script(u):
                users.setdefault(p, []).append(u)
        return users

    def _pos(self, unit: int, lst: int, entry: int) -> int:
        return self._off + unit * AI_ROW + AI_HEAD + lst * AI_LIST + entry * AI_ENTRY

    def entries(self, unit: int) -> list[tuple[int, int, int, int]]:
        """(list, entry, probability, action) of the non-empty entries."""
        out = []
        for l in range(AI_LISTS):
            for k in range(AI_ENTRIES):
                prob, action = struct.unpack_from("<HH", self.data, self._pos(unit, l, k))
                if prob or action:
                    out.append((l, k, prob, action))
        return out

    def set_action(self, unit: int, lst: int, entry: int, action: int) -> None:
        struct.pack_into("<H", self.data, self._pos(unit, lst, entry) + 2, action)


# --- ENCOUNT.TBL: block 0 = encounters (1024 × 0x28), block 2 = zones (128 × 0x20C) ---

ENC_BLOCK, ENC_SIZE, ENC_SLOTS, OFF_ENEMIES, OFF_BOSS = 0, 0x28, 7, 0x06, 0x26
ZONE_BLOCK, ZONE_SIZE, ZONE_HEAD, ZONE_LIST, ZONE_LISTS, LIST_LEN = 2, 0x20C, 0x1C, 0x7C, 4, 20


class Encounters:
    """Editable ENCOUNT.TBL in memory (bytearray of the same size as the original)."""

    def __init__(self, data: bytes):
        self.data = bytearray(data)
        blocks = tbl_blocks(self.data)
        self._enc, enc_len = blocks[ENC_BLOCK]
        self._zones, zone_len = blocks[ZONE_BLOCK]
        self.count = enc_len // ENC_SIZE
        self.zone_count = zone_len // ZONE_SIZE

    def flag(self, n: int) -> int:
        """+0x00: 0 for random battles, 1 for scripted battles (0–255 / 256–383)."""
        return struct.unpack_from("<H", self.data, self._enc + n * ENC_SIZE)[0]

    def boss_number(self, n: int) -> int:
        """+0x26: boss battle number (901–920, 0 otherwise); the story continues from it."""
        return struct.unpack_from("<H", self.data, self._enc + n * ENC_SIZE + OFF_BOSS)[0]

    def enemies(self, n: int) -> list[int]:
        """The 7 u16 slots at +0x06, 0 = empty."""
        return list(struct.unpack_from(f"<{ENC_SLOTS}H", self.data, self._enc + n * ENC_SIZE + OFF_ENEMIES))

    def set_enemies(self, n: int, ids: list[int]) -> None:
        if len(ids) != ENC_SLOTS:
            raise ValueError("7 slots expected")
        struct.pack_into(f"<{ENC_SLOTS}H", self.data, self._enc + n * ENC_SIZE + OFF_ENEMIES, *ids)

    def zone_lists(self, zone: int) -> list[list[tuple[int, int]]]:
        """The 4 lists of a zone: (encounter, weight in ‰), empty triplets removed."""
        lists = []
        for l in range(ZONE_LISTS):
            base = self._zones + zone * ZONE_SIZE + ZONE_HEAD + l * ZONE_LIST + 4
            triplets = (struct.unpack_from("<3H", self.data, base + 6 * i) for i in range(LIST_LEN))
            lists.append([(enc, weight) for enc, weight, _x in triplets if enc])
        return lists
