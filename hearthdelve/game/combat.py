"""Light bump-combat, monster AI, and the Bomb ability (M4 Stage 2)."""
from __future__ import annotations

import random

from ..data import content
from ..engine import constants as C
from ..entities import items
from ..world import tile
from .state import GameState


def _sign(n: int) -> int:
    return (n > 0) - (n < 0)


def mob_at(state: GameState, x: int, y: int):
    for m in state.world.monsters:
        if m.alive and m.x == x and m.y == y:
            # a critter that's out of season isn't really here
            if m.seasons and state.season not in m.seasons:
                continue
            return m
    return None


# --- kills --------------------------------------------------------------------
def _on_kill(state: GameState, m, award_combat: bool = True) -> None:
    """Resolve a slain mob: removal, karma/XP, kill-count, and drops.

    Shared by the sword (``player_attack``) and the bomb (``throw_bomb``) so
    both obey the same rules. Peaceful surface wildlife costs karma and yields
    no XP or loot; a dungeon monster gains Combat XP, bumps the slain count and
    rolls its reagent drops.
    """
    from . import skills
    p = state.player
    state.world.monsters = [x for x in state.world.monsters if x is not m]
    if getattr(m, "kind", "monster") == "wildlife":
        if not getattr(m, "hostile", False):
            from . import karma
            karma.adjust(state, -2)  # slaying a peaceful creature is unkind
        state.log.add(f"You put down the {m.name.lower()}.", (200, 180, 150))
    else:
        state.bump("monsters_slain")
        if award_combat:
            skills.gain(state, "Combat", 20)
        state.log.add(f"You strike down the {m.name.lower()}!", (200, 220, 160))
        for drop in content.monster_drops(m.name, random):
            p.inventory.add(drop, 1)
            state.log.add(f"  It drops {drop.name.lower()}.", C.DIM)


# --- player attacks ----------------------------------------------------------
def player_attack(state: GameState, m) -> None:
    from . import skills
    p = state.player
    watk = content.WEAPON_STATS[p.weapon].atk if p.weapon in content.WEAPON_STATS else 0
    dmg = max(1, C.BASE_ATK + watk + skills.combat_atk_bonus(state) - m.defense + random.randint(-1, 1))
    m.hp -= dmg
    p.energy = max(0, p.energy - C.ATTACK_COST[0])
    wild = getattr(m, "kind", "monster") == "wildlife"
    if m.hp <= 0:
        _on_kill(state, m)
    elif wild:
        if m.behavior == "defensive":
            m.hostile = True
            state.log.add(f"The {m.name.lower()} rounds on you!", (224, 160, 110))
        else:
            state.log.add(f"You hit the {m.name.lower()} — it bolts!", C.DIM)
    else:
        skills.gain(state, "Combat", 4)
        state.log.add(f"You hit the {m.name.lower()} for {dmg}.")


# --- monster turns -----------------------------------------------------------
def monsters_act(state: GameState) -> None:
    w = state.world
    if not w.is_dungeon or not w.monsters:
        return
    from . import delve
    delve.update_fov(state)                     # act on an up-to-date FOV
    p = state.player
    for m in list(w.monsters):
        if not m.alive:
            continue
        if not m.awake and w.visible is not None and w.visible[m.x, m.y]:
            m.awake = True
        if not m.awake:
            continue
        m.energy += m.speed
        while m.energy >= 2 and m.alive and p.hp > 0:
            m.energy -= 2
            _step(state, m)
    w.monsters = [m for m in w.monsters if m.alive]


def _can_move(state: GameState, m, dx: int, dy: int) -> bool:
    nx, ny = m.x + dx, m.y + dy
    p = state.player
    if not state.world.walkable(nx, ny) or (nx, ny) == (p.x, p.y):
        return False
    return mob_at(state, nx, ny) is None


def _step(state: GameState, m) -> None:
    p = state.player
    if max(abs(m.x - p.x), abs(m.y - p.y)) == 1:
        _attack_player(state, m)
        return
    # bats flit erratically; wounded ones flee
    if m.behavior == "erratic" and random.random() < 0.45:
        dirs = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
        random.shuffle(dirs)
        for dx, dy in dirs:
            if _can_move(state, m, dx, dy):
                m.x += dx
                m.y += dy
                return
        return
    fleeing = m.behavior == "erratic" and m.hp <= m.max_hp * 0.35
    sx = _sign(p.x - m.x) * (-1 if fleeing else 1)
    sy = _sign(p.y - m.y) * (-1 if fleeing else 1)
    for ax, ay in ((sx, sy), (sx, 0), (0, sy)):
        if (ax or ay) and _can_move(state, m, ax, ay):
            m.x += ax
            m.y += ay
            return


def _attack_player(state: GameState, m) -> None:
    dmg = max(1, m.atk)
    state.player.hp -= dmg
    state.log.add(f"The {m.name.lower()} hits you for {dmg}!", (224, 140, 120))


# --- the Bomb ability --------------------------------------------------------
BOMB_DAMAGE = 8
BOMB_RANGE = 5                     # how far a bomb can be lobbed
_BREAKABLE = {"rock", "ore_vein", "gem_vein", "ruins_wall"}


def _line(x0: int, y0: int, x1: int, y1: int):
    """Bresenham cells from (x0,y0) to (x1,y1), excluding the start."""
    pts = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx - dy
    x, y = x0, y0
    while (x, y) != (x1, y1):
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
        pts.append((x, y))
    return pts


def bomb_landing(state: GameState, tx: int, ty: int) -> tuple[int, int]:
    """Where a bomb aimed at (tx, ty) actually detonates: it flies along the
    line from the player, stopping at the first wall (thunking short), a mob it
    strikes, the aimed tile, or its maximum range."""
    p = state.player
    bx, by = p.x, p.y
    for nx, ny in _line(p.x, p.y, tx, ty):
        if (max(abs(nx - p.x), abs(ny - p.y)) > BOMB_RANGE
                or not state.world.in_bounds(nx, ny)
                or not state.world.walkable(nx, ny)):
            break                               # can't fly past a wall / its range
        bx, by = nx, ny
        if mob_at(state, nx, ny) or (nx, ny) == (tx, ty):
            break
    return bx, by


def in_bomb_range(state: GameState, tx: int, ty: int) -> bool:
    return max(abs(tx - state.player.x), abs(ty - state.player.y)) <= BOMB_RANGE


def _detonate(state: GameState, bx: int, by: int) -> None:
    """Resolve the 3x3 blast at (bx, by): damage mobs, shatter rock/ore/gems."""
    hit = []
    for x in range(bx - 1, bx + 2):
        for y in range(by - 1, by + 2):
            if not state.world.in_bounds(x, y):
                continue
            m = mob_at(state, x, y)
            if m:
                m.awake = True                  # the blast rouses survivors
                m.hp -= BOMB_DAMAGE
                hit.append(m)
            t = state.world.tile_at(x, y)
            if t.name in _BREAKABLE:
                _shatter(state, x, y, t)
    for m in hit:                               # snapshot: _on_kill mutates the list
        if not m.alive:
            _on_kill(state, m)


def throw_bomb_at(state: GameState, tx: int, ty: int) -> bool:
    """Lob a bomb at an aimed tile (see targeting mode). Returns True if thrown."""
    p = state.player
    if p.inventory.count(items.BOMB) < 1:
        state.log.add("You have no bombs. (craft one: 1 Coal + 2 Fiber)", C.DIM)
        return False
    if p.energy < C.BOMB_COST[0]:
        state.log.add("You're too winded to throw.", C.DIM)
        return False
    if (tx, ty) == (p.x, p.y):
        state.log.add("Best not drop it at your own feet — aim away.", C.DIM)
        return False
    bx, by = bomb_landing(state, tx, ty)
    p.inventory.remove(items.BOMB, 1)
    p.energy = max(0, p.energy - C.BOMB_COST[0])
    state.log.add("You hurl a bomb — BOOM!", (236, 180, 90))
    _detonate(state, bx, by)
    from . import turns
    turns.advance_time(state, C.BOMB_COST[1])
    return True


def throw_bomb(state: GameState) -> bool:
    """Lob straight ahead (kept for convenience / callers without a target)."""
    fx, fy = state.player.facing
    return throw_bomb_at(state, state.player.x + fx * BOMB_RANGE, state.player.y + fy * BOMB_RANGE)


def _shatter(state: GameState, x: int, y: int, t) -> None:
    """A bomb breaks rock/ore/gem, dropping materials."""
    inv = state.player.inventory
    if t.name == "gem_vein":
        inv.add(content.random_gem(random), 1)
    elif t.name == "ore_vein":
        inv.add(content.ore_for_depth(state.world.depth, random), 1)
        if random.random() < 0.5:
            inv.add(items.COAL, 1)
    elif t.name in ("rock", "ruins_wall"):
        inv.add(items.STONE, 1)
    floor = tile.DUNGEON_FLOOR if state.world.is_dungeon else tile.GRASS
    state.world.tiles[x, y] = floor
