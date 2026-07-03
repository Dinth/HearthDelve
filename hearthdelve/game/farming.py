"""Farming verbs and the day cycle: plant, water, harvest, sleep.

Kept separate from the input/render layers so the loop in main.py just routes
key presses here.
"""
from __future__ import annotations

import random

import numpy as np

from ..data import content
from ..data.content import SEED_TO_CROP
from ..engine import constants as C
from ..entities.items import Item
from ..world import tile
from ..world.crops import CropPlot, Tree, advance_growth, advance_tree
from .state import GameState
from . import turns


# --- Weather -----------------------------------------------------------------
_WEATHER_BY_SEASON = {
    "Spring": [("Clear", 0.50), ("Rain", 0.35), ("Fog", 0.15)],
    "Summer": [("Clear", 0.60), ("Rain", 0.18), ("Storm", 0.12), ("Fog", 0.10)],
    "Fall":   [("Clear", 0.50), ("Rain", 0.30), ("Fog", 0.20)],
    "Winter": [("Snow", 0.60), ("Clear", 0.30), ("Fog", 0.10)],
}


def roll_weather(season: str, rng: random.Random) -> str:
    table = _WEATHER_BY_SEASON[season]
    r = rng.random()
    acc = 0.0
    for name, p in table:
        acc += p
        if r <= acc:
            return name
    return table[0][0]


def is_wet_weather(weather: str) -> bool:
    return weather in ("Rain", "Storm")


def init_weather(state: GameState) -> None:
    """Set the opening day's weather."""
    state.weather = roll_weather(state.season, random.Random(state.seed * 100003 + state.day))


# --- Planting / watering / harvest ------------------------------------------
def plant(state: GameState, x: int, y: int, seed: Item) -> None:
    world = state.world
    if world.tile_at(x, y).name != "tilled":
        state.log.add("You can only plant on tilled soil.", C.DIM)
        return
    if (x, y) in world.crops:
        state.log.add("Something is already growing there.", C.DIM)
        return
    crop = SEED_TO_CROP.get(seed)
    if crop is None:
        state.log.add("You can't plant that.", C.DIM)
        return
    if crop.season != state.season:
        state.log.add(f"{crop.name} is a {crop.season} crop — it won't sprout now.", C.DIM)
        return
    if state.player.inventory.count(seed) <= 0:
        state.log.add(f"You're out of {seed.name}.", C.DIM)
        return

    state.player.inventory.remove(seed, 1)
    world.crops[(x, y)] = CropPlot(crop=crop)
    turns.advance_time(state, C.PLANT_COST[1])
    state.player.energy = max(0, state.player.energy - C.PLANT_COST[0])
    state.log.add(f"You plant {crop.name.lower()} seeds.")


def plant_tree(state: GameState, x: int, y: int, sapling: Item) -> None:
    world = state.world
    if world.is_dungeon:
        state.log.add("No room to plant a tree down here.", C.DIM)
        return
    if world.tile_at(x, y).name not in ("grass", "meadow", "tall_grass", "tilled", "path"):
        state.log.add("Plant saplings on open ground.", C.DIM)
        return
    if (x, y) in world.trees or (x, y) in world.crops or (x, y) in world.machines:
        state.log.add("Something is already growing there.", C.DIM)
        return
    tdef = content.SAPLING_TO_TREE.get(sapling)
    if tdef is None or state.player.inventory.count(sapling) <= 0:
        state.log.add("You have no such sapling.", C.DIM)
        return
    state.player.inventory.remove(sapling, 1)
    world.trees[(x, y)] = Tree(tdef.name, tdef.fruit, tdef.fruit_color, tdef.season, tdef.days_to_mature)
    state.bump("trees_planted")
    turns.advance_time(state, C.PLANT_COST[1])
    state.player.energy = max(0, state.player.energy - C.PLANT_COST[0])
    state.log.add(f"You plant a {tdef.name.lower()} sapling. It will take days to grow.")


def pick_tree(state: GameState, x: int, y: int) -> bool:
    tree = state.world.trees.get((x, y))
    if tree is None:
        return False
    if not tree.has_fruit:
        state.log.add(f"The {tree.name.lower()} tree has no ripe fruit right now.", C.DIM)
        return False
    from . import skills
    state.player.inventory.add(tree.fruit, 1, quality=skills.roll_quality(state, "Farming"))
    tree.has_fruit = False
    tree.refruit_in = random.randint(4, 6)          # bears again in a few days (jittered)
    skills.gain(state, "Foraging", 10)
    state.log.add(f"You pick a {tree.fruit.name.lower()}.", (180, 230, 160))
    state.player.energy = max(0, state.player.energy - C.HARVEST_COST[0])
    turns.advance_time(state, C.HARVEST_COST[1])
    return True


def water_crop(state: GameState, x: int, y: int) -> bool:
    """Water a planted tile. Returns True if there was a crop to water."""
    plot = state.world.crops.get((x, y))
    if plot is None or plot.dead:
        return False
    plot.watered = True
    state.log.add(f"You water the {plot.crop.name.lower()}.")
    return True


def harvest(state: GameState, x: int, y: int) -> bool:
    """Harvest a mature crop on (x, y). Returns True if something was harvested."""
    plot = state.world.crops.get((x, y))
    if plot is None:
        return False
    if plot.dead:
        del state.world.crops[(x, y)]
        state.log.add("You clear away the withered plant.", C.DIM)
        turns.advance_time(state, C.HARVEST_COST[1])
        return True
    if not plot.mature:
        state.log.add(f"The {plot.crop.name.lower()} isn't ready yet.", C.DIM)
        return False

    crop = plot.crop
    from . import skills
    q = skills.roll_quality(state, "Farming")
    state.player.inventory.add(crop.produce, 1, quality=q)
    state.bump("crops_harvested")
    skills.gain(state, "Farming", 15)
    if random.random() < skills.extra_yield_chance(state, "Farming"):
        state.player.inventory.add(crop.produce, 1, quality=q)
        state.log.add("  Your farming skill yields an extra one!", C.DIM)
    if crop.regrows:
        plot.days_grown = max(0, crop.days_to_mature - crop.regrow_days)
        plot.watered = False
        state.log.add(f"You harvest a {crop.produce.name.lower()}. It will fruit again.", (180, 230, 160))
    else:
        del state.world.crops[(x, y)]
        state.log.add(f"You harvest a {crop.produce.name.lower()}!", (180, 230, 160))
    state.player.energy = max(0, state.player.energy - C.HARVEST_COST[0])
    turns.advance_time(state, C.HARVEST_COST[1])
    return True


# --- The day cycle -----------------------------------------------------------
def can_sleep(state: GameState) -> bool:
    """True if the player is on or next to their bed."""
    bed = state.world.bed
    if bed is None:
        return False
    return abs(state.player.x - bed[0]) <= 1 and abs(state.player.y - bed[1]) <= 1


def new_day(state: GameState, rested: bool = True) -> None:
    """Advance to the next morning: sell shipment, grow crops, roll weather."""
    from . import crafting
    crafting.sell_shipment(state)

    old_season = state.season
    state.day += 1
    state.clock = 0
    state.warned.clear()            # a fresh morning re-arms the day's warnings
    season = state.season
    if season != old_season:
        _seasonal_flora(state, old_season, season)
    _tick_flora(state, season)

    state.weather = roll_weather(season, random.Random(state.seed * 100003 + state.day))
    fest = content.festival_on(season, state.day_of_season)
    if fest is not None and len(fest) > 4:          # festivals script their own weather
        state.weather = fest[4]
    raining = is_wet_weather(state.weather)

    # Watering: rain soaks every plot; sprinklers water their neighbours.
    if raining:
        for plot in state.world.crops.values():
            if not plot.dead and not plot.mature:
                plot.watered = True
    from . import crafting
    crafting.run_sprinklers(state)

    # Growth tick.
    for plot in state.world.crops.values():
        advance_growth(plot, season)
    for tree in state.world.trees.values():
        advance_tree(tree, season)

    # Village farmhouse fields tend themselves: empty/out-of-season rows are
    # replanted with a fresh in-season crop, so they recover after a raid and
    # change over with the seasons (bare and fallow through winter).
    _tend_village_fields(state, season)

    # Living-world drift: picked berry shrubs re-berry, the odd new tree/shrub
    # takes root by an old one, and fresh wildlife wanders in.
    _regrow_berries(state)
    wilds = random.Random(state.seed * 5171 + state.day)
    _propagate(state, wilds)
    from . import wildlife
    wildlife.respawn(state, wilds)

    # farm animals grow, settle their mood, and leave the morning's produce;
    # any carpenter outbuilding whose time is up is finished off
    from . import husbandry
    husbandry.new_day(state)

    # residents are open to a fresh chat and gift each day
    for npc in state.world.npcs:
        npc.gifted_today = False
        npc.talked_today = False

    _deliver_mail(state)

    p = state.player
    p.energy = p.max_energy if rested else p.max_energy // 2
    p.hp = p.max_hp if rested else max(1, p.max_hp // 2)
    p.stamina = p.max_stamina

    # auto-save each morning
    try:
        from ..engine import save
        save.save(state)
    except Exception:  # noqa: BLE001 - never let a save error break the day
        pass


# Seasonal, drifting flora (mushrooms & wildflowers). Each is a pool of spots
# on natural ground; while in season a rough fraction is "standing" and the set
# drifts day to day (some wither, a random scattering sprouts elsewhere).
_NATURAL_GROUND = {tile.GRASS, tile.MEADOW, tile.TALL_GRASS, tile.FOG_GRASS, tile.MOOR}
#            spots attr        seasons                 active  wither  rng salt
_FLORA = {
    "mushroom_spots": (("Summer", "Fall"),           0.5,    0.16,   7919),
    "flower_spots":   (("Spring", "Summer"),         0.55,   0.12,   6271),
}


def _drift_flora(state: GameState, attr: str, frac: float, wither: float, salt: int) -> None:
    """Drift one flora pool one day: wither some standing tiles, then sprout a
    fresh random scattering of empty spots toward the target population."""
    surf = state.surface
    spots = getattr(surf, attr, None)
    if not spots:
        return
    rng = random.Random(state.seed * salt + state.day)
    standing, empty = [], []
    for s in spots:
        x, y, species, base = s
        if surf.tiles[x, y] == species:
            standing.append(s)
        elif surf.tiles[x, y] in _NATURAL_GROUND:
            empty.append(s)
    survivors = 0
    for x, y, species, base in standing:
        if rng.random() < wither:
            surf.tiles[x, y] = base
        else:
            survivors += 1
    target = int((len(standing) + len(empty)) * frac)
    need = target - survivors
    if need > 0 and empty:
        rng.shuffle(empty)
        for x, y, species, base in empty[:need]:
            surf.tiles[x, y] = species


def _clear_flora(state: GameState, attr: str) -> None:
    surf = state.surface
    for x, y, species, base in getattr(surf, attr, ()) or ():
        if surf.tiles[x, y] == species:
            surf.tiles[x, y] = base


def _seasonal_flora(state: GameState, old: str, new: str) -> None:
    """On a season change, clear any pool whose season has just ended (winter
    snow, autumn foliage). Growth *within* season is handled daily."""
    for attr, (seasons, _f, _w, _s) in _FLORA.items():
        if old in seasons and new not in seasons:
            _clear_flora(state, attr)


def _tick_flora(state: GameState, season: str) -> None:
    """Daily drift for whichever pools are in season."""
    for attr, (seasons, frac, wither, salt) in _FLORA.items():
        if season in seasons:
            _drift_flora(state, attr, frac, wither, salt)


def prime_seasonal_flora(state: GameState) -> None:
    """Populate in-season pools to their target at once (used at game start so a
    spring meadow already has flowers rather than filling in over days)."""
    surf = state.surface
    for attr, (seasons, frac, wither, salt) in _FLORA.items():
        spots = getattr(surf, attr, None)
        if not spots or state.season not in seasons:
            continue
        _clear_flora(state, attr)
        viable = [s for s in spots if surf.tiles[s[0], s[1]] in _NATURAL_GROUND]
        rng = random.Random(state.seed * salt + state.day + 1)
        rng.shuffle(viable)
        for x, y, species, base in viable[:int(len(viable) * frac)]:
            surf.tiles[x, y] = species


def _deliver_mail(state: GameState) -> None:
    """The morning post: festival invitations (a day ahead) and the occasional
    gift from a friend, dropped in the post box by the farmhouse door."""
    from . import skills
    surf = state.surface
    npcs = surf.npcs if surf else []
    arrived = 0

    # Festival invitation, delivered the day before.
    fest = content.festival_on(state.season, state.day_of_season + 1)
    if fest is not None and npcs:
        host = next((n for n in npcs if n.role == "innkeeper"), npcs[0])
        state.mail.append({
            "sender": host.name,
            "body": (f"You're invited! Tomorrow the village keeps {fest[1]}\n"
                     f"in the square — {fest[2]}.\n"
                     "Come and join us. There'll be more than enough to go round!"),
            "items": [],
        })
        arrived += 1

    # A friend occasionally sends a little something (from their own gift pool).
    friends = [n for n in npcs if n.hearts >= 4 and n.gifts]
    if friends and random.random() < 0.18:
        n = random.choice(friends)
        gift = random.choice(n.gifts)
        state.mail.append({
            "sender": n.name,
            "body": ("Was thinking of you, and thought you might like this.\n"
                     "No occasion — just from a friend."),
            "items": [(gift, 1, skills.roll_quality(state, "Foraging") if skills.has_quality(gift) else 0)],
        })
        arrived += 1

    if arrived and surf and surf.post_box:
        state.log.add(f"The post has come — {arrived} letter(s) in your box.", (230, 200, 130))


# Living-world drift for trees & shrubs (gentler than the mushroom/flower pools:
# they don't wither or move, they just occasionally seed a neighbour).
TREE_SPREAD_CHANCE = 0.04       # per day, one mature tree may seed a sapling nearby
SHRUB_SPREAD_CHANCE = 0.06      # per day, one berry shrub may spread to a neighbour
_SPREAD_GROUND = {tile.GRASS, tile.MEADOW, tile.TALL_GRASS}
_BERRY_IDS = (tile.SHRUB_RASPBERRY, tile.SHRUB_GOOSEBERRY, tile.SHRUB_CURRANT)


def _regrow_berries(state: GameState) -> None:
    """Re-berry any picked shrubs whose regrow day has come (unless the bush was
    since cleared away)."""
    surf = state.surface
    for pos, (btile, ready) in list(surf.berry_regrow.items()):
        if state.day >= ready:
            if surf.tiles[pos] == tile.SHRUB:
                surf.tiles[pos] = btile
            del surf.berry_regrow[pos]


def _empty_adjacent(surf, x: int, y: int, rng: random.Random):
    """An open, unclaimed ground tile beside (x, y), or None."""
    dirs = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
    rng.shuffle(dirs)
    for dx, dy in dirs:
        nx, ny = x + dx, y + dy
        if (surf.in_bounds(nx, ny) and surf.tiles[nx, ny] in _SPREAD_GROUND
                and (nx, ny) not in surf.crops and (nx, ny) not in surf.trees
                and (nx, ny) not in surf.machines):
            return (nx, ny)
    return None


def _propagate(state: GameState, rng: random.Random) -> None:
    """Now and then a mature tree drops a sapling, or a berry shrub spreads, onto
    open ground beside it — a slow spread (a few a season), never a takeover."""
    surf = state.surface
    if rng.random() < TREE_SPREAD_CHANCE and surf.trees:
        mature = [(pos, t) for pos, t in surf.trees.items() if t.mature]
        if mature:
            (tx, ty), parent = mature[rng.randrange(len(mature))]
            spot = _empty_adjacent(surf, tx, ty, rng)
            if spot is not None:                      # a fresh sapling — years to bear
                surf.trees[spot] = Tree(parent.name, parent.fruit, parent.fruit_color,
                                        parent.season, parent.days_to_mature, age=0)
    if rng.random() < SHRUB_SPREAD_CHANCE:
        coords = np.argwhere(np.isin(surf.tiles, _BERRY_IDS))
        if len(coords):
            i = rng.randrange(len(coords))
            sx, sy = int(coords[i][0]), int(coords[i][1])
            spot = _empty_adjacent(surf, sx, sy, rng)
            if spot is not None:
                surf.tiles[spot] = int(surf.tiles[sx, sy])


def _tend_village_fields(state: GameState, season: str) -> None:
    surf = state.surface
    fields = getattr(surf, "village_fields", None)
    if not fields:
        return
    in_season = content.crops_in_season(season)
    rng = random.Random(state.seed * 977 + state.day)
    for (x, y) in fields:
        if surf.tile_at(x, y).name != "tilled":
            continue                                   # tile was changed; leave it
        plot = surf.crops.get((x, y))
        keep = (plot is not None and not plot.dead and plot.crop.season == season)
        if keep:
            continue
        if not in_season:
            surf.crops.pop((x, y), None)               # nothing grows now — fallow
            continue
        if rng.random() < 0.85:
            crop = rng.choice(in_season)
            surf.crops[(x, y)] = CropPlot(crop=crop,
                                          days_grown=rng.randint(0, crop.days_to_mature),
                                          watered=True)


def sleep(state: GameState) -> None:
    state.log.add("You sleep soundly. A new day dawns.", (180, 200, 240))
    new_day(state, rested=True)
    _announce_morning(state)


def collapse(state: GameState, reason: str) -> None:
    state.log.add(reason, (220, 140, 120))
    p = state.player
    gold_lost = p.gold // 10
    p.gold -= gold_lost
    dropped = 0
    if state.depth > 0:                     # drop the loose loot carried in the dark
        for it, q, ql in list(p.inventory.slots):
            if it.kind in ("crop", "material", "artisan", "food", "fish", "animal"):
                p.inventory.remove(it, q, quality=ql)
                dropped += q
        from . import delve
        delve.leave_to_surface(state)       # dragged up to the farm
    if gold_lost or dropped:
        loss = f"You lose {gold_lost}g"
        loss += f" and {dropped} loose items." if dropped else "."
        state.log.add(loss, (200, 160, 140))
    # you're carried to bed and wake there the next morning
    if state.surface and state.surface.bed:
        state.player.x, state.player.y = state.surface.bed
    new_day(state, rested=False)
    _announce_morning(state)


def _announce_morning(state: GameState) -> None:
    state.log.add(f"{state.date_str()} — {state.weather}.", (236, 226, 180))
    fest = content.festival_on(state.season, state.day_of_season)
    if fest is not None:
        state.log.add(f"Today is {fest[1]}! The village gathers in the square.",
                      (244, 210, 130))
