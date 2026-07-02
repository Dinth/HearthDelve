"""Save and load the whole game to a JSON file.

The world is regenerated from its seed on load (roads, villages, NPCs, dungeon
sites), then the player's changes are restored exactly: the surface tile grid
(base64-encoded), planted crops, placed machines, NPC friendships, and the full
player state. Dungeons are ephemeral (re-rolled), so a save always resolves the
player onto the surface.
"""
from __future__ import annotations

import base64
import json
import os

import numpy as np

from ..data import content
from ..entities import items
from ..entities.items import Inventory
from ..entities.machine import Machine
from ..entities.player import Player
from ..world import worldgen
from ..world.crops import CropPlot, Tree
from ..game.state import GameState, MessageLog

SAVE_VERSION = 2
SAVE_PATH = os.path.join(os.path.expanduser("~"), ".hearthdelve_save.json")


def exists(path: str = SAVE_PATH) -> bool:
    return os.path.isfile(path)


def delete(path: str = SAVE_PATH) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# --- save --------------------------------------------------------------------
def save(state: GameState, path: str = SAVE_PATH) -> None:
    surf = state.surface
    px, py = state.return_pos if state.depth > 0 else (state.player.x, state.player.y)
    p = state.player

    data = {
        "version": SAVE_VERSION,
        "seed": state.seed,
        "day": state.day,
        "clock": state.clock,
        "weather": state.weather,
        "player": {
            "x": px, "y": py, "facing": list(p.facing),
            "hp": p.hp, "energy": p.energy, "stamina": p.stamina, "gold": p.gold,
            "max_hp": p.max_hp, "max_energy": p.max_energy,
            "level": p.level, "xp": p.xp,
            "active_slot": p.active_slot,
            "hotbar": [it.name for it in p.hotbar],
            "weapon": p.weapon.name if p.weapon else None,
            "inventory": [[it.name, q] for it, q in p.inventory.slots],
            "tool_tier": {it.name: t for it, t in p.tool_tier.items()},
            "active_seed": p.active_seed.name if p.active_seed else None,
            "skills": dict(p.skills),
        },
        "ship_bin": [[it.name, q] for it, q in state.ship_bin.slots],
        "stats": dict(state.stats),
        "quests_done": list(state.quests_done),
        "tiles_shape": [surf.width, surf.height],
        "tiles": base64.b64encode(np.ascontiguousarray(surf.tiles).tobytes()).decode("ascii"),
        "crops": {f"{x},{y}": [pl.crop.name, pl.days_grown, pl.watered, pl.dead]
                  for (x, y), pl in surf.crops.items()},
        "trees": {f"{x},{y}": [t.name, t.age, t.has_fruit]
                  for (x, y), t in surf.trees.items()},
        "machines": {f"{x},{y}": [m.kind, m.loaded_output.name if m.loaded_output else None,
                                   m.ready_at, m.has_queen]
                     for (x, y), m in surf.machines.items()},
        "npcs": {n.name: [n.friendship, n.gifted_today, n.talked_today, n._blurb_i, n.met]
                 for n in surf.npcs},
    }
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


# --- load --------------------------------------------------------------------
def load(path: str = SAVE_PATH) -> GameState:
    with open(path) as f:
        data = json.load(f)
    if data.get("version") != SAVE_VERSION:
        raise ValueError("incompatible save version")

    world = worldgen.generate(data["seed"])           # rebuild base world

    w, h = data["tiles_shape"]
    world.tiles = np.frombuffer(base64.b64decode(data["tiles"]), dtype=np.uint8).reshape(w, h).copy()

    world.crops = {}
    for key, (cname, days, watered, dead) in data["crops"].items():
        x, y = map(int, key.split(","))
        crop = content.CROP_BY_NAME.get(cname)
        if crop:
            world.crops[(x, y)] = CropPlot(crop=crop, days_grown=days, watered=watered, dead=dead)

    world.trees = {}
    for key, (name, age, has_fruit) in data.get("trees", {}).items():
        x, y = map(int, key.split(","))
        tdef = content.TREE_BY_NAME.get(name)
        if tdef:
            world.trees[(x, y)] = Tree(tdef.name, tdef.fruit, tdef.fruit_color, tdef.season,
                                       tdef.days_to_mature, age=age, has_fruit=has_fruit)

    world.machines = {}
    for key, rec in data["machines"].items():
        x, y = map(int, key.split(","))
        kind, out, ready = rec[0], rec[1], rec[2]
        m = Machine(kind=kind)
        m.loaded_output = items.by_name(out) if out else None
        m.ready_at = ready
        if len(rec) > 3:
            m.has_queen = rec[3]
        world.machines[(x, y)] = m

    for n in world.npcs:
        rec = data["npcs"].get(n.name)
        if rec:
            n.friendship, n.gifted_today, n.talked_today, n._blurb_i = rec[:4]
            if len(rec) > 4:
                n.met = rec[4]

    pd = data["player"]
    player = Player(x=pd["x"], y=pd["y"])
    player.facing = tuple(pd["facing"])
    player.hp = pd["hp"]
    player.energy = pd["energy"]
    player.stamina = pd["stamina"]
    player.gold = pd["gold"]
    player.max_hp = pd.get("max_hp", player.max_hp)
    player.max_energy = pd.get("max_energy", player.max_energy)
    player.level = pd.get("level", 1)
    player.xp = pd.get("xp", 0)
    player.active_slot = pd["active_slot"]
    player.hotbar = [items.by_name(n) for n in pd["hotbar"] if items.by_name(n)]
    player.weapon = items.by_name(pd["weapon"]) if pd["weapon"] else None
    player.inventory = Inventory(slots=[[items.by_name(n), q] for n, q in pd["inventory"] if items.by_name(n)])
    player.tool_tier = {items.by_name(n): t for n, t in pd["tool_tier"].items() if items.by_name(n)}
    player.active_seed = items.by_name(pd.get("active_seed") or "") or items.PARSNIP_SEEDS
    player.skills = dict(pd.get("skills", {}))

    state = GameState(world=world, player=player, log=MessageLog(), seed=data["seed"])
    state.surface = world
    state.day = data["day"]
    state.clock = data["clock"]
    state.weather = data["weather"]
    state.ship_bin = Inventory(slots=[[items.by_name(n), q] for n, q in data["ship_bin"] if items.by_name(n)])
    state.stats = dict(data.get("stats", {}))
    state.quests_done = set(data.get("quests_done", []))
    return state
