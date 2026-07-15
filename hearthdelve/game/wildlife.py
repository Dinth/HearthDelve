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

from ..engine import constants as C
from ..world import tile
from .state import GameState

WILDLIFE_CAP = C.WILDLIFE_CAP    # the Vale's rough carrying capacity (matches worldgen)
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
    season = state.season
    for m in state.world.monsters:
        if m.alive and m.x == x and m.y == y and present(m, season):
            # an out-of-season critter isn't really here, so it can't block
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


def _spooked(state: GameState) -> bool:
    """A firecracker's echo lingers: for a few days after one goes off, the
    wildlife keeps well clear of anything that smells of the farm."""
    return state.stats.get("wildlife_calm_until", 0) > state.day


def _eat_crops(state: GameState, m) -> bool:
    if _spooked(state):
        return False
    for cx, cy in [(m.x, m.y)] + _neighbours(m):
        plot = state.world.crops.get((cx, cy))
        if plot is not None and not plot.dead:
            del state.world.crops[(cx, cy)]
            _notice(state, m, f"A {m.name.lower()} nibbles your {plot.crop.name.lower()} to the ground!",
                    (224, 170, 110))
            return True
    return False


def _eat_berries(state: GameState, m) -> bool:
    if _spooked(state):
        return False
    for bx, by in _neighbours(m):
        if state.world.tile_at(bx, by).kind == "shrub_berry":
            btile = int(state.world.tiles[bx, by])
            state.world.tiles[bx, by] = tile.SHRUB
            from . import farming                    # stripped bushes re-berry, same as picking
            farming.schedule_berry_regrow(state, bx, by, btile)
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
            if mac.kind != "beehive" or not mac.has_queen:
                continue                          # empty hives hold no honey
            d = max(abs(hx - m.x), abs(hy - m.y))
            if d < best_d:
                best, best_d = (hx, hy), d
    return best


def _raid_hive(state: GameState, m, hx: int, hy: int) -> bool:
    if _spooked(state):
        return False
    mac = state.world.machines.get((hx, hy))
    if mac is None or mac.kind != "beehive" or not mac.has_queen:
        return False
    # a bear tears into the hive, setting the colony's honey-making right back
    mac.ready_at = state.abs_minutes + 480
    _notice(state, m, f"A {m.name.lower()} raids your beehive for honey!", (228, 150, 110))
    return True


HUNT_RANGE = 8                  # a predator arms itself when you stray this close


def _behave(state: GameState, m) -> None:
    p = state.player
    dist = max(abs(m.x - p.x), abs(m.y - p.y))
    skittish = m.behavior == "skittish"

    # Westreach predators hunt on sight — no provocation needed.
    if m.behavior == "predator" and not m.hostile and dist <= HUNT_RANGE:
        m.hostile = True

    if m.hostile and dist > CALM_DIST and m.behavior != "predator":
        m.hostile = False
    elif m.hostile and m.behavior == "predator" and dist > CALM_DIST + 6:
        m.hostile = False           # even a wolf gives up a long chase
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
        if (m.x, m.y) == (p.x, p.y):
            # a dormant critter can wake sharing the player's tile at a season
            # rollover — step it aside to the first free neighbour.
            for nx, ny in _neighbours(m):
                if _can_stand(state, nx, ny):
                    m.x, m.y = nx, ny
                    break
        if max(abs(m.x - p.x), abs(m.y - p.y)) > ACTIVE_RADIUS:
            m.energy = 0                        # dormant until you come near
            continue
        m.energy += m.speed
        while m.energy >= 2 and m.alive and p.hp > 0:   # stop piling on a downed player
            m.energy -= 2
            _behave(state, m)
    w.monsters = [m for m in w.monsters if m.alive]


def respawn(state: GameState, rng: random.Random) -> None:
    """A slow morning trickle of new critters into the Vale, so it doesn't
    permanently empty out as things are hunted or eaten. Called from new_day."""
    surf = state.surface
    if surf is None:
        return
    alive = sum(1 for m in surf.monsters if m.alive)
    if alive >= WILDLIFE_CAP:
        return
    from ..data import content
    from ..entities.monster import Mob
    cx, cy = C.WORLD_CENTER
    for _ in range(rng.randint(0, 2)):              # 0-2 arrivals a day
        for _try in range(30):
            x, y = rng.randint(4, surf.width - 5), rng.randint(4, surf.height - 5)
            if not surf.walkable(x, y) or surf.tile_at(x, y).kind in ("road", "bridge", "stairs"):
                continue
            if max(abs(x - cx), abs(y - cy)) < 20:  # not right on the farmyard
                continue
            if any(m.x == x and m.y == y for m in surf.monsters):
                continue                            # don't drop a critter onto another
            c = rng.choice(content.WILDLIFE)
            surf.monsters.append(Mob(c.name, c.glyph, c.color, c.hp, c.hp, c.speed, c.behavior, x, y,
                                     dv=c.dv, pv=c.pv, to_hit=c.to_hit, dmg=c.dmg,
                                     kind="wildlife", diet=c.diet, seasons=c.seasons,
                                     inflicts=c.inflicts))
            break


WEST_CAP = 22


def respawn_west(state: GameState, rng: random.Random) -> None:
    """The Westreach restocks itself the same slow way the Vale does — from
    its own, meaner bestiary. Called from new_day once the region exists."""
    west = state.west
    if west is None:
        return
    from ..data import content
    from ..entities.monster import Mob
    alive = sum(1 for m in west.monsters if m.alive)
    if alive >= WEST_CAP:
        return
    for _ in range(rng.randint(0, 2)):
        for _try in range(30):
            x, y = rng.randint(4, west.width - 5), rng.randint(4, west.height - 5)
            if not west.walkable(x, y):
                continue
            if any(m.x == x and m.y == y for m in west.monsters):
                continue
            c = rng.choice(content.WEST_WILDLIFE)
            west.monsters.append(Mob(c.name, c.glyph, c.color, c.hp, c.hp, c.speed,
                                     c.behavior, x, y, dv=c.dv, pv=c.pv, to_hit=c.to_hit,
                                     dmg=c.dmg, kind="wildlife", diet=c.diet,
                                     seasons=c.seasons, inflicts=c.inflicts))
            break
