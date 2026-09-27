"""DDS1 Randomizer — command line.

Usage: python -m randomizer ORIGINAL_ISO OUTPUT_ISO [--seed N] [--preset file.toml] [options]

The original ISO is never modified: it is copied to OUTPUT_ISO, then only battle/ENCOUNT.TBL,
UNIT.TBL, AICALC.TBL (AI and scripts), MSG.TBL (Analyze text), fld/f/bin/FLDALL.TBL (chests) and the
executable SLUS_209.74 (mantras, shops) are rewritten in the copy (same size).
The spoiler log (seed + options + replacements) is written next to the copy.
Command-line options override the preset file.
"""
import argparse
import random
import shutil
import sys
from pathlib import Path

from . import __version__
from .affinities import randomize_affinities
from .bosses import randomize_bosses
from .bosses import spoiler as boss_spoiler
from .chests import CHEST_FILE, ChestTable, randomize_chests, read_item_names
from .chests import spoiler as chest_spoiler
from .enemies import random_encounters, randomize, species_pool, spoiler
from .iso import REDUMP_SIZE, GameISO
from .mantras import ELF, MantraTable, randomize_mantras, read_mantra_names
from .mantras import spoiler as mantra_spoiler
from .options import Options
from .shops import ShopTable, item_values, randomize_shops
from .shops import spoiler as shop_spoiler
from .tables import AiTable, AnalyzeText, Encounters, UnitTable, read_skill_names, read_skills, read_units


def main() -> None:
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
    ap.add_argument("--mantras", choices=("tiered", "random", "original"), help="mantra skills")
    ap.add_argument("--no-heal-guarantee", action="store_true",
                    help="guarantee neither Dia at level 1 nor Media at level 15 or lower")
    ap.add_argument("--chests", choices=("shuffle", "random", "original"), help="chest contents")
    ap.add_argument("--shops", choices=("tiered", "random", "original"), help="shop items")
    a = ap.parse_args()

    if a.src.resolve() == a.dst.resolve():
        raise ValueError("the output must be a different file from the original ISO")
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
    if a.mantras:
        opts.mantras.mode = a.mantras
    if a.no_heal_guarantee:
        opts.mantras.guarantee_heal = opts.mantras.guarantee_group_heal = False
    if a.chests:
        opts.chests.mode = a.chests
    if a.shops:
        opts.shops.mode = a.shops
    seed = a.seed if a.seed is not None else random.randrange(1 << 32)

    if not a.src.is_file():
        raise ValueError(f"ISO not found: {a.src}")
    game = GameISO(a.src)                       # also checks that this is DDS1 NTSC-U
    game.check_original()                       # used files = original ones (not an already randomized ISO)
    if a.verify_iso:
        print("Checking the whole ISO (Redump #253 hash)…")
        game.check_full()
        print("ISO matches the Redump dump.")
    free = shutil.disk_usage(a.dst.resolve().parent).free
    if free < REDUMP_SIZE and not (a.dst.exists() and a.dst.stat().st_size == REDUMP_SIZE):
        raise ValueError(f"not enough disk space for {a.dst}: {free // 2**20} MB free, "
                         f"{REDUMP_SIZE // 2**20} MB needed")
    unit_data = game.read("battle/UNIT.TBL")
    msg = game.read("battle/MSG.TBL")
    units = read_units(unit_data, msg)
    skills = read_skills(game.read("battle/SKILL.TBL"), msg)
    enc = Encounters(game.read("battle/ENCOUNT.TBL"))
    table = UnitTable(unit_data)
    ai = AiTable(game.read("battle/AICALC.TBL"))
    text = AnalyzeText(msg)
    # species of random battles, computed before the shuffle modifies the encounters
    species = [s.id for s in species_pool(enc, random_encounters(enc), units)]
    mode = opts.enemy_skills.mode
    result = randomize(enc, table, units, seed, opts.enemies,
                       skills if mode != "original" else None, ai, mode)
    aff = randomize_affinities(table, text, species, seed, opts.affinities.mode, opts.affinities.protect_physical)
    # after the enemies: a boss summoning a shuffled species targets its rescaled level
    boss = randomize_bosses(enc, table, ai, units, skills if mode != "original" else None, seed, opts.bosses.hp) \
        if opts.bosses.shuffle else None
    skill_names = read_skill_names(msg)
    mantras = MantraTable(game.read(ELF), read_mantra_names(msg))
    item_names = read_item_names(msg)
    chests = ChestTable(game.read(CHEST_FILE))
    cres = randomize_chests(chests, item_names, seed, opts.chests.mode)
    mres = randomize_mantras(mantras, skill_names, seed, opts.mantras.mode, opts.mantras.level_spread,
                             opts.mantras.guarantee_heal, opts.mantras.guarantee_group_heal)
    values = item_values(game.read("battle/SKILL.TBL"))
    shops = ShopTable(mantras.data)             # same executable as the mantras
    sres = randomize_shops(shops, values, item_names, seed, opts.shops.mode, opts.shops.value_spread,
                           opts.shops.keep_ration)

    print(f"Copying {a.src} to {a.dst}…")
    shutil.copyfile(a.src, a.dst)
    out = GameISO(a.dst)
    out.write("battle/ENCOUNT.TBL", bytes(enc.data))
    out.write("battle/UNIT.TBL", bytes(table.data))
    out.write("battle/AICALC.TBL", bytes(ai.data))
    out.write("battle/MSG.TBL", bytes(text.data))
    out.write(ELF, bytes(mantras.data))
    out.write(CHEST_FILE, bytes(chests.data))

    log = a.dst.with_name(f"{a.dst.stem}_spoiler_{seed}.txt")
    def shown(lines: list[str]) -> str:
        # "_" = line break of Atlus texts (shown as such in game): readable separator in the spoiler
        return " ".join(lines).replace("/_", "/").replace("_", " · ") or "-"
    aff_lines = ["", f"Affinities ({opts.affinities.mode}):"] + [
        f"  {units[i].name:<16} {shown(b)}  ->  {shown(a_)}" for i, (b, a_) in sorted(aff.items())]
    log.write_text(f"DDS1 Randomizer {__version__}\n" + spoiler(result, units, skills, opts.describe())
                   + "\n".join(aff_lines) + "\n"
                   + (boss_spoiler(boss, units, table) if boss else "")
                   + mantra_spoiler(mres, mantras, skill_names) + chest_spoiler(cres, item_names)
                   + shop_spoiler(sres, values, item_names), encoding="utf-8")
    print(f"seed {seed}: {len(result.mapping)} species ({len(result.scaled)} rescaled), "
          f"{result.changed} encounters modified, {result.ai_changes} AI actions and {result.script_changes} "
          f"script skills adapted, {sum(map(len, result.summons.values()))} summons replaced, "
          f"{len(aff)} species with new affinities"
          + (f", {len(boss.mapping)} bosses moved" if boss else "")
          + f", mantras: {opts.mantras.mode}, {len(cres.changes)} chests modified, shops: {opts.shops.mode}")
    print(f"spoiler: {log}")


if __name__ == "__main__":
    main()
