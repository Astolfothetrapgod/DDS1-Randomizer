"""Generation of a randomized ISO: shared by the command line (__main__) and the window (gui).

The original ISO is never modified: it is copied to the output, then only battle/ENCOUNT.TBL,
UNIT.TBL, AICALC.TBL (AI and scripts), MSG.TBL (Analyze text), SKILL.TBL (unique boss skills option),
fld/f/bin/FLDALL.TBL (chests) and the executable SLUS_209.74 (mantras, shops) are rewritten in the copy
(same size). The spoiler log (seed + options + replacements) is written next to the copy.
"""
import random
import shutil
from pathlib import Path
from typing import Callable

from . import __version__
from .affinities import randomize_affinities
from .bosses import randomize_bosses, scale_unique_skills
from .bosses import spoiler as boss_spoiler
from .chests import CHEST_FILE, ChestTable, randomize_chests, read_item_names
from .chests import spoiler as chest_spoiler
from .enemies import random_encounters, randomize, species_pool, spoiler
from .iso import REDUMP_SIZE, GameISO
from .mantras import ELF, N_MANTRAS, MantraTable, randomize_mantras, read_mantra_names
from .mantras import spoiler as mantra_spoiler
from .options import Options
from .shops import ShopTable, item_values, randomize_shops
from .shops import spoiler as shop_spoiler
from .tables import (AiTable, AnalyzeText, Encounters, SkillTable, UnitTable, read_skill_names, read_skills,
                     read_units)


def new_seed() -> int:
    return random.randrange(1 << 32)


def generate(src: Path, dst: Path, seed: int | None, opts: Options, verify_iso: bool = False,
             log: Callable[[str], None] = print) -> Path:
    """Creates the randomized ISO `dst` from `src`; returns the path of the spoiler log.
    Raises ValueError / OSError with a message meant for the player."""
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        raise ValueError("the output must be a different file from the original ISO")
    seed = seed if seed is not None else new_seed()
    if not src.is_file():
        raise ValueError(f"ISO not found: {src}")
    game = GameISO(src)                       # also checks that this is DDS1 NTSC-U
    game.check_original()                       # used files = original ones (not an already randomized ISO)
    if verify_iso:
        log("Checking the whole ISO (Redump #253 hash)…")
        game.check_full()
        log("ISO matches the Redump dump.")
    free = shutil.disk_usage(dst.resolve().parent).free
    if free < REDUMP_SIZE and not (dst.exists() and dst.stat().st_size == REDUMP_SIZE):
        raise ValueError(f"not enough disk space for {dst}: {free // 2**20} MB free, "
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
    skill_table = SkillTable(game.read("battle/SKILL.TBL"))
    if boss and opts.bosses.unique_skills == "power":
        # skills of the mantras (the party's): never modified; the mantra shuffle only permutes them
        protected = {s for m in range(N_MANTRAS) for s in mantras.get(m).skills}
        scale_unique_skills(boss, skill_table, ai, units, skills, protected)
    item_names = read_item_names(msg)
    chests = ChestTable(game.read(CHEST_FILE))
    cres = randomize_chests(chests, item_names, seed, opts.chests.mode)
    mres = randomize_mantras(mantras, skill_names, seed, opts.mantras.mode, opts.mantras.level_spread,
                             opts.mantras.guarantee_heal, opts.mantras.guarantee_group_heal)
    values = item_values(game.read("battle/SKILL.TBL"))
    shops = ShopTable(mantras.data)             # same executable as the mantras
    sres = randomize_shops(shops, values, item_names, seed, opts.shops.mode, opts.shops.value_spread,
                           opts.shops.keep_ration)

    log(f"Copying {src} to {dst}…")
    shutil.copyfile(src, dst)
    out = GameISO(dst)
    out.write("battle/ENCOUNT.TBL", bytes(enc.data))
    out.write("battle/UNIT.TBL", bytes(table.data))
    out.write("battle/AICALC.TBL", bytes(ai.data))
    out.write("battle/MSG.TBL", bytes(text.data))
    out.write(ELF, bytes(mantras.data))
    out.write(CHEST_FILE, bytes(chests.data))
    out.write("battle/SKILL.TBL", bytes(skill_table.data))

    log_path = dst.with_name(f"{dst.stem}_spoiler_{seed}.txt")
    def shown(lines: list[str]) -> str:
        # "_" = line break of Atlus texts (shown as such in game): readable separator in the spoiler
        return " ".join(lines).replace("/_", "/").replace("_", " · ") or "-"
    aff_lines = ["", f"Affinities ({opts.affinities.mode}):"] + [
        f"  {units[i].name:<16} {shown(b)}  ->  {shown(a_)}" for i, (b, a_) in sorted(aff.items())]
    log_path.write_text(f"DDS1 Randomizer {__version__}\n" + spoiler(result, units, skills, opts.describe())
                   + "\n".join(aff_lines) + "\n"
                   + (boss_spoiler(boss, units, table, skills) if boss else "")
                   + mantra_spoiler(mres, mantras, skill_names) + chest_spoiler(cres, item_names)
                   + shop_spoiler(sres, values, item_names), encoding="utf-8")
    log(f"seed {seed}: {len(result.mapping)} species ({len(result.scaled)} rescaled), "
          f"{result.changed} encounters modified, {result.ai_changes} AI actions and {result.script_changes} "
          f"script skills adapted, {sum(map(len, result.summons.values()))} summons replaced, "
          f"{len(aff)} species with new affinities"
          + (f", {len(boss.mapping)} bosses moved" if boss else "")
          + (f", {len(boss.unique)} unique boss skills rescaled" if boss and boss.unique else "")
          + f", mantras: {opts.mantras.mode}, {len(cres.changes)} chests modified, shops: {opts.shops.mode}")
    log(f"spoiler: {log_path}")
    return log_path
