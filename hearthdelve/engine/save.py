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
import shutil

import numpy as np

from ..data import content
from ..entities import items
from ..entities.items import Inventory
from ..entities.machine import Machine
from ..entities.player import Player
from ..world import worldgen
from ..world.crops import CropPlot, Tree
from ..game.state import GameState, MessageLog

# Bump whenever the on-disk format changes so an older/newer binary refuses a
# save it can't read instead of crashing partway through a load.
SAVE_VERSION = 8
SAVE_PATH = os.path.join(os.path.expanduser("~"), ".hearthdelve_save.json")


class IncompatibleSaveError(Exception):
    """The save file's format version doesn't match this build — distinct from a
    truly corrupt/unreadable file so the caller can explain it clearly."""

# Housing the carpenter/player raises (not produced by worldgen), so it must be
# persisted and re-registered on load — otherwise look-mode forgets the barn.
_PLAYER_BUILT_KINDS = ("coop_small", "coop_big", "barn", "greenhouse", "windmill", "pen")


def exists(path: str = SAVE_PATH) -> bool:
    return os.path.isfile(path)


def delete(path: str = SAVE_PATH) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def backup(path: str = SAVE_PATH) -> str | None:
    """Copy an existing save aside (e.g. before abandoning an unreadable one so
    a version mismatch never silently destroys it). Returns the backup path."""
    if not os.path.isfile(path):
        return None
    bak = path + ".bak"
    try:
        shutil.copy2(path, bak)
        return bak
    except OSError:
        return None


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
            "level": p.level, "xp": p.xp, "karma": p.karma,
            "buff": p.buff, "buff_until": p.buff_until,
            "active_slot": p.active_slot,
            "hotbar": [it.name for it in p.hotbar],
            "weapon": p.weapon.name if p.weapon else None,
            "equipment": {slot: (it.name if it else None) for slot, it in p.equipment.items()},
            "equip_quality": dict(p.equip_quality),
            "mastery": dict(p.mastery),
            "inventory": [[it.name, q, ql] for it, q, ql in p.inventory.slots],
            "tool_tier": {it.name: t for it, t in p.tool_tier.items()},
            "tool_affix": {it.name: a for it, a in p.tool_affix.items()},
            "tool_gem": {it.name: list(g) for it, g in p.tool_gem.items()},
            "active_seed": p.active_seed.name if p.active_seed else None,
            "skills": dict(p.skills),
        },
        "ship_bin": [[it.name, q, ql] for it, q, ql in state.ship_bin.slots],
        "stats": dict(state.stats),
        "pending_build": state.pending_build,
        "claims": [f"{x},{y}" for (x, y) in state.claims],
        "tax_owed": state.tax_owed,
        "last_tax_day": state.last_tax_day,
        "quests_done": list(state.quests_done),
        "known_recipes": sorted(state.known_recipes),
        "requests": [dict(r) for r in state.requests],
        "demand": dict(state.demand),
        "mail": [{"sender": m["sender"], "body": m["body"],
                  "items": [[(it.name if hasattr(it, "name") else it), q, ql]
                            for it, q, ql in m.get("items", [])],
                  **({"tax": True} if m.get("tax") else {})}
                 for m in state.mail],
        "tiles_shape": [surf.width, surf.height],
        "tiles": base64.b64encode(np.ascontiguousarray(surf.tiles).tobytes()).decode("ascii"),
        "crops": {f"{x},{y}": [pl.crop.name, pl.days_grown, pl.watered, pl.dead]
                  for (x, y), pl in surf.crops.items()},
        "trees": {f"{x},{y}": [t.name, t.age, t.has_fruit, t.refruit_in]
                  for (x, y), t in surf.trees.items()},
        "berry_regrow": {f"{x},{y}": [bt, ready]
                         for (x, y), (bt, ready) in surf.berry_regrow.items()},
        "machines": {f"{x},{y}": [m.kind, m.loaded_output.name if m.loaded_output else None,
                                   m.ready_at, m.has_queen, m.out_quality, m.build_kind, m.feed]
                     for (x, y), m in surf.machines.items()},
        "animals": [[a.kind, a.name, a.x, a.y, list(a.home),
                     a.happiness, a.age_days, a.produce_ready, a.petted_today]
                    for a in surf.animals],
        # Surface wildlife is persistent (a boar you put down stays down, and
        # its karma cost sticks) rather than re-scattered from the seed on load.
        "wildlife": [[m.name, m.glyph, list(m.color), m.hp, m.max_hp, m.speed, m.behavior,
                      m.x, m.y, m.dv, m.pv, m.to_hit, list(m.dmg), m.awake,
                      m.kind, m.diet, m.hostile, list(m.seasons)]
                     for m in surf.monsters],
        # Player-raised outbuildings (worldgen doesn't recreate these).
        "buildings": [b for b in surf.buildings
                      if b.get("kind") in _PLAYER_BUILT_KINDS and not b.get("village")],
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
    ver = data.get("version")
    if ver != SAVE_VERSION:
        raise IncompatibleSaveError(
            f"save is format version {ver}, but this build reads version {SAVE_VERSION}")

    world = worldgen.generate(data["seed"])           # rebuild base world

    w, h = data["tiles_shape"]
    # Villages gained notice boards after some saves were written; remember where
    # the regenerated world put them so an older grid can be stamped below.
    from ..world import tile as _tile
    _boards = np.argwhere(world.tiles == _tile.NOTICE_BOARD)
    world.tiles = np.frombuffer(base64.b64decode(data["tiles"]), dtype=np.uint8).reshape(w, h).copy()
    for bx, by in _boards:
        if world.tiles[bx, by] == _tile.COBBLE:   # untouched square corner -> board
            world.tiles[bx, by] = _tile.NOTICE_BOARD

    world.crops = {}
    for key, (cname, days, watered, dead) in data["crops"].items():
        x, y = map(int, key.split(","))
        crop = content.CROP_BY_NAME.get(cname)
        if crop:
            world.crops[(x, y)] = CropPlot(crop=crop, days_grown=days, watered=watered, dead=dead)

    world.trees = {}
    for key, rec in data.get("trees", {}).items():
        name, age, has_fruit = rec[:3]
        refruit = rec[3] if len(rec) > 3 else 0
        x, y = map(int, key.split(","))
        tdef = content.TREE_BY_NAME.get(name)
        if tdef:
            world.trees[(x, y)] = Tree(tdef.name, tdef.fruit, tdef.fruit_color, tdef.season,
                                       tdef.days_to_mature, age=age, has_fruit=has_fruit,
                                       refruit_in=refruit)

    world.berry_regrow = {}
    for key, (bt, ready) in data.get("berry_regrow", {}).items():
        x, y = map(int, key.split(","))
        world.berry_regrow[(x, y)] = [bt, ready]

    world.machines = {}
    for key, rec in data["machines"].items():
        x, y = map(int, key.split(","))
        kind, out, ready = rec[0], rec[1], rec[2]
        m = Machine(kind=kind)
        m.loaded_output = items.by_name(out) if out else None
        m.ready_at = ready
        if len(rec) > 3:
            m.has_queen = rec[3]
        if len(rec) > 4:
            m.out_quality = rec[4]
        if len(rec) > 5:
            m.build_kind = rec[5]
        if len(rec) > 6:
            m.feed = rec[6]
        world.machines[(x, y)] = m

    from ..entities.animal import Animal
    from ..game.husbandry import SPECIES
    world.animals = []
    for rec in data.get("animals", []):
        kind, name, ax, ay, home, happ, age, ready = rec[:8]
        petted = rec[8] if len(rec) > 8 else False
        spec = SPECIES.get(kind)
        if not spec:
            continue
        world.animals.append(Animal(kind=kind, name=name, glyph=spec.glyph, color=spec.color,
                                    x=ax, y=ay, home=tuple(home), happiness=happ,
                                    age_days=age, produce_ready=ready, petted_today=petted))

    # Restore persistent surface wildlife exactly (replacing the freshly
    # seed-scattered set) so kills and roused states carry across a reload.
    if "wildlife" in data:
        from ..entities.monster import Mob
        world.monsters = []
        for rec in data["wildlife"]:
            (nm, glyph, color, hp, mhp, spd, behavior, mx, my,
             dv, pv, th, dmg, awake, mkind, diet, hostile, seasons) = rec
            world.monsters.append(Mob(nm, glyph, tuple(color), hp, mhp, spd, behavior, mx, my,
                                      dv=dv, pv=pv, to_hit=th, dmg=tuple(dmg), awake=awake,
                                      kind=mkind, diet=diet, hostile=hostile, seasons=tuple(seasons)))

    # Re-register player-raised outbuildings (their tiles + housing machine are
    # restored above; this puts back the record the look tool names them by).
    for b in data.get("buildings", []):
        world.buildings.append(dict(b))

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
    player.karma = pd.get("karma", 0)
    player.buff = pd.get("buff", "")
    player.buff_until = pd.get("buff_until", 0)
    player.hotbar = [it for it in (items.by_name(n) for n in pd["hotbar"]) if it]
    # Dropping unresolvable hotbar entries can shrink the bar, so clamp the saved
    # cursor rather than trusting an index that may now point past the end.
    player.active_slot = min(max(0, pd.get("active_slot", 0)), max(0, len(player.hotbar) - 1))
    player.weapon = items.by_name(pd["weapon"]) if pd["weapon"] else None
    for slot, nm in pd.get("equipment", {}).items():
        if slot in player.equipment:
            player.equipment[slot] = items.by_name(nm) if nm else None
    player.equip_quality = {s: q for s, q in pd.get("equip_quality", {}).items()
                            if s in player.equipment}
    player.mastery = dict(pd.get("mastery", {}))
    player.inventory = Inventory(slots=[[items.by_name(rec[0]), rec[1], rec[2] if len(rec) > 2 else 0]
                                        for rec in pd["inventory"] if items.by_name(rec[0])])
    player.tool_tier = {items.by_name(n): t for n, t in pd["tool_tier"].items() if items.by_name(n)}
    player.tool_affix = {items.by_name(n): a for n, a in pd.get("tool_affix", {}).items() if items.by_name(n)}
    player.tool_gem = {items.by_name(n): tuple(g) for n, g in pd.get("tool_gem", {}).items() if items.by_name(n)}
    player.active_seed = items.by_name(pd.get("active_seed") or "") or items.PARSNIP_SEEDS
    player.skills = dict(pd.get("skills", {}))

    state = GameState(world=world, player=player, log=MessageLog(), seed=data["seed"])
    state.surface = world
    state.day = data["day"]
    state.clock = data["clock"]
    state.weather = data["weather"]
    state.ship_bin = Inventory(slots=[[items.by_name(rec[0]), rec[1], rec[2] if len(rec) > 2 else 0]
                                      for rec in data["ship_bin"] if items.by_name(rec[0])])
    state.stats = dict(data.get("stats", {}))
    state.quests_done = set(data.get("quests_done", []))
    kr = data.get("known_recipes")
    # A save from before recipe discovery knew every recipe — keep it that way.
    state.known_recipes = (set(kr) if kr is not None else
                           {r.name for r in content.RECIPES if r.kind == "cook"})
    state.requests = [dict(r) for r in data.get("requests", [])]
    state.demand = dict(data.get("demand") or {})
    state.mail = data.get("mail", [])
    state.pending_build = data.get("pending_build", "")
    state.claims = {tuple(map(int, k.split(","))) for k in data.get("claims", [])}
    state.tax_owed = data.get("tax_owed", 0)
    state.last_tax_day = data.get("last_tax_day", state.day)
    return state
