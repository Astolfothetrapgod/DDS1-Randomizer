#!/usr/bin/env python3
"""Tests of the mantra table (executable SLUS_209.74, 0x2917B4, NOTES "Mantras").

Test 1 (✅ skills, ❌ price): Ice Demon (26) -> Media + Mabufu, +0x04 1500 -> 3000: Media shown, price still
  2500 -> +0x04 is not the price (it is the AP to earn, test 4).
Test 2 (✅ +0x00 = difficulty; Ice Demon required level 5 -> 15: disappears from the grid).
Test 3 (❌ badly designed test): Devourer at 1 AP, but Devourer was already mastered in the save: skills are
  given to the character when it masters the mantra, not read from the table afterwards.
Test 4 (✅, current): already randomized ISO (seed 2523) modified in place: Devourer, Fire Spirit (20) and Ice
  Demon (26) at 1 AP; PCSX2 cheat: 50,000 Macca (u32 at 0x0114133C, found by comparing 2 savestates: 9 then
  17 Macca). Expected: buy Fire Spirit / Ice Demon, equip it, 1 battle -> mastered -> Serph learns its skills
  (seed 2523: Fire Spirit = Void Elec + Dia; Ice Demon = Devour + Raving Slash).

Usage: python scripts/test_mantra.py work/dds1_test.iso work/   (after python -m randomizer …)
       writes the cheat work/SLUS-20974_<CRC>.pnach, to copy into ~/.config/PCSX2/cheats/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from randomizer.iso import GameISO, pcsx2_crc  # noqa: E402
from randomizer.mantras import ELF, MantraTable, read_mantra_names  # noqa: E402

ONE_AP = (1, 20, 26)                    # Devourer, Fire Spirit, Ice Demon
MACCA, MACCA_ADDR = 50000, 0x0114133C


def main(path: str, outdir: str) -> None:
    game = GameISO(path)
    table = MantraTable(game.read(ELF), read_mantra_names(game.read("battle/MSG.TBL")))
    for m in ONE_AP:
        table.set_field(m, "ap", 1)
        print(table.get(m))
    game.write(ELF, bytes(table.data))
    crc = pcsx2_crc(bytes(table.data))
    cheat = Path(outdir) / f"SLUS-20974_{crc:08X}.pnach"
    cheat.write_text("gametitle=Shin Megami Tensei: Digital Devil Saga (SLUS-20974, test ISO)\n\n"
                     "[Mantra test 4: 50000 Macca]\n"
                     "description=Macca locked at 50000 (randomizer test)\n"
                     f"patch=1,EE,{MACCA_ADDR:08X},word,{MACCA:08X}\n")
    print(f"PCSX2 CRC {crc:08X} -> {cheat}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
