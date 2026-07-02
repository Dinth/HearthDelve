"""One-time procedural generation of Hollowmere Vale (DESIGN §4/§8).

Pipeline:
  1. wildness field  = normalized distance-from-center + low-freq noise
  2. biome assignment = per-tier base terrain chosen by a second noise field
  3. river            = a noise-traced band carved across the map
  4. homestead carve  = safe clearing at center: house, bed, bin, fenced plot
  5. features         = trees/forage/ore scatter + dungeon entrances

Deterministic for a given seed so a save reproduces its world.
"""
from __future__ import annotations

import random

import numpy as np
import tcod.noise

from . import tile
from .gamemap import GameMap
from ..engine import constants as C
from ..data import content


def _noise_field(seed: int, w: int, h: int, scale: float, octaves: int = 4) -> np.ndarray:
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


def _wildness(w: int, h: int, seed: int) -> np.ndarray:
    cx, cy = w / 2.0, h / 2.0
    yy, xx = np.meshgrid(np.arange(h), np.arange(w))  # both (w, h)
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    dist /= dist.max()                                # 0 at center .. 1 at corner
    jitter = _noise_field(seed, w, h, scale=0.035, octaves=3)
    field = 0.78 * dist + 0.22 * jitter
    return np.clip(field, 0.0, 1.0)


def _grow_veins(tiles, w, h, host_id, ore_veins, max_len, gems, rng) -> None:
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


def generate(seed: int = 1337) -> GameMap:
    w, h = C.WORLD_W, C.WORLD_H
    tiles = np.full((w, h), tile.GRASS, dtype=np.uint8)

    wild = _wildness(w, h, seed)
    flora = _noise_field(seed + 7, w, h, scale=0.08, octaves=4)
    detail = _noise_field(seed + 13, w, h, scale=0.20, octaves=2)
    variety = _noise_field(seed + 41, w, h, scale=0.16, octaves=2)   # tree/shrub kind
    rare = _noise_field(seed + 57, w, h, scale=0.55, octaves=1)       # rare-feature mask

    t1 = wild < C.TIER1_MAX
    t2 = (wild >= C.TIER1_MAX) & (wild < C.TIER2_MAX)
    t3 = wild >= C.TIER2_MAX

    # --- T1 homestead belt: gentle grass & meadow ---------------------------
    tiles[t1] = tile.GRASS
    tiles[t1 & (detail > 0.62)] = tile.MEADOW

    # --- T2 edge: meadow, then woods where flora is dense -------------------
    tiles[t2] = tile.MEADOW
    tiles[t2 & (detail > 0.55)] = tile.TALL_GRASS
    woods = t2 & (flora > 0.58)
    tiles[woods] = tile.GRASS
    treemask = woods & (detail > 0.42)
    # broadleaf varieties in smooth groves (passable on their own)
    tiles[treemask & (variety < 0.20)] = tile.TREE_OAK
    tiles[treemask & (variety >= 0.20) & (variety < 0.40)] = tile.TREE_MAPLE
    tiles[treemask & (variety >= 0.40) & (variety < 0.60)] = tile.TREE_BIRCH
    tiles[treemask & (variety >= 0.60) & (variety < 0.80)] = tile.TREE_POPLAR
    tiles[treemask & (variety >= 0.80)] = tile.TREE_WILLOW
    # dense grove cores choke with impassable foliage
    tiles[woods & (flora > 0.74) & (detail > 0.60)] = tile.FOLIAGE
    # surface rock outcrops in the edge (ore is added sparsely as veins later)
    rocky = t2 & (flora < 0.30)
    tiles[rocky] = tile.GRASS
    tiles[rocky & (detail > 0.66)] = tile.ROCK

    # --- T3 wilds: old forest / moor / ruins by flora value -----------------
    old_forest = t3 & (flora > 0.55)
    moor = t3 & (flora <= 0.55) & (flora > 0.32)
    ruins = t3 & (flora <= 0.32)
    tiles[old_forest] = tile.GRASS
    conif = old_forest & (detail > 0.38)
    tiles[conif & (variety < 0.5)] = tile.TREE_PINE
    tiles[conif & (variety >= 0.5)] = tile.TREE_SPRUCE
    tiles[old_forest & (flora > 0.70) & (detail > 0.50)] = tile.FOLIAGE
    tiles[moor] = tile.MOOR
    tiles[moor & (detail > 0.6)] = tile.FOG_GRASS
    tiles[ruins] = tile.RUINS_FLOOR
    tiles[ruins & (detail > 0.58)] = tile.RUINS_WALL

    # Shrubs: plain shrubs scatter through wooded land; fruit-bearing shrubs
    # are much rarer (a sparse subset), split between the three berry kinds.
    shrubland = (t2 | t3) & (flora > 0.45)
    shrub_spots = shrubland & (detail > 0.50) & (detail < 0.55)
    tiles[shrub_spots] = tile.SHRUB
    fruit_spots = shrub_spots & (rare > 0.84)
    tiles[fruit_spots & (variety < 0.34)] = tile.SHRUB_RASPBERRY
    tiles[fruit_spots & (variety >= 0.34) & (variety < 0.67)] = tile.SHRUB_GOOSEBERRY
    tiles[fruit_spots & (variety >= 0.67)] = tile.SHRUB_CURRANT

    # Wild mushrooms. Forest species (bolete, chanterelle) grow on the shaded
    # grass under the woods; field species (button, parasol) dot open grass and
    # meadow. We only RECORD the spots here — the day cycle sprouts them in
    # summer/autumn and clears them otherwise (farming._seasonal_flora).
    forest_m = ((tiles == tile.GRASS) | (tiles == tile.MOOR) | (tiles == tile.FOG_GRASS)) \
        & (t2 | t3) & (flora > 0.5) & (detail > 0.40) & (detail < 0.47)
    field_m = ((tiles == tile.GRASS) | (tiles == tile.MEADOW)) \
        & (t1 | t2) & (flora < 0.40) & (detail > 0.44) & (detail < 0.47)
    mushroom_spots = []
    for mask, lo, hi in ((forest_m, tile.BOLETE, tile.CHANTERELLE),
                         (field_m, tile.BUTTON_MUSHROOM, tile.PARASOL_MUSHROOM)):
        mx, my = np.where(mask)
        for x, y in zip(mx.tolist(), my.tolist()):
            species = hi if variety[x, y] >= 0.5 else lo
            mushroom_spots.append((x, y, int(species), int(tiles[x, y])))

    # Wildflowers dappled across the meadows. Like mushrooms, we only RECORD the
    # spots and let the day cycle bloom them in spring/summer, drifting daily.
    bloom = (tiles == tile.MEADOW) & (detail > 0.26) & (detail < 0.40)
    _flower_cols = (tile.FLOWER_RED, tile.FLOWER_YELLOW, tile.FLOWER_VIOLET, tile.FLOWER_WHITE)
    flower_spots = []
    bx, by = np.where(bloom)
    for x, y in zip(bx.tolist(), by.tolist()):
        col = _flower_cols[min(3, int(variety[x, y] * 4))]
        flower_spots.append((x, y, int(col), int(tiles[x, y])))

    # Sparse ore: a handful of short veins in rock outcrops, plus a few lone gems.
    _grow_veins(tiles, w, h, tile.ROCK, ore_veins=12, max_len=6, gems=6,
                rng=random.Random(seed + 71))

    # --- River: a meandering watercourse -----------------------------------
    # A momentum-driven random walk (steered by fractal noise) rather than a
    # sine wave — so it wanders irregularly like a real river. The band is
    # filled from the previous row's centre to this row's, keeping it watertight
    # (a real barrier roads must bridge).
    steer = _noise_field(seed + 29, w, 1, scale=0.07, octaves=4).reshape(-1)
    wide_n = _noise_field(seed + 53, w, 1, scale=0.05, octaves=3).reshape(-1)
    c, vel, prev_c = w * 0.5, 0.0, None
    centerline = []
    for y in range(h):
        vel = vel * 0.86 + (steer[min(y, w - 1)] - 0.5) * 1.7   # accelerate, damped
        vel = max(-2.7, min(2.7, vel))
        c = max(28.0, min(w - 28.0, c + vel))
        ci = int(round(c))
        half = 1 + int(wide_n[min(y, w - 1)] * 2.4)             # irregular width 3..7
        lo, hi = ci - half, ci + half
        if prev_c is not None:                                  # keep watertight
            lo, hi = min(lo, prev_c - 1), max(hi, prev_c + 1)
        for x in range(lo, hi + 1):
            if 0 <= x < w:
                tiles[x, y] = tile.RIVER
        for x in (lo - 1, hi + 1):                              # sandy banks
            if 0 <= x < w and tiles[x, y] != tile.RIVER:
                tiles[x, y] = tile.SAND
        prev_c = ci
        centerline.append((ci, y))

    # A couple of broader sandy beaches where the river slows and widens.
    brng = random.Random(seed + 91)
    body = centerline[20:-20]
    for ci, by in (brng.sample(body, min(3, len(body))) if body else []):
        bx = ci + brng.choice((-1, 1)) * brng.randint(3, 5)
        rad = brng.randint(4, 6)
        for x in range(bx - rad, bx + rad + 1):
            for y in range(by - rad, by + rad + 1):
                if not (0 <= x < w and 0 <= y < h):
                    continue
                if (x - bx) ** 2 + (y - by) ** 2 <= rad * rad and tiles[x, y] != tile.RIVER:
                    tiles[x, y] = tile.SAND

    gm = GameMap(width=w, height=h, tiles=tiles)
    gm.mushroom_spots = mushroom_spots
    gm.flower_spots = flower_spots
    coast = _carve_sea(gm, seed)
    _carve_homestead(gm, seed)
    centers = _carve_villages(gm, seed, coast)
    gm.village_centers = dict(centers)
    _place_dungeons(gm, wild, flora)
    forest_track = _carve_forest(gm, seed)
    _draw_roads(gm, centers)
    if forest_track is not None:                    # a track links the hut to the network
        _draw_road(gm, forest_track, gm.spawn)
        _fill_road_gaps(gm)
    _place_waypoints(gm)
    _populate_wildlife(gm, random.Random(seed + 131))
    return gm


def _carve_sea(gm: GameMap, seed: int) -> np.ndarray:
    """Flood the southern reach with an open sea behind an irregular coast.

    Returns the per-column coastline y (first sea row), so a coastal village can
    site its piers against real water.
    """
    w, h = gm.width, gm.height
    wob = _noise_field(seed + 211, w, 1, scale=0.045, octaves=3).reshape(-1)
    base = int(h * 0.86)
    coast = np.empty(w, dtype=np.int32)
    for x in range(w):
        cy = base + int((wob[x] - 0.5) * 46)      # wander the shoreline ±23
        cy = max(4, min(h - 4, cy))
        coast[x] = cy
        gm.tiles[x, cy:h] = tile.WATER
        for y in range(cy - 2, cy):               # a sandy strand above the tide
            if 0 <= y < h and gm.tiles[x, y] not in (tile.WATER, tile.RIVER):
                gm.tiles[x, y] = tile.SAND
    return coast


def _populate_wildlife(gm: GameMap, rng: random.Random) -> None:
    """Scatter roaming critters over open ground across the Vale.

    Placed on walkable, non-road tiles and kept out of the immediate homestead
    so they wander in rather than start on your doorstep. Positions are
    deterministic from the seed, so a reloaded world re-populates the same way.
    """
    from ..data import content
    from ..entities.monster import Mob

    cx, cy = C.WORLD_CENTER
    count = 140
    placed = 0
    attempts = 0
    while placed < count and attempts < count * 40:
        attempts += 1
        x = rng.randint(4, gm.width - 5)
        y = rng.randint(4, gm.height - 5)
        if not gm.walkable(x, y):
            continue
        if gm.tile_at(x, y).kind in ("road", "bridge", "stairs"):
            continue
        if max(abs(x - cx), abs(y - cy)) < 10:      # give the farmyard some space
            continue
        c = rng.choice(content.WILDLIFE)
        gm.monsters.append(Mob(c.name, c.glyph, c.color, c.hp, c.hp, c.atk,
                               c.defense, c.speed, c.behavior, x, y,
                               kind="wildlife", diet=c.diet, seasons=c.seasons))
        placed += 1

    # A few rare bears, roaming far from the farmstead.
    bears, tries = 0, 0
    while bears < rng.randint(2, 4) and tries < 2000:
        tries += 1
        x, y = rng.randint(4, gm.width - 5), rng.randint(4, gm.height - 5)
        if not gm.walkable(x, y) or gm.tile_at(x, y).kind in ("road", "bridge", "stairs"):
            continue
        if max(abs(x - cx), abs(y - cy)) < 40:        # keep them out in the wilds
            continue
        b = content.BEAR
        gm.monsters.append(Mob(b.name, b.glyph, b.color, b.hp, b.hp, b.atk,
                               b.defense, b.speed, b.behavior, x, y,
                               kind="wildlife", diet=b.diet, seasons=b.seasons))
        bears += 1


def _place_waypoints(gm: GameMap) -> None:
    """Stand a signpost beside notable road junctions (3+ road neighbours)."""
    rs = (tile.ROAD, tile.BRIDGE)
    placed: list = []
    for x in range(1, gm.width - 1):
        for y in range(1, gm.height - 1):
            if gm.tiles[x, y] not in rs:
                continue
            nb = sum(gm.tiles[x + dx, y + dy] in rs
                     for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if nb < 3:
                continue
            if any(abs(x - px) + abs(y - py) < 8 for px, py in placed):
                continue          # one signpost per junction cluster
            for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                sx, sy = x + dx, y + dy
                if (gm.in_bounds(sx, sy) and gm.walkable(sx, sy)
                        and gm.tile_at(sx, sy).kind in ("terrain", "tree", "flower")):
                    gm.tiles[sx, sy] = tile.SIGNPOST
                    placed.append((x, y))
                    break


# Built features a road must route AROUND, never through (impassable to roads).
_ROAD_BLOCK = {"house_wall", "house_floor", "door", "bed", "shipping_bin",
               "fence", "tilled", "dungeon_down", "well", "lamp", "stall",
               "statue", "hearth", "table", "counter", "barrel", "altar", "grave"}
_BLOCK_BY_ID = np.array([t.name in _ROAD_BLOCK for t in tile.TILES])
_WATER_BY_ID = np.array([t.kind == "water" for t in tile.TILES])
# Existing paving (dirt road, bridge, cobble) is reused by A* so lanes braid
# into one network and never repave a square or a bridge.
_ROAD_BY_ID = np.array([t.name in ("road", "bridge", "cobble") for t in tile.TILES])


def _gate(center: tuple[int, int], target: tuple[int, int], rx: int, ry: int) -> tuple[int, int]:
    """The point where a village's ROAD cross meets its edge, facing target.

    Country roads connect here, so the village cross and the country road are
    one continuous network.
    """
    cx, cy = center
    dx, dy = target[0] - cx, target[1] - cy
    if abs(dx) >= abs(dy):
        return cx + (rx if dx > 0 else -rx), cy
    return cx, cy + (ry if dy > 0 else -ry)


def _road_path(gm: GameMap, a: tuple[int, int], b: tuple[int, int], reuse: bool = True) -> list:
    """A*-route from a to b. Cardinal-only, so a river crossing is a proper
    full-width bridge. With ``reuse`` off, existing roads get no discount, so the
    path is carved directly (bridging water) instead of detouring along the
    network."""
    import tcod.path

    cost = np.full((gm.width, gm.height), 4, dtype=np.int16)   # open country
    cost[_ROAD_BY_ID[gm.tiles]] = 1 if reuse else 4           # reuse existing roads -> junctions
    cost[_WATER_BY_ID[gm.tiles]] = 6          # bridge a river rather than detour far
    cost[_BLOCK_BY_ID[gm.tiles]] = 0          # never pave buildings/plots
    cost[a[0], a[1]] = cost[b[0], b[1]] = 1   # endpoints must be reachable
    graph = tcod.path.SimpleGraph(cost=cost, cardinal=2, diagonal=0)
    pf = tcod.path.Pathfinder(graph)
    pf.add_root((b[0], b[1]))
    return pf.path_from((a[0], a[1])).tolist()


def _paint_road(gm: GameMap, path: list) -> None:
    for x, y in path:
        t = tile.TILES[gm.tiles[x, y]]
        if t.name in _ROAD_BLOCK or t.kind in ("bridge", "road"):
            continue                       # keep buildings, bridges, and paving
        gm.tiles[x, y] = tile.BRIDGE if t.kind == "water" else tile.ROAD


def _draw_road(gm: GameMap, a: tuple[int, int], b: tuple[int, int]) -> None:
    """Lay a connected road from a to b, reusing the existing network so the
    whole thing is one piece."""
    _paint_road(gm, _road_path(gm, a, b, reuse=True))


def _draw_roads(gm: GameMap, centers: dict) -> None:
    hub = gm.spawn                       # the farm sits on the main road
    pts = list(centers.values())
    # Trunk roads: each village plaza connects to the farm.
    for c in pts:
        _draw_road(gm, c, hub)
    # Every pair of villages is linked. Prefer sharing the existing network, but
    # if that forces a big detour (e.g. routing all the way via the farm when a
    # short direct road — bridging a river — would do), carve the direct road.
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            via = _road_path(gm, pts[i], pts[j], reuse=True)
            direct = _road_path(gm, pts[i], pts[j], reuse=False)
            if direct and (not via or len(direct) <= 0.8 * len(via)):
                _paint_road(gm, direct)
            else:
                _paint_road(gm, via or direct)
    # Each dungeon is reached from the farm AND its nearest village (more loops);
    # roads reuse existing roads so they branch at junctions.
    for d in gm.dungeons:
        _draw_road(gm, hub, d)
        nc = min(pts, key=lambda c: (c[0] - d[0]) ** 2 + (c[1] - d[1]) ** 2)
        _draw_road(gm, nc, d)
    _fill_road_gaps(gm)


def _fill_road_gaps(gm: GameMap) -> None:
    """Close single-tile holes in a straight run of road (e.g. a stray flower or
    a bump the pathfinder stepped around), so road lines read as continuous."""
    rk = ("road", "bridge", "cobble")
    fills = []
    for x in range(1, gm.width - 1):
        for y in range(1, gm.height - 1):
            t = tile.TILES[gm.tiles[x, y]]
            if t.kind in rk or not t.walkable or t.name in _ROAD_BLOCK:
                continue
            ns = tile.TILES[gm.tiles[x, y - 1]].kind in rk and tile.TILES[gm.tiles[x, y + 1]].kind in rk
            ew = tile.TILES[gm.tiles[x - 1, y]].kind in rk and tile.TILES[gm.tiles[x + 1, y]].kind in rk
            if ns or ew:
                fills.append((x, y))
    for x, y in fills:
        gm.tiles[x, y] = tile.BRIDGE if tile.TILES[gm.tiles[x, y]].kind == "water" else tile.ROAD


def _overlap(a, b, margin: int) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (ax - margin < bx + bw and ax + aw + margin > bx
            and ay - margin < by + bh and ay + ah + margin > by)


# --- building shells & interiors ---------------------------------------------
def _door_toward(bxc: int, byc: int, tx: int, ty: int) -> str:
    """Which wall (N/S/E/W) a building's door sits on to face point (tx,ty)."""
    dx, dy = tx - bxc, ty - byc
    if abs(dx) >= abs(dy):
        return "E" if dx > 0 else "W"
    return "S" if dy > 0 else "N"


# terrain a building may be carved over (open, natural ground only — never
# roads, water, or anything already built)
_NO_BUILD = {"water", "river", "road", "bridge", "cobble", "sand", "house_wall",
             "house_floor", "door", "bed", "shipping_bin", "fence", "tilled", "well",
             "lamp", "stall", "signpost", "statue", "hearth", "table", "counter",
             "barrel", "altar", "grave", "boat", "dungeon_down"}


def _area_clear(gm: GameMap, x: int, y: int, w: int, h: int, margin: int = 1) -> bool:
    for xx in range(x - margin, x + w + margin):
        for yy in range(y - margin, y + h + margin):
            if not gm.in_bounds(xx, yy) or tile.TILES[gm.tiles[xx, yy]].name in _NO_BUILD:
                return False
    return True


def _rect_building(gm: GameMap, x: int, y: int, w: int, h: int, side: str) -> dict:
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


def _interior_floor(gm: GameMap, b: dict) -> list:
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


def _partition(gm: GameMap, b: dict) -> tuple:
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


def _put(gm: GameMap, x: int, y: int, tid: int) -> bool:
    if gm.in_bounds(x, y) and gm.tiles[x, y] == tile.HOUSE_FLOOR:
        gm.tiles[x, y] = tid
        return True
    return False


def _ring_cells(rect: tuple) -> list:
    """Interior tiles that touch a wall (where furniture naturally stands)."""
    x0, y0, x1, y1 = rect
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)
            if x in (x0, x1) or y in (y0, y1)]


def _keep_clear(b: dict, gap: tuple | None) -> set:
    """Tiles that must stay walkable so no room gets sealed off by furniture."""
    keep = {b["inner"]}
    if gap:
        gx, gy = gap
        keep |= {(gx, gy), (gx + 1, gy), (gx - 1, gy), (gx, gy + 1), (gx, gy - 1)}
    return keep


def _furnish_room(gm: GameMap, rect: tuple, spec: list, rng, keep: set) -> None:
    """Place furniture on random wall-adjacent tiles (varied, never sealing)."""
    cells = [c for c in _ring_cells(rect) if c not in keep]
    rng.shuffle(cells)
    for tid, count in spec:
        for _ in range(count):
            while cells:
                c = cells.pop()
                if _put(gm, *c, tid):
                    break


def _pick_home(rect: tuple, free: list):
    x0, y0, x1, y1 = rect
    inside = [(x, y) for (x, y) in free if x0 <= x <= x1 and y0 <= y <= y1]
    return inside[0] if inside else (free[0] if free else None)


def _furnish_house(gm: GameMap, b: dict, rng) -> dict:
    """A dwelling: a kitchen/living room and a bedroom, furniture placed with
    variety. Which room is which, counts and positions all vary per house."""
    front, back, gap = _partition(gm, b)
    keep = _keep_clear(b, gap)
    kitchen, bedroom = (front, back) if rng.random() < 0.5 else (back, front)
    ksp = [(tile.HEARTH, 1), (tile.TABLE, 1 + (1 if rng.random() < 0.35 else 0))]
    if rng.random() < 0.4:
        ksp.append((tile.BARREL, 1))
    _furnish_room(gm, kitchen, ksp, rng, keep)
    bsp = [(tile.BED, 2 if rng.random() < 0.3 else 1)]
    if rng.random() < 0.45:
        bsp.append((tile.TABLE, 1))
    _furnish_room(gm, bedroom, bsp, rng, keep)
    free = _interior_floor(gm, b)
    return {"home": _pick_home(bedroom, free) or b["inner"], "work": b["front"], "seats": free}


def _furnish_shop(gm: GameMap, b: dict, rng) -> dict:
    """A dedicated shop room (counters and goods) up front, living quarters behind."""
    front, back, gap = _partition(gm, b)
    keep = _keep_clear(b, gap)
    _furnish_room(gm, front, [(tile.COUNTER, 2), (tile.BARREL, 2)], rng, keep)   # the shop
    _furnish_room(gm, back, [(tile.BED, 1), (tile.HEARTH, 1), (tile.TABLE, 1)], rng, keep)
    free = _interior_floor(gm, b)
    return {"home": _pick_home(back, free) or b["inner"], "work": b["front"], "seats": free}


def _furnish_inn(gm: GameMap, b: dict, rng) -> dict:
    """A taproom (hearth, tables, barrels) with guest bedrooms behind."""
    front, back, gap = _partition(gm, b)
    keep = _keep_clear(b, gap)
    _furnish_room(gm, front, [(tile.HEARTH, 1), (tile.TABLE, 3), (tile.BARREL, 2)], rng, keep)
    _furnish_room(gm, back, [(tile.BED, 3)], rng, keep)
    free = _interior_floor(gm, b)
    seats = [c for c in free if _in_rect(c, front)]
    return {"home": _pick_home(back, free) or b["inner"], "work": b["front"],
            "seats": seats or free}


def _in_rect(c, rect):
    x0, y0, x1, y1 = rect
    return x0 <= c[0] <= x1 and y0 <= c[1] <= y1


def _furnish_temple(gm: GameMap, b: dict, rng) -> dict:
    """A chapel: a clear central aisle from the door to a raised altar at the
    far end, candles beside it, and just a couple of pews near the entrance."""
    x, y, w, h = b["x"], b["y"], b["w"], b["h"]
    s = b["side"]
    if s == "S":                       # door south → altar at north wall
        ax, ay = x + w // 2, y + 1; approach = (ax, ay + 1); vertical = True
        cand1, cand2 = (ax - 1, ay), (ax + 1, ay)
        pew_span = range(y + h - 3, y + h - 2)
    elif s == "N":
        ax, ay = x + w // 2, y + h - 2; approach = (ax, ay - 1); vertical = True
        cand1, cand2 = (ax - 1, ay), (ax + 1, ay)
        pew_span = range(y + 2, y + 3)
    elif s == "W":
        ax, ay = x + w - 2, y + h // 2; approach = (ax - 1, ay); vertical = False
        cand1, cand2 = (ax, ay - 1), (ax, ay + 1)
        pew_span = range(x + 2, x + 3)
    else:                              # door east → altar at west wall
        ax, ay = x + 1, y + h // 2; approach = (ax + 1, ay); vertical = False
        cand1, cand2 = (ax, ay - 1), (ax, ay + 1)
        pew_span = range(x + w - 3, x + w - 2)
    _put(gm, ax, ay, tile.ALTAR)
    _put(gm, *cand1, tile.LAMP)        # altar candles
    _put(gm, *cand2, tile.LAMP)
    # a couple of pews near the entrance, flanking the aisle (never on it)
    if vertical:
        for px in (ax - 2, ax + 2):
            for py in pew_span:
                _put(gm, px, py, tile.TABLE)
    else:
        for py in (ay - 2, ay + 2):
            for px in pew_span:
                _put(gm, px, py, tile.TABLE)
    free = _interior_floor(gm, b)
    return {"home": approach, "work": approach if gm.walkable(*approach) else b["front"],
            "seats": free, "altar": (ax, ay), "vertical": vertical}


def _furnish(gm: GameMap, b: dict, tag: str, rng) -> dict:
    if b["w"] < 5 or b["h"] < 4:
        return {"home": b["inner"], "work": b["front"], "seats": _interior_floor(gm, b)}
    if tag == "temple":
        return _furnish_temple(gm, b, rng)
    if tag == "shop":
        return _furnish_shop(gm, b, rng)
    if tag == "inn":
        return _furnish_inn(gm, b, rng)
    return _furnish_house(gm, b, rng)          # cottage / farmhouse / smithy dwelling


def _build_field(gm: GameMap, b: dict, rng, placed: list) -> None:
    """A fenced, tilled field behind a farmhouse, stocked with real in-season
    crops (re-tended each morning). Records tiles in village_fields."""
    from ..data.content import crops_in_season
    from ..world.crops import CropPlot
    x, y, w, h = b["x"], b["y"], b["w"], b["h"]
    s = b["side"]                                  # field goes behind (away from door)
    fw, fh = 6, 4
    if s == "S":
        fx, fy = x, y - fh - 2
    elif s == "N":
        fx, fy = x, y + h + 1
    elif s == "W":
        fx, fy = x + w + 1, y
    else:
        fx, fy = x - fw - 2, y
    if not _area_clear(gm, fx, fy, fw, fh, margin=1):
        return
    for xx in range(fx - 1, fx + fw + 1):
        for yy in range(fy - 1, fy + fh + 1):
            edge = xx in (fx - 1, fx + fw) or yy in (fy - 1, fy + fh)
            gm.tiles[xx, yy] = tile.FENCE if edge else tile.TILLED
    gate = (fx + fw // 2, fy - 1 if s != "N" else fy + fh)
    gm.tiles[gate] = tile.GRASS
    placed.append((fx - 1, fy - 1, fw + 2, fh + 2))
    spring = crops_in_season("Spring") or []
    for xx in range(fx, fx + fw):
        for yy in range(fy, fy + fh):
            gm.village_fields.append((xx, yy))
            if spring and rng.random() < 0.8:
                crop = rng.choice(spring)
                gm.crops[(xx, yy)] = CropPlot(crop=crop,
                                              days_grown=rng.randint(0, crop.days_to_mature),
                                              watered=True)


def _build_garden(gm: GameMap, b: dict, rng, placed: list) -> None:
    """A small fenced kitchen-garden of leafy greens on whichever side of a
    cottage has open ground."""
    x, y, w, h = b["x"], b["y"], b["w"], b["h"]
    gw = gh = 3
    options = [(x, y - gh - 1), (x, y + h + 1), (x - gw - 1, y), (x + w + 1, y),
               (x + w - gw, y - gh - 1), (x + w - gw, y + h + 1)]
    rng.shuffle(options)
    for gx, gy in options:
        if not _area_clear(gm, gx, gy, gw, gh, margin=1):
            continue
        for xx in range(gx - 1, gx + gw + 1):
            for yy in range(gy - 1, gy + gh + 1):
                edge = xx in (gx - 1, gx + gw) or yy in (gy - 1, gy + gh)
                if edge:
                    gm.tiles[xx, yy] = tile.FENCE
                else:
                    gm.tiles[xx, yy] = tile.BUSH if rng.random() < 0.7 else tile.TILLED
        gm.tiles[gx + gw // 2, gy + gh] = tile.GRASS       # a little gate
        placed.append((gx - 1, gy - 1, gw + 2, gh + 2))
        return


def _grave_layout(tb: dict, step: tuple):
    """Origin, back-door and gate for a churchyard in direction `step` off the
    chapel wall."""
    x, y, w, h = tb["x"], tb["y"], tb["w"], tb["h"]
    cxm, cym = x + w // 2, y + h // 2
    gw, gh = 9, 7
    if step[0]:                                       # east / west of the chapel
        gx0 = (x + w + 2) if step[0] > 0 else (x - 2 - gw)
        gy0 = cym - gh // 2
        bd = (x + w - 1 if step[0] > 0 else x, min(max(cym + 2, y + 1), y + h - 2))
        gate = (gx0 if step[0] > 0 else gx0 + gw - 1, gy0 + gh // 2)
    else:                                             # north / south
        gy0 = (y + h + 2) if step[1] > 0 else (y - 2 - gh)
        gx0 = cxm - gw // 2
        bd = (min(max(cxm + 2, x + 1), x + w - 2), y + h - 1 if step[1] > 0 else y)
        gate = (gx0 + gw // 2, gy0 if step[1] > 0 else gy0 + gh - 1)
    return gx0, gy0, gw, gh, bd, gate


def _carve_graveyard(gm: GameMap, tb: dict, vx: int, vy: int, placed: list, rng) -> None:
    """A fenced churchyard beside the chapel, joined to it by a back door and a
    short path. Tries the far side first, then whatever side has open ground."""
    behind = {"W": (1, 0), "E": (-1, 0), "S": (0, -1), "N": (0, 1)}[tb["side"]]
    door_step = (-behind[0], -behind[1])
    if behind[0]:
        order = [behind, (0, -1), (0, 1), door_step]
    else:
        order = [behind, (1, 0), (-1, 0), door_step]

    for step in order:
        gx0, gy0, gw, gh, bd, gate = _grave_layout(tb, step)
        if not _area_clear(gm, gx0, gy0, gw, gh, margin=1):
            continue
        for xx in range(gx0 - 1, gx0 + gw + 1):
            for yy in range(gy0 - 1, gy0 + gh + 1):
                edge = xx in (gx0 - 1, gx0 + gw) or yy in (gy0 - 1, gy0 + gh)
                gm.tiles[xx, yy] = tile.FENCE if edge else tile.GRASS
        gm.tiles[gate] = tile.GRASS                    # lychgate facing the chapel
        for xx in range(gx0 + 1, gx0 + gw - 1, 2):
            for yy in range(gy0 + 1, gy0 + gh - 1, 2):
                if rng.random() < 0.75:
                    gm.tiles[xx, yy] = tile.GRAVE
        if gm.in_bounds(*bd) and gm.tiles[bd] == tile.HOUSE_WALL:
            gm.tiles[bd] = tile.DOOR                    # back door to the churchyard
        for cxp in (gate[0] - 2, gate[0] + 2):          # cypress flank the gate
            cyp = gate[1] + step[1]
            if gm.in_bounds(cxp, cyp) and gm.tiles[cxp, cyp] in (tile.GRASS, tile.MEADOW):
                gm.tiles[cxp, cyp] = tile.TREE_SPRUCE
        # the churchyard sits on open grass right behind the chapel — you step
        # from the back door across the grass to the lychgate, no paving needed
        placed.append((gx0 - 1, gy0 - 1, gw + 2, gh + 2))
        return


def _carve_pond_beside(gm: GameMap, b: dict, placed: list):
    """A small pond just behind an inland fisher's cottage, with a grassy bank
    tile between house and water. Returns the bank tile (a fishing spot)."""
    x, y, w, h = b["x"], b["y"], b["w"], b["h"]
    s = b["side"]
    r = 2
    if s == "S":
        bank = (x + w // 2, y - 2); pc = (x + w // 2, y - 5)
    elif s == "N":
        bank = (x + w // 2, y + h + 1); pc = (x + w // 2, y + h + 4)
    elif s == "W":
        bank = (x + w + 1, y + h // 2); pc = (x + w + 4, y + h // 2)
    else:
        bank = (x - 2, y + h // 2); pc = (x - 5, y + h // 2)
    px, py = pc
    if not _area_clear(gm, px - r, py - r, 2 * r + 1, 2 * r + 1, margin=1):
        return None
    for xx in range(px - r, px + r + 1):
        for yy in range(py - r, py + r + 1):
            if (xx - px) ** 2 + (yy - py) ** 2 <= r * r:
                gm.tiles[xx, yy] = tile.WATER
    placed.append((px - r - 1, py - r - 1, 2 * r + 3, 2 * r + 3))
    return bank if (gm.in_bounds(*bank) and gm.walkable(*bank)) else (px, py + r + 1)


def _carve_docks(gm: GameMap, vx: int, vy: int, coast: np.ndarray, rng) -> list:
    """Plank piers reaching from the shore into the sea, with moored boats.
    Returns walkable pier tiles (a fisher's workplace)."""
    piers: list = []
    for px in (vx - 4, vx, vx + 4):
        if not (0 <= px < len(coast)):
            continue
        cyc = int(coast[px])
        for y in range(cyc - 1, cyc + 5):
            if gm.in_bounds(px, y) and gm.tiles[px, y] in (tile.WATER, tile.SAND):
                gm.tiles[px, y] = tile.BRIDGE
                if y >= cyc:
                    piers.append((px, y))
        by = cyc + 5
        bx = px + rng.choice((-1, 1))
        if gm.in_bounds(bx, by) and gm.tiles[bx, by] == tile.WATER:
            gm.tiles[bx, by] = tile.BOAT
    return piers


def _try_building(gm: GameMap, vx: int, vy: int, placed: list,
                  w: int, h: int, ang: float, rad: int) -> dict | None:
    """Place a building near (angle, radius) from the square, nudging outward
    until it fits on open ground clear of roads, water and other structures."""
    import math
    for r in range(rad, rad + 14):
        bxc = vx + int(round(math.cos(ang) * r))
        byc = vy + int(round(math.sin(ang) * r))
        x, y = bxc - w // 2, byc - h // 2
        rect = (x, y, w, h)
        if any(_overlap(rect, p, 2) for p in placed):
            continue
        if not _area_clear(gm, x, y, w, h, margin=1):
            continue
        b = _rect_building(gm, x, y, w, h, _door_toward(bxc, byc, vx, vy))
        placed.append(rect)
        return b
    return None


def _lay_square(gm: GameMap, vx: int, vy: int, R: int, rng) -> list:
    """A cobbled market square with a crossroads high street, well, market cross,
    stalls, lamps and flower beds. Returns walkable cobble tiles (gathering spots)."""
    seats: list = []
    for dx in range(-3, 4):
        for dy in range(-2, 3):
            x, y = vx + dx, vy + dy
            if gm.in_bounds(x, y) and gm.walkable(x, y) and gm.tiles[x, y] not in (
                    tile.WATER, tile.RIVER, tile.SAND):
                gm.tiles[x, y] = tile.COBBLE
                seats.append((x, y))
    # Country roads and building lanes braid into the square on their own, so we
    # don't lay fixed arms (they used to dangle as dead-end stubs at the edge).
    # square furniture, kept off the cardinal through-lines
    for (dx, dy), tid in (((-2, -1), tile.WELL), ((2, 1), tile.STATUE),
                          ((-2, 1), tile.STALL), ((2, -1), tile.STALL)):
        x, y = vx + dx, vy + dy
        if gm.in_bounds(x, y) and gm.tiles[x, y] == tile.COBBLE:
            gm.tiles[x, y] = tid
    for dx, dy in ((-3, -2), (3, -2), (-3, 2), (3, 2)):
        x, y = vx + dx, vy + dy
        if gm.in_bounds(x, y) and gm.tiles[x, y] in (tile.COBBLE, tile.GRASS):
            gm.tiles[x, y] = tile.LAMP
    # Flower beds about the square — recorded as spots so they bloom with the
    # seasons alongside the wild meadows (bare in autumn/winter).
    for _ in range(rng.randint(12, 20)):
        fx, fy = vx + rng.randint(-R, R), vy + rng.randint(-R, R)
        if gm.in_bounds(fx, fy) and gm.tiles[fx, fy] == tile.GRASS:
            col = rng.choice((tile.FLOWER_RED, tile.FLOWER_YELLOW,
                              tile.FLOWER_VIOLET, tile.FLOWER_WHITE))
            gm.flower_spots.append((fx, fy, int(col), int(tile.GRASS)))
    return [s for s in seats if gm.tiles[s] == tile.COBBLE]


def _carve_villages(gm: GameMap, seed: int, coast: np.ndarray) -> dict:
    import math
    cx, cy = C.WORLD_CENTER
    groups = content.village_npcs()

    salt_x = cx - 30
    salt_cy = int(coast[salt_x]) if 0 <= salt_x < len(coast) else int(cy + 150)
    sites = {
        "Mossford":   (cx + 150, cy - 70, False),          # farming hamlet, NE
        "Cinderhope": (cx - 165, cy + 55, False),          # mining outpost, SW
        "Saltmere":   (salt_x, salt_cy - 22, True),        # fishing village on the coast
    }
    centers: dict = {}

    for name, (vx, vy, coastal) in sites.items():
        rng = random.Random((sum(ord(c) for c in name) * 9173 + seed) & 0x7FFFFFFF)
        R = 16 if coastal else 21

        # 1. organic clearing
        ph = [rng.uniform(0, 6.28) for _ in range(3)]
        for x in range(vx - R - 2, vx + R + 3):
            for y in range(vy - R - 2, vy + R + 3):
                if not gm.in_bounds(x, y) or gm.tiles[x, y] in (tile.WATER, tile.RIVER, tile.SAND):
                    continue
                dx, dy = x - vx, y - vy
                ang = math.atan2(dy, dx)
                rr = R * (0.76 + 0.11 * math.sin(ang * 2 + ph[0])
                          + 0.09 * math.sin(ang * 3 + ph[1])
                          + 0.06 * math.sin(ang * 5 + ph[2]))
                if dx * dx + dy * dy <= rr * rr:
                    gm.tiles[x, y] = tile.GRASS

        # 2. cobbled square + high street
        square_seats = _lay_square(gm, vx, vy, R, rng)

        # 3. buildings by role. Off-cardinal angles keep them clear of the arms.
        npcs = list(groups.get(name, []))
        roles = {n.role for n in npcs}
        placed: list = []
        buildings: dict = {}
        farmhouses: list = []
        cottages: list = []
        fisher_home = None
        fisher_bank = None

        def build(kind, tag, w, h, ang, rad):
            b = _try_building(gm, vx, vy, placed, w, h, ang, rad)
            if b is None:
                return None
            anchors = _furnish(gm, b, tag, rng)
            _draw_road(gm, b["front"], (vx, vy))
            b["kind"] = kind
            b["village"] = name
            b["owner"] = None
            gm.buildings.append(b)
            return (b, anchors)

        if "innkeeper" in roles:
            buildings["inn"] = build("inn", "inn", rng.randint(10, 12), rng.randint(7, 8),
                                     -math.pi * 0.5 + 0.4, 10)
        if "priest" in roles:
            buildings["temple"] = build("temple", "temple", 9, rng.randint(9, 11), 0.28, 12)
            if buildings["temple"]:
                _carve_graveyard(gm, buildings["temple"][0], vx, vy, placed, rng)
        if "shopkeeper" in roles:
            buildings["shop"] = build("shop", "shop", rng.randint(8, 10), rng.randint(7, 8),
                                      math.pi - 0.3, 12)
        if "blacksmith" in roles:
            sm = build("smithy", "house", 7, 6, math.pi * 0.72, 12)
            buildings["smithy"] = sm
            if sm:                                     # a separate forge outbuilding
                forge = _build_forge(gm, sm[0], placed, name, rng)
                if forge:
                    buildings["forge"] = forge

        # a waterside cottage for an inland fisher: build it, then set a pond
        # right behind it so the fisher lives and works by the water
        if not coastal and "fisher" in roles:
            fh = build("cottage", "house", 7, 6, math.pi * 1.25, 14)
            if fh:
                fisher_home = fh
                fisher_bank = _carve_pond_beside(gm, fh[0], placed)
                _build_garden(gm, fh[0], rng, placed)

        # farmhouses — one per farmer, with a field behind
        n_farm = sum(1 for n in npcs if n.role == "farmer")
        farm_angles = (math.pi * 0.5, math.pi * 0.35, math.pi * 0.62)
        for i in range(n_farm):
            fb = build("farmhouse", "house", rng.randint(7, 9), 6,
                       farm_angles[i % len(farm_angles)], 18)
            if fb:
                _build_field(gm, fb[0], rng, placed)
                farmhouses.append(fb)

        # cottages for everyone else, plus a couple spare for size
        already = 1 if fisher_home else 0
        n_cottage = sum(1 for n in npcs if n.role not in
                        ("innkeeper", "priest", "shopkeeper", "blacksmith", "farmer")) + 2 - already
        cot_angles = [math.pi * a for a in (0.28, 0.72, 1.28, 1.72, 0.12, 0.88, 1.12, 1.55)]
        for i in range(max(0, n_cottage)):
            cb = build("cottage", "house", rng.randint(7, 9), rng.randint(6, 7),
                       cot_angles[i % len(cot_angles)], 14)
            if cb:
                if rng.random() < 0.7:
                    _build_garden(gm, cb[0], rng, placed)
                cottages.append(cb)

        piers = _carve_docks(gm, vx, vy, coast, rng) if coastal else []

        # 4. assign residents to buildings and daytime anchors
        temple_seats = buildings.get("temple") and buildings["temple"][1].get("seats") or []
        inn_seats = buildings.get("inn") and buildings["inn"][1].get("seats") or []
        cot_iter = iter(cottages)
        farm_iter = iter(farmhouses)
        si = 0

        def gather(seats, i):
            return seats[i % len(seats)] if seats else None

        for i, npc in enumerate(npcs):
            home = work = None; owner_b = None
            if npc.role == "innkeeper" and buildings.get("inn"):
                b, a = buildings["inn"]; home = a["home"]; work = gather(inn_seats, 0); owner_b = b
            elif npc.role == "priest" and buildings.get("temple"):
                b, a = buildings["temple"]; home = a["home"]; work = a["work"]; owner_b = b
            elif npc.role == "shopkeeper" and buildings.get("shop"):
                b, a = buildings["shop"]; home = a["home"]; work = a["work"]; owner_b = b
            elif npc.role == "blacksmith" and buildings.get("smithy"):
                b, a = buildings["smithy"]; home = a["home"]; owner_b = b
                work = buildings["forge"][0]["front"] if buildings.get("forge") else a["work"]
            elif npc.role == "farmer":
                fb = next(farm_iter, None)
                if fb:
                    home = fb[1]["home"]; work = fb[0]["front"]; owner_b = fb[0]
            elif npc.role == "fisher" and fisher_home:
                home = fisher_home[1]["home"]; work = fisher_bank or fisher_home[0]["front"]
                owner_b = fisher_home[0]
            if home is None:
                cb = next(cot_iter, None)
                if cb:
                    home = cb[1]["home"]; work = cb[0]["front"]; owner_b = cb[0]
            if home is None:
                home = work = (vx, vy)
            if npc.role == "fisher" and piers:      # coastal fishers work the piers
                work = piers[si % len(piers)]
            if owner_b is not None and owner_b.get("kind") in ("cottage", "farmhouse"):
                owner_b["owner"] = npc.name         # so 'look' can name the house
            npc.home = home
            npc.work = work or home
            npc.village = name
            npc.spots = {
                "home": npc.home,
                "work": npc.work,
                "inn": gather(inn_seats, i + 1) or npc.home,
                "temple": gather(temple_seats, i) or npc.work,
                "square": gather(square_seats, i * 2) or npc.work,
            }
            npc.x, npc.y = npc.work
            gm.npcs.append(npc)
            si += 1

        centers[name] = (vx, vy)

    return centers


def _build_forge(gm: GameMap, house_b: dict, placed: list, village: str, rng):
    """A small forge outbuilding beside the blacksmith's house."""
    x, y, w, h = house_b["x"], house_b["y"], house_b["w"], house_b["h"]
    fw, fh = 5, 4
    for sx, sy in ((x + w + 2, y), (x - fw - 2, y), (x, y + h + 2), (x, y - fh - 2)):
        if not _area_clear(gm, sx, sy, fw, fh, margin=1):
            continue
        if any(_overlap((sx, sy, fw, fh), p, 2) for p in placed):
            continue
        side = _door_toward(sx + fw // 2, sy + fh // 2, x + w // 2, y + h // 2)
        b = _rect_building(gm, sx, sy, fw, fh, side)
        keep = _keep_clear(b, None)
        _furnish_room(gm, (sx + 1, sy + 1, sx + fw - 2, sy + fh - 2),
                      [(tile.HEARTH, 1), (tile.BARREL, 1), (tile.TABLE, 1)], rng, keep)
        b["kind"] = "smithy"; b["village"] = village; b["owner"] = None
        gm.buildings.append(b)
        placed.append((sx, sy, fw, fh))
        _draw_road(gm, b["front"], house_b["front"])
        return (b, {"home": b["inner"], "work": b["front"], "seats": _interior_floor(gm, b)})
    return None


_FOREST_OK = {"grass", "meadow", "tall_grass", "fog_grass", "moor", "bush",
              "shrub", "shrub_raspberry", "shrub_gooseberry", "shrub_currant",
              "oak", "maple", "birch", "poplar", "willow", "pine", "spruce", "foliage",
              "red flowers", "yellow flowers", "violet flowers", "white flowers",
              "button_mushroom", "parasol_mushroom", "bolete", "chanterelle"}


def _carve_forest(gm: GameMap, seed: int):
    """A large, dense wildwood in the NW, with a forester's hut in a clearing at
    its heart. Returns the hut's doorstep (to link by a forest track), or None."""
    import math
    from ..data import content
    rng = random.Random((seed + 4242) & 0x7FFFFFFF)
    cx, cy = C.WORLD_CENTER
    fx, fy = cx - 150, cy - 140                      # NW quarter, clear of the villages
    R = 42
    ph = [rng.uniform(0, 6.28) for _ in range(3)]
    trees = (tile.TREE_OAK, tile.TREE_MAPLE, tile.TREE_BIRCH, tile.TREE_POPLAR,
             tile.TREE_WILLOW, tile.TREE_PINE, tile.TREE_SPRUCE)
    clearings, tree_cells = [], []
    for x in range(fx - R - 2, fx + R + 3):
        for y in range(fy - R - 2, fy + R + 3):
            if not gm.in_bounds(x, y) or tile.TILES[gm.tiles[x, y]].name not in _FOREST_OK:
                continue
            dx, dy = x - fx, y - fy
            ang = math.atan2(dy, dx)
            rr = R * (0.72 + 0.14 * math.sin(ang * 2 + ph[0])
                      + 0.10 * math.sin(ang * 3 + ph[1])
                      + 0.06 * math.sin(ang * 5 + ph[2]))
            if dx * dx + dy * dy > rr * rr:
                continue
            r = rng.random()
            if r < 0.58:
                gm.tiles[x, y] = rng.choice(trees)   # dense canopy (walkable)
                tree_cells.append((x, y))
            elif r < 0.70:
                gm.tiles[x, y] = tile.FOLIAGE        # impassable thickets
            elif r < 0.77:
                gm.tiles[x, y] = tile.SHRUB
            else:
                gm.tiles[x, y] = tile.GRASS          # a clearing
                clearings.append((x, y))
    # rare wild bee hives up in the trees (well away from the hut)
    rng.shuffle(tree_cells)
    for x, y in tree_cells:
        if (x - fx) ** 2 + (y - fy) ** 2 < 10 ** 2:  # keep the hut clearing clear
            continue
        gm.tiles[x, y] = tile.WILD_HIVE
        if sum(1 for c in tree_cells if gm.tiles[c] == tile.WILD_HIVE) >= rng.randint(4, 6):
            break
    # seasonal forest mushrooms scattered through the clearings
    for x, y in clearings:
        if rng.random() < 0.08:
            species = tile.CHANTERELLE if rng.random() < 0.5 else tile.BOLETE
            gm.mushroom_spots.append((x, y, int(species), int(tile.GRASS)))

    # open a clearing and raise the forester's hut at the heart of the wood
    for x in range(fx - 4, fx + 5):
        for y in range(fy - 4, fy + 5):
            if gm.in_bounds(x, y) and tile.TILES[gm.tiles[x, y]].name in _FOREST_OK:
                gm.tiles[x, y] = tile.GRASS
    hut = _rect_building(gm, fx - 2, fy - 2, 5, 5, "S")
    anchors = _furnish(gm, hut, "house", rng)
    hut["kind"] = "hut"
    hut["village"] = "Wildwood"
    hut["owner"] = None
    gm.buildings.append(hut)
    # a woodpile by the door for flavour
    px, py = hut["front"][0] + 1, hut["front"][1]
    if gm.in_bounds(px, py) and gm.tiles[px, py] == tile.GRASS:
        gm.tiles[px, py] = tile.BARREL

    for npc in content.solo_npcs():
        npc.home = anchors["home"]
        npc.work = hut["front"] if gm.walkable(*hut["front"]) else anchors["home"]
        npc.village = "Wildwood"
        npc.spots = {"home": npc.home, "work": npc.work}
        npc.x, npc.y = npc.work
        hut["owner"] = npc.name
        gm.npcs.append(npc)
    return hut["front"]


def _carve_homestead(gm: GameMap, seed: int) -> None:
    cx, cy = C.WORLD_CENTER
    t = gm.tiles

    # 1. clearing
    R = 16
    for x in range(cx - R, cx + R + 1):
        for y in range(cy - R, cy + R + 1):
            if not gm.in_bounds(x, y):
                continue
            if (x - cx) ** 2 + (y - cy) ** 2 <= R * R:
                # don't pave over the river running through home
                if t[x, y] not in (tile.RIVER, tile.SAND):
                    t[x, y] = tile.GRASS

    # 2. house: kept EAST of the river (which meanders the clearing's west side)
    #    so building it never severs the river — roads must then bridge it.
    hx, hy, hw, hh = cx + 2, cy - 7, 6, 5
    for x in range(hx, hx + hw):
        for y in range(hy, hy + hh):
            if not gm.in_bounds(x, y) or t[x, y] in (tile.RIVER, tile.SAND):
                continue
            edge = x in (hx, hx + hw - 1) or y in (hy, hy + hh - 1)
            t[x, y] = tile.HOUSE_WALL if edge else tile.HOUSE_FLOOR
    door = (hx + hw // 2, hy + hh - 1)
    t[door] = tile.DOOR
    bed = (hx + 1, hy + 1)
    t[bed] = tile.BED
    gm.bed = bed

    # 3. shipping bin just outside the door
    bin_pos = (door[0] + 1, door[1] + 1)
    if gm.in_bounds(*bin_pos):
        t[bin_pos] = tile.SHIP_BIN
        gm.bin = bin_pos

    # 4. fenced tilled plot below the house (also east of the river)
    px, py, pw, ph = cx + 2, cy + 1, 6, 5
    for x in range(px - 1, px + pw + 1):
        for y in range(py - 1, py + ph + 1):
            if not gm.in_bounds(x, y):
                continue
            on_edge = x in (px - 1, px + pw) or y in (py - 1, py + ph)
            if on_edge:
                if t[x, y] not in (tile.RIVER, tile.SAND):
                    t[x, y] = tile.FENCE
    # plot gate
    t[px + pw // 2, py - 1] = tile.GRASS
    for x in range(px, px + pw):
        for y in range(py, py + ph):
            if gm.in_bounds(x, y) and t[x, y] not in (tile.RIVER, tile.SAND):
                t[x, y] = tile.TILLED

    # 5. spawn just below the door, on walkable ground
    sx, sy = door[0], door[1] + 1
    if not gm.walkable(sx, sy):
        sx, sy = cx, cy
    gm.spawn = (sx, sy)


def _place_dungeons(gm: GameMap, wild: np.ndarray, flora: np.ndarray) -> None:
    """Drop two dungeon entrances: a mine (rocky T2/T3) and a woodland grotto."""
    t = gm.tiles
    cx, cy = C.WORLD_CENTER

    def find(pred, prefer_far=True):
        ys, xs = np.where(pred)
        if len(xs) == 0:
            return None
        d = (xs - cx) ** 2 + (ys - cy) ** 2
        idx = np.argsort(d)
        order = idx[::-1] if prefer_far else idx
        for i in order:
            x, y = int(xs[i]), int(ys[i])
            if gm.walkable(x, y):
                return x, y
        return None

    # np.where on a (w,h) array returns (x_index, y_index); name accordingly
    mine_mask = (wild >= C.TIER1_MAX) & (flora < 0.30)
    grotto_mask = (wild >= C.TIER1_MAX) & (flora > 0.62)

    for mask, kind in ((mine_mask, "mine"), (grotto_mask, "grotto")):
        xs, ys = np.where(mask)
        if len(xs) == 0:
            continue
        d = (xs - cx) ** 2 + (ys - cy) ** 2
        for i in np.argsort(d):
            x, y = int(xs[i]), int(ys[i])
            # well out into the wilds, with a walkable neighbour to stand on
            if d[i] < (130 ** 2):
                continue
            if any(gm.walkable(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                _carve_dungeon_site(gm, x, y, kind)
                gm.dungeons.append((x, y))
                gm.dungeon_kind[(x, y)] = kind
                break


def _carve_dungeon_site(gm: GameMap, ex: int, ey: int, kind: str) -> None:
    """A small themed clearing around a dungeon mouth: a rocky cave (mine) or
    crumbling ruins (otherwise), with the stairs-down at its heart."""
    import random
    rng = random.Random(ex * 7349 + ey)
    floor = tile.DIRT_PATH if kind == "mine" else tile.RUINS_FLOOR
    boulder = tile.ROCK if kind == "mine" else tile.RUINS_WALL
    R = 4
    for x in range(ex - R, ex + R + 1):
        for y in range(ey - R, ey + R + 1):
            if not gm.in_bounds(x, y):
                continue
            d2 = (x - ex) ** 2 + (y - ey) ** 2
            if d2 > R * R or gm.tiles[x, y] in (tile.RIVER, tile.SAND):
                continue
            gm.tiles[x, y] = floor
            if d2 > (R * R) * 0.5 and (x, y) != (ex, ey):   # scatter on the outer ring
                r = rng.random()
                if r < 0.30:
                    gm.tiles[x, y] = boulder
                elif r < 0.45 and kind == "mine":
                    gm.tiles[x, y] = tile.ORE_VEIN
    gm.tiles[ex, ey] = tile.DUNGEON_DOWN
