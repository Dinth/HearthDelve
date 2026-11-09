"""Save and load the whole game to a JSON file.

The world is regenerated from its seed on load (roads, villages, NPCs, dungeon
sites), then the player's changes are restored exactly: the surface tile grid
(base64-encoded), planted crops, placed machines, NPC friendships, and the full
player state. Dungeon floors re-roll each dawn, but today's are kept: each is
rebuilt from its seed and overlaid with what the player changed, and a save made
underground resumes there.
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


def default_path() -> str:
    """Where the save lives: ``$HEARTHDELVE_SAVE`` when set, else ``SAVE_PATH``.

    Resolved on every call rather than frozen into default arguments at import,
    so the test suite (which points the variable at a scratch directory) and the
    dawn autosave inside ``farming.new_day`` can never write to a real farm."""
    return os.environ.get("HEARTHDELVE_SAVE") or SAVE_PATH


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
            m.level, m.energy, m.boss, m.inflicts, dict(m.status),
            # dungeon monsters (saved with today's floors): their elite affix,
            # template, ranged reach, summoning and a boss's enrage
            m.elite, m.base, m.reach, m.summons, m.summon_cd, m.enrage, m.enraged]


def _item_key(it):
    """Serialize an item reference. Gear & jewellery persist by their STRUCTURED
    identity (base + material + affixes + gems) so a save survives any change to
    how display names are composed — a gem glyph, an affix rename. Everything
    else stores by name (stable). The name rides along only as a human-readable
    hint; load never trusts it for gear."""
    if it is None:
        return None
    base = content._GEAR_BASE.get(it)
    if base is not None:
        return {"g": base, "m": it.material, "p": it.prefix, "s": it.suffix,
                "x": list(it.gems), "n": it.name}
    jbase = content._JEWEL_BASE.get(it)
    if jbase is not None:
        return {"j": jbase, "m": it.material, "x": list(it.gems), "n": it.name}
    return it.name


def _item_from_key(tok):
    """Inverse of _item_key. A dict is the structured form (new saves): rebuild
    through the factory, which memoizes to the very same canonical item. A bare
    string is a name — old saves and every non-gear item — resolved the legacy
    way (which for gear still parses the name, the grandfather path)."""
    if isinstance(tok, dict):
        try:
            if "g" in tok:
                return content.make_gear(tok["g"], tok["m"], tok.get("p", ""),
                                         tok.get("s", ""), tuple(tok.get("x", ())))
            if "j" in tok:
                gems = tok.get("x", ())
                return content.make_jewel(tok["j"], tok["m"], gems[0]) if gems else None
        except (KeyError, ValueError, IndexError):
            # A base, material, affix or gem this build no longer knows (renamed
            # or cut). Raising here failed the whole load — and the .bak, which
            # holds the same piece — so one renamed affix bricked a farm. Lose
            # that one piece instead (its name is a last hope), and say so.
            it = _by_name_or_none(tok.get("n", ""))
            if it is None:
                _LOST.add(tok.get("n") or "a piece of gear")
            return it
        return items.by_name(tok.get("n", ""))
    return items.by_name(tok)


_LOST: set = set()        # names of saved pieces this build couldn't rebuild (per load)


def _by_name_or_none(name: str):
    try:
        return items.by_name(name) if name else None
    except (KeyError, ValueError, IndexError):
        return None


def _npc_to_rec(n) -> list:
    """Serialize a villager's/dwarf's persistent state. Append-only like the mob
    record: add a new field to the END and read it with a guarded default in
    _npc_apply_rec, so old and new saves both keep loading."""
    return [n.friendship, n.gifted_today, n.talked_today, n._blurb_i, n.met]


def _npc_apply_rec(n, rec) -> None:
    """Copy a saved record back onto a freshly-regenerated NPC (NPCs rebuild from
    content on load; only this mutable state persists). Each field is guarded so
    a shorter (older) or longer (newer) record loads cleanly."""
    if not rec:
        return
    n.friendship, n.gifted_today, n.talked_today, n._blurb_i = rec[:4]
    if len(rec) > 4:
        n.met = rec[4]


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
               level=g(18, 1), energy=g(19, 0), boss=g(20, False),
               inflicts=g(21, ""),
               status={str(k): int(v) for k, v in g(22, {}).items()},
               elite=g(23, ""), base=g(24, ""), reach=g(25, 0), summons=g(26, ""),
               summon_cd=g(27, 0), enrage=g(28, False), enraged=g(29, False))


def _season_of(day: int) -> str:
    from ..engine import constants as C
    return C.SEASONS[(day // C.SEASON_LEN) % len(C.SEASONS)]


def _b64(arr) -> str:
    return base64.b64encode(np.ascontiguousarray(arr).tobytes()).decode("ascii")


def _delve_to_rec(state: GameState):
    """Today's dungeon floors as the player left them — tiles (opened chests,
    scooped gold, mined veins), what they've explored, the monsters still
    about, the traps still hidden — and where underground they stand, if they
    do. Without it a save made below rolled every floor afresh: chests refilled,
    and quitting was a free way out of a losing fight. None when there's
    nothing of today's to keep (floors re-roll at dawn anyway)."""
    floors = []
    if state.floor_cache_day == state.day:
        for (kind, site, depth), gm in state.floor_cache.items():
            floors.append({
                "kind": kind, "site": list(site), "depth": depth,
                "tiles": _b64(gm.tiles),
                "explored": _b64(np.packbits(np.asarray(gm.explored, dtype=bool))),
                "monsters": [_mob_to_rec(m) for m in gm.monsters],
                "traps": sorted([x, y] for x, y in gm.hidden_traps),
            })
    here = None
    if state.depth > 0:
        from ..game import delve
        here = {"kind": state.dungeon_kind, "site": list(delve._site(state)),
                "depth": state.depth, "x": state.player.x, "y": state.player.y}
    return {"floors": floors, "here": here} if (floors or here) else None


def _delve_from_rec(state: GameState, rec) -> None:
    """Rebuild each saved floor from its seed, lay the saved state over it, and
    put the player back where they stood underground."""
    from ..entities.monster import Mob as _Mob
    from ..game import delve
    state.floor_cache.clear()
    state.floor_cache_day = state.day
    for f in rec.get("floors", []):
        site = tuple(f["site"])
        gm = delve.build_floor(state, f["kind"], site, f["depth"])
        w, h = gm.tiles.shape
        gm.tiles = np.frombuffer(base64.b64decode(f["tiles"]), dtype=np.uint8).reshape(w, h).copy()
        bits = np.frombuffer(base64.b64decode(f["explored"]), dtype=np.uint8)
        gm.explored = np.unpackbits(bits)[:w * h].reshape(w, h).astype(bool)
        gm.monsters = [_mob_from_rec(r, _Mob) for r in f.get("monsters", [])]
        gm.hidden_traps = {(x, y) for x, y in f.get("traps", [])}
        state.floor_cache[(f["kind"], site, f["depth"])] = gm
    here = rec.get("here")
    if not here:
        return
    key = (here["kind"], tuple(here["site"]), here["depth"])
    gm = state.floor_cache.get(key)
    if gm is None:
        return                         # nothing to stand on: wake at the mouth, as before
    where, sx, sy = key[1]
    state.dungeon_kind, state.depth = key[0], key[2]
    state.return_pos, state.return_west = (sx, sy), where == "west"
    state.world = gm
    state.player.x, state.player.y = here["x"], here["y"]
    delve.update_fov(state)


def exists(path: str | None = None) -> bool:
    return os.path.isfile(path or default_path())


def delete(path: str | None = None) -> None:
    try:
        os.remove(path or default_path())
    except OSError:
        pass


def backup(path: str | None = None) -> str | None:
    """Copy an unreadable/incompatible save aside as ``.broken`` before it's
    abandoned — never silently destroyed, and never clobbering the rolling
    ``.bak`` (which holds the previous GOOD save; see :func:`save`)."""
    path = path or default_path()
    if not os.path.isfile(path):
        return None
    bak = path + ".broken"
    try:
        shutil.copy2(path, bak)
        return bak
    except OSError:
        return None


def load_or_backup(path: str | None = None):
    """Load the save; if the main file is corrupt but the previous morning's
    rolling ``.bak`` reads fine, set the broken file aside, promote the backup
    to main, and load that instead. Returns ``(state, restored)``.

    A version mismatch (IncompatibleSaveError) propagates untouched — the
    backup is from the same build, so it can't help there."""
    path = path or default_path()
    try:
        return load(path), False
    except IncompatibleSaveError:
        raise
    except Exception:
        bak = path + ".bak"
        if not os.path.isfile(bak):
            raise
        backup(path)                      # keep the broken one for post-mortems
        os.replace(bak, path)             # promote the last good morning
        return load(path), True


# --- save --------------------------------------------------------------------
def save(state: GameState, path: str | None = None) -> None:
    path = path or default_path()
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
            "hotbar": [_item_key(it) for it in p.hotbar],
            "weapon": _item_key(p.weapon),
            "equipment": {slot: _item_key(it) for slot, it in p.equipment.items()},
            "equip_quality": dict(p.equip_quality),
            "mastery": dict(p.mastery),
            "inventory": [[_item_key(it), q, ql] for it, q, ql in p.inventory.slots],
            "tool_tier": {it.name: t for it, t in p.tool_tier.items()},
            "tool_affix": {it.name: a for it, a in p.tool_affix.items()},
            "tool_gem": {it.name: list(g) for it, g in p.tool_gem.items()},
            "active_seed": p.active_seed.name if p.active_seed else None,
            "skills": dict(p.skills),
            "status": dict(p.status),
            "sign": p.sign,
            "attrs": dict(p.attrs),
        },
        "ship_bin": [[_item_key(it), q, ql] for it, q, ql in state.ship_bin.slots],
        "storage": [[_item_key(it), q, ql] for it, q, ql in state.storage.slots],
        "pack_bonus": state.pack_bonus,
        "shipped": {"day": state.shipped.get("day", -1),
                    "lines": [[_item_key(it), q, ql, g] for it, q, ql, g in state.shipped.get("lines", ())]},
        "stats": dict(state.stats),
        "bestiary": dict(state.bestiary),
        "pending_build": state.pending_build,
        "chargen_pending": state.chargen_pending,
        "claims": [f"{x},{y}" for (x, y) in state.claims],
        "tax_owed": state.tax_owed,
        "last_tax_day": state.last_tax_day,
        "quests_done": list(state.quests_done),
        "known_recipes": sorted(state.known_recipes),
        "donated": sorted(state.donated),
        "seen_events": sorted(state.seen_events),
        "event": dict(state.event),
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
            n.name: _npc_to_rec(n) for n in state.dwarves},
        "delve": _delve_to_rec(state),
        "mail": [{"sender": m["sender"], "body": m["body"],
                  "items": [[(it.name if hasattr(it, "name") else it), q, ql]
                            for it, q, ql in m.get("items", [])],
                  **({"tax": True} if m.get("tax") else {}),
                  **({"until": m["until"]} if m.get("until") is not None else {})}
                 for m in state.mail],
        "tiles_shape": [surf.width, surf.height],
        # The Vale's dungeon mouths, in placement order — rebuilt from these on
        # load rather than re-picked, so the world comes back the same on any
        # machine (see worldgen._place_dungeons).
        "sites": [[x, y, surf.dungeon_kind[(x, y)]] for x, y in surf.dungeons],
        "tiles": base64.b64encode(np.ascontiguousarray(surf.tiles).tobytes()).decode("ascii"),
        "crops": {f"{x},{y}": [pl.crop.name, pl.days_grown, pl.watered, pl.dead, pl.fertilized,
                               pl.thirst, pl.season_ended, pl.cross]
                  for (x, y), pl in surf.crops.items()},
        "soil": {f"{x},{y}": lvl for (x, y), lvl in surf.soil.items() if lvl > 0},
        "trees": {f"{x},{y}": [t.name, t.age, t.has_fruit, t.refruit_in]
                  for (x, y), t in surf.trees.items()},
        "berry_regrow": {f"{x},{y}": [bt, ready]
                         for (x, y), (bt, ready) in surf.berry_regrow.items()},
        "machines": {f"{x},{y}": [m.kind, m.loaded_output.name if m.loaded_output else None,
                                   m.ready_at, m.has_queen, m.out_quality, m.build_kind, m.feed,
                                   m.out_qty]
                     for (x, y), m in surf.machines.items()},
        "animals": [[a.kind, a.name, a.x, a.y, list(a.home),
                     a.happiness, a.age_days, a.produce_ready, a.petted_today, a.sick]
                    for a in surf.animals],
        # Surface wildlife is persistent (a boar you put down stays down, and
        # its karma cost sticks) rather than re-scattered from the seed on load.
        "wildlife": [_mob_to_rec(m) for m in surf.monsters],
        # Player-raised outbuildings (worldgen doesn't recreate these).
        "buildings": [b for b in surf.buildings
                      if b.get("kind") in _PLAYER_BUILT_KINDS and not b.get("village")],
        "npcs": {n.name: _npc_to_rec(n) for n in surf.npcs},
    }
    # Keep the previous good save as a rolling .bak (recovery if this write's
    # result ever proves unreadable — see load_or_backup), then write atomically.
    if os.path.isfile(path):
        try:
            shutil.copy2(path, path + ".bak")
        except OSError:
            pass                          # a failed backup must never block the save
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


# --- load --------------------------------------------------------------------
def load(path: str | None = None) -> GameState:
    _LOST.clear()
    with open(path or default_path()) as f:
        data = json.load(f)
    ver = data.get("version")
    if ver != SAVE_VERSION:
        raise IncompatibleSaveError(
            f"save is format version {ver}, but this build reads version {SAVE_VERSION}")

    # Rebuild the base world. A save that recorded its dungeon mouths gets them
    # back as they were; an older one is rebuilt with the tie order its world
    # was first made with, and records them from its next save on.
    sites = data.get("sites")
    if sites is not None:
        world = worldgen.generate(data["seed"], sites=[(int(x), int(y), str(k)) for x, y, k in sites])
    else:
        world = worldgen.generate(data["seed"], legacy_ties=True)

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
        # older saves don't say why a plot died: a dead crop that's now out of
        # season most likely ran its season out, so grandfather it as one — any
        # doubt (it may have withered first) goes the player's way
        ended = rec[6] if len(rec) > 6 else None
        cross = rec[7] if len(rec) > 7 else ""          # older saves: nothing crossed
        x, y = map(int, key.split(","))
        crop = content.CROP_BY_NAME.get(cname)
        if crop:
            if ended is None:
                ended = bool(dead) and crop.season != _season_of(data["day"])
            world.crops[(x, y)] = CropPlot(crop=crop, days_grown=days, watered=watered,
                                           dead=dead, fertilized=fert, thirst=thirst,
                                           season_ended=ended, cross=cross)

    world.soil = {}
    for key, lvl in data.get("soil", {}).items():
        x, y = map(int, key.split(","))
        world.soil[(x, y)] = int(lvl)

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
        sick = rec[9] if len(rec) > 9 else 0
        spec = SPECIES.get(kind)
        if not spec:
            continue
        world.animals.append(Animal(kind=kind, name=name, glyph=spec.glyph, color=spec.color,
                                    x=ax, y=ay, home=tuple(home), happiness=happ,
                                    age_days=age, produce_ready=ready, petted_today=petted,
                                    sick=sick))

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
        _npc_apply_rec(n, data["npcs"].get(n.name))

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
    player.hotbar = [it for it in (_item_from_key(n) for n in pd["hotbar"]) if it]
    # Dropping unresolvable hotbar entries can shrink the bar, so clamp the saved
    # cursor rather than trusting an index that may now point past the end.
    player.active_slot = min(max(0, pd.get("active_slot", 0)), max(0, len(player.hotbar) - 1))
    player.weapon = _item_from_key(pd["weapon"]) if pd["weapon"] else None
    for slot, nm in pd.get("equipment", {}).items():
        if slot in player.equipment:
            player.equipment[slot] = _item_from_key(nm) if nm else None
    player.equip_quality = {s: q for s, q in pd.get("equip_quality", {}).items()
                            if s in player.equipment}
    player.mastery = dict(pd.get("mastery", {}))
    player.inventory = Inventory(slots=[[_item_from_key(rec[0]), rec[1], rec[2] if len(rec) > 2 else 0]
                                        for rec in pd["inventory"] if _item_from_key(rec[0])])
    player.tool_tier = {items.by_name(n): t for n, t in pd["tool_tier"].items() if items.by_name(n)}
    player.tool_affix = {items.by_name(n): a for n, a in pd.get("tool_affix", {}).items() if items.by_name(n)}
    player.tool_gem = {items.by_name(n): tuple(g) for n, g in pd.get("tool_gem", {}).items() if items.by_name(n)}
    player.active_seed = items.by_name(pd.get("active_seed") or "") or items.PARSNIP_SEEDS
    player.skills = dict(pd.get("skills", {}))
    player.status = {k: int(v) for k, v in pd.get("status", {}).items()}
    player.sign = pd.get("sign", "")
    player.attrs = {k: int(v) for k, v in pd.get("attrs", {}).items()}

    state = GameState(world=world, player=player, log=MessageLog(), seed=data["seed"])
    state.surface = world
    state.day = data["day"]
    state.clock = data["clock"]
    state.weather = data["weather"]
    state.ship_bin = Inventory(slots=[[_item_from_key(rec[0]), rec[1], rec[2] if len(rec) > 2 else 0]
                                      for rec in data["ship_bin"] if _item_from_key(rec[0])])
    state.storage = Inventory(slots=[[_item_from_key(rec[0]), rec[1], rec[2] if len(rec) > 2 else 0]
                                     for rec in data.get("storage", []) if _item_from_key(rec[0])])
    state.pack_bonus = data.get("pack_bonus", 0)
    shipped = data.get("shipped") or {}               # older saves: no ledger yet
    lines = [[_item_from_key(r[0]), r[1], r[2], r[3]] for r in shipped.get("lines", ())]
    state.shipped = ({"day": shipped.get("day", -1), "lines": [ln for ln in lines if ln[0] is not None]}
                     if shipped else {})
    state.stats = dict(data.get("stats", {}))
    state.bestiary = dict(data.get("bestiary", {}))
    state.quests_done = set(data.get("quests_done", []))
    kr = data.get("known_recipes")
    # A save from before recipe discovery knew every recipe — keep it that way.
    state.known_recipes = (set(kr) if kr is not None else
                           {r.name for r in content.RECIPES if r.kind == "cook"})
    state.donated = set(data.get("donated", []))
    state.seen_events = set(data.get("seen_events", []))
    state.event = dict(data.get("event") or {})
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
            _npc_apply_rec(n, raw_dwarves.get(n.name))
    state.mail = data.get("mail", [])
    state.pending_build = data.get("pending_build", "")
    # Absent from older saves, whose lives were all begun (or, if the window
    # closed mid-creation, already skipped — nothing to tell those apart by).
    state.chargen_pending = bool(data.get("chargen_pending", False))
    state.claims = {tuple(map(int, k.split(","))) for k in data.get("claims", [])}
    state.tax_owed = data.get("tax_owed", 0)
    state.last_tax_day = data.get("last_tax_day", state.day)
    # Today's floors, and the player back underground if they saved there.
    # (Older saves have none: they wake at the mouth, as they always did.)
    if data.get("delve"):
        _delve_from_rec(state, data["delve"])
    if _LOST:
        state.log.add(f"Some gear from an older version couldn't be recognised and was lost: "
                      f"{', '.join(sorted(_LOST))}.", (240, 180, 120))
    return state
