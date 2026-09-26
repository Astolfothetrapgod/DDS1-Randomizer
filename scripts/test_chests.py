#!/usr/bin/env python3
"""Chest test (fld/f/bin/FLDALL.TBL at 0xDAD8, 256 × 16 bytes, NOTES "Items, chests, shops").

Modifies an already randomized ISO in place: every normal chest without trap or fixed item -> Soma ×9,
every gem box -> Megido Fire ×1, every Macca chest -> 7777 Macca. Any chest opened in game must therefore
give one of these contents (evidence that the game reads this table).

Usage: python scripts/test_chests.py work/dds1_test.iso   (after python -m randomizer …)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from randomizer.chests import CHEST_FILE, ChestTable, groups  # noqa: E402
from randomizer.iso import GameISO  # noqa: E402

SOMA, MEGIDO_FIRE, MACCA = 12, 53, 7777


def main(path: str) -> None:
    game = GameISO(path)
    table = ChestTable(game.read(CHEST_FILE))
    g = groups(table)
    for c in g["chests"]:
        table.set_item(c, SOMA, 9)
    for c in g["gem_boxes"]:
        table.set_item(c, MEGIDO_FIRE, 1)
    for c in g["macca"]:
        table.set_value(c, MACCA)
    game.write(CHEST_FILE, bytes(table.data))
    print({k: len(v) for k, v in g.items()}, "chests marked")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
