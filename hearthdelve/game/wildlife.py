"""Surface wildlife: roaming critters that give the overworld some life.

Ticked from ``turns.advance_time`` whenever time passes on the surface (the
mirror of ``combat.monsters_act`` for dungeons). Critters only simulate near
the player — a far-off rabbit sits idle until you wander back into its patch,
which keeps the sim cheap and means your farm is safe while you're away.

Behaviours:
  * skittish  — wanders; flees when the player comes within FLEE_RANGE.
  * defensive — wanders; ignores the player until struck, then (via
                ``combat.player_attack`` setting ``hostile``) charges and
                fights back until you leave it well alone.

Diet decides what they raid: "crops" (any sown plot they can reach — fenced
plots are naturally safe, since a critter can't walk through a fence) or
"berries" (ripe berry shrubs, stripped back to a plain shrub).
"""
from __future__ import annotations

import random

from ..world import tile
from .state import GameState

FLEE_RANGE = 5        # skittish critters shy away inside this Chebyshev distance
PANIC_RANGE = 2       # ...but a feeding critter only bolts at point-blank range
FORAGE_RADIUS = 8     # how far a hungry critter will spot and stalk toward food
ACTIVE_RADIUS = 28    # critters beyond this idle (just outside a big viewport)
WANDER_CHANCE = 0.6   # chance an idle critter ambles a step
CALM_DIST = 12        # a roused critter settles once the player is this far off
NOTICE_DIST = 12      # only log a critter's antics when it's near the player


def _sign(n: int) -> int:
    return (n > 0) - (n < 0)


def _occupied(state: GameState, x: int, y: int) -> bool:
    for m in state.world.monsters:
        if m.alive and m.x == x and m.y == y:
            return True
    return False


def _can_stand(state: GameState, x: int, y: int) -> bool:
    p = state.player
    return (state.world.walkable(x, y) and (x, y) != (p.x, p.y)
            and not _occupied(state, x, y))


def _move(state: GameState, m, dx: int, dy: int) -> bool:
    if (dx or dy) and _can_stand(state, m.x + dx, m.y + dy):
        m.x += dx
        m.y += dy
        return True
    return False


def _toward(state: GameState, m, tx: int, ty: int, away: bool = False) -> bool:
    sx, sy = _sign(tx - m.x), _sign(ty - m.y)
    if away:
        sx, sy = -sx, -sy
    for ax, ay in ((sx, sy), (sx, 0), (0, sy)):
        if _move(state, m, ax, ay):
            return True
    return False


def _wander(state: GameState, m) -> None:
    if random.random() > WANDER_CHANCE:
        return
    dirs = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
    random.shuffle(dirs)
    for dx, dy in dirs:
        if _move(state, m, dx, dy):
            return


def _neighbours(m):
    return [(m.x + dx, m.y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def _notice(state: GameState, m, msg: str, color=(180, 170, 120)) -> None:
    p = state.player
    if max(abs(m.x - p.x), abs(m.y - p.y)) <= NOTICE_DIST:
        state.log.add(msg, color)


def _eat_crops(state: GameState, m) -> bool:
    for cx, cy in [(m.x, m.y)] + _neighbours(m):
        plot = state.world.crops.get((cx, cy))
        if plot is not None and not plot.dead:
            del state.world.crops[(cx, cy)]
            _notice(state, m, f"A {m.name.lower()} nibbles your {plot.crop.name.lower()} to the ground!",
                    (224, 170, 110))
            return True
    return False


def _eat_berries(state: GameState, m) -> bool:
    for bx, by in _neighbours(m):
        if state.world.tile_at(bx, by).kind == "shrub_berry":
            state.world.tiles[bx, by] = tile.SHRUB
            _notice(state, m, f"A {m.name.lower()} strips a berry shrub bare.", (200, 170, 120))
            return True
    return False


def _nearest_food(state: GameState, m):
    """Closest reachable morsel of this critter's diet within FORAGE_RADIUS."""
    best, best_d = None, FORAGE_RADIUS + 1
    if m.diet == "crops":
        for (cx, cy), plot in state.world.crops.items():
            if plot.dead:
                continue
            d = max(abs(cx - m.x), abs(cy - m.y))
            if d < best_d:
                best, best_d = (cx, cy), d
    elif m.diet == "berries":
        for dx in range(-FORAGE_RADIUS, FORAGE_RADIUS + 1):
            for dy in range(-FORAGE_RADIUS, FORAGE_RADIUS + 1):
                x, y = m.x + dx, m.y + dy
                if state.world.in_bounds(x, y) and state.world.tile_at(x, y).kind == "shrub_berry":
                    d = max(abs(dx), abs(dy))
                    if d < best_d:
                        best, best_d = (x, y), d
    elif m.diet == "honey":                       # bears make for beehives
        for (hx, hy), mac in state.world.machines.items():
            if mac.kind != "beehive":
                continue
            d = max(abs(hx - m.x), abs(hy - m.y))
            if d < best_d:
                best, best_d = (hx, hy), d
    return best


def _raid_hive(state: GameState, m, hx: int, hy: int) -> bool:
    mac = state.world.machines.get((hx, hy))
    if mac is None or mac.kind != "beehive":
        return False
    # a bear tears into the hive, setting the colony's honey-making right back
    mac.ready_at = state.abs_minutes + 480
    _notice(state, m, f"A {m.name.lower()} raids your beehive for honey!", (228, 150, 110))
    return True


def _behave(state: GameState, m) -> None:
    p = state.player
    dist = max(abs(m.x - p.x), abs(m.y - p.y))
    skittish = m.behavior == "skittish"

    if m.hostile and dist > CALM_DIST:
        m.hostile = False
    if m.hostile:
        if dist == 1:
            from .combat import _attack_player
            _attack_player(state, m)
        else:
            _toward(state, m, p.x, p.y)
        return

    # Point-blank: even a brave grazer bolts if you're right on top of it.
    if skittish and dist <= PANIC_RANGE:
        _toward(state, m, p.x, p.y, away=True)
        return

    # Foragers stalk toward the nearest food and raid it once adjacent. A
    # defensive boar roots up crops fearlessly; a skittish grazer keeps a
    # little distance from the player but will still work an unfenced field.
    if m.diet:
        food = _nearest_food(state, m)
        if food is not None:
            fx, fy = food
            if max(abs(fx - m.x), abs(fy - m.y)) <= 1:
                if (m.diet == "crops" and _eat_crops(state, m)) or \
                   (m.diet == "berries" and _eat_berries(state, m)) or \
                   (m.diet == "honey" and _raid_hive(state, m, fx, fy)):
                    return
            elif not skittish or dist > PANIC_RANGE:
                if _toward(state, m, fx, fy):
                    return

    if skittish and dist <= FLEE_RANGE:
        _toward(state, m, p.x, p.y, away=True)
        return

    _wander(state, m)


def present(m, season: str) -> bool:
    """Whether a critter is out and about this season (empty seasons = always)."""
    return not getattr(m, "seasons", ()) or season in m.seasons


def act(state: GameState) -> None:
    """Advance every nearby critter by its speed. No-op in dungeons."""
    w = state.world
    if w.is_dungeon or not w.monsters:
        return
    p = state.player
    season = state.season
    for m in list(w.monsters):
        if not m.alive or not present(m, season):
            continue
        if max(abs(m.x - p.x), abs(m.y - p.y)) > ACTIVE_RADIUS:
            m.energy = 0                        # dormant until you come near
            continue
        m.energy += m.speed
        while m.energy >= 2 and m.alive:
            m.energy -= 2
            _behave(state, m)
    w.monsters = [m for m in w.monsters if m.alive]
