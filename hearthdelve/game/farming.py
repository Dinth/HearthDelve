"""Farming verbs and the day cycle: plant, water, harvest, sleep.

Kept separate from the input/render layers so the loop in main.py just routes
key presses here.
"""
from __future__ import annotations

import random

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
    state.player.inventory.add(tree.fruit, 1)
    tree.has_fruit = False
    from . import skills
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
    state.player.inventory.add(crop.produce, 1)
    state.bump("crops_harvested")
    from . import skills
    skills.gain(state, "Farming", 15)
    if random.random() < skills.extra_yield_chance(state, "Farming"):
        state.player.inventory.add(crop.produce, 1)
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

    state.day += 1
    state.clock = 0
    season = state.season

    state.weather = roll_weather(season, random.Random(state.seed * 100003 + state.day))
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

    # residents are open to a fresh chat and gift each day
    for npc in state.world.npcs:
        npc.gifted_today = False
        npc.talked_today = False

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
        for it, q in list(p.inventory.slots):
            if it.kind in ("crop", "material", "artisan", "food", "fish"):
                p.inventory.remove(it, q)
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
