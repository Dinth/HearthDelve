"""Furnishing the farmhouse: what the loom's finest work, and a fair's ribbon,
are for once they're home.

A quilt goes on the bed and a tapestry on the wall (g, facing either, with one
in the pack). Each makes the house warmer to sleep in: you wake with stamina
over your usual full measure, the more for a finer piece. Prize ribbons are
pinned up on the wall beside it; a farm known for its ribbons sells its starred
goods a little dearer.

All of it lives in ``state.stats`` (plain counters, saved as they are):
``home_quilt`` and ``home_tapestry`` hold the piece's stars + 1 (0 = bare), and
``home_ribbons`` how many are pinned up.
"""
from __future__ import annotations

from ..engine import constants as C
from ..entities import items
from .state import GameState

QUILT, TAPESTRY, RIBBONS = "home_quilt", "home_tapestry", "home_ribbons"

# A piece's waking stamina: a plain one, and what each star adds.
COMFORT_BASE, COMFORT_PER_STAR = 6, 3
# Ribbons pinned up: each lifts what a STARRED good fetches at the bin.
RIBBON_BONUS, RIBBON_CAP = 0.02, 5

_WARM = (226, 196, 150)


def _piece_comfort(level: int) -> int:
    return COMFORT_BASE + COMFORT_PER_STAR * (level - 1) if level > 0 else 0


def comfort(state: GameState) -> int:
    """Stamina over the full measure that a night at home now gives."""
    return (_piece_comfort(state.stats.get(QUILT, 0))
            + _piece_comfort(state.stats.get(TAPESTRY, 0)))


def ribbons(state: GameState) -> int:
    return int(state.stats.get(RIBBONS, 0))


def ribbon_mult(state: GameState, quality: int) -> float:
    """What the pinned-up ribbons add to one unit's bin price. Plain goods get
    nothing: a ribbon is a name for quality, and it sells quality."""
    if quality <= 0:
        return 1.0
    return 1.0 + RIBBON_BONUS * min(RIBBON_CAP, ribbons(state))


def _stars(level: int) -> str:
    from . import skills
    return (" " + skills.stars(level - 1)) if level > 1 else ""


def _lay(state: GameState, item, key: str, done: str, same: str) -> bool:
    """Put the finest carried ``item`` in its place. The piece it replaces
    comes back to the pack at its own stars; a lesser one stays in the pack."""
    inv = state.player.inventory
    held = [ql for it, n, ql in inv.slots if it is item and n > 0]
    if not held:
        return False
    best, old = max(held) + 1, int(state.stats.get(key, 0))
    if best <= old:
        state.log.add(same, C.DIM)
        return True
    inv.remove(item, 1, quality=best - 1)
    if old:
        inv.add(item, 1, quality=old - 1)
    state.stats[key] = best
    state.log.add(done.format(stars=_stars(best), comfort=comfort(state)), _WARM)
    from . import turns
    turns.advance_time(state, C.USE_SECONDS)
    return True


def furnish(state: GameState, x: int, y: int) -> bool:
    """g at the farmhouse bed or one of its walls: lay a quilt, hang a
    tapestry, pin up a ribbon. True if (x, y) took, or pointedly refused,
    something — False if there was nothing to do there."""
    from . import husbandry
    surf = state.surface
    if state.world is not surf or surf is None or not surf.bed:
        return False
    t = surf.tile_at(x, y)
    if (x, y) == tuple(surf.bed):
        return _lay(state, items.QUILT, QUILT,
                    "You spread the quilt{stars} over your bed. You'll wake with "
                    "+{comfort} stamina now.",
                    "The quilt on your bed is every bit as fine as this one.")
    if t.name != "house_wall" or not husbandry.in_house(state, x, y):
        return False
    if _lay(state, items.WALL_TAPESTRY, TAPESTRY,
            "You hang the tapestry{stars} on the wall. The house keeps its warmth: "
            "you'll wake with +{comfort} stamina now.",
            "The tapestry on your wall is every bit as fine as this one."):
        return True
    return _pin_ribbon(state)


def _pin_ribbon(state: GameState) -> bool:
    inv = state.player.inventory
    if inv.count(items.FAIR_RIBBON) <= 0:
        return False
    n = ribbons(state)
    if n >= RIBBON_CAP:
        state.log.add(f"{RIBBON_CAP} ribbons hang there already — the wall can say no "
                      "more for you than it does.", C.DIM)
        return True
    inv.remove(items.FAIR_RIBBON, 1)
    state.stats[RIBBONS] = n + 1
    pct = round(RIBBON_BONUS * (n + 1) * 100)
    state.log.add(f"You pin the ribbon up where callers will see it. Word gets about: "
                  f"your starred goods fetch +{pct}% at the bin.", _WARM)
    return True


def describe_bed(state: GameState) -> str:
    lvl = int(state.stats.get(QUILT, 0))
    if not lvl:
        return "your bed. Sleep here (s) to end the day. A quilt would warm it (g)."
    return f"your bed, under a quilt{_stars(lvl)}. Sleep here (s) to end the day."


def describe_wall(state: GameState) -> str:
    lvl, n = int(state.stats.get(TAPESTRY, 0)), ribbons(state)
    hung = []
    if lvl:
        hung.append(f"a tapestry{_stars(lvl)}")
    if n:
        hung.append("a fair ribbon" if n == 1 else f"{n} fair ribbons")
    if not hung:
        return "the wall of your farmhouse."
    return f"the wall of your farmhouse, hung with {' and '.join(hung)}."
