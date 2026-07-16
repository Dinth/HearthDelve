"""Player commands and world interactions — the verbs of the game.

These functions mutate GameState (move, work a tile, eat, equip, run, rest…)
and write to the message log; none of them touch the console. The UI screens
in screens.py call them, keeping presentation and simulation apart.
"""
from __future__ import annotations

import random

from ..engine import constants as C
from ..entities import items
from ..world import tile
from . import combat, crafting, delve, farming, fishing, skills, turns
from .state import GameState


def _cheat_locations(state: GameState):
    """(label, target) teleport targets for the cheat menu. Targets are surface
    (x, y) coords, or a special string for the far places."""
    surf = state.surface
    locs = [("Home (the farm)", surf.spawn)]
    for name, c in getattr(surf, "village_centers", {}).items():
        locs.append((name, c))
    for b in surf.buildings:
        if b.get("kind") == "hut":
            locs.append(("The Wildwood hut", b["front"]))
    for (dx, dy) in surf.dungeons:
        locs.append((f"Enter dungeon — {surf.dungeon_kind.get((dx, dy), 'delve')}", (dx, dy)))
    locs.append(("The Westreach (volcano)", "west:volcano"))
    locs.append(("Khazgrim (the dwarf town)", "west:khazgrim"))
    return locs


def _cheat_go(state: GameState, target) -> None:
    """Teleport to a surface spot — or, if it's a dungeon entrance, drop right
    into the dungeon. String targets reach the Westreach and Khazgrim."""
    if state.world.is_dungeon:
        delve.leave_to_surface(state)          # back to the open air first
    if isinstance(target, str) and target.startswith("west:"):
        from ..world import westgen, tile as _t
        import numpy as _np
        if state.west is None:
            state.west = westgen.generate(state.seed)
        west = state.west
        if target == "west:volcano":
            lava = _np.argwhere(west.tiles == _t.LAVA)
            cx, cy = ((int(lava[:, 0].mean()), int(lava[:, 1].mean())) if len(lava)
                      else west.spawn)
            state.world = west
            state.player.x, state.player.y = _edge_landing(west, cx + 12, cy, step=1)
        else:                                  # Khazgrim: straight down the mine
            mouth = next((pos for pos, k in west.dungeon_kind.items()
                          if k == "dwarfhold"), west.spawn)
            state.world = west
            state.player.x, state.player.y = mouth
            delve.enter(state, "dwarfhold")
            from ..world import dwarftown
            while state.depth < dwarftown.TOWN_DEPTH:
                delve.descend(state)
        state.cam_focus = None
        return
    surf = state.surface
    state.world = surf                          # a surface target from anywhere
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

# which herb item each wild-herb tile yields when foraged
_HERB_ITEM = {
    tile.HERB_CHAMOMILE: items.CHAMOMILE,
    tile.HERB_YARROW: items.YARROW,
    tile.HERB_COMFREY: items.COMFREY,
    tile.HERB_LAVENDER: items.LAVENDER,
    tile.HERB_SAGE: items.SAGE,
    tile.HERB_MANDRAKE: items.MANDRAKE,
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
        from . import husbandry
        if husbandry.animal_at(state, x, y) is not None or _npc_at(state, x, y) is not None:
            return True
    return False


def _scoop_gold(state: GameState) -> None:
    """Pick up a gold pile the player is standing on (dungeon vaults)."""
    p = state.player
    if state.world.tile_at(p.x, p.y).kind == "gold":
        amt = random.randint(20, 60) + state.world.depth * 10
        p.gold += amt
        state.world.tiles[p.x, p.y] = _floor_of(state.world)
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
    if b.get("steal"):
        from . import land
        land.penalize(state, b["tx"], b["ty"], "growth")


def _apply_walk(state: GameState, on_road: bool) -> None:
    """Spend the time and stamina of one step, scaled by how laden you are.

    Time always advances (a heavy pack slows you everywhere, so monsters get
    their turns). Stamina is spent only above ground — roads and a Brisk meal
    still spare you the *base* footfall, but the weight of a real haul tells on
    you even on a good road (see game.encumbrance)."""
    from . import encumbrance as enc
    ratio = enc.load_ratio(state)
    base_time = C.ROAD_MOVE_SECONDS if on_road else C.MOVE_SECONDS
    turns.advance_time(state, max(1, round(base_time * enc.time_mult(ratio))))
    if state.world.is_dungeon:
        return
    brisk = skills.active_buff(state) == "brisk"
    base = 0.0 if (on_road or brisk) else float(C.WALK_STAMINA)
    load = enc.load_stamina(ratio) * (0.6 if on_road else 1.0)   # roads carry easier
    cost = int(round(base + load))
    if cost:
        state.player.energy = max(0, state.player.energy - cost)


def try_move(state: GameState, dx: int, dy: int) -> None:
    p = state.player
    p.facing = (dx, dy)
    nx, ny = p.x + dx, p.y + dy
    # bump a farm animal to pet it or collect its produce (never a strike)
    if not state.world.is_dungeon:
        from . import husbandry
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
        on_road = _is_road(state, nx, ny)                       # roads/bridges/cobble: fast & easy
        _apply_walk(state, on_road)                             # time + stamina, scaled by load
        if state.world.is_dungeon:
            delve.update_fov(state)
            _dungeon_tile_fx(state)
    else:
        if not state.world.in_bounds(nx, ny):
            # Walking off the western edge crosses into the Westreach (and the
            # Westreach's eastern edge leads home) — the world is wider than
            # the map.
            if nx < 0 and state.world is state.surface:
                _cross_to_west(state)
            elif state.west is not None and state.world is state.west \
                    and nx >= state.world.width:
                _cross_to_surface(state)
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


def _floor_of(w) -> int:
    """This dungeon's re-skinned floor tile (so a mined vein or sprung trap heals
    to the kind's palette, not a bright generic scar). Falls back to the default."""
    return getattr(w, "floor_tile", 0) or tile.DUNGEON_FLOOR


def _spring_trap(state: GameState) -> None:
    """Trigger the trap under the player and disarm the tile."""
    p, w = state.player, state.world
    w.tiles[p.x, p.y] = _floor_of(w)
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
    pos = (p.x, p.y)
    kind = w.tile_at(p.x, p.y).kind
    if pos in w.hidden_traps:              # an unspotted trap underfoot
        w.hidden_traps.discard(pos)
        _spring_trap(state)
        sprang = True
    elif kind == "trap":                   # an already-spotted trap, stepped on anyway
        _spring_trap(state)
        sprang = True
    elif kind == "rubble":
        turns.advance_time(state, C.MOVE_SECONDS)   # loose footing, slow going
    for ddx in (-1, 0, 1):                 # notice adjacent hidden traps
        for ddy in (-1, 0, 1):
            xy = (p.x + ddx, p.y + ddy)
            if xy in w.hidden_traps and random.random() < 0.4:
                w.hidden_traps.discard(xy)
                w.tiles[xy] = tile.TRAP
    return sprang


def use_tool(state: GameState) -> None:
    """Use the active hotbar item on the tile the player is facing.

    Seeds plant; the watering can waters a crop if one is there; other tools
    fall through to the pure resolver.
    """
    from ..data import content
    from . import actions

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
        ctx = fishing.begin(state, tx, ty)
        return {"fishing": ctx} if ctx else None

    # Watering can over a planted tile waters the crop directly.
    if item is items.WATERING_CAN and (tx, ty) in state.world.crops:
        if p.energy <= 0:
            state.log.add("You're too exhausted. Rest first.", C.DIM)
            return None
        if farming.water_crop(state, tx, ty):
            tier = p.tool_tier.get(items.WATERING_CAN, 0)
            p.energy = max(0, p.energy - max(1, round(C.WATER_COST[0] * (1 - 0.12 * tier))))
            turns.advance_time(state, C.WATER_COST[1])
            return None

    target = state.world.tile_at(tx, ty)
    success, new_tile, msg = actions.resolve_tool(item, target)
    if not success:
        state.log.add(msg, C.DIM)
        return None

    # The deep rock outgrows a cheap pickaxe — but it never refuses you.
    # Under-tooled mining is slow, sweaty and wasteful (see _gather_drop), so
    # a stubborn delver can always chip at the deeps; the smithy just makes
    # the same rock cheap. Progression as efficiency, not permission.
    underpick = 0
    if (item is items.PICKAXE and state.world.is_dungeon
            and target.name in ("ore_vein", "gem_vein")):
        need = _pick_tier_for_depth(state.world.depth)
        have = p.tool_tier.get(items.PICKAXE, 0)
        underpick = max(0, need - have)
        if underpick:
            state.log.add(f"Your {C.TOOL_TIERS[have].lower()} pickaxe barely bites this "
                          f"rock — slow, wasteful work. ({C.TOOL_TIERS[need]} would serve.)",
                          C.DIM)

    # Whose land is this? Tilling/working another's land is refused; felling
    # their tree or clearing their brush is vandalism — allowed once confirmed,
    # but it costs karma and the owner's regard.
    from . import land
    steal = False
    if land.owned_by_other(state, tx, ty):
        if item is items.HOE or new_tile == tile.TILLED:
            state.log.add(f"You can't work {land.owner_label(state, tx, ty)} land.", C.DIM)
            return None
        gate = land.check_take(state, tx, ty, "growth")
        if gate == "confirm":
            return None
        steal = gate == "steal"

    if p.energy <= 0:
        state.log.add("You're too exhausted. Rest first.", C.DIM)
        return None

    if item.kind == "weapon":
        # a weapon doing a tool's job: slower and more tiring than the real tool
        cat = content.profile_of(item).category
        base = C.CHOP_COST if cat == "axe" else C.MACHETE_COST
        stamina, seconds = base[0] + 2, int(base[1] * 1.5)
    else:
        from . import jewelry
        stat = content.TOOL_STATS.get(item)
        tier = p.tool_tier.get(item, 0)          # 0 Wooden … 5 Mithril
        # Each tier eases the work by 12% — a Mithril tool costs 40% of the
        # wooden one's sweat, but never nothing: the tool ladder stretches the
        # day's stamina budget rather than deleting it.
        stamina = max(1, round(stat.stamina * (1 - 0.12 * tier))) if stat else 1
        if item in p.tool_affix:                 # an imbued tool works with less effort
            stamina = max(1, stamina - 1)
        # An amethyst — set in this tool or worn as jewellery — eases the effort.
        discount = round(jewelry.tool_gem_bonus(state, item, "energy")
                         + jewelry.cozy_bonus(state, "energy"))
        if discount:
            stamina = max(1, stamina - discount)
        # Finer tools also work FASTER — each tier shaves 10% off the action time,
        # so a full upgrade (Mithril) halves it. Time is the day's real currency,
        # so this is what makes the tool ladder worth the metal.
        base_secs = stat.seconds if stat else C.USE_SECONDS
        seconds = max(1, round(base_secs * (1 - 0.10 * tier)))
    # Fighting rock above your pick's band: half again the time and sweat per
    # band you're short — punishing, never impossible.
    if underpick:
        stamina = round(stamina * (1 + 0.5 * underpick))
        seconds = round(seconds * (1 + 0.5 * underpick))
    # The dark weighs on you: every floor down, work drains a little more —
    # so how deep a delve can run is bounded by stamina, and by the tools and
    # meals that spare it.
    if state.world.is_dungeon:
        stamina += state.world.depth // 3
    if new_tile is not None and state.world.is_dungeon and new_tile == tile.GRASS:
        new_tile = _floor_of(state.world)     # mined rock/ore heals to the kind's floor

    # Long tasks (felling a tree, breaking rock) play out over a few seconds so
    # the world moves around you — and a menacing creature can break them off.
    if seconds >= LONG_ACTION_SECONDS:
        threat = _threat_near(state)
        if threat is not None:
            state.log.add(f"You can't focus with a {threat.name.lower()} so close.", C.DIM)
            return None
        state.log.add(f"You set to work with the {item.name.lower()}...", C.DIM)
        return {"left": seconds, "item": item, "tx": tx, "ty": ty, "target": target,
                "new_tile": new_tile, "stamina": stamina, "msg": msg, "steal": steal}

    # Short tasks resolve at once.
    if new_tile is not None:
        state.world.tiles[tx, ty] = new_tile
    p.energy = max(0, p.energy - stamina)
    turns.advance_time(state, seconds)
    state.log.add(msg)
    _gather_drop(state, item, target)
    if steal:
        land.penalize(state, tx, ty, "growth")
    elif new_tile == tile.TILLED:
        land.note_claim(state, [(tx, ty)])
    return None


def _pick_tier_for_depth(depth: int) -> int:
    """Minimum pickaxe tier to break veins at a depth — aligned with the ore
    bands (see content._ore_band): the band you can drop into is roughly the
    band your current pick was forged from."""
    if depth <= 1:
        return 0        # Wooden — copper & tin country
    if depth <= 3:
        return 1        # Bronze — the iron/silver band
    if depth <= 5:
        return 2        # Iron — gold & platinum
    if depth <= 7:
        return 3        # Steel — adamantite runs
    return 4            # Adamantium — the mithril deeps


def _gather_drop(state: GameState, item, target) -> None:
    """Chopping and mining yield raw materials, XP, and progress."""
    from . import skills
    from ..data import content
    inv = state.player.inventory
    if item.kind == "weapon":                          # a weapon used as a tool — poor yield
        cat = content.profile_of(item).category
        if cat == "axe" and target.kind == "tree":
            inv.add(items.WOOD, 1)
            state.bump("trees_chopped")
            skills.gain(state, "Foraging", 4)
            state.log.add("  (+1 Wood — a weapon makes clumsy work of it)", C.DIM)
        elif cat == "blade" and target.name == "tall_grass":
            inv.add(items.CUT_GRASS, 1)
            state.log.add("  (+1 Cut Grass)", C.DIM)
        elif cat == "blade" and target.kind in ("foliage", "shrub") and random.random() < 0.4:
            inv.add(items.FIBER, 1)
            state.log.add("  (+1 Fiber)", C.DIM)
        return
    # An under-tiered pick mangles what it breaks: per band it falls short, a
    # rising chance the vein's riches come away as worthless rubble. The deeps
    # stay open to a stubborn wooden pick — they just pay it poorly.
    def _mangled() -> bool:
        if not state.world.is_dungeon or item is not items.PICKAXE:
            return False
        short = _pick_tier_for_depth(state.world.depth) - state.player.tool_tier.get(items.PICKAXE, 0)
        return short > 0 and random.random() < min(0.85, 0.3 * short)

    if item is items.AXE and target.kind == "tree":
        inv.add(items.WOOD, 2)
        state.bump("trees_chopped")
        skills.gain(state, "Foraging", 8)
        state.log.add("  (+2 Wood)", C.DIM)
    elif item is items.PICKAXE and target.name == "gem_vein":
        if _mangled():
            inv.add(items.STONE, 2)
            state.bump("ore_mined")
            skills.gain(state, "Mining", 4)
            state.log.add("  Your pick shatters the seam — just rubble. (+2 Stone)", C.DIM)
            return
        from ..data import content
        gem = content.gem_for_depth(state.world.depth, random)   # deeper veins, finer gems
        inv.add(gem, 1)
        state.bump("ore_mined")
        skills.gain(state, "Mining", 20)
        if random.random() < 0.3:
            inv.add(items.STONE, 1)
        state.log.add(f"  (+1 {gem.name})", C.DIM)
    elif item is items.PICKAXE and target.name == "ore_vein" and _mangled():
        inv.add(items.STONE, 2)
        if random.random() < 0.45:
            inv.add(items.COAL, 1)
        state.bump("ore_mined")
        skills.gain(state, "Mining", 4)
        state.log.add("  Your pick mangles the vein — mostly rubble. (+2 Stone)", C.DIM)
    elif item is items.PICKAXE and target.name == "ore_vein":
        # An ore vein mostly gives stone, often coal, sometimes ore — and now and
        # then a geode to crack open later (a little likelier the deeper you dig).
        got = []
        if random.random() < 0.80:
            inv.add(items.STONE, 1); got.append("Stone")
        if random.random() < 0.45:
            inv.add(items.COAL, 1); got.append("Coal")
        if random.random() < 0.30:
            from ..data import content
            ore = content.ore_for_depth(state.world.depth, random)
            inv.add(ore, 1); got.append(ore.name)
        if random.random() < 0.05 + 0.02 * state.world.depth:
            inv.add(items.GEODE, 1); got.append("Geode")
        if not got:                       # always yield something
            inv.add(items.STONE, 1); got.append("Stone")
        state.bump("ore_mined")
        skills.gain(state, "Mining", 16)
        state.log.add("  (+" + ", +".join(got) + ")", C.DIM)
    elif item is items.PICKAXE and target.name == "sulphur_deposit":
        n = 1 + (random.random() < 0.5)
        inv.add(items.SULPHUR, n)
        state.bump("ore_mined")
        skills.gain(state, "Mining", 10)
        state.log.add(f"  (+{n} Sulphur)", C.DIM)
    elif item is items.PICKAXE and target.name == "nitre_deposit":
        n = 1 + (random.random() < 0.5)
        inv.add(items.SALTPETER, n)
        state.bump("ore_mined")
        skills.gain(state, "Mining", 10)
        state.log.add(f"  (+{n} Saltpeter)", C.DIM)
    elif item is items.PICKAXE and target.name in ("rock", "ruins_wall"):
        inv.add(items.STONE, 2)
        state.bump("ore_mined")
        skills.gain(state, "Mining", 10)
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
        from ..data import content
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

    # What a gather tool drops a bonus unit of, by the tile worked.
    def _bonus_drop():
        if item is items.AXE and target.kind == "tree":
            return items.WOOD
        if item is items.PICKAXE and target.name in ("ore_vein", "rock", "ruins_wall"):
            return items.STONE
        if item is items.MACHETE and target.kind in ("tall_grass", "foliage", "shrub", "shrub_berry"):
            return items.FIBER
        return None

    # An imbued gather tool now and then yields a little extra of its craft.
    affix = state.player.tool_affix.get(item)
    if affix and random.random() < 0.45:
        extra = _bonus_drop()
        if extra:
            inv.add(extra, 1)
            state.log.add(f"  ({affix}: +1 {extra.name})", (180, 220, 150))

    # An emerald (or diamond) set in the tool enriches the same yield.
    from . import jewelry
    gem_yield = jewelry.tool_gem_bonus(state, item, "yield")
    if gem_yield and random.random() < gem_yield * 4:      # ~0.08 -> ~32% for an extra
        extra = _bonus_drop()
        if extra:
            inv.add(extra, 1)
            state.log.add(f"  (gem: +1 {extra.name})", (150, 210, 170))


def _equip(state: GameState, item) -> None:
    """Equip a carried weapon (into the held hotbar weapon slot) or armour piece
    (into its paperdoll slot); whatever was there returns to the pack."""
    from ..data import content
    p = state.player
    if item.kind == "weapon":
        idx = next((i for i, h in enumerate(p.hotbar) if h.kind == "weapon"), None)
        old = p.hotbar[idx] if idx is not None else None
        if not p.inventory.remove(item, 1):
            return
        if idx is None:
            p.hotbar.append(item)
        else:
            p.hotbar[idx] = item
        if old:
            p.inventory.add(old)
        p.weapon = item
        state.log.add(f"You ready the {item.name.lower()}.", (200, 220, 160))
    elif item.kind == "armor":
        slot = content.ARMOR_SLOT.get(item)
        if slot is None:
            return
        if not p.inventory.remove(item, 1):
            return
        old = p.equipment.get(slot)
        p.equipment[slot] = item
        if old:
            p.inventory.add(old)
        state.log.add(f"You don the {item.name.lower()}.", (200, 220, 160))
    elif item.kind == "jewelry":
        # A ring or amulet. Amulets fill the neck slot; rings fill the first free
        # ring slot (else replace ring1). Star quality rides with the piece into
        # its slot (equip_quality), so a fine jeweller's work stays fine when worn.
        want = content.jewel_slot(item)
        if want == "neck":
            slot = "neck"
        else:
            slot = "ring1" if p.equipment.get("ring1") is None else (
                "ring2" if p.equipment.get("ring2") is None else "ring1")
        q = p.inventory.pop_quality(item, 1)     # take one, remember its stars
        old, oldq = p.equipment.get(slot), p.equip_quality.get(slot, 0)
        p.equipment[slot] = item
        p.equip_quality[slot] = int(round(q))
        if old:
            p.inventory.add(old, 1, quality=oldq)
        state.log.add(f"You put on the {item.name.lower()}.", (200, 220, 160))
    elif item.kind in ("ranged", "ammo", "bomb"):
        # ranged launchers go in the ranged slot; arrows/stones/bombs in the ammo
        # slot. Ammo is a stackable type, so the panel just marks which you'll
        # loose — the count stays in your pack; the old item isn't pulled out.
        slot = "ranged" if item.kind == "ranged" else "ammo"
        old = p.equipment.get(slot)
        if slot == "ranged":
            if not p.inventory.remove(item, 1):
                return
            if old:
                p.inventory.add(old)
        p.equipment[slot] = item
        verb = "take up" if slot == "ranged" else "ready"
        state.log.add(f"You {verb} the {item.name.lower()}.", (200, 220, 160))


def _unequip(state: GameState, slot: str) -> None:
    """Take off a worn piece, returning it to the pack. Ammo just clears its
    ready-marker (the stack lives in the pack); other slots hand the item back."""
    p = state.player
    it = p.equipment.get(slot)
    if it is None:
        state.log.add("Nothing worn in that slot.", C.DIM)
        return
    p.equipment[slot] = None
    if slot == "ammo":                      # ammo was only marked, never pulled out
        state.log.add(f"You unready the {it.name.lower()}.", (200, 200, 180))
    else:
        q = p.equip_quality.pop(slot, 0)    # hand jewellery back at its stored stars
        p.inventory.add(it, 1, quality=q)
        state.log.add(f"You take off the {it.name.lower()}.", (200, 200, 180))


def _beside_sea(state: GameState, x: int, y: int) -> bool:
    """Whether (x, y) borders open water — a genuine sea beach, not inland sand."""
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if state.world.in_bounds(x + dx, y + dy) and state.world.tile_at(x + dx, y + dy).kind == "water":
            return True
    return False


def do_grab(state: GameState) -> None:
    """Harvest a crop or interact with a machine — faced tile, then underfoot."""
    from . import land
    p = state.player
    for gx, gy in ((p.x + p.facing[0], p.y + p.facing[1]), (p.x, p.y)):
        if not state.world.in_bounds(gx, gy):
            continue
        tk = state.world.tile_at(gx, gy).kind

        # Taking crops/fruit/berries/fungus off another's land is theft: warn
        # once, then it's allowed at the cost of karma and the owner's regard.
        stealing = False
        if tk in ("mushroom", "glowcap", "shrub_berry", "herb") or (gx, gy) in state.world.crops \
                or (gx, gy) in state.world.trees:
            if land.owned_by_other(state, gx, gy):
                gate = land.check_take(state, gx, gy, "harvest")
                if gate == "confirm":
                    return None
                stealing = gate == "steal"

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
                item, floor, col = items.CAVE_MUSHROOM, _floor_of(state.world), (206, 160, 190)
            else:                                        # a named wild species
                item = _MUSHROOM_ITEM.get(state.world.tiles[gx, gy], items.BUTTON_MUSHROOM)
                floor, col = tile.GRASS, (206, 176, 130)
            state.world.tiles[gx, gy] = floor
            from . import skills
            q = skills.roll_quality(state, "Foraging")
            p.inventory.add(item, 1, quality=q)
            skills.gain(state, "Foraging", 12 if tk == "glowcap" else 8)
            star = (" " + skills.stars(q)) if q else ""
            state.log.add(f"You gather a {item.name.lower()}{star}.", col)
            turns.advance_time(state, C.HARVEST_COST[1])
            if stealing:
                land.penalize(state, gx, gy, "harvest")
            return
        if tk == "herb":                                 # forage a wild herb (Herbalism)
            item = _HERB_ITEM.get(state.world.tiles[gx, gy], items.SAGE)
            base = next((b for (hx, hy, sp, b) in state.world.herb_spots
                         if (hx, hy) == (gx, gy)), tile.GRASS)
            state.world.tiles[gx, gy] = base
            from . import skills
            q = skills.roll_quality(state, "Herbalism")
            p.inventory.add(item, 1, quality=q)
            skills.gain(state, "Herbalism", 10)
            star = (" " + skills.stars(q)) if q else ""
            state.log.add(f"You gather {item.name.lower()}{star}.", (150, 196, 140))
            turns.advance_time(state, C.HARVEST_COST[1])
            if stealing:
                land.penalize(state, gx, gy, "harvest")
            return
        if tk == "shrub_berry":                          # pick berries; the bush stays
            _pick_berries(state, gx, gy)
            if stealing:
                land.penalize(state, gx, gy, "harvest")
            return
        if state.world.tile_at(gx, gy).name == "sand" and _beside_sea(state, gx, gy):  # scrape sea salt off the strand
            from . import skills
            if random.random() < 0.55:
                p.inventory.add(items.SALT_LUMP, 1)
                skills.gain(state, "Foraging", 6)
                state.log.add("You scrape a lump of sea salt from the strand.", (206, 216, 224))
            else:
                state.log.add("Only damp sand here — try again.", C.DIM)
            turns.advance_time(state, C.HARVEST_COST[1])
            return
        if (gx, gy) in state.world.crops:
            plot = state.world.crops[(gx, gy)]
            # A growing crop takes fertiliser (g with some in the pack): the
            # nitre-fed soil grows a finer harvest (+1 star at picking).
            if (not plot.mature and not plot.dead and not plot.fertilized
                    and p.inventory.count(items.FERTILISER) > 0
                    and not land.owned_by_other(state, gx, gy)):
                p.inventory.remove(items.FERTILISER, 1)
                plot.fertilized = True
                turns.advance_time(state, C.HARVEST_COST[1])
                state.log.add(f"You work fertiliser into the soil around the "
                              f"{plot.crop.name.lower()}.", (200, 220, 160))
                return
            if farming.harvest(state, gx, gy):
                if stealing:
                    land.penalize(state, gx, gy, "harvest")
                return
        if (gx, gy) in state.world.trees:
            if farming.pick_tree(state, gx, gy):
                if stealing:
                    land.penalize(state, gx, gy, "harvest")
                return
        if (gx, gy) in state.world.machines:
            res = crafting.interact_machine(state, gx, gy)
            if isinstance(res, dict):        # machine wants a "what to load?" choice
                return res
            if res:
                return None
    state.log.add("Nothing here to gather.", C.DIM)
    return None


def _pick_berries(state: GameState, x: int, y: int) -> None:
    """Forage a berry shrub without destroying it — it's stripped to a plain bush
    and re-berries a few days later (see farming._regrow_berries)."""
    from ..data import content
    from . import skills
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
    farming.schedule_berry_regrow(state, x, y, btile)
    skills.gain(state, "Foraging", 8)
    star = (" " + skills.stars(q)) if q else ""
    fn = fruit.name.lower() if fruit else "berries"
    state.log.add(f"You pick {n} {fn}{star}; the bush will bear again in a few days.",
                  (200, 170, 120))
    turns.advance_time(state, C.HARVEST_COST[1])


def _rob_hive(state: GameState, x: int, y: int) -> None:
    """Rob a wild bee hive: honey and wax, a mild sting, and rarely a queen."""
    from . import skills
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
    from . import skills
    skills.gain(state, "Foraging", 14)
    turns.advance_time(state, C.HARVEST_COST[1])


def _at_postbox(state: GameState) -> bool:
    return _facing_tile_kind(state, "postbox")


def _at_board(state: GameState) -> bool:
    return _facing_tile_kind(state, "board")


def _edge_landing(gm, x0: int, y0: int, step: int):
    """A walkable arrival tile near (x0, y0), scanning inward (by `step` in x)
    and outward in y — so a crossing never strands you in rock or lava."""
    for dx in range(0, 12):
        for dy in [0] + [s * d for d in range(1, 9) for s in (1, -1)]:
            x, y = x0 + dx * step, y0 + dy
            if gm.in_bounds(x, y) and gm.walkable(x, y):
                return (x, y)
    return gm.spawn or (x0, y0)


def _cross_to_west(state: GameState) -> None:
    from ..world import westgen
    first = state.west is None
    if first:
        state.west = westgen.generate(state.seed)
    west = state.west
    wy = int(state.player.y / state.surface.height * west.height)
    state.player.x, state.player.y = _edge_landing(west, west.width - 2, wy, step=-1)
    state.world = west
    state.cam_focus = None
    if first:
        state.log.add("You crest the pass into the Westreach — hill country, ash "
                      "on the wind, and eyes in the rocks.", (232, 200, 120))
        state.log.add("The beasts out here don't wait to be provoked. Walk east to "
                      "come home.", C.DIM)
    else:
        state.log.add("You cross the pass into the Westreach.", (210, 200, 190))


def _cross_to_surface(state: GameState) -> None:
    surf = state.surface
    sy = int(state.player.y / state.world.height * surf.height)
    state.player.x, state.player.y = _edge_landing(surf, 1, sy, step=1)
    state.world = surf
    state.cam_focus = None
    state.log.add("You come down out of the hills, back into the Vale.", (210, 200, 190))


def _facing_tile_kind(state: GameState, kind: str) -> bool:
    p = state.player
    for gx, gy in ((p.x + p.facing[0], p.y + p.facing[1]), (p.x, p.y)):
        if state.world.in_bounds(gx, gy) and state.world.tile_at(gx, gy).kind == kind:
            return True
    return False


def _board_village(state: GameState) -> str:
    """Which village's notice board the player is standing at (nearest square)."""
    p = state.player
    centers = getattr(state.surface, "village_centers", {}) if state.surface else {}
    best, best_d = "", 10**9
    for name, (vx, vy) in centers.items():
        d = max(abs(p.x - vx), abs(p.y - vy))
        if d < best_d:
            best, best_d = name, d
    return best if best_d <= 45 else ""


def collect_letter(state: GameState, letter) -> None:
    """Take a letter's contents into the pack and read it out. A tax notice
    settles the land tax instead of holding items."""
    from . import skills
    p = state.player
    if letter.get("tax"):
        from . import land
        land.settle_tax(state)
        return
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
    from . import skills
    p = state.player
    if p.inventory.count(item, quality) <= 0:
        return
    p.inventory.remove(item, 1, quality=quality)
    if item.heal and not item.energy:                    # a remedy, not a meal
        p.hp = min(p.max_hp, p.hp + item.heal)
        cured = bool(p.status)
        p.status.clear()                                 # brimstone draws out poison, staunches bleeding, cools burns
        msg = f"You dress your wounds with the {item.name.lower()}. (+{item.heal} HP)"
        if cured:
            msg += " The sting eases — your afflictions clear."
        state.log.add(msg, (180, 230, 160))
        turns.advance_time(state, C.USE_SECONDS)
        return
    gain = round(item.energy * (1 + 0.12 * quality))     # tastier food goes further
    heal = max(1, gain // 6) + item.heal
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
    from ..data import content
    p = state.player
    state.world.tiles[x, y] = _floor_of(state.world)
    gold, loot = content.chest_loot(state.world.depth, random)
    p.gold += gold
    got = [f"{gold}g"]
    for it in loot:
        p.inventory.add(it, 1)
        got.append(p.display_name(it) if hasattr(p, "display_name") else it.name)
    state.bump("chests_opened")
    state.log.add("You pry open the chest! " + ", ".join(got) + ".", (244, 216, 120))
    _maybe_imbue_tool(state)
    turns.advance_time(state, C.USE_SECONDS)


def _maybe_imbue_tool(state: GameState) -> None:
    """A rare chest holds an old charm that imbues one of your plain tools with a
    themed affix (a lasting bonus in that tool's craft)."""
    from ..data import content
    p = state.player
    if random.random() >= 0.12:
        return
    plain = [t for t in content.TOOL_AFFIX_NAMES if t in p.tool_tier and t not in p.tool_affix]
    if not plain:
        return
    tool = random.choice(plain)
    affix = content.TOOL_AFFIX_NAMES[tool]
    p.tool_affix[tool] = affix
    state.log.add(f"An old charm lies within — your {tool.name} is now a "
                  f"{tool.name} {affix}!", (200, 230, 160))


def near_bin(state: GameState) -> bool:
    b = state.world.bin
    if b is None:
        return False
    return abs(state.player.x - b[0]) <= 1 and abs(state.player.y - b[1]) <= 1


RUN_MAX_TILES = 50
REST_MAX_SECONDS = 3600          # rest up to an in-game hour
LONG_ACTION_SECONDS = 120        # tasks at/above this animate over frames (chop, mine)


_NOTABLE_TILE = {"stairs": "a stairway down", "stairs_up": "a stairway up",
                 "bin": "the shipping bin"}
# (berry shrubs used to stop a run here, but they're common and renewable now —
#  halting at every bush beside the road was just noise; forage them with g.)


def _is_friendly(state: GameState, m) -> bool:
    """A surface critter that isn't out to get you — worth noticing once, but not
    worth halting a run at every step while it grazes beside the road."""
    return (not state.world.is_dungeon and m.kind == "wildlife" and not m.hostile)


def _notice_range(state: GameState) -> int:
    """How far off you notice creatures & features. Fog closes it right in — a
    beast is on top of you before you spot it, out on the frontier."""
    return 3 if (not state.world.is_dungeon and state.weather == "Fog") else 6


def _nearby_friendlies(state: GameState) -> set:
    """Identities of friendly creatures already within notice range — the ones a
    run should run *past* rather than stop dead beside every single tile."""
    p = state.player
    rng = _notice_range(state)
    ack = set()
    for npc in state.world.npcs:
        if max(abs(npc.x - p.x), abs(npc.y - p.y)) <= rng:
            ack.add(id(npc))
    for m in state.world.monsters:
        if _is_friendly(state, m) and m.alive and max(abs(m.x - p.x), abs(m.y - p.y)) <= rng:
            ack.add(id(m))
    return ack


def _notable_nearby(state: GameState, ignore: frozenset = frozenset()) -> str:
    """A reason a run/rest should stop — someone close by or an interesting tile
    underfoot — or '' if nothing of note (so it stays usable as a boolean).
    Friendly creatures whose id is in `ignore` are passed over: they were already
    beside us when the run began, so we don't want to halt at them each step."""
    p = state.player
    rng = _notice_range(state)
    for npc in state.world.npcs:
        if id(npc) in ignore:
            continue                                   # already acknowledged
        if max(abs(npc.x - p.x), abs(npc.y - p.y)) <= rng:
            return f"{npc.name} is nearby"
    for m in state.world.monsters:
        if m.seasons and state.season not in m.seasons:
            continue                                   # hibernating — not around
        if not (m.alive and max(abs(m.x - p.x), abs(m.y - p.y)) <= rng):
            continue
        if _is_friendly(state, m) and id(m) in ignore:
            continue                                   # a grazing beast we ran past
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
        from . import husbandry
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


_CARD4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _route_groups(state: GameState, x: int, y: int, exclude: tuple) -> list:
    """Group the road exits from (x, y) into distinct routes, ignoring the way
    we came from (`exclude`). Two perpendicular exits belong to the SAME route
    when the diagonal cell between them is also road — that's a widened corner
    or a blob of paving, not a spot where the road truly splits. So a fat corner
    or a 2-wide patch collapses to one route (the run flows through it), while a
    real T or crossroads stays two-or-more (the run stops to let you choose)."""
    dirs = [d for d in _CARD4 if d != exclude and _is_road(state, x + d[0], y + d[1])]
    parent = {d: d for d in dirs}

    def find(a):
        while parent[a] != a:
            a = parent[a]
        return a

    for i, d in enumerate(dirs):
        for e in dirs[i + 1:]:
            if d[0] * e[0] + d[1] * e[1] == 0 and _is_road(  # perpendicular pair
                    state, x + d[0] + e[0], y + d[1] + e[1]):
                parent[find(d)] = find(e)
    groups: dict = {}
    for d in dirs:
        groups.setdefault(find(d), []).append(d)
    return list(groups.values())


def start_run(state: GameState, dx: int, dy: int) -> dict | None:
    """Begin a run; returns its context, or None if blocked immediately."""
    p = state.player
    on_road = _is_road(state, p.x, p.y)
    if not on_road and not state.world.walkable(p.x + dx, p.y + dy):
        return None
    tunnel = state.world.is_dungeon and not (
        state.world.walkable(p.x - dy, p.y + dx) or state.world.walkable(p.x + dy, p.y - dx))
    return {"d": (dx, dy), "steps": 0, "on_road": on_road, "tunnel": tunnel,
            "ack": frozenset(_nearby_friendlies(state))}


def run_step(state: GameState, ctx: dict) -> bool:
    """Advance one tile of a run. Returns True to keep running."""
    p = state.player
    dx, dy = ctx["d"]

    # Road runs FOLLOW the road: keep straight if we can, otherwise take the
    # single bend; stop where the road genuinely forks, dead-ends, or ends. A
    # widened corner or a 2-wide patch is one route (see _route_groups), so we
    # flow through it instead of halting on open road.
    if ctx["on_road"]:
        back = (-dx, -dy)
        groups = _route_groups(state, p.x, p.y, back)
        if not groups:
            ctx["stop"] = "The road ends."
            return False
        if any((dx, dy) in g for g in groups):
            ndir = (dx, dy)                            # carry straight on
        elif len(groups) == 1:                         # one route — follow the bend
            ndir = min(groups[0], key=lambda d: (d[0] - dx) ** 2 + (d[1] - dy) ** 2)
        else:
            ctx["stop"] = "The road forks."
            return False
        nx, ny = p.x + ndir[0], p.y + ndir[1]
        if _entity_at(state, nx, ny):
            ctx["stop"] = f"You stop — {_blocker_name(state, nx, ny)} is in the way."
            return False
        p.x, p.y = nx, ny
        ctx["d"] = ndir
        _apply_walk(state, True)
        ctx["steps"] += 1
        note = _notable_nearby(state, ctx["ack"])
        if ctx["steps"] >= RUN_MAX_TILES:
            ctx["stop"] = "You pause to catch your breath."
            return False
        if note:
            ctx["stop"] = f"You stop — {note}."
            return False
        if len(_route_groups(state, p.x, p.y, (-ndir[0], -ndir[1]))) > 1:
            ctx["stop"] = "You reach a junction."     # a real split — you choose
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
    _apply_walk(state, False)
    if state.world.is_dungeon:
        delve.update_fov(state)
        _scoop_gold(state)                             # grab gold we ran over
        if _dungeon_tile_fx(state):
            return False                               # a trap sprang — it logs its own message
    ctx["steps"] += 1

    note = _notable_nearby(state, ctx["ack"])
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
