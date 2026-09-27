"""Tests of the enemy shuffle and rescaling. They read the local ISO (read-only).

Run: python -m pytest -q
"""
from pathlib import Path

import pytest

from randomizer.enemies import EXCLUDED_UNITS, actions, own_script, random_encounters, randomize, scalable, species_pool
from randomizer.iso import GameISO
from randomizer.options import Enemies, Options
from randomizer.skills import families, mp_needed, skill_class, usage_levels
from randomizer.scaling import fit, scale
from randomizer.tables import (AI_ENTRY, AI_HEAD, AI_OFF_SCRIPT, AI_ROW, AiTable, N_SKILLS, OFF_HP, OFF_KARMA,
                               OFF_LEVEL, OFF_MACCA, OFF_MP, OFF_SKILLS, OFF_STATS, UNIT_SIZE, Encounters, UnitTable,
                               read_skills, read_units, tbl_blocks)

ISO = Path(__file__).resolve().parent.parent / "iso" / "dds1_us.iso"
pytestmark = pytest.mark.skipif(not ISO.exists(), reason="reference ISO missing")
SEEDS = range(20)
# Record bytes the rescaling is allowed to modify
ALLOWED = ({OFF_LEVEL} | set(range(OFF_HP, OFF_HP + 4)) | set(range(OFF_MP, OFF_MP + 4))
           | set(range(OFF_STATS, OFF_STATS + 5)) | set(range(OFF_MACCA, OFF_MACCA + 4))
           | set(range(OFF_KARMA, OFF_KARMA + 2)) | set(range(OFF_SKILLS, OFF_SKILLS + 2 * N_SKILLS)))


@pytest.fixture(scope="module")
def game():
    g = GameISO(ISO)
    unit, msg = g.read("battle/UNIT.TBL"), g.read("battle/MSG.TBL")
    return (g.read("battle/ENCOUNT.TBL"), unit, read_units(unit, msg), read_skills(g.read("battle/SKILL.TBL"), msg),
            g.read("battle/AICALC.TBL"))


def run(game, seed, with_skills=True, with_ai=False, skill_mode="adapt", **opts):
    enc_data, unit_data, units, skills, ai_data = game
    enc, table, ai = Encounters(enc_data), UnitTable(unit_data), AiTable(ai_data)
    result = randomize(enc, table, units, seed, Enemies(**opts), skills if with_skills else None, ai, skill_mode)
    return (enc, table, result, ai) if with_ai else (enc, table, result)


def test_same_sizes(game):
    enc, table, _ = run(game, 1)
    assert len(enc.data) == len(game[0]) and len(table.data) == len(game[1])


@pytest.mark.parametrize("seed", SEEDS)
def test_only_random_encounters_change(game, seed):
    enc, _, result = run(game, seed)
    allowed = set(result.encounters)
    start, end = enc._enc, enc._enc + enc.count * 0x28
    diff = [i for i, (a, b) in enumerate(zip(enc.data, game[0])) if a != b]
    assert all(start <= i < end and (i - start) % 0x28 >= 6 and (i - start) // 0x28 in allowed for i in diff)


@pytest.mark.parametrize("seed", SEEDS)
def test_enemy_count_kept(game, seed):
    enc, _, result = run(game, seed)
    before = Encounters(game[0])
    for n in result.encounters:
        assert [x == 0 for x in before.enemies(n)] == [x == 0 for x in enc.enemies(n)]


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("scaling", [True, False])
def test_permutation_without_identity_and_spread(game, seed, scaling):
    """Permutation without fixed point; species that are not rescaled respect 2 × spread + gap."""
    units = game[2]
    _, _, result = run(game, seed, level_spread=5, scaling=scaling)
    m = result.mapping
    assert sorted(m) == sorted(m.values()) and all(a != b for a, b in m.items())
    constrained = [a for a in m if a not in result.scaled and m[a] not in result.scaled]
    levels = sorted(units[i].level for i in constrained)
    gap = max((b - a for a, b in zip(levels, levels[1:])), default=0)
    assert all(abs(units[a].level - units[m[a]].level) <= 10 + gap for a in constrained)


@pytest.mark.parametrize("seed", SEEDS)
def test_exclusions(game, seed):
    _, _, result = run(game, seed)
    units = game[2]
    assert all(i not in EXCLUDED_UNITS and units[i].name and units[i].level < 99 for i in result.mapping)


@pytest.mark.parametrize("seed", SEEDS)
def test_records_only_modified_when_safe(game, seed):
    """Only records of "scalable" species change, and only in validated fields."""
    enc_data, unit_data, units, _, _ = game
    _, table, result = run(game, seed)
    enc0 = Encounters(enc_data)
    free = scalable(enc0, species_pool(enc0, random_encounters(enc0), units))
    off = tbl_blocks(unit_data)[3][0]
    diff = [i for i, (a, b) in enumerate(zip(table.data, unit_data)) if a != b]
    for i in diff:
        unit, pos = divmod(i - off, UNIT_SIZE)
        assert i >= off and unit in free and unit in result.scaled and pos in ALLOWED


@pytest.mark.parametrize("seed", SEEDS)
def test_rescaling_takes_level_and_rewards(game, seed):
    units = game[2]
    _, _, result = run(game, seed)
    inverse = {b: a for a, b in result.mapping.items()}
    assert result.scaled
    for b, s in result.scaled.items():
        a = units[inverse[b]]
        assert (s.level, s.karma, s.macca) == (a.level, a.karma, a.macca)
        assert 1 <= s.hp <= 32767 and all(1 <= v <= 99 for v in s.stats)


def test_scaling_to_own_level_changes_nothing(game):
    units = game[2]
    enc = Encounters(game[0])
    pool = species_pool(enc, random_encounters(enc), units)
    e = fit(pool)
    assert all(scale(u, u.level, e) == (u.hp, u.mp, u.stats) for u in pool)


def test_disabled_options(game):
    enc, table, _ = run(game, 3, scaling=False)
    assert bytes(table.data) == game[1] and bytes(enc.data) != game[0]
    enc, table, _ = run(game, 3, shuffle=False)
    assert bytes(table.data) == game[1] and bytes(enc.data) == game[0]


def test_same_seed_same_result(game):
    a, b = run(game, 42), run(game, 42)
    assert a[0].data == b[0].data and a[1].data == b[1].data
    assert run(game, 43)[0].data != a[0].data


@pytest.mark.parametrize("seed", SEEDS)
def test_adapted_skills(game, seed):
    """Only rescaled species change skills; every replacement stays in the family; a demoted enemy
    never gets a stronger version."""
    _, unit_data, units, skills, _ = game
    fam = families(skills)
    before = UnitTable(unit_data)
    _, table, result = run(game, seed)
    inverse = {b: a for a, b in result.mapping.items()}
    assert result.skill_changes
    for b in range(table.count):
        if b not in result.skill_changes:
            assert table.skills(b) == before.skills(b)
    for b, changes in result.skill_changes.items():
        assert b in result.scaled
        for old, new in changes:
            assert new in fam and fam[new] is fam[old]
            if units[inverse[b]].level < units[b].level:
                assert skills[new].strength <= skills[old].strength
            else:
                assert skills[new].strength >= skills[old].strength


def script_args(ai):
    """Bytes of the PUSHIS arguments the randomizer may rewrite (casts, checks, summons)."""
    f = ai.flow
    return {f.code + 4 * k + j for p in f.procedures for k in p.casts + p.checks + p.summons for j in (2, 3)}


@pytest.mark.parametrize("seed", SEEDS)
def test_adapted_ai(game, seed):
    """AI: only the "action" fields of rescaled species' rows change, always within the family;
    probabilities never move. Elsewhere in AICALC: only the script number of detached units and
    PUSHIS arguments of the scripts."""
    _, _, units, skills, ai_data = game
    fam = families(skills)
    _, _, result, ai = run(game, seed, with_ai=True)
    before = AiTable(ai_data)
    assert result.ai_changes > 0 and len(ai.data) == len(ai_data)
    allowed_script = script_args(before)
    rows_end = before._off + before.rows * AI_ROW
    diff = [i for i, (x, y) in enumerate(zip(ai.data, ai_data)) if x != y]
    for i in diff:
        if before._off <= i < rows_end:
            unit, pos = divmod(i - before._off, AI_ROW)
            assert unit in result.scaled
            assert (pos >= AI_HEAD and (pos - AI_HEAD) % AI_ENTRY in (2, 3)) or (
                unit in result.detached and pos in (AI_OFF_SCRIPT, AI_OFF_SCRIPT + 1))
        else:
            assert i in allowed_script
    for b in result.scaled:
        for (l, k, p, act), (l2, k2, p2, act2) in zip(before.entries(b), ai.entries(b)):
            assert (l, k, p) == (l2, k2, p2)
            assert act == act2 or (act in fam and fam[act2] is fam[act])


@pytest.mark.parametrize("seed", SEEDS)
def test_random_skills(game, seed):
    """Same type, among skills already used by an enemy's AI; record and AI replaced the same way;
    probabilities intact; only shuffled species change."""
    enc_data, unit_data, units, skills, ai_data = game
    usage = usage_levels(units, AiTable(ai_data), skills)
    before_t, before_ai = UnitTable(unit_data), AiTable(ai_data)
    _, table, result, ai = run(game, seed, with_ai=True, skill_mode="random")
    assert result.skill_changes
    for u, changes in result.skill_changes.items():
        assert u in result.mapping
        m = dict(changes)
        assert len(set(m.values())) == len(m)                       # no duplicate within the unit
        for old, new in m.items():
            assert new in usage and skill_class(skills[new]) == skill_class(skills[old]) is not None
            assert skills[new].cost_type == skills[old].cost_type
        assert table.skills(u) == [m.get(s, s) for s in before_t.skills(u)]
        for (l, k, p, a), (l2, k2, p2, a2) in zip(before_ai.entries(u), ai.entries(u)):
            assert (l, k, p) == (l2, k2, p2) and a2 == m.get(a, a)
    for u in range(table.count):
        if u not in result.skill_changes:
            assert table.skills(u) == before_t.skills(u) and ai.entries(u) == before_ai.entries(u)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("mode", ["adapt", "random"])
def test_mp_budget(game, seed, mode):
    """Every rewritten record can cast its most expensive spell MP_FACTOR times (record + AI)."""
    skills = game[3]
    _, table, result, ai = run(game, seed, with_ai=True, skill_mode=mode)
    for u in set(result.scaled) | set(result.skill_changes):
        used = table.skills(u) + [a for *_x, a in ai.entries(u)]
        assert table.get(u).mp >= mp_needed(used, skills)
    pool = set(result.mapping)
    for u, (before, after) in result.mp_raised.items():
        assert after > before and after == mp_needed(table.skills(u) + actions(ai, u, pool), skills)


def test_random_skills_do_not_change_placement(game):
    a = run(game, 11, skill_mode="adapt")
    b = run(game, 11, skill_mode="random")
    assert a[2].mapping == b[2].mapping and a[0].data == b[0].data


def test_original_skills(game):
    _, table, result, ai = run(game, 5, with_skills=False, with_ai=True)
    assert not result.skill_changes and result.ai_changes == 0 and result.script_changes == 0
    summon_args = {ai.flow.code + 4 * k + j for p in ai.flow.procedures for k in p.summons for j in (2, 3)}
    # only summons change (they follow the level, not the skill option)
    assert all(i in summon_args for i, (x, y) in enumerate(zip(ai.data, game[4])) if x != y)
    before = UnitTable(game[1])
    assert all(table.skills(i) == before.skills(i) for i in range(table.count))


def test_preset_toml(tmp_path):
    p = tmp_path / "p.toml"
    p.write_text("[enemies]\nlevel_spread = 8\nscaling = false\n")
    o = Options.from_toml(p)
    assert o.enemies.level_spread == 8 and o.enemies.scaling is False and o.enemies.shuffle is True
    p.write_text("[enemies]\ntypo = 1\n")
    with pytest.raises(ValueError):
        Options.from_toml(p)
    p.write_text('[enemy_skills]\nmode = "original"\n')
    assert Options.from_toml(p).enemy_skills.mode == "original"
    p.write_text('[enemy_skills]\nmode = "whatever"\n')
    with pytest.raises(ValueError):
        Options.from_toml(p)


def test_default_preset_equals_defaults():
    preset = Path(__file__).resolve().parent.parent / "presets" / "default.toml"
    assert Options.from_toml(preset) == Options()


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("mode", ["adapt", "random"])
def test_scripts_follow_the_record(game, seed, mode):
    """Script owned by a rewritten species: every cast skill and every "do I have this skill" check
    got the same replacement as the record and the lists (same family in "adapt", same mapping in
    "random"); no script of a unit outside the shuffle changes."""
    _, _, units, skills, ai_data = game
    fam = families(skills)
    before = AiTable(ai_data)
    _, table, result, ai = run(game, seed, with_ai=True, skill_mode=mode)
    pool = set(result.mapping)
    touched = set()
    for u in result.skill_changes:
        p = own_script(before, u, pool)
        if p is None:
            continue
        touched.add(p.index)
        for k in p.casts + p.checks:
            old, new = before.flow.arg(k), ai.flow.arg(k)
            if mode == "random":
                assert new == dict(result.skill_changes[u]).get(old, old)
            else:
                assert new == old or fam[new] is fam[old]
        assert result.script_changes
    for p in before.flow.procedures:
        if p.index not in touched:
            assert all(ai.flow.arg(k) == before.flow.arg(k) for k in p.casts + p.checks)


@pytest.mark.parametrize("seed", SEEDS)
def test_shared_scripts_detached(game, seed):
    """A script shared with a unit outside the shuffle (AI_Zin: Jinn 48 and Jinn 338) is never
    rewritten: the rewritten species is detached from it, the other unit keeps it."""
    before = AiTable(game[4])
    _, _, result, ai = run(game, seed, with_ai=True)
    pool = set(result.mapping)
    for u in result.detached:
        assert u in pool and ai.script(u) == 0
        users = before.script_users()[before.script(u)]
        assert not set(users) <= pool
        assert all(ai.script(v) == before.script(v) for v in users if v != u)


@pytest.mark.parametrize("seed", SEEDS)
def test_summons_at_level(game, seed):
    """A shuffled species that summons another one now summons a shuffled species whose level (after
    rescaling) is one of the closest to the proportional target."""
    units = game[2]
    before = AiTable(game[4])
    _, table, result, ai = run(game, seed, with_ai=True)
    pool = set(result.mapping)
    assert result.summons                      # Hanuman, Girimehkala: always rescaled
    for u, pairs in result.summons.items():
        level = table.get(u).level
        for x, y in pairs:
            assert x in pool and y in pool and y != u
            target = max(1, round(level * units[x].level / units[u].level))
            best = min(abs(table.get(z).level - target) for z in pool if z != u)
            assert abs(table.get(y).level - target) <= best + 1
    for p in before.flow.procedures:            # summons of scripts outside the shuffle intact
        if not (set(before.script_users().get(p.index, [])) & set(result.summons)):
            assert all(ai.flow.arg(k) == before.flow.arg(k) for k in p.summons)


def test_flowscript_reader(game):
    """Counts identical to Atlus-Script-Tools' decompilation; +0x02 = procedure named after the unit."""
    ai = AiTable(game[4])
    procs = ai.flow.procedures
    assert len(procs) == 72
    assert sum(len(p.casts) for p in procs) == 811
    assert sum(len(p.summons) for p in procs) == 23
    assert sum(len(p.checks) for p in procs) == 31
    assert procs[ai.script(261)].name == "AI_Ushasu" and procs[ai.script(48)].name == "AI_Zin"
    assert [ai.flow.arg(k) for k in procs[9].summons] == [301]          # Usas summons Unicorn 301
