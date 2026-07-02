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
        state.world.monsters = [x for x in state.world.monsters if x is not m]
        if wild:
            state.log.add(f"You put down the {m.name.lower()}.", (200, 180, 150))
        else:
            state.bump("monsters_slain")
            skills.gain(state, "Combat", 20)
            state.log.add(f"You strike down the {m.name.lower()}!", (200, 220, 160))
            for drop in content.monster_drops(m.name, random):
                p.inventory.add(drop, 1)
                state.log.add(f"  It drops {drop.name.lower()}.", C.DIM)
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
_BREAKABLE = {"rock", "ore_vein", "gem_vein", "ruins_wall"}


def throw_bomb(state: GameState) -> None:
    p = state.player
    if p.inventory.count(items.BOMB) < 1:
        state.log.add("You have no bombs. (craft one: 1 Coal + 2 Fiber)", C.DIM)
        return
    if p.energy < C.BOMB_COST[0]:
        state.log.add("You're too winded to throw.", C.DIM)
        return

    fx, fy = p.facing
    bx, by = p.x, p.y
    for _ in range(5):                          # flies up to 5 tiles / until blocked
        nx, ny = bx + fx, by + fy
        if not state.world.in_bounds(nx, ny) or not state.world.walkable(nx, ny):
            break
        bx, by = nx, ny
        if mob_at(state, bx, by):
            break

    p.inventory.remove(items.BOMB, 1)
    p.energy = max(0, p.energy - C.BOMB_COST[0])
    state.log.add("You hurl a bomb — BOOM!", (236, 180, 90))

    for x in range(bx - 1, bx + 2):
        for y in range(by - 1, by + 2):
            if not state.world.in_bounds(x, y):
                continue
            m = mob_at(state, x, y)
            if m:
                m.hp -= BOMB_DAMAGE
            t = state.world.tile_at(x, y)
            if t.name in _BREAKABLE:
                _shatter(state, x, y, t)
    killed = sum(1 for m in state.world.monsters if not m.alive)
    if killed:
        from . import skills
        state.bump("monsters_slain", killed)
        skills.gain(state, "Combat", 12 * killed)
    state.world.monsters = [m for m in state.world.monsters if m.alive]

    from . import turns
    turns.advance_time(state, C.BOMB_COST[1])


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
