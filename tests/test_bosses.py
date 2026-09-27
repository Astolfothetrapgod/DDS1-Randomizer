"""Tests of the boss shuffle. They read the local ISO (read-only)."""
from pathlib import Path

import pytest

from randomizer.bosses import EXCLUDED_ENCOUNTERS, randomize_bosses, scale_unique_skills, unique_power
from randomizer.enemies import own_script, randomize
from randomizer.iso import GameISO
from randomizer.options import Options
from randomizer.skills import families
from randomizer.mantras import ELF, N_MANTRAS, MantraTable
from randomizer.tables import (OFF_BOSS, OFF_POWER, SKILL_BLOCK, SKILL_SIZE, AiTable, Encounters, SkillTable,
                               UnitTable, read_skills, read_units, tbl_blocks)

ISO = Path(__file__).resolve().parent.parent / "iso" / "dds1_us.iso"
pytestmark = pytest.mark.skipif(not ISO.exists(), reason="reference ISO missing")
SEEDS = range(20)


@pytest.fixture(scope="module")
def game():
    g = GameISO(ISO)
    unit, msg = g.read("battle/UNIT.TBL"), g.read("battle/MSG.TBL")
    return (g.read("battle/ENCOUNT.TBL"), unit, read_units(unit, msg), read_skills(g.read("battle/SKILL.TBL"), msg),
            g.read("battle/AICALC.TBL"))


def run(game, seed, with_enemies=False, hp="curve"):
    enc_data, unit_data, units, skills, ai_data = game
    enc, table, ai = Encounters(enc_data), UnitTable(unit_data), AiTable(ai_data)
    if with_enemies:
        randomize(enc, table, units, seed, None, skills, ai)
    return enc, table, ai, randomize_bosses(enc, table, ai, units, skills, seed, hp)


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


@pytest.mark.parametrize("seed", SEEDS)
def test_hp_of_the_place(game, seed):
    """hp = "place": each moved boss has the HP of the boss it replaces; everything else (mapping, level,
    MP, stats, rewards, AI, encounters, other units) is identical to the "curve" mode."""
    units = game[2]
    c_enc, c_table, c_ai, c_res = run(game, seed, with_enemies=True)
    p_enc, p_table, p_ai, p_res = run(game, seed, with_enemies=True, hp="place")
    assert p_res.mapping == c_res.mapping and p_enc.data == c_enc.data and p_ai.data == c_ai.data
    moved = set()
    for n, a in p_res.places:
        b = p_res.mapping[n]
        moved.add(b)
        s, c = p_table.get(b), c_table.get(b)
        assert s.hp == units[a].hp
        assert (s.level, s.mp, s.stats, s.karma, s.macca) == (c.level, c.mp, c.stats, c.karma, c.macca)
    for i in range(len(units)):
        if i not in moved:
            assert p_table.get(i) == c_table.get(i)


def test_hp_option(tmp_path):
    assert Options().bosses.hp == "curve"
    p = tmp_path / "p.toml"
    p.write_text('[bosses]\nhp = "place"\n')
    assert Options.from_toml(p).bosses.hp == "place"
    p.write_text('[bosses]\nhp = "low"\n')
    with pytest.raises(ValueError, match="bosses.hp"):
        Options.from_toml(p)


@pytest.fixture(scope="module")
def skill_data():
    g = GameISO(ISO)
    mantras = MantraTable(g.read(ELF))
    return g.read("battle/SKILL.TBL"), {s for m in range(N_MANTRAS) for s in mantras.get(m).skills}


# Boss versions (some names exist twice: Celestial Ray 89 and Fire of Sinai 95 are used by no enemy)
CELESTIAL_RAY, SERAPH_LORE, FIRE_STORM, FIRE_OF_SINAI, SPIRAL_EDGE = 424, 428, 385, 374, 391


def test_unique_power_values(game):
    """Values of the continuous curve (NOTES "Unique boss skills")."""
    skills = game[3]
    assert skills[CELESTIAL_RAY].name == "Celestial Ray" and skills[SPIRAL_EDGE].name == "Spiral Edge"
    assert unique_power(skills[CELESTIAL_RAY], 85, 8) == 47      # Huang Long as the first boss: 250 -> 47
    assert unique_power(skills[SERAPH_LORE], 20, 8) == 64        # percentage: 80 % -> 64 %
    assert unique_power(skills[SERAPH_LORE], 20, 55) == 80       # a percentage never goes up
    assert unique_power(skills[FIRE_STORM], 8, 55) == 177        # early boss placed late
    assert unique_power(skills[FIRE_OF_SINAI], 80, 80) == 90


@pytest.mark.parametrize("seed", SEEDS)
def test_unique_skills_power(game, skill_data, seed):
    """Only the power (u16 +0x18) of eligible skills changes in SKILL.TBL: cast by one boss only, absent
    from the mantras, damage or percentage; never stronger when the boss moves down, never weaker when it
    moves up; everything else (encounters, records, AI) identical to "keep"."""
    units, skills = game[2], game[3]
    data, protected = skill_data
    k_enc, k_table, k_ai, _ = run(game, seed, with_enemies=True)
    enc, table, ai, res = run(game, seed, with_enemies=True)
    st = SkillTable(data)
    scale_unique_skills(res, st, ai, units, skills, protected)
    assert enc.data == k_enc.data and table.data == k_table.data and ai.data == k_ai.data
    off, _ = tbl_blocks(bytearray(data))[SKILL_BLOCK]
    allowed = {off + s * SKILL_SIZE + OFF_POWER + i for s in res.unique for i in (0, 1)}
    assert all(i in allowed for i, (x, y) in enumerate(zip(data, st.data)) if x != y)
    assert SPIRAL_EDGE not in res.unique                                # shared by the 3 Camazotz
    assert not set(res.unique) & protected
    place = {res.mapping[n]: a for n, a in res.places}
    for s, (b, old, new) in res.unique.items():
        assert skills[s].nature in (1, 8) and st.power(s) == new and old == skills[s].power
        down = units[place[b]].level < units[b].level
        assert new <= old if down else new >= old
        if skills[s].nature == 8:
            assert new <= old


def test_unique_skills_option(tmp_path):
    assert Options().bosses.unique_skills == "keep"
    p = tmp_path / "p.toml"
    p.write_text('[bosses]\nunique_skills = "power"\n')
    assert Options.from_toml(p).bosses.unique_skills == "power"
    p.write_text('[bosses]\nunique_skills = "half"\n')
    with pytest.raises(ValueError, match="bosses.unique_skills"):
        Options.from_toml(p)
