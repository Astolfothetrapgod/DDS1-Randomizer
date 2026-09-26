"""Randomizer options: defaults, TOML preset file, command line.

Preset file (every key is optional; see presets/default.toml for the commented version):

    [enemies]
    shuffle = true              # shuffle the enemies of random battles
    level_spread = 5            # tolerated level spread (species that are not rescaled)
    allow_identity = false      # a species may replace itself
    scaling = true              # rescale the replacement to the level of the species it replaces

    [enemy_skills]
    mode = "adapt"              # "adapt": damage spells brought to the rank of the new level
                                # "random": skills drawn at random (same type, same rank)
                                # "original": unchanged

    [affinities]
    mode = "shuffle"            # "shuffle": each species keeps its values, moved to other elements of the
                                #   same group (damage / instant death / ailments)
                                # "random": values drawn according to their frequency in the game
                                # "original": unchanged
    protect_physical = false    # never "null / repel / drain" on physical

    [bosses]
    shuffle = true              # shuffle single-unit bosses (rescaled to their new place)

    [mantras]
    mode = "tiered"             # "tiered": skills redistributed between mantras of similar required level
                                # "random": any skill in any mantra
                                # "original": unchanged
    level_spread = 5            # tolerated level spread in "tiered" mode
    guarantee_heal = true       # Dia in a level-1 mantra
    guarantee_group_heal = true # Media in a mantra of level 15 or lower

    [chests]
    mode = "shuffle"            # "shuffle": contents redistributed between chests of the same type
                                # "random": item drawn among those found in that type of chest
                                # "original": unchanged (key items and trapped chests are never touched)

    [shops]
    mode = "tiered"             # "tiered": each sold item becomes an item of similar value (same tab)
                                # "random": any buyable item of the same tab
                                # "original": unchanged
    value_spread = 4            # tolerated value-rank spread in "tiered" mode
    keep_ration = true          # Ration stays for sale everywhere
"""
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


def _check(section: str, mode: str, allowed: tuple[str, ...]) -> None:
    if mode not in allowed:
        raise ValueError(f"{section}.mode: {mode!r} (expected " + ", ".join(f'"{m}"' for m in allowed) + ")")


@dataclass
class Enemies:
    shuffle: bool = True
    level_spread: float = 5
    allow_identity: bool = False
    scaling: bool = True


@dataclass
class EnemySkills:
    mode: str = "adapt"

    def __post_init__(self) -> None:
        _check("enemy_skills", self.mode, ("adapt", "random", "original"))


@dataclass
class Affinities:
    mode: str = "shuffle"
    protect_physical: bool = False

    def __post_init__(self) -> None:
        _check("affinities", self.mode, ("shuffle", "random", "original"))


@dataclass
class Bosses:
    shuffle: bool = True


@dataclass
class Mantras:
    mode: str = "tiered"
    level_spread: float = 5
    guarantee_heal: bool = True
    guarantee_group_heal: bool = True

    def __post_init__(self) -> None:
        _check("mantras", self.mode, ("tiered", "random", "original"))


@dataclass
class Chests:
    mode: str = "shuffle"

    def __post_init__(self) -> None:
        _check("chests", self.mode, ("shuffle", "random", "original"))


@dataclass
class Shops:
    mode: str = "tiered"
    value_spread: float = 4
    keep_ration: bool = True

    def __post_init__(self) -> None:
        _check("shops", self.mode, ("tiered", "random", "original"))


@dataclass
class Options:
    enemies: Enemies = field(default_factory=Enemies)
    enemy_skills: EnemySkills = field(default_factory=EnemySkills)
    affinities: Affinities = field(default_factory=Affinities)
    bosses: Bosses = field(default_factory=Bosses)
    mantras: Mantras = field(default_factory=Mantras)
    chests: Chests = field(default_factory=Chests)
    shops: Shops = field(default_factory=Shops)

    @classmethod
    def from_toml(cls, path: Path) -> "Options":
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        opts = cls()
        for section, values in data.items():
            if not hasattr(opts, section):
                raise ValueError(f"{path}: unknown section [{section}]")
            target = getattr(opts, section)
            known = {f.name for f in fields(target)}
            for key, value in values.items():
                if key not in known:
                    raise ValueError(f"{path}: unknown option {section}.{key}")
                setattr(target, key, type(getattr(target, key))(value))
            if hasattr(target, "__post_init__"):
                target.__post_init__()          # re-validate the section after reading it
        return opts

    def describe(self) -> str:
        """Options as text, for the spoiler log: seed + options = reproducible game."""
        return "\n".join(f"  {section}.{key} = {value}"
                         for section, values in asdict(self).items() for key, value in values.items())
