"""Tests of the chest table and shuffle. They read the local ISO (read-only)."""
from collections import Counter
from pathlib import Path

import pytest

from randomizer.chests import (CHEST_FILE, CHEST_SIZE, CHEST_TABLE, FIXED_ITEMS, MACCA, N_CHESTS, ChestTable,
                               groups, randomize_chests, read_item_names)
from randomizer.iso import GameISO
from randomizer.options import Options

ISO = Path(__file__).resolve().parent.parent / "iso" / "dds1_us.iso"
pytestmark = pytest.mark.skipif(not ISO.exists(), reason="reference ISO missing")
SEEDS = range(30)


@pytest.fixture(scope="module")
def game():
    g = GameISO(ISO)
    return g.read(CHEST_FILE), read_item_names(g.read("battle/MSG.TBL"))


def run(game, seed, mode="shuffle"):
    table = ChestTable(game[0])
    return table, randomize_chests(table, game[1], seed, mode)


def test_reading(game):
    """Contents read in RAM in the tester's savestates (global table, identical everywhere)."""
    t, names = ChestTable(game[0]), game[1]
    assert (t.get(1).type, names[t.get(1).item], t.get(1).count) == (0, "Revival Bead", 1)
    assert (t.get(3).type, names[t.get(3).item], t.get(3).count) == (0, "Chakra Drop", 3)
    assert names[t.get(8).item] == "Tyrant Skull" and t.get(0).type == MACCA
    assert sum(1 for c in range(N_CHESTS) if t.get(c).trap == 1) == 9


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("mode", ["shuffle", "random"])
def test_only_contents_change(game, seed, mode):
    """Same size; only item / quantity / Macca of the chests change (never type or trap); fixed items
    and trapped chests intact; no unnamed item."""
    table, res = run(game, seed, mode)
    before = ChestTable(game[0])
    assert len(table.data) == len(game[0])
    for i, (x, y) in enumerate(zip(table.data, game[0])):
        if x != y:
            c, pos = divmod(i - CHEST_TABLE, CHEST_SIZE)
            assert 0 <= c < N_CHESTS and (4 <= pos < 8 or pos >= 12)
    for c in range(N_CHESTS):
        a, b = before.get(c), table.get(c)
        assert (a.type, a.trap) == (b.type, b.trap)
        if a.trap or a.item in FIXED_ITEMS:
            assert a == b
        if b.item:
            assert game[1][b.item] and b.item not in FIXED_ITEMS or a.item == b.item


@pytest.mark.parametrize("seed", SEEDS)
def test_shuffle_keeps_contents(game, seed):
    """"shuffle" mode: each group keeps exactly the same contents, redistributed."""
    table, res = run(game, seed)
    before = ChestTable(game[0])
    assert res.changes
    for name, chests in groups(before).items():
        key = (lambda t, c: t.get(c).value) if name == "macca" else (lambda t, c: (t.get(c).item, t.get(c).count))
        assert Counter(key(before, c) for c in chests) == Counter(key(table, c) for c in chests)


def test_original_determinism_options(game, tmp_path):
    table, res = run(game, 1, "original")
    assert bytes(table.data) == game[0] and not res.changes
    assert run(game, 7)[0].data == run(game, 7)[0].data and run(game, 8)[0].data != run(game, 7)[0].data
    assert Options().chests.mode == "shuffle"
    p = tmp_path / "p.toml"
    p.write_text('[chests]\nmode = "random"\n')
    assert Options.from_toml(p).chests.mode == "random"
    p.write_text('[chests]\nmode = "all"\n')
    with pytest.raises(ValueError):
        Options.from_toml(p)
