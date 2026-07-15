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


def _mob_to_rec(m) -> list:
    """Serialize a surface/west critter as a positional record. Append-only: to
    persist a new Mob field, add it to the END here and read it with a guarded
    default in _mob_from_rec — old and new saves then both keep loading, with no
    SAVE_VERSION bump."""
    return [m.name, m.glyph, list(m.color), m.hp, m.max_hp, m.speed, m.behavior,
            m.x, m.y, m.dv, m.pv, m.to_hit, list(m.dmg), m.awake,
            m.kind, m.diet, m.hostile, list(m.seasons),
            m.level, m.energy, m.boss]


def _mob_from_rec(rec: list, Mob) -> object:
    """Deserialize a critter defensively: each field is read positionally with a
    default, so a record shorter than this build expects (an older save) or
    longer (a newer one) loads cleanly instead of raising on a length mismatch."""
    def g(i, d):
        return rec[i] if len(rec) > i else d
    return Mob(g(0, "?"), g(1, "?"), tuple(g(2, (200, 200, 200))),
               g(3, 1), g(4, 1), g(5, 1), g(6, "skittish"), g(7, 0), g(8, 0),
               dv=g(9, 0), pv=g(10, 0), to_hit=g(11, 0), dmg=tuple(g(12, (1, 3))),
               awake=g(13, False), kind=g(14, "monster"), diet=g(15, ""),
               hostile=g(16, False), seasons=tuple(g(17, ())),
               level=g(18, 1), energy=g(19, 0), boss=g(20, False))


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
        "storage": [[it.name, q, ql] for it, q, ql in state.storage.slots],
        "pack_bonus": state.pack_bonus,
        "stats": dict(state.stats),
        "pending_build": state.pending_build,
        "claims": [f"{x},{y}" for (x, y) in state.claims],
        "tax_owed": state.tax_owed,
        "last_tax_day": state.last_tax_day,
        "quests_done": list(state.quests_done),
        "known_recipes": sorted(state.known_recipes),
        "requests": [dict(r) for r in state.requests],
        "demand": dict(state.demand),
        "projects": [dict(p) for p in state.projects],
        # The Westreach, once discovered: its grid + beasts persist like the
        # surface's. (Regenerated from seed on load, then overlaid.)
        "west": None if state.west is None else {
            "tiles": base64.b64encode(np.ascontiguousarray(state.west.tiles).tobytes()).decode("ascii"),
            "wildlife": [_mob_to_rec(m) for m in state.west.monsters],
        },
        "on_west": ((state.world is state.west and state.west is not None)
                    or (state.depth > 0 and state.return_west)),
        # Khazgrim's folk remember a friend across saves.
        "dwarves": None if state.dwarves is None else {
            n.name: [n.friendship, n.gifted_today, n.talked_today, n._blurb_i, n.met]
            for n in state.dwarves},
        "mail": [{"sender": m["sender"], "body": m["body"],
                  "items": [[(it.name if hasattr(it, "name") else it), q, ql]
                            for it, q, ql in m.get("items", [])],
                  **({"tax": True} if m.get("tax") else {})}
                 for m in state.mail],
        "tiles_shape": [surf.width, surf.height],
        "tiles": base64.b64encode(np.ascontiguousarray(surf.tiles).tobytes()).decode("ascii"),
        "crops": {f"{x},{y}": [pl.crop.name, pl.days_grown, pl.watered, pl.dead, pl.fertilized, pl.thirst]
                  for (x, y), pl in surf.crops.items()},
        "trees": {f"{x},{y}": [t.name, t.age, t.has_fruit, t.refruit_in]
                  for (x, y), t in surf.trees.items()},
        "berry_regrow": {f"{x},{y}": [bt, ready]
                         for (x, y), (bt, ready) in surf.berry_regrow.items()},
        "machines": {f"{x},{y}": [m.kind, m.loaded_output.name if m.loaded_output else None,
                                   m.ready_at, m.has_queen, m.out_quality, m.build_kind, m.feed,
                                   m.out_qty]
                     for (x, y), m in surf.machines.items()},
        "animals": [[a.kind, a.name, a.x, a.y, list(a.home),
                     a.happiness, a.age_days, a.produce_ready, a.petted_today]
                    for a in surf.animals],
        # Surface wildlife is persistent (a boar you put down stays down, and
        # its karma cost sticks) rather than re-scattered from the seed on load.
        "wildlife": [_mob_to_rec(m) for m in surf.monsters],
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
    # Keep the freshly-generated grid: worldgen improvements (new boards, the
    # West Pass road, tamed signposts) are retrofitted onto older saved grids
    # below, wherever the player hasn't touched the ground.
    from ..world import tile as _tile
    _fresh = world.tiles.copy()
    world.tiles = np.frombuffer(base64.b64decode(data["tiles"]), dtype=np.uint8).reshape(w, h).copy()
    # Notice boards: stamp onto untouched square corners.
    for bx, by in np.argwhere(_fresh == _tile.NOTICE_BOARD):
        if world.tiles[bx, by] == _tile.COBBLE:
            world.tiles[bx, by] = _tile.NOTICE_BOARD
    # Signposts: older worldgen sprinkled them down every hill switchback —
    # any post the fresh world no longer plants reverts to its natural ground.
    extra_posts = (world.tiles == _tile.SIGNPOST) & (_fresh != _tile.SIGNPOST)
    world.tiles[extra_posts] = _fresh[extra_posts]
    # New roads (the West Pass): lay fresh road/bridge over still-wild ground.
    _natural = np.isin(world.tiles, (_tile.GRASS, _tile.MEADOW, _tile.TALL_GRASS,
                                     _tile.DIRT_PATH, _tile.SAND, _tile.FOG_GRASS,
                                     _tile.MOOR, _tile.HILL, _tile.SCREE, _tile.BUSH))
    _roads = np.isin(_fresh, (_tile.ROAD, _tile.BRIDGE)) & _natural
    world.tiles[_roads] = _fresh[_roads]

    world.crops = {}
    for key, rec in data["crops"].items():
        cname, days, watered, dead = rec[:4]
        fert = rec[4] if len(rec) > 4 else False
        thirst = rec[5] if len(rec) > 5 else 0
        x, y = map(int, key.split(","))
        crop = content.CROP_BY_NAME.get(cname)
        if crop:
            world.crops[(x, y)] = CropPlot(crop=crop, days_grown=days, watered=watered,
                                           dead=dead, fertilized=fert, thirst=thirst)

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
        if len(rec) > 7:
            m.out_qty = rec[7]
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
        world.monsters = [_mob_from_rec(rec, Mob) for rec in data["wildlife"]]

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
    state.storage = Inventory(slots=[[items.by_name(rec[0]), rec[1], rec[2] if len(rec) > 2 else 0]
                                     for rec in data.get("storage", []) if items.by_name(rec[0])])
    state.pack_bonus = data.get("pack_bonus", 0)
    state.stats = dict(data.get("stats", {}))
    state.quests_done = set(data.get("quests_done", []))
    kr = data.get("known_recipes")
    # A save from before recipe discovery knew every recipe — keep it that way.
    state.known_recipes = (set(kr) if kr is not None else
                           {r.name for r in content.RECIPES if r.kind == "cook"})
    state.requests = [dict(r) for r in data.get("requests", [])]
    state.demand = dict(data.get("demand") or {})
    from ..game import projects as _projects
    state.projects = _projects.merge_loaded(data.get("projects"))
    # Completed landmarks' tiles live in the grid, but their look-mode records
    # aren't in the saved buildings list (village-owned) — rebuild them.
    _projects.register_buildings(world, state.projects)

    # The Westreach: regenerate from seed, then overlay the saved grid & beasts.
    raw_west = data.get("west")
    if raw_west:
        from ..world import westgen
        from ..entities.monster import Mob as _Mob
        wmap = westgen.generate(data["seed"])
        wmap.tiles = np.frombuffer(base64.b64decode(raw_west["tiles"]),
                                   dtype=np.uint8).reshape(westgen.W, westgen.H).copy()
        wmap.monsters = [_mob_from_rec(rec, _Mob) for rec in raw_west.get("wildlife", [])]
        state.west = wmap
        if data.get("on_west"):
            state.world = wmap        # the player saved out in the Westreach

    raw_dwarves = data.get("dwarves")
    if raw_dwarves:
        state.dwarves = content.dwarf_npcs()
        for n in state.dwarves:
            rec = raw_dwarves.get(n.name)
            if rec:
                n.friendship, n.gifted_today, n.talked_today, n._blurb_i = rec[:4]
                if len(rec) > 4:
                    n.met = rec[4]
    state.mail = data.get("mail", [])
    state.pending_build = data.get("pending_build", "")
    state.claims = {tuple(map(int, k.split(","))) for k in data.get("claims", [])}
    state.tax_owed = data.get("tax_owed", 0)
    state.last_tax_day = data.get("last_tax_day", state.day)
    return state
