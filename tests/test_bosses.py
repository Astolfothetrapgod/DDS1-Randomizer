"""Tests of the boss shuffle. They read the local ISO (read-only)."""
from pathlib import Path

import pytest

from randomizer.bosses import EXCLUDED_ENCOUNTERS, randomize_bosses
from randomizer.enemies import own_script, randomize
from randomizer.iso import GameISO
from randomizer.options import Options
from randomizer.skills import families
from randomizer.tables import (OFF_BOSS, AiTable, Encounters, UnitTable, read_skills, read_units)

ISO = Path(__file__).resolve().parent.parent / "iso" / "dds1_us.iso"
pytestmark = pytest.mark.skipif(not ISO.exists(), reason="reference ISO missing")
SEEDS = range(20)


@pytest.fixture(scope="module")
def game():
    g = GameISO(ISO)
    unit, msg = g.read("battle/UNIT.TBL"), g.read("battle/MSG.TBL")
    return (g.read("battle/ENCOUNT.TBL"), unit, read_units(unit, msg), read_skills(g.read("battle/SKILL.TBL"), msg),
            g.read("battle/AICALC.TBL"))


def run(game, seed, with_enemies=False):
    enc_data, unit_data, units, skills, ai_data = game
    enc, table, ai = Encounters(enc_data), UnitTable(unit_data), AiTable(ai_data)
    if with_enemies:
        randomize(enc, table, units, seed, None, skills, ai)
    return enc, table, ai, randomize_bosses(enc, table, ai, units, skills, seed)


def test_places(game):
    """The 24 expected places (NOTES: catalogue of scripted battles), exclusions included."""
    enc, table, ai, res = run(game, 1)
    units = game[2]
    names = [units[u].name for _n, u in res.places]
    assert len(res.places) == 24
    assert names.count("Camazotz") == 3 and "Hayagriva" in names and "Usas" in names and "Metatron" in names
    assert not {n for n, _u in res.places} & set(EXCLUDED_ENCOUNTERS)
    assert "Jinn" not in names                          # AI_Zin script shared with Jinn 48


@pytest.mark.parametrize("seed", SEEDS)
def test_permutation(game, seed):
    """Each boss is used once, none stays in its place; only the old boss's slot changes (not always
    slot 0: Camazotz 259 is in slot 1); the boss battle number (+0x26) and other encounters are intact."""
    enc, _, _, res = run(game, seed)
    before = Encounters(game[0])
    bosses = [u for _n, u in res.places]
    assert sorted(res.mapping.values()) == sorted(bosses)
    assert all(res.mapping[n] != u for n, u in res.places)
    for n in range(enc.count):
        if n in res.mapping:
            old = dict(res.places)[n]
            assert enc.enemies(n) == [res.mapping[n] if x == old else x for x in before.enemies(n)]
            assert sum(1 for x in enc.enemies(n) if x) == 1
            assert enc.boss_number(n) == before.boss_number(n)
        else:
            assert enc.enemies(n) == before.enemies(n)
    diff = [i for i, (x, y) in enumerate(zip(enc.data, before.data)) if x != y]
    assert all(not (OFF_BOSS <= (i - enc._enc) % 0x28 < OFF_BOSS + 2) for i in diff)


@pytest.mark.parametrize("seed", SEEDS)
def test_level_and_rewards_of_the_place(game, seed):
    _, table, _, res = run(game, seed)
    units = game[2]
    for n, a in res.places:
        s = table.get(res.mapping[n])
        assert (s.level, s.karma, s.macca) == (units[a].level, units[a].karma, units[a].macca)


@pytest.mark.parametrize("seed", SEEDS)
def test_reserved_reinforcements(game, seed):
    """Reserved summon: same level ratio as its boss, same id in the script."""
    _, table, ai, res = run(game, seed)
    units = game[2]
    place = {b: a for (_n, a), b in ((p, res.mapping[p[0]]) for p in res.places)}
    for b, pairs in res.reinforcements.items():
        for x, level in pairs:
            assert level == max(1, round(units[place[b]].level * units[x].level / units[b].level))
            assert table.get(x).level == level
            assert x in {ai.flow.arg(k) for k in own_script(ai, b).summons}


@pytest.mark.parametrize("seed", SEEDS)
def test_boss_spells_adapted(game, seed):
    """Spells of a boss script: same family, never stronger when it moves down, never weaker when it
    moves up; unique skills (outside families) unchanged."""
    _, _, units, skills, ai_data = game
    fam = families(skills)
    before = AiTable(ai_data)
    _, _, ai, res = run(game, seed)
    for n, a in res.places:
        b = res.mapping[n]
        p = own_script(before, b)
        if p is None:
            continue
        down = units[a].level < units[b].level
        for k in p.casts + p.checks:
            old, new = before.flow.arg(k), ai.flow.arg(k)
            if old not in fam:
                assert new == old
            elif new != old:
                assert fam[new] is fam[old]
                assert (skills[new].power <= skills[old].power) if down else (skills[new].power >= skills[old].power)


def test_with_the_enemy_shuffle(game):
    """Chained after the enemy shuffle: summons of ordinary species target shuffled species."""
    enc, table, ai, res = run(game, 3, with_enemies=True)
    assert res.mapping and len(enc.data) == len(game[0]) and len(ai.data) == len(game[4])


def test_determinism_and_option(game, tmp_path):
    a, b = run(game, 9), run(game, 9)
    assert a[0].data == b[0].data and a[1].data == b[1].data and a[2].data == b[2].data
    assert run(game, 10)[3].mapping != a[3].mapping
    assert Options().bosses.shuffle is True
    p = tmp_path / "p.toml"
    p.write_text("[bosses]\nshuffle = false\n")
    assert Options.from_toml(p).bosses.shuffle is False
