"""Shops: table of the executable SLUS_209.74 (RAM 0x368CF0, file 0x269CF0).

Format (NOTES "Items, chests, shops", found by reading the code at 0x244C00):
9 shops of 386 bytes = u16 default percentage (200) + 64 entries of 6 bytes
(u16 item, u16 tab: 0 "Buy item" / 2 "Buy ammo", u16 own percentage, 0 = default).
Displayed price = item value (SKILL.TBL block 5, +0x04) × percentage / 100.
Shop 2 = list seen in game by the tester; 1–8 = stock growing along the story; 0 = debug?

Karma Temple bonuses (items added to the stock by selling Cells): RAM 0x369A88, file 0x26AA88,
5 tiers of 260 bytes = header (u16 0x0970 + tier ❓ unlock flag, u16 percentage 200) + 32 entries of
8 bytes (u16 item, u8 marker 0 / 2 ammo / 3 ❓, u8 percentage, u8 1 = new at this tier, 3 ❓).

Shuffle: one item -> item mapping (a bijection over the buyable items of a tab) applied to every shop
1–8 and to the 5 Karma Temple tiers: the progression (growing stock) is kept, and an item never appears
twice unless it already did in the original game.
"""
import random
import struct
from dataclasses import dataclass

from .tables import tbl_blocks

SHOP_TABLE, N_SHOPS, SHOP_SIZE, N_ENTRIES, ENTRY_SIZE = 0x269CF0, 9, 386, 64, 6
SHUFFLED_SHOPS = range(1, 9)
KARMA_TABLE, N_KARMA, KARMA_SIZE, KARMA_HEAD, N_KARMA_ENTRIES, KARMA_ENTRY = 0x26AA88, 5, 260, 4, 32, 8
KARMA_FLAG = 0x0970
ITEMS, TAB_AMMO = 0, 2
ITEM_BLOCK, ITEM_SIZE = 5, 8                   # SKILL.TBL block 5: 192 items of 8 bytes
RATION = 1
# Buyable items (no key items, Noise, Cells or special items): tab -> ids
AMMO = tuple(range(161, 172)) + (173, 174)     # Bullet … Neutron Shot, Silver Shot, Forged Shot
USABLE = (2, 3)                                # usage (SKILL block 5 +0x00): 2 battle, 3 healing


@dataclass
class ShopEntry:
    item: int
    tab: int
    percent: int


class ShopTable:
    """Shops in the executable; modifies `data` in place (same bytearray as the mantra table)."""

    def __init__(self, data: bytearray):
        self.data = data
        for s in range(N_SHOPS):
            if struct.unpack_from("<H", self.data, self._pos(s))[0] != 200:
                raise ValueError("shop table not found: unexpected executable")
        for lvl in range(N_KARMA):
            if struct.unpack_from("<2H", self.data, self._karma(lvl)) != (KARMA_FLAG + lvl, 200):
                raise ValueError("Karma Temple bonuses not found: unexpected executable")

    def _karma(self, lvl: int, k: int | None = None) -> int:
        base = KARMA_TABLE + lvl * KARMA_SIZE
        return base if k is None else base + KARMA_HEAD + k * KARMA_ENTRY

    def karma(self, lvl: int) -> list[int]:
        """Items added to the stock at Karma Temple tier `lvl` (cumulative)."""
        items = [struct.unpack_from("<H", self.data, self._karma(lvl, k))[0] for k in range(N_KARMA_ENTRIES)]
        return [i for i in items if i]

    def _pos(self, shop: int, k: int | None = None) -> int:
        base = SHOP_TABLE + shop * SHOP_SIZE
        return base if k is None else base + 2 + k * ENTRY_SIZE

    def entries(self, shop: int) -> list[ShopEntry]:
        out = []
        for k in range(N_ENTRIES):
            item, tab, pct = struct.unpack_from("<3H", self.data, self._pos(shop, k))
            if item:
                out.append(ShopEntry(item, tab, pct))
        return out

    def set_item(self, shop: int, k: int, item: int) -> None:
        struct.pack_into("<H", self.data, self._pos(shop, k), item)


def item_values(skill_tbl: bytes) -> list[tuple[int, int]]:
    """(usage, value) of the 192 items (SKILL.TBL block 5)."""
    off, _ = tbl_blocks(skill_tbl)[ITEM_BLOCK]
    return [(skill_tbl[off + i * ITEM_SIZE], struct.unpack_from("<I", skill_tbl, off + i * ITEM_SIZE + 4)[0])
            for i in range(192)]


def pools(values: list[tuple[int, int]], names: list[str]) -> dict[int, list[int]]:
    """Buyable items per tab, sorted by value."""
    items = [i for i in range(1, 129) if names[i] and values[i][0] in USABLE and values[i][1] > 0]
    ammo = [i for i in AMMO if names[i] and values[i][1] > 0]
    return {ITEMS: sorted(items, key=lambda i: (values[i][1], i)), TAB_AMMO: sorted(ammo, key=lambda i: (values[i][1], i))}


@dataclass
class ShopResult:
    mode: str
    mapping: dict[int, int]
    before: dict[int, list[int]]
    after: dict[int, list[int]]
    karma_after: dict[int, list[int]] | None = None


def randomize_shops(table: ShopTable, values: list[tuple[int, int]], names: list[str], seed: int,
                    mode: str = "tiered", value_spread: float = 4, keep_ration: bool = True) -> ShopResult:
    """"tiered": each item becomes an item of the same tab with a similar value (noisy sort on the value
    rank, ±value_spread ranks); "random": any buyable item of the same tab; "original": nothing."""
    rng = random.Random(f"{seed}-boutiques")        # stream name frozen: changing it would change every seed
    before = {s: [e.item for e in table.entries(s)] for s in SHUFFLED_SHOPS}
    res = ShopResult(mode, {}, before, dict(before))
    if mode == "original":
        return res
    if mode not in ("tiered", "random"):
        raise ValueError(f"unknown shop mode: {mode!r}")
    for tab, pool in pools(values, names).items():
        if mode == "tiered":
            target = sorted(pool, key=lambda i: pool.index(i) + rng.uniform(-value_spread, value_spread))
        else:
            target = pool[:]
            rng.shuffle(target)
        res.mapping |= dict(zip(pool, target))
    if keep_ration and RATION in res.mapping:
        src = next(i for i, j in res.mapping.items() if j == RATION)
        res.mapping[src], res.mapping[RATION] = res.mapping[RATION], RATION
    for s in SHUFFLED_SHOPS:
        for k in range(N_ENTRIES):
            item = struct.unpack_from("<H", table.data, table._pos(s, k))[0]
            if item in res.mapping:
                table.set_item(s, k, res.mapping[item])
        res.after[s] = [e.item for e in table.entries(s)]
    for lvl in range(N_KARMA):
        for k in range(N_KARMA_ENTRIES):
            pos = table._karma(lvl, k)
            item = struct.unpack_from("<H", table.data, pos)[0]
            if item in res.mapping:
                struct.pack_into("<H", table.data, pos, res.mapping[item])
    res.karma_after = {lvl: table.karma(lvl) for lvl in range(N_KARMA)}
    return res


def spoiler(res: ShopResult, values: list[tuple[int, int]], names: list[str]) -> str:
    lines = ["", f"Shops ({res.mode}): price = value × 2"]
    for s in SHUFFLED_SHOPS:
        lines.append(f"  shop {s}: " + ", ".join(f"{names[i]} {values[i][1] * 2}" for i in res.after[s]))
    for lvl, items in (res.karma_after or {}).items():
        lines.append(f"  Karma Temple bonus {lvl + 1}: " + ", ".join(f"{names[i]} {values[i][1] * 2}" for i in items))
    return "\n".join(lines) + "\n"
