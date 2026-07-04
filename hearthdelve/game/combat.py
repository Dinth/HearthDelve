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


# --- combat stats (ADOM-style: to-hit vs DV, then damage - PV) ---------------
BASE_DV = 8              # a bare, unskilled defender's Defensive Value


def held_profile(state: GameState):
    """The combat profile of whatever the player is holding (a tool fights, but
    badly; a real weapon fights well; bare hands / seed pouch = unarmed)."""
    return content.profile_of(state.player.active_tool)


def _worn(state: GameState):
    dv = pv = 0
    for it in state.player.equipment.values():
        stats = content.ARMOR_STATS.get(it)
        if stats:
            dv += stats[0]
            pv += stats[1]
    return dv, pv


def player_dv(state: GameState) -> int:
    from . import skills
    prof = held_profile(state)
    wdv, _ = _worn(state)
    lvl = skills.mastery_level(state, prof.category)
    return (BASE_DV + skills.skill_level(state, "Combat")   # Dodge
            + prof.dv + wdv + skills.mastery_parry(lvl))


def player_pv(state: GameState) -> int:
    return _worn(state)[1]


def player_to_hit(state: GameState) -> int:
    from . import skills
    prof = held_profile(state)
    lvl = skills.mastery_level(state, prof.category)
    bonus = prof.to_hit + skills.skill_level(state, "Combat") // 2 + skills.mastery_to_hit(lvl)
    if skills.active_buff(state) == "hearty":
        bonus += 2
    return bonus


def player_crit(state: GameState) -> float:
    from . import skills
    lvl = skills.mastery_level(state, held_profile(state).category)
    return 0.03 + skills.skill_level(state, "Combat") * 0.01 + skills.mastery_crit(lvl)


def _resolve(to_hit: int, dmg_range, dmg_bonus: int, crit_chance: float,
             target_dv: int, target_pv: int):
    """One attack. Returns (damage, crit) if it lands, or None on a miss. A crit
    doubles the damage and ignores Protection."""
    if random.randint(1, 20) + to_hit < target_dv:
        return None
    dmg = random.randint(dmg_range[0], dmg_range[1]) + dmg_bonus
    if random.random() < crit_chance:
        return dmg * 2, True
    return max(0, dmg - target_pv), False


# --- player attacks ----------------------------------------------------------
def player_attack(state: GameState, m) -> None:
    from . import skills
    p = state.player
    prof = held_profile(state)
    p.energy = max(0, p.energy - C.ATTACK_COST[0])
    dmg_bonus = skills.mastery_dmg(skills.mastery_level(state, prof.category))
    res = _resolve(player_to_hit(state), prof.dmg, dmg_bonus, player_crit(state), m.dv, m.pv)
    wild = getattr(m, "kind", "monster") == "wildlife"

    if res is None:
        state.log.add(f"You swing at the {m.name.lower()} and miss.", C.DIM)
        if wild and m.behavior == "defensive":
            m.hostile = True
        m.awake = True
        return

    dmg, crit = res
    skills.gain_mastery(state, prof.category, 3)     # learn by doing
    m.awake = True
    if wild and m.behavior == "defensive":
        m.hostile = True
    if dmg <= 0:
        state.log.add(f"Your blow glances off the {m.name.lower()}'s hide.", C.DIM)
        return
    m.hp -= dmg
    if m.hp <= 0:
        _on_kill(state, m)
        return
    if wild and not m.hostile:
        state.log.add(f"You hit the {m.name.lower()} for {dmg} — it bolts!", C.DIM)
    else:
        lead = "A critical hit! " if crit else ""
        state.log.add(f"{lead}You hit the {m.name.lower()} for {dmg}.",
                      (240, 220, 140) if crit else C.WHITE)
        if not wild:
            skills.gain(state, "Combat", 4)


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


def _dist(m, p) -> int:
    return max(abs(m.x - p.x), abs(m.y - p.y))


def _move_toward(state: GameState, m, away: bool = False) -> bool:
    p = state.player
    sx = _sign(p.x - m.x) * (-1 if away else 1)
    sy = _sign(p.y - m.y) * (-1 if away else 1)
    for ax, ay in ((sx, sy), (sx, 0), (0, sy)):
        if (ax or ay) and _can_move(state, m, ax, ay):
            m.x += ax
            m.y += ay
            return True
    return False


def _step(state: GameState, m) -> None:
    p = state.player
    if _dist(m, p) == 1:
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
    # a "charge" monster lunges — an extra stride when closing from nearby, so
    # it covers ground and reaches you fast once roused.
    strides = 2 if (m.behavior == "charge" and not fleeing and 2 <= _dist(m, p) <= 4) else 1
    for _ in range(strides):
        if _dist(m, p) == 1:
            _attack_player(state, m)
            return
        if not _move_toward(state, m, away=fleeing):
            return


def _attack_player(state: GameState, m) -> None:
    res = _resolve(m.to_hit, m.dmg, 0, 0.0, player_dv(state), player_pv(state))
    if res is None:
        state.log.add(f"The {m.name.lower()} lunges — you dodge.", C.DIM)
        return
    dmg, _crit = res
    if dmg <= 0:
        state.log.add(f"The {m.name.lower()} strikes, but your armour holds.", C.DIM)
        return
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


def projectile_landing(state: GameState, tx: int, ty: int, rng: int) -> tuple[int, int]:
    """Where a projectile aimed at (tx, ty) actually lands: it flies along the
    line from the player, stopping at the first wall (thunking short), a mob it
    strikes, the aimed tile, or its maximum range."""
    p = state.player
    bx, by = p.x, p.y
    for nx, ny in _line(p.x, p.y, tx, ty):
        if (max(abs(nx - p.x), abs(ny - p.y)) > rng
                or not state.world.in_bounds(nx, ny)
                or not state.world.walkable(nx, ny)):
            break                               # can't fly past a wall / its range
        bx, by = nx, ny
        if mob_at(state, nx, ny) or (nx, ny) == (tx, ty):
            break
    return bx, by


def bomb_landing(state: GameState, tx: int, ty: int) -> tuple[int, int]:
    return projectile_landing(state, tx, ty, BOMB_RANGE)


def in_range(state: GameState, tx: int, ty: int, rng: int) -> bool:
    return max(abs(tx - state.player.x), abs(ty - state.player.y)) <= rng


def in_bomb_range(state: GameState, tx: int, ty: int) -> bool:
    return in_range(state, tx, ty, BOMB_RANGE)


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


# --- ranged weapons (bows & sling) -------------------------------------------
def equipped_ranged(state: GameState):
    """The (weapon, stat) in the ranged slot whose ammo you actually carry, or
    None — so a bow with an empty quiver falls back to hand-thrown bombs."""
    it = state.player.equipment.get("ranged")
    stat = content.ranged_stat(it) if it else None
    if stat is None or state.player.inventory.count(stat.ammo) < 1:
        return None
    return it, stat


def can_fire(state: GameState) -> bool:
    """True if the player can loose a shot (bow+ammo) or throw a bomb."""
    return equipped_ranged(state) is not None or state.player.inventory.count(items.BOMB) >= 1


def aim_purpose(state: GameState) -> str:
    """"shoot" if a loaded ranged weapon is readied, else "throw" (bombs)."""
    return "shoot" if equipped_ranged(state) is not None else "throw"


def aim_range(state: GameState) -> int:
    ready = equipped_ranged(state)
    return ready[1].rng if ready else BOMB_RANGE


def aim_start(state: GameState) -> tuple[int, int]:
    """Where the reticle opens: back onto the last monster you fired at, if it
    survived and is still in range; otherwise the tile you're facing."""
    p = state.player
    m = state.aim_target
    if (m is not None and getattr(m, "alive", False)
            and any(x is m for x in state.world.monsters)
            and in_range(state, m.x, m.y, aim_range(state))):
        return m.x, m.y
    state.aim_target = None
    return p.x + p.facing[0], p.y + p.facing[1]


def _ranged_to_hit(state: GameState, stat) -> int:
    from . import skills
    lvl = skills.mastery_level(state, stat.category)
    bonus = stat.to_hit + skills.skill_level(state, "Combat") // 2 + skills.mastery_to_hit(lvl)
    if skills.active_buff(state) == "hearty":
        bonus += 2
    return bonus


def fire_ranged_at(state: GameState, tx: int, ty: int) -> bool:
    """Loose the readied ranged weapon at an aimed tile: the shot flies to the
    first foe (or wall) in its path and strikes that one target."""
    from . import skills
    p = state.player
    ready = equipped_ranged(state)
    if ready is None:                          # quiver ran dry between aim & loose
        state.log.add("You've nothing to shoot.", C.DIM)
        return False
    weapon, stat = ready
    if p.energy < C.ATTACK_COST[0]:
        state.log.add("You're too winded to draw.", C.DIM)
        return False
    if (tx, ty) == (p.x, p.y):
        state.log.add("Aim away from yourself.", C.DIM)
        return False

    p.inventory.remove(stat.ammo, 1)
    p.energy = max(0, p.energy - C.ATTACK_COST[0])
    from . import turns
    turns.advance_time(state, C.ATTACK_COST[1])

    lx, ly = projectile_landing(state, tx, ty, stat.rng)
    m = mob_at(state, lx, ly)
    if m is None:
        state.log.add(f"Your {stat.ammo.name.lower()} flies wide and clatters down.", C.DIM)
        return True
    state.aim_target = m                       # re-aim onto this foe next time (until it dies)

    dmg_bonus = skills.mastery_dmg(skills.mastery_level(state, stat.category))
    crit = 0.03 + skills.skill_level(state, "Combat") * 0.01 + skills.mastery_crit(
        skills.mastery_level(state, stat.category))
    res = _resolve(_ranged_to_hit(state, stat), stat.dmg, dmg_bonus, crit, m.dv, m.pv)
    wild = getattr(m, "kind", "monster") == "wildlife"
    m.awake = True
    if wild and m.behavior == "defensive":
        m.hostile = True

    if res is None:
        state.log.add(f"Your shot streaks past the {m.name.lower()}.", C.DIM)
        return True
    dmg, was_crit = res
    skills.gain_mastery(state, stat.category, 3)
    if dmg <= 0:
        state.log.add(f"Your {stat.ammo.name.lower()} glances off the {m.name.lower()}.", C.DIM)
        return True
    m.hp -= dmg
    if m.hp <= 0:
        _on_kill(state, m)
        return True
    if wild and not m.hostile:
        state.log.add(f"You hit the {m.name.lower()} for {dmg} — it bolts!", C.DIM)
    else:
        lead = "A critical shot! " if was_crit else ""
        state.log.add(f"{lead}You shoot the {m.name.lower()} for {dmg}.",
                      (240, 220, 140) if was_crit else C.WHITE)
        if not wild:
            skills.gain(state, "Combat", 4)
    return True


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
