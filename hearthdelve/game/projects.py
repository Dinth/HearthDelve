"""Community restoration projects — each village's one great work.

The player funds a project in freeform instalments (gold and materials) at that
village's notice board. Once fully funded a site is staked near the square
(SCAFFOLD tiles + a ``kind="site"`` timer machine, exactly like a carpenter
commission), raised over a few days by ``husbandry._finish_construction``'s
dispatch, and then stands forever: landmark tiles stamped into the world, a
``buildings`` record for look-mode, and a lasting perk queried through
:func:`done`. Nothing is ever locked behind a project — perks make the world
cheaper or richer, never newly permitted.
"""
from __future__ import annotations

from ..data import content
from ..engine import constants as C
from ..entities import items
from ..entities.machine import Machine
from ..entities.npc import MAX_HEARTS
from ..world import tile
from .state import GameState

# A single Enter at the board hands over at most this much gold (Space = all-in),
# so one reflexive keypress can never drain a fortune.
GOLD_STEP = 500


# --- records -------------------------------------------------------------------
def fresh() -> list[dict]:
    return [{"id": d.id, "village": d.village, "state": "open",
             "gold_paid": 0, "mats": {it.name: 0 for it, _q in d.mats},
             "site": None, "ready_at": 0}
            for d in content.PROJECTS.values()]


def merge_loaded(raw) -> list[dict]:
    """Reconcile saved project records with the current defs: unknown ids drop,
    new projects appear fresh, and mat lists follow the defs (old saves — or
    saves from before projects existed — grandfather to everything open)."""
    out = fresh()
    by_id = {p["id"]: p for p in out}
    for rec in raw or []:
        p = by_id.get(rec.get("id"))
        if p is None:
            continue
        p["state"] = rec.get("state", "open")
        p["gold_paid"] = rec.get("gold_paid", 0)
        p["site"] = rec.get("site")
        p["ready_at"] = rec.get("ready_at", 0)
        for name, qty in (rec.get("mats") or {}).items():
            if name in p["mats"]:
                p["mats"][name] = qty
    return out


def get(state: GameState, pid: str) -> dict | None:
    return next((p for p in state.projects if p["id"] == pid), None)


def for_village(state: GameState, village: str) -> dict | None:
    """The great work the village is currently rallying around: an open one to
    fund first, else one being built, else None once all are raised. This lets a
    village host several projects over the game's life — finish one and the next
    steps up at the notice board."""
    ps = [p for p in state.projects if p["village"] == village]
    return (next((p for p in ps if p["state"] == "open"), None)
            or next((p for p in ps if p["state"] == "building"), None))


def done(state: GameState, pid: str) -> bool:
    p = get(state, pid)
    return p is not None and p["state"] == "done"


def remaining(state: GameState, proj: dict):
    """(gold_left, [(Item, qty_left), ...]) still needed to fund a project."""
    d = content.PROJECTS[proj["id"]]
    gold_left = max(0, d.gold - proj["gold_paid"])
    mats_left = [(it, need - proj["mats"].get(it.name, 0))
                 for it, need in d.mats
                 if need - proj["mats"].get(it.name, 0) > 0]
    return gold_left, mats_left


# --- funding ---------------------------------------------------------------------
def contribute(state: GameState, proj: dict, all_in: bool = False) -> bool:
    """Hand over everything useful the player carries: all still-needed
    materials, plus gold (a GOLD_STEP instalment, or the full remainder when
    ``all_in``). Returns True if anything moved."""
    from . import karma
    d = content.PROJECTS[proj["id"]]
    p = state.player
    gold_left, mats_left = remaining(state, proj)
    gave = []
    for it, left in mats_left:
        have = p.inventory.count(it)
        give = min(have, left)
        if give > 0:
            p.inventory.remove(it, give)
            proj["mats"][it.name] = proj["mats"].get(it.name, 0) + give
            gave.append(f"{give} {it.name}")
    cap = gold_left if all_in else min(gold_left, GOLD_STEP)
    gold = min(p.gold, cap)
    if gold > 0:
        p.gold -= gold
        proj["gold_paid"] += gold
        state.bump("gold_donated", gold)
        gave.append(f"{gold}g")
    if not gave:
        state.log.add("You've nothing the project needs to hand. "
                      f"({_needs_str(state, proj)})", C.DIM)
        return False
    # A generous neighbour is remembered (karma nudge once a day, not per press).
    key = f"donated_day_{proj['id']}"
    if state.stats.get(key) != state.day:
        state.stats[key] = state.day
        karma.adjust(state, 1)
    gold_left, mats_left = remaining(state, proj)
    if gold_left == 0 and not mats_left:
        state.log.add(f"You hand over {', '.join(gave)} — the {d.name} is fully funded!",
                      (232, 200, 120))
        _stake_site(state, proj)
    else:
        state.log.add(f"You hand over {', '.join(gave)}. Still needed: "
                      f"{_needs_str(state, proj)}.", (200, 220, 160))
    return True


def _needs_str(state: GameState, proj: dict) -> str:
    gold_left, mats_left = remaining(state, proj)
    parts = [f"{q} {it.name}" for it, q in mats_left]
    if gold_left:
        parts.append(f"{gold_left}g")
    return ", ".join(parts) if parts else "nothing"


# --- siting ------------------------------------------------------------------------
def _ring_cells(cx: int, cy: int, r: int):
    """The cells of the square ring at Chebyshev radius r, in a fixed clockwise
    order starting north — deterministic scan order (harmless anyway: the chosen
    site is persisted, so the scan runs once per project per world)."""
    cells = []
    for x in range(cx - r, cx + r + 1):
        cells.append((x, cy - r))
    for y in range(cy - r + 1, cy + r + 1):
        cells.append((cx + r, y))
    for x in range(cx + r - 1, cx - r - 1, -1):
        cells.append((x, cy + r))
    for y in range(cy + r - 1, cy - r, -1):
        cells.append((cx - r, y))
    return cells


def _site_ground():
    """Tiles a work crew will happily level for a foundation — the farm's
    whitelist plus the hills, scree and flower beds villages sit among."""
    from .husbandry import _GROUND
    return _GROUND | {tile.HILL, tile.SCREE, tile.FLOWER_RED, tile.FLOWER_YELLOW,
                      tile.FLOWER_VIOLET, tile.FLOWER_WHITE}


def _rect_clear(state: GameState, rect) -> bool:
    surf = state.surface
    ground = _site_ground()
    x0, y0, w, h = rect
    for x in range(x0, x0 + w):
        for y in range(y0, y0 + h):
            if not surf.in_bounds(x, y):
                return False
            if surf.tiles[x, y] not in ground:
                return False
            if (x, y) in surf.crops or (x, y) in surf.machines or (x, y) in surf.trees:
                return False
            if (x, y) == (state.player.x, state.player.y):
                return False
    for b in surf.buildings:                       # never overlap a building record
        if (x0 < b["x"] + b["w"] and x0 + w > b["x"]
                and y0 < b["y"] + b["h"] and y0 + h > b["y"]):
            return False
    if any(n.x >= x0 and n.x < x0 + w and n.y >= y0 and n.y < y0 + h
           for n in surf.npcs):
        return False
    # keep the doorway breathing: the tile south of the door must be walkable
    dx, dy = x0 + w // 2, y0 + h
    return surf.in_bounds(dx, dy) and surf.walkable(dx, dy)


def _site_score(state: GameState, d, rect) -> float:
    """Flavour bias: the lighthouse hugs the water; the causeway hugs the road."""
    surf = state.surface
    x0, y0, w, h = rect
    cx, cy = x0 + w // 2, y0 + h // 2
    if d.id == "lighthouse":
        best = 99
        for r in range(1, 13):
            if any(surf.in_bounds(x, y) and surf.tile_at(x, y).kind == "water"
                   for x, y in _ring_cells(cx, cy, r)):
                best = r
                break
        return best
    if d.id == "causeway":
        for r in range(1, 7):
            if any(surf.in_bounds(x, y) and surf.tile_at(x, y).kind in ("road", "bridge")
                   for x, y in _ring_cells(cx, cy, r)):
                return r
        return 99
    return 0


def _find_site(state: GameState, d) -> tuple | None:
    surf = state.surface
    centers = getattr(surf, "village_centers", {})
    if d.village not in centers:
        return None
    vx, vy = centers[d.village]
    w, h = d.size
    candidates = []
    for r in range(7, 34):
        for (x, y) in _ring_cells(vx, vy, r):
            rect = (x - w // 2, y - h + 1, w, h)
            if _rect_clear(state, rect):
                candidates.append(rect)
        if candidates:
            # first ring with room; pick the best-flavoured spot on it
            return min(candidates, key=lambda rc: _site_score(state, d, rc))
    return None


def _stake_site(state: GameState, proj: dict) -> None:
    d = content.PROJECTS[proj["id"]]
    rect = _find_site(state, d)
    if rect is None:
        state.log.add(f"The village can't find clear ground for the {d.name} — "
                      "the wardens will keep looking each morning.", (224, 180, 120))
        return                                    # funding kept; new_day retries
    surf = state.surface
    x0, y0, w, h = rect
    for x in range(x0, x0 + w):
        for y in range(y0, y0 + h):
            surf.tiles[x, y] = tile.SCAFFOLD
    anchor = (x0 + w // 2, y0 + h - 1)            # the door-to-be, south-centre
    surf.machines[anchor] = Machine(kind="site", build_kind=d.id,
                                    ready_at=(state.day + d.build_days) * 1440
                                    + C.DAY_START_MIN)
    proj["state"] = "building"
    proj["site"] = list(rect)
    state.log.add(f"Ground is broken for the {d.name} — the frame should stand "
                  f"in ~{d.build_days} days.", (232, 200, 120))


def new_day(state: GameState) -> None:
    """Dawn tick: a funded project that couldn't find ground tries again."""
    for proj in state.projects:
        if proj["state"] == "open" and proj["site"] is None:
            gold_left, mats_left = remaining(state, proj)
            if gold_left == 0 and not mats_left:
                _stake_site(state, proj)


# --- completion --------------------------------------------------------------------
def finish(state: GameState, x: int, y: int, m: Machine) -> None:
    """Raise the finished landmark (called from husbandry's construction tick)."""
    from . import karma
    d = content.PROJECTS[m.build_kind]
    proj = get(state, m.build_kind)
    surf = state.surface
    del surf.machines[(x, y)]
    rect = tuple(proj["site"]) if proj and proj["site"] else (x - d.size[0] // 2,
                                                              y - d.size[1] + 1, *d.size)
    _STAMPS[d.id](state, rect)
    surf.buildings.append({"x": rect[0], "y": rect[1], "w": rect[2], "h": rect[3],
                           "kind": d.id, "village": d.village, "owner": None})
    if proj:
        proj["state"] = "done"
    # the whole village turns out for the raising
    for n in surf.npcs:
        if getattr(n, "village", "") == d.village:
            n.friendship = min(MAX_HEARTS * 100, n.friendship + 150)
    karma.adjust(state, 5)
    state.log.add(f"The {d.name} stands finished! {d.perk}", (232, 200, 120))
    state.mail.append({
        "sender": d.village,
        "body": (f"The {d.name} is finished, and the whole village turned out\n"
                 f"for the raising. {d.perk}\n"
                 "None of it would stand without you. Thank you, friend."),
        "items": [],
    })


def _stamp_hall(state: GameState, rect, interior=()) -> None:
    """A walled hall with a south door: the shared skeleton of the landmarks."""
    surf = state.surface
    x0, y0, w, h = rect
    for x in range(x0, x0 + w):
        for y in range(y0, y0 + h):
            edge = x in (x0, x0 + w - 1) or y in (y0, y0 + h - 1)
            surf.tiles[x, y] = tile.HOUSE_WALL if edge else tile.HOUSE_FLOOR
    surf.tiles[x0 + w // 2, y0 + h - 1] = tile.DOOR
    for (dx, dy), t in interior:
        surf.tiles[x0 + dx, y0 + dy] = t


def _stamp_grange(state: GameState, rect) -> None:
    x0, y0, w, h = rect
    _stamp_hall(state, rect, interior=(
        ((2, 2), tile.TABLE), ((w // 2, 2), tile.TABLE), ((w - 3, 2), tile.TABLE),
        ((1, h - 3), tile.HEARTH)))
    for dx in (-1, w):
        if state.surface.in_bounds(x0 + dx, y0 + h - 1):
            if state.surface.tiles[x0 + dx, y0 + h - 1] in (tile.GRASS, tile.MEADOW):
                state.surface.tiles[x0 + dx, y0 + h - 1] = tile.LAMP


def _stamp_forge(state: GameState, rect) -> None:
    x0, y0, w, h = rect
    _stamp_hall(state, rect, interior=(
        ((1, 1), tile.HEARTH), ((w - 2, 1), tile.HEARTH), ((w - 2, h - 3), tile.BARREL)))
    # the point of the Deep Forge: a public furnace and anvil anyone may work
    state.surface.machines[(x0 + 2, y0 + 2)] = Machine(kind="furnace")
    state.surface.machines[(x0 + w - 3, y0 + 2)] = Machine(kind="anvil")


def _stamp_lighthouse(state: GameState, rect) -> None:
    surf = state.surface
    x0, y0, w, h = rect
    for x in range(x0, x0 + w):
        for y in range(y0, y0 + h):
            edge = x in (x0, x0 + w - 1) or y in (y0, y0 + h - 1)
            surf.tiles[x, y] = tile.RUINS_WALL if edge else tile.HOUSE_FLOOR
    surf.tiles[x0 + w // 2, y0 + h - 1] = tile.DOOR
    surf.tiles[x0 + w // 2, y0 + h // 2] = tile.LAMP      # the beam
    surf.tiles[x0 + w // 2, y0] = tile.LAMP               # visible over the wall


def _stamp_causeway(state: GameState, rect) -> None:
    """A small gatehouse, then the works: the fen tracks are paved and lit."""
    surf = state.surface
    _stamp_hall(state, rect)
    centers = getattr(surf, "village_centers", {})
    vx, vy = centers.get("Fenwick", (rect[0], rect[1]))
    paved = 0
    for x in range(vx - 40, vx + 41):
        for y in range(vy - 40, vy + 41):
            if not surf.in_bounds(x, y):
                continue
            if surf.tiles[x, y] == tile.DIRT_PATH:
                surf.tiles[x, y] = tile.ROAD
                paved += 1
                if paved % 7 == 0:               # a lamp beside every stretch
                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if (surf.in_bounds(nx, ny)
                                and surf.tiles[nx, ny] in (tile.GRASS, tile.MEADOW,
                                                           tile.MOOR, tile.FOG_GRASS)):
                            surf.tiles[nx, ny] = tile.LAMP
                            break


def _stamp_shrine(state, rect) -> None:
    """A walled shrine: an altar at the far wall, flanked by candle-lamps."""
    x0, y0, w, h = rect
    _stamp_hall(state, rect, interior=(
        ((w // 2, 1), tile.ALTAR),
        ((w // 2 - 2, 1), tile.LAMP), ((w // 2 + 2, 1), tile.LAMP)))


_STAMPS = {"grange_hall": _stamp_grange, "deep_forge": _stamp_forge,
           "lighthouse": _stamp_lighthouse, "causeway": _stamp_causeway,
           "shrine": _stamp_shrine}


def register_buildings(world, projects: list) -> None:
    """Re-register completed landmarks' look-mode records after a load (the save
    only persists player-built, non-village buildings — the landmark's tiles
    survive in the grid, but its record must be rebuilt from the project)."""
    for proj in projects:
        if proj.get("state") == "done" and proj.get("site"):
            x, y, w, h = proj["site"]
            world.buildings.append({"x": x, "y": y, "w": w, "h": h,
                                    "kind": proj["id"],
                                    "village": proj.get("village", ""), "owner": None})
