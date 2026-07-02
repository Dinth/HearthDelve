"""Hearthdelve — entry point and main loop (M1 walking skeleton)."""
from __future__ import annotations

import os
import random
import sys
import time

import tcod.console
import tcod.context
import tcod.event

from .engine import constants as C
from .engine import font, input as game_input, rendering, save
from .entities import items
from .entities.player import Player
from .game import combat, crafting, delve, farming, fishing, quests, turns, village
from .game.state import GameState, MessageLog
from .world import tile, worldgen


def new_game(seed: int = 1337) -> GameState:
    world = worldgen.generate(seed)
    sx, sy = world.spawn
    player = Player(x=sx, y=sy)
    state = GameState(world=world, player=player, log=MessageLog(), seed=seed)
    state.surface = world
    farming.init_weather(state)
    farming.prime_seasonal_flora(state)     # bloom the opening season's flora

    state.log.add("A letter from your grandfather: the old farm is yours now.", (236, 226, 180))
    state.log.add(f"You wake in Hollowmere Vale. {state.date_str()}, {state.weather.lower()}.", C.WHITE)
    state.log.add("Hoe (1) the soil, plant seeds (6), water them (2), then sleep (s).", C.DIM)
    state.log.add("Chop/mine for materials, c to craft & build, b at the bin to sell.", C.DIM)
    state.log.add("Space uses the active tool. ? for help, l to look, g to gather.", C.DIM)
    state.log.add("Visit Mossford (east) & Cinderhope (west): t to talk/shop, f to gift.", C.DIM)
    return state


_KONAMI = [tcod.event.KeySym.UP, tcod.event.KeySym.UP,
           tcod.event.KeySym.DOWN, tcod.event.KeySym.DOWN,
           tcod.event.KeySym.LEFT, tcod.event.KeySym.RIGHT,
           tcod.event.KeySym.LEFT, tcod.event.KeySym.RIGHT,
           tcod.event.KeySym.b, tcod.event.KeySym.a]


def _cheat_locations(state: GameState):
    """(label, (x, y)) surface teleport targets for the cheat menu."""
    surf = state.surface
    locs = [("Home (the farm)", surf.spawn)]
    for name, c in getattr(surf, "village_centers", {}).items():
        locs.append((name, c))
    for b in surf.buildings:
        if b.get("kind") == "hut":
            locs.append(("The Wildwood hut", b["front"]))
    for (dx, dy) in surf.dungeons:
        locs.append((f"Enter dungeon — {surf.dungeon_kind.get((dx, dy), 'delve')}", (dx, dy)))
    return locs


def _cheat_go(state: GameState, target) -> None:
    """Teleport to a surface spot — or, if it's a dungeon entrance, drop right
    into the dungeon."""
    if state.world.is_dungeon:
        delve.leave_to_surface(state)          # back to the surface first
    surf = state.surface
    state.player.x, state.player.y = target
    if target in surf.dungeons:                # a dungeon mouth — descend into it
        delve.enter(state, surf.dungeon_kind.get(target, "mine"))


# which wild-mushroom item each surface mushroom tile yields when foraged
_MUSHROOM_ITEM = {
    tile.BUTTON_MUSHROOM: items.BUTTON_MUSHROOM,
    tile.PARASOL_MUSHROOM: items.PARASOL_MUSHROOM,
    tile.BOLETE: items.BOLETE,
    tile.CHANTERELLE: items.CHANTERELLE,
}


def try_move(state: GameState, dx: int, dy: int) -> None:
    p = state.player
    p.facing = (dx, dy)
    nx, ny = p.x + dx, p.y + dy
    # bump a farm animal to pet it or collect its produce (never a strike)
    if not state.world.is_dungeon:
        from .game import husbandry
        a = husbandry.animal_at(state, nx, ny)
        if a is not None:
            husbandry.interact_animal(state, a)
            turns.advance_time(state, C.HARVEST_COST[1])
            return
    # bump-attack a creature instead of moving onto it (dungeon monster or
    # surface wildlife — striking a critter is a choice, not an accident)
    m = combat.mob_at(state, nx, ny)
    if m is not None:
        combat.player_attack(state, m)
        turns.advance_time(state, C.ATTACK_COST[1])   # a combat turn
        return
    if state.world.walkable(nx, ny):
        p.x, p.y = nx, ny
        if state.world.tile_at(nx, ny).kind == "gold":          # scoop up a gold pile
            amt = random.randint(20, 60) + state.world.depth * 10
            p.gold += amt
            state.world.tiles[nx, ny] = tile.DUNGEON_FLOOR
            state.log.add(f"You scoop up {amt}g!", (244, 216, 110))
        on_road = state.world.tile_at(nx, ny).kind in ("road", "bridge")
        turns.advance_time(state, C.ROAD_MOVE_SECONDS if on_road else C.MOVE_SECONDS)
        # roads are effortless, and you don't tire underground
        if not on_road and not state.world.is_dungeon:
            p.energy = max(0, p.energy - C.WALK_STAMINA)
        if state.world.is_dungeon:
            delve.update_fov(state)
            _dungeon_tile_fx(state)
    else:
        if not state.world.in_bounds(nx, ny):
            return
        t = state.world.tile_at(nx, ny)
        blocked = {
            "water": "The water is too deep to wade through.",
            "wall": "A wall blocks the way.",
            "fence": "A fence pens in the plot.",
            "ore": "An ore vein — you'll need a pickaxe.",
            "bin": "The shipping bin sits here.",
            "foliage": "Dense foliage blocks the way — clear it with a machete.",
            "shrub": "A shrub blocks the way — clear it with a machete.",
            "shrub_berry": "A berry shrub blocks the way — clear it with a machete.",
            "chest": "A sturdy chest — press g to open it.",
        }
        msg = blocked.get(t.kind)
        if msg:
            state.log.add(msg, C.DIM)


def _spring_trap(state: GameState) -> None:
    """Trigger the trap under the player and disarm the tile."""
    p, w = state.player, state.world
    w.tiles[p.x, p.y] = tile.DUNGEON_FLOOR
    roll = random.random()
    if roll < 0.34:
        dmg = random.randint(2, 4) + w.depth
        p.hp -= dmg
        state.log.add(f"A dart trap fires — you take {dmg} damage!", (228, 120, 110))
    elif roll < 0.67:
        loss = random.randint(4, 8)
        p.energy = max(0, p.energy - loss)
        turns.advance_time(state, 60)
        state.log.add(f"A snare! You struggle free (−{loss} stamina).", (228, 186, 110))
    else:
        for m in w.monsters:
            m.awake = True
        state.log.add("An alarm trap clatters — the whole floor stirs!", (228, 208, 120))


def _dungeon_tile_fx(state: GameState) -> bool:
    """React to the tile the player just stepped onto underground. Springs a
    trap, drags through rubble, and spots nearby hidden traps. Returns True if
    a trap went off (so a run stops)."""
    w = state.world
    if not w.is_dungeon:
        return False
    p = state.player
    sprang = False
    kind = w.tile_at(p.x, p.y).kind
    if kind == "trap":                    # hidden or already-spotted — both fire
        _spring_trap(state)
        sprang = True
    elif kind == "rubble":
        turns.advance_time(state, C.MOVE_SECONDS)   # loose footing, slow going
    for ddx in (-1, 0, 1):                 # notice adjacent hidden traps
        for ddy in (-1, 0, 1):
            x, y = p.x + ddx, p.y + ddy
            if w.in_bounds(x, y) and w.tiles[x, y] == tile.TRAP_HIDDEN and random.random() < 0.4:
                w.tiles[x, y] = tile.TRAP
    return sprang


def use_tool(state: GameState) -> None:
    """Use the active hotbar item on the tile the player is facing.

    Seeds plant; the watering can waters a crop if one is there; other tools
    fall through to the pure resolver.
    """
    from .data import content
    from .game import actions

    p = state.player
    item = p.active_tool
    if item is None:
        state.log.add("Nothing selected (press 1-9).", C.DIM)
        return

    fx, fy = p.facing
    tx, ty = p.x + fx, p.y + fy
    if not state.world.in_bounds(tx, ty):
        state.log.add("There's nothing there to work on.", C.DIM)
        return

    # Seed pouch: plant the selected seed (crop) or sapling (tree).
    if item is items.SEED_POUCH:
        seed = p.active_seed
        if seed is None or p.inventory.count(seed) < 1:
            state.log.add("Seed pouch empty — buy seeds/saplings, or press 7 to cycle.", C.DIM)
            return
        if seed.kind == "sapling":
            farming.plant_tree(state, tx, ty, seed)
        else:
            farming.plant(state, tx, ty, seed)
        return

    # Fishing rod cast at water.
    if item is items.FISHING_ROD and state.world.tile_at(tx, ty).kind == "water":
        fishing.cast(state)
        return

    # Watering can over a planted tile waters the crop directly.
    if item is items.WATERING_CAN and (tx, ty) in state.world.crops:
        if p.energy <= 0:
            state.log.add("You're too exhausted. Rest first.", C.DIM)
            return
        if farming.water_crop(state, tx, ty):
            tier = p.tool_tier.get(items.WATERING_CAN, 0)
            p.energy = max(0, p.energy - max(1, C.WATER_COST[0] - tier))
            turns.advance_time(state, C.WATER_COST[1])
            return

    target = state.world.tile_at(tx, ty)
    success, new_tile, msg = actions.resolve_tool(item, target)
    if not success:
        state.log.add(msg, C.DIM)
        return
    if p.energy <= 0:
        state.log.add("You're too exhausted. Rest first.", C.DIM)
        return

    stat = content.TOOL_STATS.get(item)
    stamina = max(1, stat.stamina - p.tool_tier.get(item, 0)) if stat else 1
    seconds = stat.seconds if stat else C.USE_SECONDS
    if new_tile is not None:
        if state.world.is_dungeon and new_tile == tile.GRASS:
            new_tile = tile.DUNGEON_FLOOR     # mined rock/ore leaves dungeon floor
        state.world.tiles[tx, ty] = new_tile
    p.energy = max(0, p.energy - stamina)
    turns.advance_time(state, seconds)
    state.log.add(msg)
    _gather_drop(state, item, target)


def _gather_drop(state: GameState, item, target) -> None:
    """Chopping and mining yield raw materials, XP, and progress."""
    from .game import skills
    inv = state.player.inventory
    if item is items.AXE and target.kind == "tree":
        inv.add(items.WOOD, 2)
        state.bump("trees_chopped")
        skills.gain(state, "Foraging", 8)
        state.log.add("  (+2 Wood)", C.DIM)
    elif item is items.PICKAXE and target.name == "gem_vein":
        from .data import content
        gem = content.random_gem(random)
        inv.add(gem, 1)
        state.bump("ore_mined")
        skills.gain(state, "Mining", 12)
        if random.random() < 0.3:
            inv.add(items.STONE, 1)
        state.log.add(f"  (+1 {gem.name})", C.DIM)
    elif item is items.PICKAXE and target.name == "ore_vein":
        # An ore vein mostly gives stone, often coal, sometimes ore.
        got = []
        if random.random() < 0.80:
            inv.add(items.STONE, 1); got.append("Stone")
        if random.random() < 0.45:
            inv.add(items.COAL, 1); got.append("Coal")
        if random.random() < 0.30:
            from .data import content
            ore = content.ore_for_depth(state.world.depth, random)
            inv.add(ore, 1); got.append(ore.name)
        if not got:                       # always yield something
            inv.add(items.STONE, 1); got.append("Stone")
        state.bump("ore_mined")
        skills.gain(state, "Mining", 10)
        state.log.add("  (+" + ", +".join(got) + ")", C.DIM)
    elif item is items.PICKAXE and target.name in ("rock", "ruins_wall"):
        inv.add(items.STONE, 2)
        state.bump("ore_mined")
        skills.gain(state, "Mining", 6)
        state.log.add("  (+2 Stone)", C.DIM)
    elif item is items.MACHETE and target.kind in ("foliage", "shrub"):
        skills.gain(state, "Foraging", 6)
        if random.random() < 0.55:
            inv.add(items.FIBER, 1)
            state.log.add("  (+1 Fiber)", C.DIM)
    elif item is items.MACHETE and target.kind == "shrub_berry":
        from .data import content
        skills.gain(state, "Foraging", 8)
        parts = []
        fruit = content.SHRUB_FRUIT.get(target.name)
        if fruit:
            n = random.randint(1, 2)
            inv.add(fruit, n, quality=skills.roll_quality(state, "Foraging"))
            parts.append(f"+{n} {fruit.name}")
        if random.random() < 0.5:
            inv.add(items.FIBER, 1)
            parts.append("+1 Fiber")
        if parts:
            state.log.add("  (" + ", ".join(parts) + ")", C.DIM)


def do_grab(state: GameState) -> None:
    """Harvest a crop or interact with a machine — faced tile, then underfoot."""
    p = state.player
    for gx, gy in ((p.x + p.facing[0], p.y + p.facing[1]), (p.x, p.y)):
        if not state.world.in_bounds(gx, gy):
            continue
        tk = state.world.tile_at(gx, gy).kind
        if tk == "chest":
            _open_chest(state, gx, gy)
            return
        if tk == "hive":
            _rob_hive(state, gx, gy)
            return
        if tk in ("mushroom", "glowcap"):
            if tk == "glowcap":
                item, floor, col = items.GLOWCAP, tile.GLOW_MOSS, (150, 236, 222)
            elif state.world.is_dungeon:
                item, floor, col = items.CAVE_MUSHROOM, tile.DUNGEON_FLOOR, (206, 160, 190)
            else:                                        # a named wild species
                item = _MUSHROOM_ITEM.get(state.world.tiles[gx, gy], items.BUTTON_MUSHROOM)
                floor, col = tile.GRASS, (206, 176, 130)
            state.world.tiles[gx, gy] = floor
            from .game import skills
            q = skills.roll_quality(state, "Foraging")
            p.inventory.add(item, 1, quality=q)
            skills.gain(state, "Foraging", 12 if tk == "glowcap" else 8)
            star = (" " + skills.stars(q)) if q else ""
            state.log.add(f"You gather a {item.name.lower()}{star}.", col)
            turns.advance_time(state, C.HARVEST_COST[1])
            return
        if (gx, gy) in state.world.crops:
            if farming.harvest(state, gx, gy):
                return
        if (gx, gy) in state.world.trees:
            if farming.pick_tree(state, gx, gy):
                return
        if (gx, gy) in state.world.machines:
            if crafting.interact_machine(state, gx, gy):
                return
    state.log.add("Nothing here to gather.", C.DIM)


def _rob_hive(state: GameState, x: int, y: int) -> None:
    """Rob a wild bee hive: honey and wax, a mild sting, and rarely a queen."""
    from .game import skills
    p = state.player
    honey = random.randint(1, 3)
    wax = random.randint(1, 2)
    p.inventory.add(items.HONEY, honey, quality=skills.roll_quality(state, "Foraging"))
    p.inventory.add(items.BEESWAX, wax)
    got = f"{honey} honey and {wax} beeswax"
    if random.random() < 0.03:                       # a very rare prize
        p.inventory.add(items.BEE_QUEEN, 1)
        got += ", and a BEE QUEEN"
    state.world.tiles[x, y] = tile.GRASS
    state.bump("hives_robbed")
    state.log.add(f"You raid the wild hive — {got}!", (232, 200, 120))
    if random.random() < 0.5:                        # the bees object
        sting = random.randint(1, 3)
        p.hp = max(1, p.hp - sting)
        state.log.add(f"  The bees sting you (−{sting} HP)!", (224, 140, 120))
    from .game import skills
    skills.gain(state, "Foraging", 14)
    turns.advance_time(state, C.HARVEST_COST[1])


def _at_postbox(state: GameState) -> bool:
    p = state.player
    for gx, gy in ((p.x + p.facing[0], p.y + p.facing[1]), (p.x, p.y)):
        if state.world.in_bounds(gx, gy) and state.world.tile_at(gx, gy).kind == "postbox":
            return True
    return False


def collect_letter(state: GameState, letter) -> None:
    """Take a letter's contents into the pack and read it out."""
    from .game import skills
    p = state.player
    got = []
    for name, qty, ql in letter.get("items", ()):
        it = items.by_name(name) if isinstance(name, str) else name
        if it:
            p.inventory.add(it, qty, ql)
            got.append(it.name + ((" " + skills.stars(ql)) if ql else ""))
    state.log.add(f"Letter from {letter['sender']}:", (230, 200, 130))
    for line in letter["body"].split("\n"):
        state.log.add("  " + line, C.WHITE)
    if got:
        state.log.add("  Enclosed: " + ", ".join(got) + ".", (180, 230, 160))


def edible_items(state: GameState):
    """Cooked dishes in the pack, one entry per (item, quality)."""
    return [(it, q, ql) for it, q, ql in state.player.inventory.slots if it.kind == "food"]


def _eat(state: GameState, item, quality: int) -> None:
    from .game import skills
    p = state.player
    if p.inventory.count(item, quality) <= 0:
        return
    p.inventory.remove(item, 1, quality=quality)
    gain = round(item.energy * (1 + 0.12 * quality))     # tastier food goes further
    p.energy = min(p.max_energy, p.energy + gain)
    p.hp = min(p.max_hp, p.hp + max(1, gain // 6))
    state.bump("meals_eaten")
    star = (" " + skills.stars(quality)) if quality else ""
    state.log.add(f"You eat the {item.name.lower()}{star}. (+{gain} stamina)", (180, 230, 160))
    turns.advance_time(state, C.USE_SECONDS)


def _open_chest(state: GameState, x: int, y: int) -> None:
    from .data import content
    p = state.player
    state.world.tiles[x, y] = tile.DUNGEON_FLOOR
    gold, loot = content.chest_loot(state.world.depth, random)
    p.gold += gold
    got = [f"{gold}g"]
    for it in loot:
        p.inventory.add(it, 1)
        got.append(p.display_name(it) if hasattr(p, "display_name") else it.name)
    state.bump("chests_opened")
    state.log.add("You pry open the chest! " + ", ".join(got) + ".", (244, 216, 120))
    turns.advance_time(state, C.USE_SECONDS)


def near_bin(state: GameState) -> bool:
    b = state.world.bin
    if b is None:
        return False
    return abs(state.player.x - b[0]) <= 1 and abs(state.player.y - b[1]) <= 1


RUN_MAX_TILES = 50
REST_MAX_SECONDS = 3600          # rest up to an in-game hour


def _notable_nearby(state: GameState) -> bool:
    """Something worth stopping for: a person close by, or an interesting tile."""
    p = state.player
    for npc in state.world.npcs:
        if max(abs(npc.x - p.x), abs(npc.y - p.y)) <= 6:
            return True
    for m in state.world.monsters:
        if m.seasons and state.season not in m.seasons:
            continue                                   # hibernating — not around
        if m.alive and max(abs(m.x - p.x), abs(m.y - p.y)) <= 6:
            return True
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            x, y = p.x + dx, p.y + dy
            if state.world.in_bounds(x, y):
                if state.world.tile_at(x, y).kind in ("stairs", "stairs_up", "bin", "shrub_berry"):
                    return True
    return False


_ROAD_KINDS = ("road", "bridge", "cobble")


def _is_road(state: GameState, x: int, y: int) -> bool:
    return state.world.in_bounds(x, y) and state.world.tile_at(x, y).kind in _ROAD_KINDS


def start_run(state: GameState, dx: int, dy: int) -> dict | None:
    """Begin a run; returns its context, or None if blocked immediately."""
    p = state.player
    on_road = _is_road(state, p.x, p.y)
    if not on_road and not state.world.walkable(p.x + dx, p.y + dy):
        return None
    tunnel = state.world.is_dungeon and not (
        state.world.walkable(p.x - dy, p.y + dx) or state.world.walkable(p.x + dy, p.y - dx))
    return {"d": (dx, dy), "steps": 0, "on_road": on_road, "tunnel": tunnel}


def run_step(state: GameState, ctx: dict) -> bool:
    """Advance one tile of a run. Returns True to keep running."""
    p = state.player
    dx, dy = ctx["d"]

    # Road runs FOLLOW the road: keep straight if we can, otherwise take the
    # single bend; stop at a fork, a dead end, or the road's end.
    if ctx["on_road"]:
        back = (-dx, -dy)
        opts = [(ax, ay) for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if (ax, ay) != back and _is_road(state, p.x + ax, p.y + ay)]
        if (dx, dy) in opts:
            ndir = (dx, dy)                            # carry straight on
        elif len(opts) == 1:
            ndir = opts[0]                             # follow the bend
        else:
            return False                               # fork or dead end — stop
        p.x, p.y = p.x + ndir[0], p.y + ndir[1]
        ctx["d"] = ndir
        turns.advance_time(state, C.ROAD_MOVE_SECONDS)
        ctx["steps"] += 1
        if ctx["steps"] >= RUN_MAX_TILES or _notable_nearby(state):
            return False
        exits = sum(_is_road(state, p.x + ax, p.y + ay) for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        if exits > 2:
            return False                               # a real junction — stop
        return True

    # Off-road (wilderness / dungeon): straight-line run.
    nx, ny = p.x + dx, p.y + dy
    if not state.world.walkable(nx, ny):
        return False                                   # wall ahead — stop here
    p.x, p.y = nx, ny
    turns.advance_time(state, C.MOVE_SECONDS)
    if not state.world.is_dungeon:
        p.energy = max(0, p.energy - C.WALK_STAMINA)
    if state.world.is_dungeon:
        delve.update_fov(state)
        if _dungeon_tile_fx(state):
            return False                               # a trap sprang — stop
    ctx["steps"] += 1

    if ctx["steps"] >= RUN_MAX_TILES or _notable_nearby(state):
        return False
    if ctx["tunnel"]:
        if state.world.walkable(p.x - dy, p.y + dx) or state.world.walkable(p.x + dy, p.y - dx):
            return False                               # corridor opened up
    return True


def check_faint(state: GameState) -> None:
    """Collapse if slain, out of energy, or up past the small hours."""
    if state.player.hp <= 0:
        state.player.hp = 1
        farming.collapse(state, "You are struck down and black out...")
    elif state.player.energy <= 0:
        farming.collapse(state, "You collapse from exhaustion...")
    elif state.time_minutes >= C.DAY_END_MIN:
        farming.collapse(state, "You can't keep your eyes open and pass out...")


def select_slot(state: GameState, n: int) -> None:
    p = state.player
    if not (0 <= n < len(p.hotbar)):
        return
    # Re-pressing the seed-pouch slot cycles through carried seeds & saplings.
    if p.active_slot == n and p.hotbar[n] is items.SEED_POUCH:
        cycle_seed(state)
        return
    p.active_slot = n
    it = p.hotbar[n]
    if it is items.SEED_POUCH:
        seed = p.active_seed.name if p.active_seed else "empty"
        state.log.add(f"Seed pouch: {seed} (press {n + 1} again to cycle).", C.DIM)
    else:
        state.log.add(f"Selected {p.display_name(it)}.", C.DIM)


def cycle_seed(state: GameState) -> None:
    p = state.player
    plantables = [it for it, *_ in p.inventory.slots if it.kind in ("seed", "sapling")]
    if not plantables:
        state.log.add("You have no seeds or saplings to plant.", C.DIM)
        return
    i = (plantables.index(p.active_seed) + 1) % len(plantables) if p.active_seed in plantables else 0
    p.active_seed = plantables[i]
    state.log.add(f"Seed pouch: {p.active_seed.name} ({p.inventory.count(p.active_seed)}).",
                  (200, 220, 160))


def clamp_look(state: GameState, x: int, y: int) -> list[int]:
    """Keep the look cursor within the (fixed) viewport and the world."""
    ox, oy = rendering.camera_origin(state)
    x = max(ox, min(x, ox + C.VIEW_W - 1, state.world.width - 1))
    y = max(oy, min(y, oy + C.VIEW_H - 1, state.world.height - 1))
    return [x, y]


def load_or_new() -> GameState:
    """Continue a saved game if one exists (unless '--new' was passed)."""
    if "--new" in sys.argv:
        save.delete()
        return new_game()
    if save.exists():
        try:
            state = save.load()
            state.log.add("Welcome back to Hollowmere Vale.", (236, 226, 180))
            state.log.add(f"{state.date_str()}, {state.weather.lower()}. (auto-saves each morning)", C.DIM)
            return state
        except Exception as e:  # noqa: BLE001 - corrupt/old save -> fresh start
            print(f"Could not load save ({e}); starting a new game.")
    return new_game()


def main() -> None:
    tileset = font.load_tileset(16)
    state = load_or_new()
    console = tcod.console.Console(C.SCREEN_W, C.SCREEN_H, order="F")

    mode = "play"            # play | look | help | inventory | equipment | craft | ship | dialogue | shop | gift
    look = [state.player.x, state.player.y]
    help_page = 0
    help_scroll = 0
    craft_sel = 0
    ship_sel = 0
    npc = None               # current NPC for dialogue/shop/gift
    dialogue_line = ""
    shop_sel = 0
    gift_sel = 0
    awaiting_run = False     # 'w' pressed, waiting for a direction or '.'
    run_ctx = None           # active run
    rest_left = 0            # seconds left in an active rest
    save_on_exit = True      # cleared by "quit without saving"
    cheat_sel = 0            # cursor in the Konami cheat menu
    konami: list = []        # rolling buffer of recent keys
    eat_sel = 0              # cursor in the eat menu
    mail_sel = 0             # cursor in the post box

    with tcod.context.new(
        columns=C.SCREEN_W,
        rows=C.SCREEN_H,
        tileset=tileset,
        title="Hearthdelve — Hollowmere Vale",
        vsync=True,
    ) as context:
        # Headless smoke test (used to validate packaged builds): draw one
        # frame, present it, and exit successfully.
        if os.environ.get("HEARTHDELVE_SMOKETEST"):
            rendering.render_all(console, state, 0.0)
            context.present(console)
            print("smoketest ok")
            return

        running = True
        start = time.perf_counter()
        while running:
            anim_time = time.perf_counter() - start

            # Cheats: hold health / stamina pinned to full while frozen.
            if state.cheats.get("freeze_hp"):
                state.player.hp = state.player.max_hp
            if state.cheats.get("freeze_stamina"):
                state.player.energy = state.player.max_energy

            # Auto-actions: a run or a rest advances one tick per frame (animated)
            # until it's interrupted or a stop condition is met.
            if mode == "play" and run_ctx is not None:
                if not run_step(state, run_ctx):
                    run_ctx = None
                    check_faint(state)
            elif mode == "play" and rest_left > 0:
                turns.advance_time(state, C.MOVE_SECONDS)
                if state.world.is_dungeon:
                    delve.update_fov(state)
                rest_left -= C.MOVE_SECONDS
                if _notable_nearby(state) or rest_left <= 0:
                    rest_left = 0
                    state.log.add("You wait a while.", C.DIM)
                    check_faint(state)

            if mode == "play":
                quests.check(state)

            rendering.render_all(console, state, anim_time)
            if mode == "play":
                rendering.render_facing(console, state)
            elif mode == "look":
                rendering.render_look(console, state, *look)
            elif mode == "help":
                rendering.render_codex(console, state, help_page, help_scroll)
            elif mode == "inventory":
                rendering.render_inventory(console, state)
            elif mode == "equipment":
                rendering.render_equipment(console, state)
            elif mode == "craft":
                rendering.render_craft(console, state, craft_sel)
            elif mode == "ship":
                rendering.render_ship(console, state, ship_sel)
            elif mode == "dialogue":
                rendering.render_dialogue(console, state, npc, dialogue_line)
            elif mode == "shop":
                rendering.render_shop(console, state, npc, shop_sel, dialogue_line)
            elif mode == "gift":
                rendering.render_gift(console, state, npc, gift_sel)
            elif mode == "journal":
                rendering.render_journal(console, state)
            elif mode == "relations":
                rendering.render_relationships(console, state)
            elif mode == "character":
                rendering.render_character(console, state)
            elif mode == "quitmenu":
                rendering.render_quit(console, state)
            elif mode == "cheats":
                rendering.render_cheats(console, state, cheat_sel, _cheat_locations(state))
            elif mode == "eat":
                rendering.render_eat(console, state, eat_sel)
            elif mode == "mail":
                rendering.render_mail(console, state, mail_sel)
            context.present(console)

            # A short timeout drives the ambient animation: when no key is
            # pressed, wait() returns after ~1/30s and we redraw the next frame.
            for event in tcod.event.wait(timeout=1.0 / 30.0):
                if isinstance(event, tcod.event.WindowEvent) and event.type == "WINDOWCLOSE":
                    running = False
                    break

                # Konami code (↑↑↓↓←→←→ B A) opens the hidden cheat menu.
                if isinstance(event, tcod.event.KeyDown):
                    konami.append(event.sym)
                    del konami[:-len(_KONAMI)]
                    if konami == _KONAMI:
                        konami.clear()
                        mode, cheat_sel = "cheats", 0
                        state.log.add("A hidden door creaks open...", (250, 230, 140))
                        continue

                # Any key interrupts an in-progress run or rest.
                if isinstance(event, tcod.event.KeyDown) and (run_ctx is not None or rest_left > 0):
                    run_ctx, rest_left = None, 0
                    continue

                action = game_input.event_to_action(event)
                if action is None:
                    continue
                cmd = action[0]

                if mode == "play":
                    if awaiting_run:
                        awaiting_run = False
                        if cmd == "move":
                            run_ctx = start_run(state, action[1], action[2])
                        elif cmd == "wait":
                            rest_left = REST_MAX_SECONDS
                        continue
                    if cmd == "runprefix":
                        awaiting_run = True
                        state.log.add("Run: press a direction — or . to rest a while.", C.DIM)
                        continue
                    if cmd in ("quit", "cancel", "quitgame"):
                        mode = "quitmenu"
                        continue
                    elif cmd == "move":
                        try_move(state, action[1], action[2])
                    elif cmd == "wait":
                        turns.advance_time(state, C.MOVE_SECONDS)
                    elif cmd == "slot":
                        select_slot(state, action[1])
                    elif cmd == "look":
                        mode = "look"
                        look = [state.player.x, state.player.y]
                    elif cmd == "use":
                        use_tool(state)
                        check_faint(state)
                    elif cmd == "grab":
                        if _at_postbox(state):
                            if state.mail:
                                mode, mail_sel = "mail", 0
                            else:
                                state.log.add("Your post box is empty.", C.DIM)
                        else:
                            do_grab(state)
                            check_faint(state)
                    elif cmd == "place":
                        from .game import husbandry
                        husbandry.place_commission(state)
                    elif cmd == "ability":
                        combat.throw_bomb(state)
                        check_faint(state)
                    elif cmd == "descend":
                        here = state.world.tile_at(state.player.x, state.player.y)
                        if not state.world.is_dungeon and here.kind == "stairs":
                            kind = state.world.dungeon_kind.get((state.player.x, state.player.y), "mine")
                            delve.enter(state, kind)
                        elif state.world.is_dungeon and here.kind == "stairs":
                            delve.descend(state)
                        else:
                            state.log.add("There are no stairs down here.", C.DIM)
                    elif cmd == "ascend":
                        here = state.world.tile_at(state.player.x, state.player.y)
                        if state.world.is_dungeon and here.kind == "stairs_up":
                            delve.ascend(state)
                        else:
                            state.log.add("There are no stairs up here.", C.DIM)
                    elif cmd == "sleep":
                        if farming.can_sleep(state):
                            farming.sleep(state)
                        else:
                            state.log.add("You can only sleep in your bed.", C.DIM)
                    elif cmd == "craft":
                        mode = "craft"
                        craft_sel = 0
                    elif cmd == "eat":
                        if edible_items(state):
                            mode, eat_sel = "eat", 0
                        else:
                            state.log.add("You have no cooked food. Craft (c) a dish first.", C.DIM)
                    elif cmd == "ship":
                        if near_bin(state):
                            mode = "ship"
                            ship_sel = 0
                        else:
                            state.log.add("Stand by the shipping bin to sell goods.", C.DIM)
                    elif cmd == "journal":
                        mode = "journal"
                    elif cmd == "relations":
                        mode = "relations"
                    elif cmd == "character":
                        mode = "character"
                    elif cmd == "talk":
                        npc = village.npc_near(state)
                        if npc is None:
                            state.log.add("There's no one here to talk to.", C.DIM)
                        elif npc.shop in ("tavern", "carpenter"):
                            dialogue_line = village.talk(state, npc)   # greeting + friendship
                            mode, shop_sel = "shop", 0
                        elif npc.shop:
                            npc.met = True
                            mode, shop_sel = "shop", 0
                        else:
                            dialogue_line = village.talk(state, npc)
                            mode = "dialogue"
                    elif cmd == "gift":
                        npc = village.npc_near(state)
                        if npc is None:
                            state.log.add("There's no one here to give a gift to.", C.DIM)
                        else:
                            mode, gift_sel = "gift", 0
                    elif cmd == "help":
                        mode = "help"
                        help_page = 0
                        help_scroll = 0
                    elif cmd == "inventory":
                        mode = "inventory"
                    elif cmd == "equipment":
                        mode = "equipment"
                    if cmd in ("move", "wait"):
                        check_faint(state)

                elif mode == "look":
                    if cmd in ("look", "cancel", "quit"):
                        mode = "play"
                    elif cmd == "move":
                        look = clamp_look(state, look[0] + action[1], look[1] + action[2])

                elif mode == "help":
                    if cmd in ("help", "cancel", "quit"):
                        mode = "play"
                    elif cmd == "move":
                        if action[1]:
                            help_page += action[1]
                            help_scroll = 0
                        if action[2]:
                            help_scroll = max(0, help_scroll + action[2])

                elif mode == "inventory":
                    if cmd == "equipment":
                        mode = "equipment"
                    elif cmd in ("cancel", "inventory", "quit"):
                        mode = "play"

                elif mode == "equipment":
                    if cmd == "inventory":
                        mode = "inventory"
                    elif cmd in ("cancel", "equipment", "quit"):
                        mode = "play"

                elif mode == "craft":
                    if cmd in ("cancel", "craft", "quit"):
                        mode = "play"
                    elif cmd == "move" and action[2]:
                        craft_sel = (craft_sel + action[2]) % len(crafting.content.RECIPES)
                    elif cmd == "confirm":
                        crafting.craft(state, crafting.content.RECIPES[craft_sel])

                elif mode == "mail":
                    if cmd in ("cancel", "grab", "quit") or not state.mail:
                        mode = "play"
                    elif cmd == "move" and action[2] and state.mail:
                        mail_sel = (mail_sel + action[2]) % len(state.mail)
                    elif cmd == "confirm" and state.mail:
                        mail_sel = min(mail_sel, len(state.mail) - 1)
                        collect_letter(state, state.mail.pop(mail_sel))
                        mail_sel = 0
                        if not state.mail:
                            mode = "play"

                elif mode == "eat":
                    foods = edible_items(state)
                    if cmd in ("cancel", "eat", "quit"):
                        mode = "play"
                    elif cmd == "move" and action[2] and foods:
                        eat_sel = (eat_sel + action[2]) % len(foods)
                    elif cmd == "confirm" and foods:
                        eat_sel = min(eat_sel, len(foods) - 1)
                        it, _q, ql = foods[eat_sel]
                        _eat(state, it, ql)
                        check_faint(state)
                        if not edible_items(state):
                            mode = "play"

                elif mode == "ship":
                    sellable = crafting.sellable_items(state)
                    if cmd in ("cancel", "ship", "quit"):
                        mode = "play"
                    elif cmd == "move" and action[2] and sellable:
                        ship_sel = (ship_sel + action[2]) % len(sellable)
                    elif cmd == "confirm" and sellable:
                        ship_sel = min(ship_sel, len(sellable) - 1)
                        entry = sellable[ship_sel]
                        crafting.ship_item(state, entry[0], entry[2])

                elif mode == "dialogue":
                    if cmd == "gift":
                        mode, gift_sel = "gift", 0
                    else:
                        mode = "play"

                elif mode == "shop":
                    entries = village.shop_entries(npc.shop)
                    if cmd in ("cancel", "talk", "quit"):
                        mode = "play"
                    elif cmd == "move" and action[2] and entries:
                        shop_sel = (shop_sel + action[2]) % len(entries)
                    elif cmd == "confirm" and entries:
                        village.purchase(state, entries[min(shop_sel, len(entries) - 1)])

                elif mode == "gift":
                    gifts = village.giftable_items(state)
                    if cmd in ("cancel", "gift", "quit"):
                        mode = "play"
                    elif cmd == "move" and action[2] and gifts:
                        gift_sel = (gift_sel + action[2]) % len(gifts)
                    elif cmd == "confirm" and gifts:
                        village.gift(state, npc, gifts[min(gift_sel, len(gifts) - 1)][0])
                        mode = "play"

                elif mode == "journal":
                    if cmd in ("cancel", "journal", "quit"):
                        mode = "play"

                elif mode == "relations":
                    if cmd in ("cancel", "relations", "quit"):
                        mode = "play"

                elif mode == "character":
                    if cmd in ("cancel", "character", "quit"):
                        mode = "play"

                elif mode == "quitmenu":
                    if cmd == "cancel":
                        mode = "play"                    # Esc — keep playing
                    elif cmd in ("sleep", "confirm"):    # S / Enter — save & quit
                        running = False
                    elif cmd == "quitgame":              # Q — quit WITHOUT saving
                        save_on_exit = False
                        running = False

                elif mode == "cheats":
                    locs = _cheat_locations(state)
                    n = 4 + len(locs)
                    if cmd in ("cancel", "quitgame"):
                        mode = "play"
                    elif cmd == "move" and action[2]:
                        cheat_sel = (cheat_sel + action[2]) % n
                    elif cmd == "confirm":
                        if cheat_sel == 0:
                            state.cheats["freeze_hp"] = not state.cheats.get("freeze_hp")
                        elif cheat_sel == 1:
                            state.cheats["freeze_stamina"] = not state.cheats.get("freeze_stamina")
                        elif cheat_sel == 2:
                            state.player.gold += 1000
                            state.log.add("A purse of 1000g appears.", (244, 216, 110))
                        elif cheat_sel == 3:
                            for mat in (items.WOOD, items.STONE, items.TIMBER_PLANK,
                                        items.COPPER_BAR, items.BEESWAX):
                                state.player.inventory.add(mat, 100)
                            state.log.add("Building materials rain down (+100 each).", (200, 200, 240))
                        else:
                            _cheat_go(state, locs[cheat_sel - 4][1])
                            state.log.add("You blink across the Vale.", (200, 180, 240))
                            mode = "play"

        # Save on exit (unless the player chose to quit without saving).
        if save_on_exit:
            try:
                save.save(state)
            except Exception as e:  # noqa: BLE001
                print(f"Could not save game: {e}")


if __name__ == "__main__":
    main()
