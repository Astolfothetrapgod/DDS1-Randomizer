"""The window's choice lists must match the options (no Tk needed)."""
from randomizer.gui import CHOICES
from randomizer.options import Affinities, Bosses, Chests, EnemySkills, Mantras, Options, Shops

BUILD = {
    "enemy_skills": lambda v: EnemySkills(mode=v), "affinities": lambda v: Affinities(mode=v),
    "boss_hp": lambda v: Bosses(hp=v), "unique_skills": lambda v: Bosses(unique_skills=v),
    "mantras": lambda v: Mantras(mode=v), "chests": lambda v: Chests(mode=v), "shops": lambda v: Shops(mode=v),
}


def test_every_choice_is_a_valid_option():
    for key, pairs in CHOICES.items():
        for _label, value in pairs:
            BUILD[key](value)                          # raises ValueError if the value is not accepted


def test_defaults_are_offered():
    o = Options()
    defaults = {"enemy_skills": o.enemy_skills.mode, "affinities": o.affinities.mode, "boss_hp": o.bosses.hp,
                "unique_skills": o.bosses.unique_skills, "mantras": o.mantras.mode, "chests": o.chests.mode,
                "shops": o.shops.mode}
    for key, value in defaults.items():
        assert value in {v for _l, v in CHOICES[key]}
    assert all(len({l for l, _v in pairs}) == len(pairs) for pairs in CHOICES.values())   # labels unique
