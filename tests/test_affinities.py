"""Tests of the affinities and of the Analyze text. They read the local ISO (read-only)."""
from collections import Counter
from pathlib import Path

import pytest

from randomizer.affinities import GROUPS, LINE_MAX, NULL, PHYS, REPEL, DRAIN, describe, randomize_affinities
from randomizer.enemies import random_encounters, species_pool
from randomizer.iso import GameISO
from randomizer.options import Options
from randomizer.tables import (ANALYZE_LINE, ANALYZE_LINES, AFFINITY_BLOCK, N_AFFINITIES, UNIT_SIZE, AnalyzeText,
                               Encounters, UnitTable, read_units, tbl_blocks)

ISO = Path(__file__).resolve().parent.parent / "iso" / "dds1_us.iso"
pytestmark = pytest.mark.skipif(not ISO.exists(), reason="reference ISO missing")
SEEDS = range(20)


@pytest.fixture(scope="module")
def game():
    g = GameISO(ISO)
    unit, msg = g.read("battle/UNIT.TBL"), g.read("battle/MSG.TBL")
    units = read_units(unit, msg)
    enc = Encounters(g.read("battle/ENCOUNT.TBL"))
    species = [s.id for s in species_pool(enc, random_encounters(enc), units)]
    return unit, msg, species


def run(game, seed, mode="shuffle", protect=False):
    unit, msg, species = game
    table, text = UnitTable(unit), AnalyzeText(msg)
    return table, text, randomize_affinities(table, text, species, seed, mode, protect)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("mode", ["shuffle", "random"])
def test_only_species_affinities_change(game, seed, mode):
    unit, msg, species = game
    table, text, changes = run(game, seed, mode)
    assert changes and set(changes) <= set(species)
    aff = tbl_blocks(unit)[AFFINITY_BLOCK][0]
    for i, (x, y) in enumerate(zip(table.data, unit)):
        if x != y:
            u, pos = divmod(i - aff, UNIT_SIZE)
            col = pos // 4
            assert i >= aff and u in changes and pos < 4 * N_AFFINITIES and any(col in g for g in GROUPS)
    off = tbl_blocks(msg)[2][0]
    for i, (x, y) in enumerate(zip(text.data, msg)):
        if x != y:
            assert (i - off) // (ANALYZE_LINE * ANALYZE_LINES) in changes


@pytest.mark.parametrize("seed", SEEDS)
def test_shuffle_keeps_the_values_of_each_group(game, seed):
    before = UnitTable(game[0])
    table, _, changes = run(game, seed)
    for u in changes:
        old, new = before.affinities(u), table.affinities(u)
        for g in GROUPS:
            assert Counter(old[c] for c in g) == Counter(new[c] for c in g)
        assert old[7] == new[7] and old[15:] == new[15:]      # almighty, column 15, end


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("mode", ["shuffle", "random"])
def test_analyze_text_follows_affinities(game, seed, mode):
    table, text, changes = run(game, seed, mode)
    for u in changes:
        lines = [t for t in text.lines(u) if t]
        assert lines == describe(table.affinities(u))
        assert all(len(t) <= LINE_MAX for t in lines)


@pytest.mark.parametrize("seed", SEEDS)
def test_protect_physical(game, seed):
    table, _, changes = run(game, seed, "random", protect=True)
    for u in changes:
        v = table.affinities(u)[PHYS]
        safe_exists = any(not table.affinities(u)[c] & (NULL | REPEL | DRAIN) for c in GROUPS[0])
        assert not v & (NULL | REPEL | DRAIN) or not safe_exists


def test_original_and_determinism(game):
    table, text, changes = run(game, 1, "original")
    assert not changes and bytes(table.data) == game[0] and bytes(text.data) == game[1]
    a, b = run(game, 7), run(game, 7)
    assert a[0].data == b[0].data and a[1].data == b[1].data
    assert run(game, 8)[0].data != a[0].data


def test_text_identical_to_atlus_for_simple_cases(game):
    """The generator reproduces Atlus' texts (sample checked by hand)."""
    table, text = UnitTable(game[0]), AnalyzeText(game[1])
    for u in (99, 102, 56, 24, 92, 23):       # Onmoraki, Preta, Slime, Macha, Kikuri-Hime, Virtue
        assert describe(table.affinities(u)) == [text.lines(u)[0]]


def test_affinity_option(tmp_path):
    p = tmp_path / "p.toml"
    p.write_text('[affinities]\nmode = "random"\nprotect_physical = true\n')
    o = Options.from_toml(p)
    assert o.affinities.mode == "random" and o.affinities.protect_physical is True
    p.write_text('[affinities]\nmode = "chaos"\n')
    with pytest.raises(ValueError):
        Options.from_toml(p)
