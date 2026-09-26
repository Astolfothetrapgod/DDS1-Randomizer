"""Rescaling a species to another level.

Model measured on the species of random battles: value ≈ c × level^k, one exponent k per value
(HP, MP, each stat). It is recomputed on every run from the player's ISO (linear regression on
log/log).

To bring B to the level of A: v' = v_B × (level_A / level_B)^k. B keeps its "personality" (sturdier
or weaker than average), at the right scale.
"""
import math
from dataclasses import dataclass

from .tables import STATS, Unit

MAX_HP_MP = 32767          # largest value seen in the game (placeholder records)
MAX_STAT = 99


@dataclass(frozen=True)
class Exponents:
    hp: float
    mp: float
    stats: tuple[float, ...]


def _slope(xs: list[float], ys: list[float]) -> float:
    """Slope of the linear regression of ys on xs (least squares)."""
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    var = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var


def fit(pool: list[Unit]) -> Exponents:
    def k(values: list[int]) -> float:
        pts = [(math.log(u.level), math.log(v)) for u, v in zip(pool, values) if v > 0 and u.level > 0]
        return _slope([p[0] for p in pts], [p[1] for p in pts])
    return Exponents(k([u.hp for u in pool]), k([u.mp for u in pool]),
                     tuple(k([u.stats[s] for u in pool]) for s in range(len(STATS))))


def scale(b: Unit, level: int, e: Exponents) -> tuple[int, int, tuple[int, ...]]:
    """(HP, MP, stats) of B brought to level `level`."""
    ratio = level / b.level

    def sc(v: int, k: float, hi: int, lo: int) -> int:
        if v == 0:
            return 0
        return max(lo, min(hi, round(v * ratio ** k)))

    return (sc(b.hp, e.hp, MAX_HP_MP, 1), sc(b.mp, e.mp, MAX_HP_MP, 0),
            tuple(sc(v, k, MAX_STAT, 1) for v, k in zip(b.stats, e.stats)))
