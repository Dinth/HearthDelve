"""The region-builder's toolbox: mechanisms shared by every generated map.

worldgen.py (Hollowmere Vale), westgen.py (the Westreach) and any future
region compose their worlds from these primitives — noise fields, ore veins,
road networks, signposts, and building shells — while keeping their own
*policy* (which biomes, whose villages, where the roads run) to themselves.

Everything here is deterministic for a given seed/rng, and the road tools are
tuned to be fast: costs come from a per-tile-id lookup table and the gap fill
is vectorised, because world generation runs on every load (a save replays
its seed and overlays the saved grid).
"""
from __future__ import annotations

import random

import numpy as np
import tcod.noise

from . import tile
from .gamemap import GameMap


# --- noise & veins -------------------------------------------------------------
def noise_field(seed: int, w: int, h: int, scale: float, octaves: int = 4) -> np.ndarray:
    """Return a (w, h) array in roughly [0, 1] from simplex noise."""
    noise = tcod.noise.Noise(
        dimensions=2,
        algorithm=tcod.noise.Algorithm.SIMPLEX,
        hurst=0.5,
        lacunarity=2.0,
        octaves=octaves,
        seed=seed,
    )
    xs = np.arange(w, dtype=np.float32) * scale
    ys = np.arange(h, dtype=np.float32) * scale
    raw = noise.sample_ogrid([xs, ys])      # (w, h) in [-1, 1]
    return (raw + 1.0) * 0.5


def grow_veins(tiles, w, h, host_id, ore_veins, max_len, gems, rng) -> None:
    """Sparse ore: a few short streaks (random walks) through host tiles, plus
    a handful of single gems. Greatly fewer than a uniform scatter."""
    hosts = list(zip(*np.where(tiles == host_id)))
    if not hosts:
        return
    for _ in range(ore_veins):
        x, y = (int(v) for v in rng.choice(hosts))
        for _ in range(rng.randint(1, max_len)):
            if not (0 <= x < w and 0 <= y < h) or tiles[x, y] != host_id:
                break
            tiles[x, y] = tile.ORE_VEIN
            nbrs = [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                    if (dx or dy) and 0 <= x + dx < w and 0 <= y + dy < h
                    and tiles[x + dx, y + dy] == host_id]
            if not nbrs:
                break
            x, y = rng.choice(nbrs)
    for _ in range(gems):                       # gems are always single
        x, y = (int(v) for v in rng.choice(hosts))
        if tiles[x, y] == host_id:
            tiles[x, y] = tile.GEM_VEIN


# --- roads ---------------------------------------------------------------------
# Built features a road must route AROUND, never through (impassable to roads).
ROAD_BLOCK = {"house_wall", "house_floor", "door", "bed", "shipping_bin",
              "fence", "tilled", "dungeon_down", "well", "lamp", "stall",
              "statue", "hearth", "table", "counter", "barrel", "altar", "grave",
              "tent", "campfire"}
_ROAD_NAMES = ("road", "bridge", "cobble")
_ROAD_KINDS = ("road", "bridge", "cobble")

SIGN_ROADS = (tile.ROAD, tile.BRIDGE, tile.COBBLE)


# How hard the land is to build a road across. Roads seek the low numbers, so a
# route naturally hugs gentle ground and skirts crags — which keeps village
# roads straight across the plains (uniform cost) yet makes a mountain approach
# wind through the passable folds instead of cutting a dead line over the rock.
_EASY = 4                           # grass, meadow, path, sand, flowers, dirt
_ROUGHNESS_BY_NAME = {
    "tall_grass": 6, "fog_grass": 6, "moor": 7,
    "marsh": 9, "hill": 10, "scree": 12,
}


def _terrain_cost(t: tile.TileType) -> int:
    if t.kind == "water":
        return 6                    # ford/bridge a river rather than detour far
    if t.kind == "wall":
        return 40                   # rock & cliff: wind around, cross only if walled in
    if t.kind == "tree":
        return 8                    # a road clears a tree — mild, skirts a stand
    if t.kind in ("foliage", "shrub", "shrub_berry", "reeds"):
        return 9                    # push through brush
    return _ROUGHNESS_BY_NAME.get(t.name, _EASY)


def _road_cost(t: tile.TileType, reuse: bool) -> int:
    """Pathing cost of one tile type: 0 = impassable (built features), 1 = reuse
    an existing road, else the terrain's build difficulty (see _terrain_cost)."""
    if t.name in ROAD_BLOCK:
        return 0                    # never pave buildings/plots
    if t.name in _ROAD_NAMES:
        return 1 if reuse else _EASY   # reuse existing roads -> junctions
    return _terrain_cost(t)


# Per-tile-id lookup tables: one fancy-index builds a whole cost/mask grid.
_COST_REUSE_BY_ID = np.array([_road_cost(t, True) for t in tile.TILES], dtype=np.int16)
_COST_DIRECT_BY_ID = np.array([_road_cost(t, False) for t in tile.TILES], dtype=np.int16)
_WATER_BY_ID = np.array([t.kind == "water" for t in tile.TILES])
_ROADKIND_BY_ID = np.array([t.kind in _ROAD_KINDS for t in tile.TILES])
# ground a gap-fill may pave: walkable, not already paving, not a built feature
_GAPFILL_BY_ID = np.array([t.walkable and t.kind not in _ROAD_KINDS
                           and t.name not in ROAD_BLOCK for t in tile.TILES])
_SIGNROAD_BY_ID = np.array([i in SIGN_ROADS for i in range(len(tile.TILES))])


def road_path(gm: GameMap, a: tuple[int, int], b: tuple[int, int], reuse: bool = True) -> list:
    """A*-route from a to b. Cardinal-only, so a river crossing is a proper
    full-width bridge. With ``reuse`` off, existing roads get no discount, so the
    path is carved directly (bridging water) instead of detouring along the
    network."""
    import tcod.path

    cost = (_COST_REUSE_BY_ID if reuse else _COST_DIRECT_BY_ID)[gm.tiles]
    cost[a[0], a[1]] = cost[b[0], b[1]] = 1   # endpoints must be reachable
    graph = tcod.path.SimpleGraph(cost=cost, cardinal=2, diagonal=0)
    pf = tcod.path.Pathfinder(graph)
    pf.add_root((b[0], b[1]))
    return pf.path_from((a[0], a[1])).tolist()


def paint_road(gm: GameMap, path: list) -> None:
    for x, y in path:
        t = tile.TILES[gm.tiles[x, y]]
        if t.name in ROAD_BLOCK or t.kind in ("bridge", "road"):
            continue                       # keep buildings, bridges, and paving
        gm.tiles[x, y] = tile.BRIDGE if t.kind == "water" else tile.ROAD


def draw_road(gm: GameMap, a: tuple[int, int], b: tuple[int, int]) -> None:
    """Lay a connected road from a to b, reusing the existing network so the
    whole thing is one piece."""
    paint_road(gm, road_path(gm, a, b, reuse=True))


def fill_road_gaps(gm: GameMap) -> None:
    """Close single-tile holes in a *straight run* of road (a stray flower or a
    bump the pathfinder stepped around), so road lines read as continuous.

    A gap is only filled when the road carries straight through it — two road
    cells on each side along one axis. Requiring the run to continue (not just
    a road cell either side) is what stops the fill from welding two roads that
    merely run parallel a tile apart into an ugly wide band near a village."""
    t = gm.tiles
    r = _ROADKIND_BY_ID[t]
    n = t.shape[1]

    def col(off):     # road grid shifted so [:, k] sees the neighbour k+off rows away
        s = np.zeros_like(r)
        if off < 0:
            s[:, -off:] = r[:, :n + off]
        elif off > 0:
            s[:, :n - off] = r[:, off:]
        else:
            s = r
        return s

    def row(off):
        s = np.zeros_like(r)
        m = t.shape[0]
        if off < 0:
            s[-off:, :] = r[:m + off, :]
        elif off > 0:
            s[:m - off, :] = r[off:, :]
        else:
            s = r
        return s

    vertical = col(-1) & col(1) & col(-2) & col(2)     # gap mid straight N-S run
    horizontal = row(-1) & row(1) & row(-2) & row(2)   # gap mid straight E-W run
    fill = _GAPFILL_BY_ID[t] & (vertical | horizontal)
    water = fill & _WATER_BY_ID[t]
    t[water] = tile.BRIDGE
    t[fill & ~water] = tile.ROAD


def gate(center: tuple[int, int], target: tuple[int, int], rx: int, ry: int) -> tuple[int, int]:
    """The point where a village's ROAD cross meets its edge, facing target.

    Country roads connect here, so the village cross and the country road are
    one continuous network.
    """
    cx, cy = center
    dx, dy = target[0] - cx, target[1] - cy
    if abs(dx) >= abs(dy):
        return cx + (rx if dx > 0 else -rx), cy
    return cx, cy + (ry if dy > 0 else -ry)


# --- signposts -------------------------------------------------------------------
def branch_through(gm: GameMap, jx: int, jy: int, dx: int, dy: int, cap: int = 14) -> bool:
    """Follow the road branch leaving junction (jx,jy) in direction (dx,dy). It's
    a "through route" if it keeps going for `cap` tiles; a short dead-end (a spur
    to a single household) runs out of road first and returns False."""
    x, y = jx + dx, jy + dy
    if not gm.in_bounds(x, y) or gm.tiles[x, y] not in SIGN_ROADS:
        return False
    px, py = jx, jy
    for _ in range(cap):
        nxts = [(x + ax, y + ay) for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if (x + ax, y + ay) != (px, py) and gm.in_bounds(x + ax, y + ay)
                and gm.tiles[x + ax, y + ay] in SIGN_ROADS]
        if not nxts:
            return False          # dead-ended — just a spur to one dwelling
        px, py = x, y
        x, y = nxts[0]            # follow the road on (a fork mid-branch still counts)
    return True                   # still going — a genuine route worth signing


def place_waypoints(gm: GameMap) -> None:
    """Stand a signpost beside road junctions where three or more real routes
    meet — not where a short spur to a single household joins the road."""
    # Vectorised prefilter: only road cells with 3+ cardinal road neighbours
    # can be junctions; the (expensive) route-tracing runs on those few.
    road = _SIGNROAD_BY_ID[gm.tiles]
    cand = np.zeros(road.shape, dtype=bool)
    cand[1:-1, 1:-1] = road[1:-1, 1:-1] & (
        (road[:-2, 1:-1].astype(np.int8) + road[2:, 1:-1] + road[1:-1, :-2]
         + road[1:-1, 2:]) >= 3)
    placed: list = []
    for x, y in np.argwhere(cand):           # row-major: same order as an x,y scan
        x, y = int(x), int(y)
        dirs = [(dx, dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if gm.tiles[x + dx, y + dy] in SIGN_ROADS]
        if len(dirs) < 3:
            continue          # not a junction at all
        # A thickened zigzag corner reads like a junction (3 road
        # neighbours) but isn't one: at a real T or crossroads of 1-wide
        # roads the gaps BETWEEN the arms are open ground, while a
        # gap-filled corner has road in the diagonal. Hill switchbacks
        # used to sprout a signpost every eight tiles because of this.
        _DIAG = {((0, -1), (1, 0)): (1, -1), ((1, 0), (0, 1)): (1, 1),
                 ((0, 1), (-1, 0)): (-1, 1), ((-1, 0), (0, -1)): (-1, -1)}
        if any(a in dirs and b in dirs and gm.tiles[x + dx, y + dy] in SIGN_ROADS
               for (a, b), (dx, dy) in _DIAG.items()):
            continue          # fat corner of one road, not a meeting of routes
        through = sum(branch_through(gm, x, y, dx, dy) for dx, dy in dirs)
        if through < 3:
            continue          # a household spur off a road — no signpost needed
        if any(abs(x - px) + abs(y - py) < 8 for px, py in placed):
            continue          # one signpost per junction cluster
        for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            sx, sy = x + dx, y + dy
            if (gm.in_bounds(sx, sy) and gm.walkable(sx, sy)
                    and gm.tile_at(sx, sy).kind in ("terrain", "tree", "flower")):
                gm.tiles[sx, sy] = tile.SIGNPOST
                placed.append((x, y))
                break


# --- building shells & interiors -------------------------------------------------
# terrain a building may be carved over (open, natural ground only — never
# roads, water, or anything already built)
NO_BUILD = {"water", "river", "road", "bridge", "cobble", "sand", "house_wall",
            "house_floor", "door", "bed", "shipping_bin", "fence", "tilled", "well",
            "lamp", "stall", "signpost", "statue", "hearth", "table", "counter",
            "barrel", "altar", "grave", "boat", "dungeon_down"}


def overlap(a, b, margin: int) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (ax - margin < bx + bw and ax + aw + margin > bx
            and ay - margin < by + bh and ay + ah + margin > by)


def door_toward(bxc: int, byc: int, tx: int, ty: int) -> str:
    """Which wall (N/S/E/W) a building's door sits on to face point (tx,ty)."""
    dx, dy = tx - bxc, ty - byc
    if abs(dx) >= abs(dy):
        return "E" if dx > 0 else "W"
    return "S" if dy > 0 else "N"


def area_clear(gm: GameMap, x: int, y: int, w: int, h: int, margin: int = 1) -> bool:
    for xx in range(x - margin, x + w + margin):
        for yy in range(y - margin, y + h + margin):
            if not gm.in_bounds(xx, yy) or tile.TILES[gm.tiles[xx, yy]].name in NO_BUILD:
                return False
    return True


def rect_building(gm: GameMap, x: int, y: int, w: int, h: int, side: str) -> dict:
    """Carve a walled shell with a door on `side`. Returns a layout dict."""
    t = gm.tiles
    for bx in range(x, x + w):
        for by in range(y, y + h):
            if not gm.in_bounds(bx, by):
                continue
            edge = bx in (x, x + w - 1) or by in (y, y + h - 1)
            t[bx, by] = tile.HOUSE_WALL if edge else tile.HOUSE_FLOOR
    if side == "S":
        door = (x + w // 2, y + h - 1); front = (door[0], door[1] + 1); inner = (door[0], door[1] - 1)
    elif side == "N":
        door = (x + w // 2, y); front = (door[0], door[1] - 1); inner = (door[0], door[1] + 1)
    elif side == "E":
        door = (x + w - 1, y + h // 2); front = (door[0] + 1, door[1]); inner = (door[0] - 1, door[1])
    else:  # W
        door = (x, y + h // 2); front = (door[0] - 1, door[1]); inner = (door[0] + 1, door[1])
    if gm.in_bounds(*door):
        t[door] = tile.DOOR
    return {"x": x, "y": y, "w": w, "h": h, "side": side,
            "door": door, "front": front, "inner": inner}


def interior_floor(gm: GameMap, b: dict) -> list:
    """Floor tiles inside a building that are actually reachable from the door
    (flood fill from the inner-door tile), so no NPC is placed in a pocket that
    furniture has sealed off."""
    x0, y0 = b["x"], b["y"]
    x1, y1 = b["x"] + b["w"] - 1, b["y"] + b["h"] - 1
    start = b["inner"]
    if gm.tiles[start] != tile.HOUSE_FLOOR:
        return []
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if x0 < nx < x1 and y0 < ny < y1 and (nx, ny) not in seen \
                    and gm.tiles[nx, ny] == tile.HOUSE_FLOOR:
                seen.add((nx, ny)); stack.append((nx, ny))
    return list(seen)


def partition(gm: GameMap, b: dict) -> tuple:
    """Split the interior into a front room (with the door) and a back room,
    joined by an inner doorway. Returns (front_rect, back_rect, gap_tile)."""
    x, y, w, h = b["x"], b["y"], b["w"], b["h"]
    dcol, drow = b["door"]
    if b["side"] in ("S", "N"):
        row = y + h // 2
        gap = (dcol, row)
        for xx in range(x + 1, x + w - 1):
            gm.tiles[xx, row] = tile.HOUSE_FLOOR if xx == dcol else tile.HOUSE_WALL
        if b["side"] == "S":
            back = (x + 1, y + 1, x + w - 2, row - 1); front = (x + 1, row + 1, x + w - 2, y + h - 2)
        else:
            front = (x + 1, y + 1, x + w - 2, row - 1); back = (x + 1, row + 1, x + w - 2, y + h - 2)
    else:
        col = x + w // 2
        gap = (col, drow)
        for yy in range(y + 1, y + h - 1):
            gm.tiles[col, yy] = tile.HOUSE_FLOOR if yy == drow else tile.HOUSE_WALL
        if b["side"] == "E":
            back = (x + 1, y + 1, col - 1, y + h - 2); front = (col + 1, y + 1, x + w - 2, y + h - 2)
        else:
            front = (x + 1, y + 1, col - 1, y + h - 2); back = (col + 1, y + 1, x + w - 2, y + h - 2)
    return front, back, gap


def put(gm: GameMap, x: int, y: int, tid: int) -> bool:
    if gm.in_bounds(x, y) and gm.tiles[x, y] == tile.HOUSE_FLOOR:
        gm.tiles[x, y] = tid
        return True
    return False


def ring_cells(rect: tuple) -> list:
    """Interior tiles that touch a wall (where furniture naturally stands)."""
    x0, y0, x1, y1 = rect
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)
            if x in (x0, x1) or y in (y0, y1)]


def keep_clear(b: dict, gap: tuple | None) -> set:
    """Tiles that must stay walkable so no room gets sealed off by furniture."""
    keep = {b["inner"]}
    if gap:
        gx, gy = gap
        keep |= {(gx, gy), (gx + 1, gy), (gx - 1, gy), (gx, gy + 1), (gx, gy - 1)}
    return keep


def furnish_room(gm: GameMap, rect: tuple, spec: list, rng: random.Random, keep: set) -> None:
    """Place furniture on random wall-adjacent tiles (varied, never sealing)."""
    cells = [c for c in ring_cells(rect) if c not in keep]
    rng.shuffle(cells)
    for tid, count in spec:
        for _ in range(count):
            while cells:
                c = cells.pop()
                if put(gm, *c, tid):
                    break


def pick_home(rect: tuple, free: list):
    x0, y0, x1, y1 = rect
    inside = [(x, y) for (x, y) in free if x0 <= x <= x1 and y0 <= y <= y1]
    return inside[0] if inside else (free[0] if free else None)
