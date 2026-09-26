"""Treasure chests: table of 256 chests in fld/f/bin/FLDALL.TBL at 0xDAD8.

Format (NOTES "Items, chests, shops", found through FLD_GET_TAKARA_TBL, code 0x14ED20):
16 bytes per chest: +0x0 u32 type (0 chest, 1 gem box, 3 Macca), +0x4 s16 item,
+0x6 s16 quantity, +0x8 u32 trap (0 none, 1 battle, 2–6 damage / ailments),
+0xC u32 battle number (trap 1) or Macca amount (type 3).
Item names: MSG.TBL block 4, 192 slots of 25 bytes.
"""
import random
import struct
from dataclasses import dataclass

CHEST_FILE, CHEST_TABLE, N_CHESTS, CHEST_SIZE = "fld/f/bin/FLDALL.TBL", 0xDAD8, 256, 16
MSG_ITEM_NAMES, ITEM_NAME_SIZE = 4, 25
CHEST, GEM_BOX, MACCA = 0, 1, 3
# Never moved: key items (the story depends on them) and special items at the end of the list
# (Reserve, Dead End, Magatama).
FIXED_ITEMS = frozenset(range(128, 151)) | frozenset(range(172, 179))
# Safety check: known chest types (the shuffle never changes a type) and key items
KNOWN = {0: MACCA, 1: CHEST, 7: GEM_BOX, 8: GEM_BOX}
KNOWN_KEYS = {8: 139, 59: 148, 66: 149}                 # Tyrant Skull, L Statue Key, R Statue Key


@dataclass
class Chest:
    id: int
    type: int
    item: int
    count: int
    trap: int
    value: int


class ChestTable:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        for c, t in KNOWN.items():
            if self.get(c).type != t:
                raise ValueError("chest table not found: unexpected FLDALL.TBL")
        for c, item in KNOWN_KEYS.items():
            if self.get(c).item != item:
                raise ValueError("chest table not found: key items missing")

    def _pos(self, c: int) -> int:
        return CHEST_TABLE + c * CHEST_SIZE

    def get(self, c: int) -> Chest:
        return Chest(c, *struct.unpack_from("<IhhII", self.data, self._pos(c)))

    def set_item(self, c: int, item: int, count: int) -> None:
        struct.pack_into("<hh", self.data, self._pos(c) + 4, item, count)

    def set_value(self, c: int, value: int) -> None:
        struct.pack_into("<I", self.data, self._pos(c) + 12, value)


def read_item_names(msg: bytes) -> list[str]:
    from .tables import read_names
    return read_names(msg, MSG_ITEM_NAMES, ITEM_NAME_SIZE)


def groups(table: ChestTable) -> dict[str, list[int]]:
    """Shufflable chests, by group (contents only move within a group): item chests, item gem
    boxes, Macca chests; no trap, no fixed item."""
    out: dict[str, list[int]] = {"chests": [], "gem_boxes": [], "macca": []}
    for c in range(N_CHESTS):
        ch = table.get(c)
        if ch.trap or ch.item in FIXED_ITEMS:
            continue
        if ch.type == CHEST and ch.item > 0:
            out["chests"].append(c)
        elif ch.type == GEM_BOX and ch.item > 0:
            out["gem_boxes"].append(c)
        elif ch.type == MACCA and ch.value > 0:
            out["macca"].append(c)
    return out


@dataclass
class ChestResult:
    mode: str
    changes: dict[int, tuple[Chest, Chest]]


def randomize_chests(table: ChestTable, item_names: list[str], seed: int, mode: str = "shuffle") -> ChestResult:
    """"shuffle": contents (item + quantity, or Macca amount) redistributed between chests of the same
    group; "random": each chest gets an item drawn among all named, non-fixed items its group contains
    in the game (quantity and Macca kept); "original": nothing. Modifies `table`."""
    rng = random.Random(f"{seed}-coffres")          # stream name frozen: changing it would change every seed
    before = {c: table.get(c) for c in range(N_CHESTS)}
    res = ChestResult(mode, {})
    if mode == "original":
        return res
    if mode not in ("shuffle", "random"):
        raise ValueError(f"unknown chest mode: {mode!r}")
    for name, chests in groups(table).items():
        if name == "macca":
            values = [before[c].value for c in chests]
            rng.shuffle(values)
            for c, v in zip(chests, values):
                table.set_value(c, v)
            continue
        contents = [(before[c].item, before[c].count) for c in chests]
        if mode == "shuffle":
            rng.shuffle(contents)
        else:
            pool = sorted({item for item, _ in contents if item_names[item]})
            contents = [(rng.choice(pool), count) for _item, count in contents]
        for c, (item, count) in zip(chests, contents):
            table.set_item(c, item, count)
    res.changes = {c: (before[c], table.get(c)) for c in range(N_CHESTS) if table.get(c) != before[c]}
    return res


def spoiler(res: ChestResult, item_names: list[str]) -> str:
    def show(ch: Chest) -> str:
        return f"{ch.value} Macca" if ch.type == MACCA else f"{item_names[ch.item] or ch.item} ×{ch.count}"

    lines = ["", f"Chests ({res.mode}): {len(res.changes)} chests modified"]
    for c, (a, b) in sorted(res.changes.items()):
        kind = {CHEST: "chest", GEM_BOX: "gems", MACCA: "Macca"}.get(a.type, a.type)
        lines.append(f"  #{c:3d} ({kind:<5}): {show(a):<22} -> {show(b)}")
    return "\n".join(lines) + "\n"
