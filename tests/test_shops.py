"""Tests of the shop table and shuffle. They read the local ISO (read-only)."""
from pathlib import Path

import pytest

from randomizer.chests import read_item_names
from randomizer.iso import GameISO
from randomizer.mantras import ELF
from randomizer.options import Options
from randomizer.shops import (ENTRY_SIZE, KARMA_ENTRY, KARMA_HEAD, KARMA_SIZE, KARMA_TABLE, N_KARMA, RATION,
                              SHOP_SIZE, SHOP_TABLE, SHUFFLED_SHOPS, ShopTable, item_values, pools, randomize_shops)

ISO = Path(__file__).resolve().parent.parent / "iso" / "dds1_us.iso"
pytestmark = pytest.mark.skipif(not ISO.exists(), reason="reference ISO missing")
SEEDS = range(30)
SEEN_IN_GAME = ["Ration", "Revival Bead", "Dis-Poison", "Dis-Ache", "Dis-Mute", "Dis-Stun", "Dis-Curse", "Panacea",
                "Molotov", "Ice Blast", "Thunder Rod", "Sonic Stone", "Land Mine", "Shot Shell", "Charge Shot"]


@pytest.fixture(scope="module")
def game():
    g = GameISO(ISO)
    return g.read(ELF), item_values(g.read("battle/SKILL.TBL")), read_item_names(g.read("battle/MSG.TBL"))


def run(game, seed, mode="tiered", **kw):
    table = ShopTable(bytearray(game[0]))
    return table, randomize_shops(table, game[1], game[2], seed, mode, **kw)


def test_reading(game):
    """Shop 2 = list seen in game (chest test 1); displayed prices = value × 2."""
    elf, values, names = game
    t = ShopTable(bytearray(elf))
    assert [names[e.item] for e in t.entries(2)] == SEEN_IN_GAME
    assert [e.tab for e in t.entries(2)][-2:] == [2, 2]
    shown = {"Ration": 100, "Revival Bead": 500, "Dis-Ache": 150, "Molotov": 500, "Shot Shell": 800, "Charge Shot": 1500}
    for n, price in shown.items():
        assert values[names.index(n)][1] * 2 == price


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("mode", ["tiered", "random"])
def test_only_items_of_shops_1_to_8_change(game, seed, mode):
    table, res = run(game, seed, mode)
    for i, (x, y) in enumerate(zip(table.data, game[0])):
        if x != y:
            if KARMA_TABLE <= i < KARMA_TABLE + N_KARMA * KARMA_SIZE:
                lvl, pos = divmod(i - KARMA_TABLE, KARMA_SIZE)
                assert pos >= KARMA_HEAD and (pos - KARMA_HEAD) % KARMA_ENTRY < 2
                continue
            s, pos = divmod(i - SHOP_TABLE, SHOP_SIZE)
            assert s in SHUFFLED_SHOPS and pos >= 2 and (pos - 2) % ENTRY_SIZE < 2
    before = ShopTable(bytearray(game[0]))
    p = pools(game[1], game[2])
    for s in SHUFFLED_SHOPS:
        a, b = before.entries(s), table.entries(s)
        assert len(a) == len(b) and len({e.item for e in b}) == len(b)            # no duplicate
        for x, y in zip(a, b):
            assert x.tab == y.tab and x.percent == y.percent
            assert y.item in p[y.tab] or y.item == x.item


@pytest.mark.parametrize("seed", SEEDS)
def test_progression_and_ration(game, seed):
    """Same mapping everywhere: what is sold in a shop is still sold in the next one if it was in the
    original game; Ration stays for sale (default option)."""
    table, res = run(game, seed)
    before = ShopTable(bytearray(game[0]))
    for s in SHUFFLED_SHOPS:
        assert [res.mapping.get(e.item, e.item) for e in before.entries(s)] == [e.item for e in table.entries(s)]
        assert RATION in [e.item for e in table.entries(s)]


@pytest.mark.parametrize("seed", SEEDS)
def test_tiered(game, seed):
    """"tiered" mode: an item never moves by more than 2 × spread + 1 value ranks within its tab."""
    _, res = run(game, seed, keep_ration=False)
    for pool in pools(game[1], game[2]).values():
        for a in pool:
            assert abs(pool.index(res.mapping[a]) - pool.index(a)) <= 2 * 4 + 1


def test_original_determinism_options(game, tmp_path):
    table, res = run(game, 1, "original")
    assert bytes(table.data) == game[0]
    assert run(game, 7)[0].data == run(game, 7)[0].data and run(game, 8)[0].data != run(game, 7)[0].data
    assert Options().shops.mode == "tiered" and Options().shops.keep_ration is True
    p = tmp_path / "p.toml"
    p.write_text('[shops]\nmode = "random"\nkeep_ration = false\n')
    o = Options.from_toml(p)
    assert o.shops.mode == "random" and o.shops.keep_ration is False


def test_karma_temple_bonuses(game):
    """Original tiers (read from the executable): cumulative, Muscle Drink … Dead End."""
    elf, values, names = game
    t = ShopTable(bytearray(elf))
    assert [names[i] for i in t.karma(0)] == ["Muscle Drink", "Spyglass"]
    assert [names[i] for i in t.karma(4)][-3:] == ["Revival Orb", "Megido Fire", "Dead End"]
    assert all(set(t.karma(l)) <= set(t.karma(l + 1)) for l in range(N_KARMA - 1))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("mode", ["tiered", "random"])
def test_karma_bonuses_shuffled_without_duplicate(game, seed, mode):
    """Same mapping as the shops; no new duplicate between shop and bonus."""
    before = ShopTable(bytearray(game[0]))
    table, res = run(game, seed, mode)
    for lvl in range(N_KARMA):
        assert table.karma(lvl) == [res.mapping.get(i, i) for i in before.karma(lvl)]
        for s in SHUFFLED_SHOPS:
            dup = lambda t: len(set(t.karma(lvl)) & {e.item for e in t.entries(s)})  # noqa: E731
            assert dup(table) == dup(before)
