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
from .game import combat, crafting, delve, farming, fishing, quests, skills, turns, village
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
    state.log.add("Visit Mossford (east) & Cinderhope (west): Shift+C to talk/shop, f to gift.", C.DIM)
    return state


# Stored as plain ints (SDL keycodes) so this doesn't depend on whether the
# installed tcod names letter keys KeySym.a (older) or KeySym.A (newer/Windows).
_K = tcod.event.KeySym
_KONAMI = [int(_K.UP), int(_K.UP), int(_K.DOWN), int(_K.DOWN),
           int(_K.LEFT), int(_K.RIGHT), int(_K.LEFT), int(_K.RIGHT),
           ord("b"), ord("a")]


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


def _npc_at(state: GameState, x: int, y: int):
    """A villager standing on (x, y), if any (surface only)."""
    if state.world.is_dungeon:
        return None
    for n in state.world.npcs:
        if (n.x, n.y) == (x, y):
            return n
    return None


def _entity_at(state: GameState, x: int, y: int) -> bool:
    """Whether a creature, farm animal, or villager occupies (x, y) — a run
    should never barrel onto one."""
    if combat.mob_at(state, x, y) is not None:
        return True
    if not state.world.is_dungeon:
        from .game import husbandry
        if husbandry.animal_at(state, x, y) is not None or _npc_at(state, x, y) is not None:
            return True
    return False


def _scoop_gold(state: GameState) -> None:
    """Pick up a gold pile the player is standing on (dungeon vaults)."""
    p = state.player
    if state.world.tile_at(p.x, p.y).kind == "gold":
        amt = random.randint(20, 60) + state.world.depth * 10
        p.gold += amt
        state.world.tiles[p.x, p.y] = tile.DUNGEON_FLOOR
        state.log.add(f"You scoop up {amt}g!", (244, 216, 110))


THREAT_RANGE = 6          # a menacing creature this close breaks your concentration


def _threat_near(state: GameState):
    """A dangerous creature within THREAT_RANGE (an awake dungeon monster, or
    roused wildlife) — peaceful critters and villagers don't count. Returns the
    mob, or None."""
    p = state.player
    for m in state.world.monsters:
        if not m.alive:
            continue
        if getattr(m, "kind", "monster") == "wildlife":
            if not m.hostile:
                continue                          # a grazing rabbit won't stop you
        elif not m.awake:
            continue                              # a sleeping mob is no threat yet
        if max(abs(m.x - p.x), abs(m.y - p.y)) <= THREAT_RANGE:
            return m
    return None


def _finish_busy(state: GameState, b: dict) -> None:
    """Complete a long, animated tool action (chop/mine) once its time is up."""
    p = state.player
    if b["new_tile"] is not None:
        state.world.tiles[b["tx"], b["ty"]] = b["new_tile"]
    p.energy = max(0, p.energy - b["stamina"])
    state.log.add(b["msg"])
    _gather_drop(state, b["item"], b["target"])


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
    # don't stand on top of a villager — nudge the player to talk/gift instead
    n = _npc_at(state, nx, ny)
    if n is not None:
        state.log.add(f"You greet {n.name}. (Shift+C to talk, f to give a gift)", C.DIM)
        return
    if state.world.walkable(nx, ny):
        p.x, p.y = nx, ny
        _scoop_gold(state)                                      # scoop up a gold pile
        on_road = _is_road(state, nx, ny)                       # roads/bridges/cobble: fast & effortless
        turns.advance_time(state, C.ROAD_MOVE_SECONDS if on_road else C.MOVE_SECONDS)
        # roads are effortless, you don't tire underground, and a Brisk meal
        # keeps you fresh afoot
        if not on_road and not state.world.is_dungeon and skills.active_buff(state) != "brisk":
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
        threat = _threat_near(state)
        if threat is not None:
            state.log.add(f"You can't fish with a {threat.name.lower()} lurking so near.", C.DIM)
            return None
        fishing.cast(state)
        return None

    # Watering can over a planted tile waters the crop directly.
    if item is items.WATERING_CAN and (tx, ty) in state.world.crops:
        if p.energy <= 0:
            state.log.add("You're too exhausted. Rest first.", C.DIM)
            return None
        if farming.water_crop(state, tx, ty):
            tier = p.tool_tier.get(items.WATERING_CAN, 0)
            p.energy = max(0, p.energy - max(1, C.WATER_COST[0] - tier))
            turns.advance_time(state, C.WATER_COST[1])
            return None

    target = state.world.tile_at(tx, ty)
    success, new_tile, msg = actions.resolve_tool(item, target)
    if not success:
        state.log.add(msg, C.DIM)
        return None
    if p.energy <= 0:
        state.log.add("You're too exhausted. Rest first.", C.DIM)
        return None

    stat = content.TOOL_STATS.get(item)
    stamina = max(1, stat.stamina - p.tool_tier.get(item, 0)) if stat else 1
    seconds = stat.seconds if stat else C.USE_SECONDS
    if new_tile is not None and state.world.is_dungeon and new_tile == tile.GRASS:
        new_tile = tile.DUNGEON_FLOOR         # mined rock/ore leaves dungeon floor

    # Long tasks (felling a tree, breaking rock) play out over a few seconds so
    # the world moves around you — and a menacing creature can break them off.
    if seconds >= LONG_ACTION_SECONDS:
        threat = _threat_near(state)
        if threat is not None:
            state.log.add(f"You can't focus with a {threat.name.lower()} so close.", C.DIM)
            return None
        state.log.add(f"You set to work with the {item.name.lower()}...", C.DIM)
        return {"left": seconds, "item": item, "tx": tx, "ty": ty, "target": target,
                "new_tile": new_tile, "stamina": stamina, "msg": msg}

    # Short tasks resolve at once.
    if new_tile is not None:
        state.world.tiles[tx, ty] = new_tile
    p.energy = max(0, p.energy - stamina)
    turns.advance_time(state, seconds)
    state.log.add(msg)
    _gather_drop(state, item, target)
    return None


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
    elif item is items.MACHETE and target.name == "tall_grass":
        n = random.randint(1, 2)
        inv.add(items.CUT_GRASS, n)
        skills.gain(state, "Foraging", 4)
        state.log.add(f"  (+{n} Cut Grass — dry it into straw)", C.DIM)
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
        if tk == "shrub_berry":                          # pick berries; the bush stays
            _pick_berries(state, gx, gy)
            return
        if (gx, gy) in state.world.crops:
            if farming.harvest(state, gx, gy):
                return
        if (gx, gy) in state.world.trees:
            if farming.pick_tree(state, gx, gy):
                return
        if (gx, gy) in state.world.machines:
            res = crafting.interact_machine(state, gx, gy)
            if isinstance(res, dict):        # machine wants a "what to load?" choice
                return res
            if res:
                return None
    state.log.add("Nothing here to gather.", C.DIM)
    return None


BERRY_REGROW_DAYS = 3            # a picked berry shrub bears again after ~this many days


def _pick_berries(state: GameState, x: int, y: int) -> None:
    """Forage a berry shrub without destroying it — it's stripped to a plain bush
    and re-berries a few days later (see farming._regrow_berries)."""
    from .data import content
    from .game import skills
    p = state.player
    btile = int(state.world.tiles[x, y])
    fruit = content.SHRUB_FRUIT.get(state.world.tile_at(x, y).name)
    q = skills.roll_quality(state, "Foraging")
    n = random.randint(1, 2)
    if fruit:
        p.inventory.add(fruit, n, quality=q)
    if random.random() < 0.4:
        p.inventory.add(items.FIBER, 1)
    state.world.tiles[x, y] = tile.SHRUB                 # picked bare; it will regrow
    state.world.berry_regrow[(x, y)] = [btile, state.day + BERRY_REGROW_DAYS + random.randint(0, 1)]
    skills.gain(state, "Foraging", 8)
    star = (" " + skills.stars(q)) if q else ""
    fn = fruit.name.lower() if fruit else "berries"
    state.log.add(f"You pick {n} {fn}{star}; the bush will bear again in a few days.",
                  (200, 170, 120))
    turns.advance_time(state, C.HARVEST_COST[1])


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


def _eat(state: GameState, item, quality: int) -> None:
    from .game import skills
    p = state.player
    if p.inventory.count(item, quality) <= 0:
        return
    p.inventory.remove(item, 1, quality=quality)
    gain = round(item.energy * (1 + 0.12 * quality))     # tastier food goes further
    heal = max(1, gain // 6)
    p.energy = min(p.max_energy, p.energy + gain)
    p.hp = min(p.max_hp, p.hp + heal)
    state.bump("meals_eaten")
    star = (" " + skills.stars(quality)) if quality else ""
    state.log.add(f"You eat the {item.name.lower()}{star}. (+{gain} stamina, +{heal} HP)", (180, 230, 160))
    if item.buff:
        skills.apply_buff(state, item.buff)
        state.log.add(f"  You feel {skills.BUFFS.get(item.buff, item.buff)}!", (200, 220, 250))
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
LONG_ACTION_SECONDS = 120        # tasks at/above this animate over frames (chop, mine)


_NOTABLE_TILE = {"stairs": "a stairway down", "stairs_up": "a stairway up",
                 "bin": "the shipping bin", "shrub_berry": "a berry shrub"}


def _notable_nearby(state: GameState) -> str:
    """A reason a run/rest should stop — someone close by or an interesting tile
    underfoot — or '' if nothing of note (so it stays usable as a boolean)."""
    p = state.player
    for npc in state.world.npcs:
        if max(abs(npc.x - p.x), abs(npc.y - p.y)) <= 6:
            return f"{npc.name} is nearby"
    for m in state.world.monsters:
        if m.seasons and state.season not in m.seasons:
            continue                                   # hibernating — not around
        if m.alive and max(abs(m.x - p.x), abs(m.y - p.y)) <= 6:
            return f"a {m.name.lower()} is nearby"
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            x, y = p.x + dx, p.y + dy
            if state.world.in_bounds(x, y):
                kind = state.world.tile_at(x, y).kind
                if kind in _NOTABLE_TILE:
                    return f"you reach {_NOTABLE_TILE[kind]}"
    return ""


def _blocker_name(state: GameState, x: int, y: int) -> str:
    """Name of whoever/whatever is standing on (x, y) — for run-stop messages."""
    m = combat.mob_at(state, x, y)
    if m is not None:
        return f"a {m.name.lower()}"
    if not state.world.is_dungeon:
        from .game import husbandry
        a = husbandry.animal_at(state, x, y)
        if a is not None:
            return a.name
        n = _npc_at(state, x, y)
        if n is not None:
            return n.name
    return "something"


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
            ctx["stop"] = "The road forks." if opts else "The road ends."
            return False
        nx, ny = p.x + ndir[0], p.y + ndir[1]
        if _entity_at(state, nx, ny):
            ctx["stop"] = f"You stop — {_blocker_name(state, nx, ny)} is in the way."
            return False
        p.x, p.y = nx, ny
        ctx["d"] = ndir
        turns.advance_time(state, C.ROAD_MOVE_SECONDS)
        ctx["steps"] += 1
        note = _notable_nearby(state)
        if ctx["steps"] >= RUN_MAX_TILES:
            ctx["stop"] = "You pause to catch your breath."
            return False
        if note:
            ctx["stop"] = f"You stop — {note}."
            return False
        exits = sum(_is_road(state, p.x + ax, p.y + ay) for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        if exits > 2:
            ctx["stop"] = "You reach a junction."
            return False
        return True

    # Off-road (wilderness / dungeon): straight-line run.
    nx, ny = p.x + dx, p.y + dy
    if not state.world.walkable(nx, ny):
        ctx["stop"] = "The way ahead is blocked."
        return False
    if _entity_at(state, nx, ny):
        ctx["stop"] = f"You stop — {_blocker_name(state, nx, ny)} is in the way."
        return False
    p.x, p.y = nx, ny
    turns.advance_time(state, C.MOVE_SECONDS)
    if not state.world.is_dungeon and skills.active_buff(state) != "brisk":
        p.energy = max(0, p.energy - C.WALK_STAMINA)
    if state.world.is_dungeon:
        delve.update_fov(state)
        _scoop_gold(state)                             # grab gold we ran over
        if _dungeon_tile_fx(state):
            return False                               # a trap sprang — it logs its own message
    ctx["steps"] += 1

    note = _notable_nearby(state)
    if ctx["steps"] >= RUN_MAX_TILES:
        ctx["stop"] = "You pause to catch your breath."
        return False
    if note:
        ctx["stop"] = f"You stop — {note}."
        return False
    if ctx["tunnel"]:
        if state.world.walkable(p.x - dy, p.y + dx) or state.world.walkable(p.x + dy, p.y - dx):
            ctx["stop"] = "The passage opens up."
            return False
    return True


def _check_warnings(state: GameState) -> None:
    """Nudge the player before a bad end: the late hour, and low HP/stamina.
    Each fires once until the condition clears (or the morning resets it)."""
    p, w = state.player, state.warned
    tm = state.time_minutes
    if tm >= C.MIDNIGHT_MIN and not w.get("midnight"):
        w["midnight"] = True
        state.log.add("Past midnight! Get to bed, or you'll drop where you stand at 2am.",
                      C.DANGER_COLOR)
    elif C.LATE_WARN_MIN <= tm < C.MIDNIGHT_MIN and not w.get("late"):
        w["late"] = True
        state.log.add("The evening draws on — best head to bed before long.", C.WARN_COLOR)

    if p.hp <= p.max_hp * C.LOW_HP_FRAC and not w.get("hp"):
        w["hp"] = True
        state.log.add("You're badly hurt — eat something or rest.", C.DANGER_COLOR)
    elif p.hp > p.max_hp * C.LOW_HP_FRAC:
        w["hp"] = False                              # re-arm once you recover

    if p.energy <= p.max_energy * C.LOW_ENERGY_FRAC and not w.get("energy"):
        w["energy"] = True
        state.log.add("You're worn out — rest soon or you'll collapse.", C.WARN_COLOR)
    elif p.energy > p.max_energy * C.LOW_ENERGY_FRAC:
        w["energy"] = False


def check_faint(state: GameState) -> None:
    """Collapse if slain, out of energy, or up past the small hours."""
    if state.player.hp <= 0:
        state.player.hp = 1
        farming.collapse(state, "You are struck down and black out...")
    elif state.player.energy <= 0:
        farming.collapse(state, "You collapse from exhaustion...")
    elif state.time_minutes >= C.DAY_END_MIN:
        farming.collapse(state, "You can't keep your eyes open and pass out...")
    else:
        _check_warnings(state)                       # not fainting yet — just warn


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
    """Keep the look cursor anywhere within the world; the camera follows it (so
    you can inspect tiles past the edge of where you stand)."""
    x = max(0, min(x, state.world.width - 1))
    y = max(0, min(y, state.world.height - 1))
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
            # Never let the morning autosave silently clobber a save we couldn't
            # read (e.g. a version mismatch): set the old one aside first.
            bak = save.backup()
            where = f" (kept a copy at {bak})" if bak else ""
            print(f"Could not load save ({e}); starting a new game{where}.")
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
    busy_ctx = None          # active long tool action (chop/mine), animating
    save_on_exit = True      # cleared by "quit without saving"
    cheat_sel = 0            # cursor in the Konami cheat menu
    konami: list = []        # rolling buffer of recent keys
    eat_sel = 0              # cursor in the eat menu
    mail_sel = 0             # cursor in the post box
    target_ctx = None        # active aiming context (throw / site a building)
    load_ctx = None          # active machine "choose input" menu
    msg_scroll = 0           # scrollback offset in the message-log view
    inv_sel = 0              # cursor in the inventory screen

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
                    reason = run_ctx.get("stop", "")
                    run_ctx = None
                    if reason:
                        state.log.add(reason, C.DIM)
                    check_faint(state)
                    quests.check(state)
            elif mode == "play" and rest_left > 0:
                turns.advance_time(state, C.MOVE_SECONDS)
                if state.world.is_dungeon:
                    delve.update_fov(state)
                rest_left -= C.MOVE_SECONDS
                note = _notable_nearby(state)
                if note or rest_left <= 0:
                    rest_left = 0
                    state.log.add(f"You stop resting — {note}." if note else "You rest a while.", C.DIM)
                    check_faint(state)
                    quests.check(state)
            elif mode == "play" and busy_ctx is not None:
                threat = _threat_near(state)
                if threat is not None:                   # a beast closes in — break off
                    state.log.add(f"You break off — a {threat.name.lower()} is too close!",
                                  C.WARN_COLOR)
                    busy_ctx = None
                else:
                    turns.advance_time(state, C.MOVE_SECONDS)
                    if state.world.is_dungeon:
                        delve.update_fov(state)
                    busy_ctx["left"] -= C.MOVE_SECONDS
                    if busy_ctx["left"] <= 0:
                        _finish_busy(state, busy_ctx)
                        busy_ctx = None
                        check_faint(state)
                        quests.check(state)

            rendering.render_all(console, state, anim_time)
            if mode == "play":
                rendering.render_facing(console, state)
            elif mode == "look":
                rendering.render_look(console, state, *look)
            elif mode == "help":
                rendering.render_codex(console, state, help_page, help_scroll)
            elif mode == "inventory":
                rendering.render_inventory(console, state, inv_sel)
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
            elif mode == "target":
                rendering.render_target(console, state, target_ctx)
            elif mode == "loadmachine":
                rendering.render_load_machine(console, state, load_ctx)
            elif mode == "log":
                rendering.render_message_log(console, state, msg_scroll)
            context.present(console)

            # A short timeout drives the ambient animation: when no key is
            # pressed, wait() returns after ~1/30s and we redraw the next frame.
            for event in tcod.event.wait(timeout=1.0 / 30.0):
                if isinstance(event, tcod.event.WindowEvent) and event.type == "WINDOWCLOSE":
                    running = False
                    break

                # Konami code (↑↑↓↓←→←→ B A) opens the hidden cheat menu.
                if isinstance(event, tcod.event.KeyDown):
                    konami.append(int(event.sym))
                    del konami[:-len(_KONAMI)]
                    if konami == _KONAMI:
                        konami.clear()
                        mode, cheat_sel = "cheats", 0
                        state.log.add("A hidden door creaks open...", (250, 230, 140))
                        continue

                # A fresh key press interrupts an in-progress run or rest — but
                # NOT OS key-repeat from still holding the direction that began
                # the run, which would cancel it almost immediately.
                if (isinstance(event, tcod.event.KeyDown) and not getattr(event, "repeat", False)
                        and (run_ctx is not None or rest_left > 0 or busy_ctx is not None)):
                    run_ctx, rest_left, busy_ctx = None, 0, None
                    continue

                # ADOM-style list screens: a bare letter picks an item / tool
                # directly. Handled here (before the normal command mapping) so
                # even keys that would otherwise be commands act as selectors.
                if isinstance(event, tcod.event.KeyDown) and mode in ("inventory", "equipment") \
                        and not (event.mod & tcod.event.Modifier.SHIFT):
                    s = int(event.sym)
                    ch = chr(s) if ord("a") <= s <= ord("z") else ""
                    if mode == "inventory" and ch and ch not in ("i", "e"):
                        n = len(state.player.inventory.slots)
                        if ord(ch) - ord("a") < n:
                            inv_sel = ord(ch) - ord("a")
                        continue
                    if mode == "equipment" and ch and ch in "abcdef":
                        select_slot(state, "abcdef".index(ch))
                        continue

                action = game_input.event_to_action(event)
                if action is None:
                    continue
                cmd = action[0]

                # OS quit (Cmd+Q / window close via SDL): leave immediately
                # without saving, from any screen.
                if cmd == "sysquit":
                    save_on_exit = False
                    running = False
                    break

                if mode == "play":
                    if awaiting_run:
                        awaiting_run = False
                        if cmd == "move":
                            run_ctx = start_run(state, action[1], action[2])
                            if run_ctx is None:
                                state.log.add("You can't run that way.", C.DIM)
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
                        state.cam_focus = tuple(look)
                    elif cmd == "use":
                        busy = use_tool(state)
                        if busy is not None:
                            busy_ctx = busy          # a long task begins — it animates
                        else:
                            check_faint(state)
                    elif cmd == "grab":
                        if _at_postbox(state):
                            if state.mail:
                                mode, mail_sel = "mail", 0
                            else:
                                state.log.add("Your post box is empty.", C.DIM)
                        else:
                            req = do_grab(state)
                            if isinstance(req, dict) and "load" in req:
                                load_ctx = {"pos": req["load"], "options": req["options"],
                                            "name": req["name"], "sel": 0}
                                mode = "loadmachine"
                            else:
                                check_faint(state)
                    elif cmd == "place":
                        if not state.pending_build:
                            state.log.add("You've nothing on order from the carpenter.", C.DIM)
                        elif state.world.is_dungeon:
                            state.log.add("You can only raise a building on the surface.", C.DIM)
                        else:
                            fx, fy = state.player.facing
                            cur = clamp_look(state, state.player.x + fx, state.player.y + fy)
                            target_ctx = {"purpose": "build", "cursor": cur,
                                          "build_kind": state.pending_build}
                            state.cam_focus = tuple(cur)
                            mode = "target"
                    elif cmd == "target":
                        if state.player.inventory.count(items.BOMB) < 1:
                            state.log.add("You've nothing to aim — craft a bomb first (c).", C.DIM)
                        else:
                            fx, fy = state.player.facing
                            cur = clamp_look(state, state.player.x + fx, state.player.y + fy)
                            target_ctx = {"purpose": "throw", "cursor": cur}
                            state.cam_focus = tuple(cur)
                            mode = "target"
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
                        if crafting.edible_items(state):
                            mode, eat_sel = "eat", 0
                        else:
                            state.log.add("You have nothing to eat. Cook (c) a dish or gather eggs/milk.", C.DIM)
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
                        elif npc.shop:
                            # every shopkeeper still gets the daily greeting
                            # (friendship, festival treats, heart gifts), then trades
                            dialogue_line = village.talk(state, npc)
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
                        state.player.inventory.slots.sort(
                            key=lambda e: rendering.inv_sort_key(e[0], e[2]))
                        mode, inv_sel = "inventory", 0
                    elif cmd == "equipment":
                        mode = "equipment"
                    elif cmd == "messages":
                        mode, msg_scroll = "log", 0
                    if cmd in ("move", "wait"):
                        check_faint(state)
                    quests.check(state)              # re-check goals on any action

                elif mode == "look":
                    if cmd in ("look", "cancel", "quit"):
                        mode = "play"
                        state.cam_focus = None
                    elif cmd == "move":
                        look = clamp_look(state, look[0] + action[1], look[1] + action[2])
                        state.cam_focus = tuple(look)

                elif mode == "target":
                    if cmd in ("cancel", "target", "quit"):
                        mode, target_ctx, state.cam_focus = "play", None, None
                    elif cmd == "move":
                        cur = clamp_look(state, target_ctx["cursor"][0] + action[1],
                                         target_ctx["cursor"][1] + action[2])
                        target_ctx["cursor"] = cur
                        state.cam_focus = tuple(cur)
                    elif cmd in ("confirm", "use"):
                        tx, ty = target_ctx["cursor"]
                        if target_ctx["purpose"] == "throw":
                            combat.throw_bomb_at(state, tx, ty)
                            check_faint(state)
                        else:
                            from .game import husbandry
                            husbandry.place_commission_at(state, tx, ty)
                        mode, target_ctx, state.cam_focus = "play", None, None
                        quests.check(state)

                elif mode == "loadmachine":
                    opts = load_ctx["options"] if load_ctx else []
                    if cmd in ("cancel", "grab", "quit") or not opts:
                        mode, load_ctx = "play", None
                    elif cmd == "move" and action[2]:
                        load_ctx["sel"] = (load_ctx["sel"] + action[2]) % len(opts)
                    elif cmd == "confirm":
                        m = state.world.machines.get(load_ctx["pos"])
                        if m is not None:
                            crafting.load_machine_choice(state, m, crafting.MACHINES[m.kind],
                                                         opts[min(load_ctx["sel"], len(opts) - 1)])
                        mode, load_ctx = "play", None
                        quests.check(state)

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
                    slots = state.player.inventory.slots
                    if cmd == "equipment":
                        mode = "equipment"
                    elif cmd in ("cancel", "inventory", "quit"):
                        mode = "play"
                    elif cmd == "slot":
                        select_slot(state, action[1])
                    elif cmd == "move" and action[2] and slots:
                        inv_sel = (inv_sel + action[2]) % len(slots)
                    elif cmd == "drop" and slots:
                        inv_sel = min(inv_sel, len(slots) - 1)
                        it, _q, ql = slots[inv_sel]
                        state.player.inventory.remove(it, 1, quality=ql)
                        state.log.add(f"You toss out a {it.name.lower()}.", C.DIM)
                        if inv_sel >= len(state.player.inventory.slots):
                            inv_sel = max(0, len(state.player.inventory.slots) - 1)

                elif mode == "log":
                    if cmd in ("cancel", "messages", "quit"):
                        mode = "play"
                    elif cmd == "move" and action[2]:
                        msg_scroll = max(0, msg_scroll - action[2])   # up = older

                elif mode == "equipment":
                    if cmd == "inventory":
                        state.player.inventory.slots.sort(
                            key=lambda e: rendering.inv_sort_key(e[0], e[2]))
                        mode, inv_sel = "inventory", 0
                    elif cmd in ("cancel", "equipment", "quit"):
                        mode = "play"
                    elif cmd == "slot":
                        select_slot(state, action[1])

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
                    foods = crafting.edible_items(state)
                    if cmd in ("cancel", "eat", "quit"):
                        mode = "play"
                    elif cmd == "move" and action[2] and foods:
                        eat_sel = (eat_sel + action[2]) % len(foods)
                    elif cmd == "confirm" and foods:
                        eat_sel = min(eat_sel, len(foods) - 1)
                        it, _q, ql = foods[eat_sel]
                        _eat(state, it, ql)
                        check_faint(state)
                        if not crafting.edible_items(state):
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
                    entries = village.shop_entries(npc.shop, state)
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
                        git, _gq, gql = gifts[min(gift_sel, len(gifts) - 1)]
                        village.gift(state, npc, git, gql)
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
                    elif cmd in ("sleep", "confirm", "quitgame"):  # S / Enter / Q — save & quit
                        running = False                  # (Q is safe so a reflexive qq can't lose the day)
                    elif cmd == "discard":               # Backspace — quit WITHOUT saving
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
