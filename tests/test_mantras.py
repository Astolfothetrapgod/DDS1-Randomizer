"""Tests of the mantra table and shuffle. They read the local ISO (read-only)."""
from collections import Counter
from pathlib import Path

import pytest

from randomizer.iso import GameISO
from randomizer.mantras import (ELF, GROUP_HEAL_MAX_LEVEL, MANTRA_SIZE, MANTRA_TABLE, N_MANTRAS, SHUFFLED,
                                MantraTable, randomize_mantras, read_mantra_names)
from randomizer.options import Options
from randomizer.tables import read_skill_names

ISO = Path(__file__).resolve().parent.parent / "iso" / "dds1_us.iso"
pytestmark = pytest.mark.skipif(not ISO.exists(), reason="reference ISO missing")
SEEDS = range(30)


@pytest.fixture(scope="module")
def game():
    g = GameISO(ISO)
    msg = g.read("battle/MSG.TBL")
    return g.read(ELF), read_mantra_names(msg), read_skill_names(msg)


def run(game, seed, mode="tiered", **kw):
    elf, names, skills = game
    table = MantraTable(elf, names)
    return table, randomize_mantras(table, skills, seed, mode, **kw)


def test_reading(game):
    """Entries checked in game (tester's notes) and bounds of the table."""
    table = MantraTable(game[0], game[1])
    skills = game[2]
    assert [skills[x] for x in table.get(2).skills] == ["Feed Frenzy", "Venom Fang", "Ingest Mana"]
    assert [skills[x] for x in table.get(26).skills] == ["Mabufu", "Ice Boost"]
    assert table.get(1).name == "Devourer" and table.get(88).name == "Earth Temple"
    assert (table.get(2).difficulty, table.get(2).level, table.get(26).level) == (2, 15, 5)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("mode", ["tiered", "random"])
def test_only_skills_change(game, seed, mode):
    """Same size; only the skill u16s of shuffled mantras change; each mantra keeps its number of
    skills; the set of skills is kept; no duplicate."""
    table, res = run(game, seed, mode)
    assert len(table.data) == len(game[0])
    for i, (x, y) in enumerate(zip(table.data, game[0])):
        if x != y:
            m, pos = divmod(i - MANTRA_TABLE, MANTRA_SIZE)
            assert 0 <= m < N_MANTRAS and m in SHUFFLED and pos >= 8
    before = MantraTable(game[0], game[1])
    for m in SHUFFLED:
        assert len(table.get(m).skills) == len(before.get(m).skills)
        assert len(set(table.get(m).skills)) == len(table.get(m).skills)
    assert Counter(x for m in SHUFFLED for x in table.get(m).skills) == \
        Counter(x for m in SHUFFLED for x in before.get(m).skills)


@pytest.mark.parametrize("seed", SEEDS)
def test_tiered(game, seed):
    """"tiered" mode: a skill never changes required level by more than 2 × spread + 10
    (largest gap between two neighbouring required levels: 60 → 70)."""
    table, res = run(game, seed, "tiered", guarantee_heal=False, guarantee_group_heal=False)
    before = MantraTable(game[0], game[1])
    level_of = {x: before.get(m).level for m in SHUFFLED for x in before.get(m).skills}
    for m in SHUFFLED:
        for x in table.get(m).skills:
            assert abs(table.get(m).level - level_of[x]) <= 2 * 5 + 10


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("mode", ["tiered", "random"])
def test_guarantees(game, seed, mode):
    table, _ = run(game, seed, mode)
    names = game[2]
    where = {names[x]: table.get(m).level for m in SHUFFLED for x in table.get(m).skills}
    assert where["Dia"] == 1 and where["Media"] <= GROUP_HEAL_MAX_LEVEL


def test_original_determinism_options(game, tmp_path):
    table, res = run(game, 1, "original")
    assert bytes(table.data) == game[0] and res.after == res.before
    a, b = run(game, 7), run(game, 7)
    assert a[0].data == b[0].data and run(game, 8)[0].data != a[0].data
    assert run(game, 7, "random")[0].data != a[0].data
    assert Options().mantras.mode == "tiered"
    p = tmp_path / "p.toml"
    p.write_text('[mantras]\nmode = "random"\nguarantee_heal = false\n')
    o = Options.from_toml(p)
    assert o.mantras.mode == "random" and o.mantras.guarantee_heal is False
    p.write_text('[mantras]\nmode = "chaos"\n')
    with pytest.raises(ValueError):
        Options.from_toml(p)
