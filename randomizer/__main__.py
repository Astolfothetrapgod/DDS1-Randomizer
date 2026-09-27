"""DDS1 Randomizer — command line.

Usage: python -m randomizer ORIGINAL_ISO OUTPUT_ISO [--seed N] [--preset file.toml] [options]
       python -m randomizer            (no argument: opens the window, see gui.py)

The original ISO is never modified (see generate.py). Command-line options override the preset file.
"""
import argparse
import sys
from pathlib import Path

from . import __version__
from .generate import generate
from .options import Options


def main() -> None:
    if len(sys.argv) == 1:                        # no argument (double click): the window
        from .gui import main as gui_main
        gui_main()
        return
    try:
        run()
    except (ValueError, OSError) as e:           # expected errors: clear message, no Python traceback
        sys.exit(f"error: {e}")


def run() -> None:
    ap = argparse.ArgumentParser(prog="python -m randomizer",
                                 description=f"DDS1 Randomizer {__version__} — Digital Devil Saga (PS2, NTSC-U, SLUS-20974)")
    ap.add_argument("--version", action="version", version=f"DDS1 Randomizer {__version__}")
    ap.add_argument("src", type=Path, help="original ISO (never modified)")
    ap.add_argument("dst", type=Path, help="randomized ISO to create (overwritten if it exists)")
    ap.add_argument("--seed", type=int, default=None, help="seed; same seed + same options = same result")
    ap.add_argument("--preset", type=Path, help="options file (.toml)")
    ap.add_argument("--verify-iso", action="store_true",
                    help="also check the whole ISO against the Redump hash (full read, slower)")
    ap.add_argument("--level-spread", type=float, help="tolerated level spread for species that are not rescaled")
    ap.add_argument("--allow-identity", action="store_true", default=None, help="a species may replace itself")
    ap.add_argument("--no-scaling", action="store_true", help="do not rescale shuffled enemies")
    ap.add_argument("--no-enemy-shuffle", action="store_true", help="do not shuffle enemies")
    ap.add_argument("--enemy-skills", choices=("adapt", "random", "original"),
                    help="enemy skills: adapted to the level, random (same type, same rank) or original")
    ap.add_argument("--affinities", choices=("shuffle", "random", "original"), help="enemy affinities")
    ap.add_argument("--protect-physical", action="store_true", help="never \"null / repel / drain\" on physical")
    ap.add_argument("--no-bosses", action="store_true", help="do not shuffle bosses")
    ap.add_argument("--boss-hp", choices=("curve", "place"),
                    help="HP of moved bosses: level curve (default) or HP of the boss they replace (easier)")
    ap.add_argument("--boss-unique-skills", choices=("keep", "power"),
                    help="unique boss skills: unchanged (default) or power following the level of the new place")
    ap.add_argument("--mantras", choices=("tiered", "random", "original"), help="mantra skills")
    ap.add_argument("--no-heal-guarantee", action="store_true",
                    help="guarantee neither Dia at level 1 nor Media at level 15 or lower")
    ap.add_argument("--chests", choices=("shuffle", "random", "original"), help="chest contents")
    ap.add_argument("--shops", choices=("tiered", "random", "original"), help="shop items")
    a = ap.parse_args()

    opts = Options.from_toml(a.preset) if a.preset else Options()
    if a.level_spread is not None:
        opts.enemies.level_spread = a.level_spread
    if a.allow_identity:
        opts.enemies.allow_identity = True
    if a.no_scaling:
        opts.enemies.scaling = False
    if a.no_enemy_shuffle:
        opts.enemies.shuffle = False
    if a.enemy_skills:
        opts.enemy_skills.mode = a.enemy_skills
    if a.affinities:
        opts.affinities.mode = a.affinities
    if a.protect_physical:
        opts.affinities.protect_physical = True
    if a.no_bosses:
        opts.bosses.shuffle = False
    if a.boss_hp:
        opts.bosses.hp = a.boss_hp
    if a.boss_unique_skills:
        opts.bosses.unique_skills = a.boss_unique_skills
    if a.mantras:
        opts.mantras.mode = a.mantras
    if a.no_heal_guarantee:
        opts.mantras.guarantee_heal = opts.mantras.guarantee_group_heal = False
    if a.chests:
        opts.chests.mode = a.chests
    if a.shops:
        opts.shops.mode = a.shops
    generate(a.src, a.dst, a.seed, opts, a.verify_iso)


if __name__ == "__main__":
    main()
