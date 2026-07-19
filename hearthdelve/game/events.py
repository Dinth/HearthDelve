"""Rare world events — days the valley surprises you.

Some mornings (a low, drifting chance, never a schedule) the world wakes
different: a caravan camps by a village, the sea boils with a shoal run, star-
stones fall in the wilds, the meadows burst into bloom, wolves come down from
the hills, or a village declares a fete. One event at most, announced at dawn
in the log, gone by the next morning. Everything is seeded from (world, day),
so a save reload wakes to the same world.

Per the design north star, events open opportunities or colour the day — they
never lock anything.
"""
from __future__ import annotations

import random

from ..engine import constants as C
from .state import GameState

_EVENT_CHANCE = 0.16          # per-dawn roll once the cooldown has passed
_COOLDOWN_DAYS = 3            # quiet days guaranteed between events
_ANNOUNCE = (240, 214, 140)   # dawn-announcement colour

# id -> (seasons it can occur in ("" = all year), base weight)
_EVENTS = {
    "caravan":  ((), 3),
    "shoal":    ((), 2),
    "starfall": ((), 2),
    "bloom":    (("Spring", "Summer"), 2),
    "flush":    (("Summer", "Fall"), 2),
    "wolves":   ((), 1),
    "fete":     ((), 2),
}
_WOLF_SEASON_WEIGHT = {"Fall": 3, "Winter": 4}   # the hungry months drive packs down


def is_active(state: GameState, eid: str) -> bool:
    return state.event.get("id") == eid


def fishing_bonus(state: GameState) -> float:
    """Extra catch chance while a shoal runs the coast."""
    return 0.25 if is_active(state, "shoal") else 0.0


def ship_mult(state: GameState) -> float:
    """Shipping-price multiplier while a caravan is buying."""
    return 1.25 if is_active(state, "caravan") else 1.0


def friendship_mult(state: GameState) -> int:
    """Friendship gains double on a fete-day."""
    return 2 if is_active(state, "fete") else 1


# --- the dawn roll -------------------------------------------------------------
def new_day(state: GameState) -> None:
    """Clear yesterday's event (walking any wolves back to the hills), then
    maybe roll today's. Called from farming.new_day after the weather is set."""
    _cleanup(state)
    state.event = {}
    surf = state.surface
    if surf is None:
        return
    rng = random.Random(state.seed * 9176 + state.day * 131)
    if state.day - state.stats.get("last_event_day", -99) < _COOLDOWN_DAYS:
        return
    if rng.random() > _EVENT_CHANCE:
        return
    pool = []
    for eid, (seasons, weight) in _EVENTS.items():
        if seasons and state.season not in seasons:
            continue
        if eid == "wolves":
            weight = _WOLF_SEASON_WEIGHT.get(state.season, weight)
        pool += [eid] * weight
    eid = rng.choice(pool)
    state.event = {"id": eid}
    state.stats["last_event_day"] = state.day
    _APPLY[eid](state, rng)


def _cleanup(state: GameState) -> None:
    """Yesterday's pack melts back into the hills (Ash Wolves never spawn in the
    home Vale on their own, so removing by name is exact)."""
    surf = state.surface
    if surf is not None and state.event.get("id") == "wolves":
        before = len(surf.monsters)
        surf.monsters = [m for m in surf.monsters if m.name != "Ash Wolf"]
        if len(surf.monsters) < before:
            state.log.add("The wolf-pack has slipped back into the hills.", C.DIM)


# --- per-event setup -------------------------------------------------------------
def _villages(state: GameState) -> list:
    return sorted(getattr(state.surface, "village_centers", {}).keys())


def _apply_caravan(state: GameState, rng) -> None:
    names = _villages(state) or ["the crossroads"]
    village = rng.choice(names)
    state.event["village"] = village
    state.log.add(f"A trading caravan has drawn its wagons up by {village}! They buy "
                  "handsomely — goods shipped today fetch a quarter more.", _ANNOUNCE)


def _apply_shoal(state: GameState, rng) -> None:
    state.log.add("Gulls wheel in clouds over the water — a great shoal runs the coast "
                  "today, and the fish all but leap at a line.", _ANNOUNCE)


def _compass(dx: int, dy: int) -> str:
    ns = "south" if dy > 0 else "north"
    ew = "east" if dx > 0 else "west"
    if abs(dx) > 2 * abs(dy):
        return ew
    if abs(dy) > 2 * abs(dx):
        return ns
    return ns + "-" + ew


def _apply_starfall(state: GameState, rng) -> None:
    from ..world import tile
    from .farming import _NATURAL_GROUND
    surf = state.surface
    centers = list(getattr(surf, "village_centers", {}).values())
    home = surf.bed or surf.spawn
    stamped = []
    want = rng.randint(5, 9)
    for _ in range(400):
        if len(stamped) >= want:
            break
        x = rng.randint(4, surf.width - 5)
        y = rng.randint(4, surf.height - 5)
        if surf.tiles[x, y] not in _NATURAL_GROUND:
            continue
        if any(abs(x - vx) + abs(y - vy) < 25 for vx, vy in centers):
            continue                                  # keep falls out in the wilds
        if abs(x - home[0]) + abs(y - home[1]) < 12:
            continue
        if (x, y) in surf.crops or (x, y) in surf.machines or (x, y) in surf.trees:
            continue
        surf.tiles[x, y] = tile.GEM_VEIN if rng.random() < 0.35 else tile.ORE_VEIN
        stamped.append((x, y))
    state.event["fell"] = len(stamped)
    where = ""
    if stamped:
        sx, sy = stamped[0]
        where = f" — away to the {_compass(sx - home[0], sy - home[1])}, by the smoke trails"
    state.log.add("Streaks of light crossed the sky in the night. Fresh-fallen crags "
                  f"glint in the wilds{where}. Worth a walk with a pickaxe.", _ANNOUNCE)


def _sprout_all(state: GameState, attr: str) -> int:
    from .farming import _NATURAL_GROUND
    surf = state.surface
    n = 0
    for x, y, species, base in getattr(surf, attr, ()) or ():
        if surf.tiles[x, y] in _NATURAL_GROUND:
            surf.tiles[x, y] = species
            n += 1
    return n


def _apply_bloom(state: GameState, rng) -> None:
    _sprout_all(state, "flower_spots")
    _sprout_all(state, "herb_spots")
    state.log.add("The meadows have burst into bloom overnight — flowers and wild "
                  "herbs everywhere you look. A gathering day if ever there was one.",
                  _ANNOUNCE)


def _apply_flush(state: GameState, rng) -> None:
    _sprout_all(state, "mushroom_spots")
    state.log.add("Rain-warm earth: mushrooms have pushed up everywhere overnight. "
                  "The foragers are already out with baskets.", _ANNOUNCE)


def _apply_wolves(state: GameState, rng) -> None:
    from ..data import content
    from ..entities.monster import Mob
    from .farming import _NATURAL_GROUND
    surf = state.surface
    home = surf.bed or surf.spawn
    wolf = next(c for c in content.WEST_WILDLIFE if c.name == "Ash Wolf")
    packed = 0
    for _ in range(300):
        if packed >= rng.randint(4, 6):
            break
        x = home[0] + rng.randint(-45, 45)
        y = home[1] + rng.randint(-45, 45)
        if not surf.in_bounds(x, y) or surf.tiles[x, y] not in _NATURAL_GROUND:
            continue
        if abs(x - home[0]) + abs(y - home[1]) < 18:   # never at the doorstep
            continue
        surf.monsters.append(Mob(wolf.name, wolf.glyph, wolf.color, wolf.hp, wolf.hp,
                                 wolf.speed, wolf.behavior, x, y, dv=wolf.dv, pv=wolf.pv,
                                 to_hit=wolf.to_hit, dmg=wolf.dmg, kind="wildlife",
                                 inflicts=wolf.inflicts))
        packed += 1
    state.log.add("Wolf-song echoed down from the hills in the night — a pack prowls "
                  "the valley today. Mind the far fields, or meet them armed: wolf "
                  "pelts tan into fine leather.", _ANNOUNCE)


def _apply_fete(state: GameState, rng) -> None:
    names = _villages(state) or ["the valley"]
    village = rng.choice(names)
    state.event["village"] = village
    state.log.add(f"{village} has declared a fete-day — song on the square and doors "
                  "thrown open! Friendships warm twice as fast today.", _ANNOUNCE)


_APPLY = {"caravan": _apply_caravan, "shoal": _apply_shoal, "starfall": _apply_starfall,
          "bloom": _apply_bloom, "flush": _apply_flush, "wolves": _apply_wolves,
          "fete": _apply_fete}
