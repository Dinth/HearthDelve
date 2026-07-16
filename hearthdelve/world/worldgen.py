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
from ..entities.machine import Machine
from ..data import content

# The generic map-building mechanisms live in worldlib (shared with westgen
# and any future region); this module keeps the Vale's *policy* — its biomes,
# villages, and where the roads run. Imported under the old private names so
# the pipeline below reads unchanged.
from .worldlib import (  # noqa: F401  (some are used by siblings via this module)
    noise_field as _noise_field,
    grow_veins as _grow_veins,
    road_path as _road_path,
    paint_road as _paint_road,
    draw_road as _draw_road,
    fill_road_gaps as _fill_road_gaps,
    weld_road_gaps as _weld_road_gaps,
    thin_roads as _thin_roads,
    gate as _gate,
    branch_through as _branch_through,
    place_waypoints as _place_waypoints,
    ROAD_BLOCK as _ROAD_BLOCK,
    SIGN_ROADS as _SIGN_ROADS,
    NO_BUILD as _NO_BUILD,
    overlap as _overlap,
    door_toward as _door_toward,
    area_clear as _area_clear,
    rect_building as _rect_building,
    interior_floor as _interior_floor,
    partition as _partition,
    put as _put,
    ring_cells as _ring_cells,
    keep_clear as _keep_clear,
    furnish_room as _furnish_room,
    pick_home as _pick_home,
)


# Region ids for the deliberate four-region composition (see generate()).
REG_FOREST, REG_MARSH, REG_HILLS, REG_PLAINS = 0, 1, 2, 3

# Peak extra cost the road-meander ripple adds to open ground. Small next to the
# terrain spread (easy 4 → scree 12) so it nudges a road to wander without ever
# overriding its instinct to hug gentle land and skirt crags.
_ROAD_MEANDER = 0.6


def _wildness(w: int, h: int, seed: int) -> np.ndarray:
    cx, cy = w / 2.0, h / 2.0
    yy, xx = np.meshgrid(np.arange(h), np.arange(w))  # both (w, h)
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    dist /= dist.max()                                # 0 at center .. 1 at corner
    jitter = _noise_field(seed, w, h, scale=0.035, octaves=3)
    field = 0.78 * dist + 0.22 * jitter
    return np.clip(field, 0.0, 1.0)


def generate(seed: int = 1337) -> GameMap:
    w, h = C.WORLD_W, C.WORLD_H
    cx, cy = C.WORLD_CENTER
    tiles = np.full((w, h), tile.GRASS, dtype=np.uint8)

    wild = _wildness(w, h, seed)
    flora = _noise_field(seed + 7, w, h, scale=0.08, octaves=4)
    detail = _noise_field(seed + 13, w, h, scale=0.20, octaves=2)
    variety = _noise_field(seed + 41, w, h, scale=0.16, octaves=2)   # tree/shrub kind
    rare = _noise_field(seed + 57, w, h, scale=0.55, octaves=1)       # rare-feature mask

    t1 = wild < C.TIER1_MAX                               # gentle homestead belt

    # --- Deliberate regions -------------------------------------------------
    # The Vale is composed of four regions meeting at the homestead: deep wood to
    # the NW, a fen to the NE, rocky hills to the SW (mining country, around
    # Cinderhope) and open plains to the SE. Rather than hard wedges, each region
    # grows from a seed point and claims the ground nearest it, with the boundary
    # ruffled by noise so borders drift and interlock organically.
    off = int(0.30 * w)                                   # region seeds, on the diagonals
    seeds = ((cx - off, cy - off),                        # NW forest
             (cx + off, cy - off),                        # NE marsh
             (cx - off, cy + off),                        # SW hills
             (cx + off, cy + off))                        # SE plains
    yy, xx = np.meshgrid(np.arange(h), np.arange(w))      # both (w, h)
    warp = 0.16 * w                                       # how far noise bends a border
    dsets = []
    for i, (sx, sy) in enumerate(seeds):
        nz = _noise_field(seed + 601 + i * 6, w, h, scale=0.018, octaves=3)
        dsets.append(np.sqrt((xx - sx) ** 2 + (yy - sy) ** 2) - (nz - 0.5) * warp)
    region = np.argmin(np.stack(dsets, axis=0), axis=0)   # (w, h) region id
    forest = region == REG_FOREST
    marsh = region == REG_MARSH
    hills = region == REG_HILLS
    plains = region == REG_PLAINS

    # Homestead belt — gentle grass & meadow near the centre in every region, so
    # home is green and safe whichever way you first set out.
    tiles[t1] = tile.GRASS
    tiles[t1 & (detail > 0.62)] = tile.MEADOW

    # --- Plains (SE): open farming country — meadow, tall grass, lone trees ----
    p = plains & ~t1
    tiles[p] = tile.MEADOW
    tiles[p & (detail > 0.55)] = tile.TALL_GRASS
    tiles[p & (flora > 0.62) & (detail > 0.30) & (detail < 0.38)] = tile.GRASS
    lone = p & (flora > 0.60) & (detail > 0.68)                 # scattered lone trees
    tiles[lone & (variety < 0.33)] = tile.TREE_OAK
    tiles[lone & (variety >= 0.33) & (variety < 0.66)] = tile.TREE_MAPLE
    tiles[lone & (variety >= 0.66)] = tile.TREE_BIRCH

    # --- Forest (NW): dense woodland, thickening with wildness ----------------
    f = forest & ~t1
    tiles[f] = tile.GRASS
    treemask = f & (detail > 0.36 - (wild - C.TIER1_MAX) * 0.3)  # denser deeper in
    tiles[treemask & (variety < 0.18)] = tile.TREE_OAK
    tiles[treemask & (variety >= 0.18) & (variety < 0.34)] = tile.TREE_MAPLE
    tiles[treemask & (variety >= 0.34) & (variety < 0.50)] = tile.TREE_BIRCH
    tiles[treemask & (variety >= 0.50) & (variety < 0.66)] = tile.TREE_POPLAR
    tiles[treemask & (variety >= 0.66) & (variety < 0.80)] = tile.TREE_WILLOW
    tiles[treemask & (variety >= 0.80) & (detail > 0.5)] = tile.TREE_PINE
    tiles[treemask & (variety >= 0.80) & (detail <= 0.5)] = tile.TREE_SPRUCE
    tiles[f & (flora > 0.68) & (detail > 0.58)] = tile.FOLIAGE   # impassable thickets

    # --- Hills (SW): rocky upland, mining country around Cinderhope -----------
    hl = hills & ~t1
    tiles[hl] = tile.HILL
    tiles[hl & (detail > 0.42) & (detail < 0.52)] = tile.SCREE   # loose stone
    tiles[hl & (detail >= 0.60)] = tile.ROCK                     # crags & outcrops
    conif_hill = hl & (flora > 0.50) & (detail > 0.28) & (detail < 0.40)
    tiles[conif_hill & (variety < 0.5)] = tile.TREE_PINE         # hardy slopes
    tiles[conif_hill & (variety >= 0.5)] = tile.TREE_SPRUCE

    # --- Marsh (NE): a soggy fen — reeds, moor and open bog pools -------------
    m = marsh & ~t1
    tiles[m] = tile.MARSH
    tiles[m & (detail > 0.30) & (detail < 0.42)] = tile.MOOR
    tiles[m & (detail >= 0.42) & (detail < 0.48)] = tile.FOG_GRASS
    tiles[m & (flora > 0.50) & (detail > 0.58) & (detail < 0.66)] = tile.REEDS
    tiles[m & (detail >= 0.72)] = tile.WATER                     # bog pools
    tiles[m & (flora > 0.66) & (detail > 0.30) & (detail < 0.36)] = tile.TREE_WILLOW

    # Shrubs: plain shrubs scatter through wood & plains edges; berry shrubs rare.
    shrubland = (forest | plains) & ~t1 & (flora > 0.45)
    shrub_spots = shrubland & (detail > 0.50) & (detail < 0.56)
    tiles[shrub_spots] = tile.SHRUB
    fruit_spots = shrub_spots & (rare > 0.76)              # a touch more berry shrubs
    tiles[fruit_spots & (variety < 0.34)] = tile.SHRUB_RASPBERRY
    tiles[fruit_spots & (variety >= 0.34) & (variety < 0.67)] = tile.SHRUB_GOOSEBERRY
    tiles[fruit_spots & (variety >= 0.67)] = tile.SHRUB_CURRANT

    # Wild mushrooms. Forest species (bolete, chanterelle) grow on the shaded
    # grass under the woods; field species (button, parasol) dot open grass and
    # meadow. We only RECORD the spots here — the day cycle sprouts them in
    # summer/autumn and clears them otherwise (farming._seasonal_flora).
    forest_m = (((tiles == tile.GRASS) & forest) | (tiles == tile.MOOR) | (tiles == tile.FOG_GRASS)) \
        & ~t1 & (flora > 0.5) & (detail > 0.40) & (detail < 0.47)
    field_m = ((tiles == tile.GRASS) | (tiles == tile.MEADOW)) \
        & plains & (flora < 0.40) & (detail > 0.44) & (detail < 0.47)
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

    # Ore: short veins through the hill crags (where ROCK is abundant), plus a
    # scatter of lone gems. Richer than before, matching the larger, hillier map.
    _grow_veins(tiles, w, h, tile.ROCK, ore_veins=34, max_len=7, gems=16,
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
    gm.coast = coast                     # per-column first sea row (salt vs fresh water)
    _carve_homestead(gm, seed)
    centers = _carve_villages(gm, seed, coast)
    _place_dungeons(gm, wild, flora, region, centers)
    forest_track = _carve_forest(gm, seed)
    camp = _carve_camp(gm, seed)                     # woodcutters' camp in the NW wood
    if camp is not None:
        centers["Thornwake Camp"] = camp
    gm.village_centers = dict(centers)
    _scatter_wild_fruit(gm, wild, seed)
    # A gentle low-frequency cost ripple so roads meander a touch across open
    # ground rather than ruling dead-straight lines (see worldlib.road_path).
    gm.road_jitter = (_noise_field(seed + 5077, w, h, 0.06, octaves=2)
                      * _ROAD_MEANDER).astype(np.int16)
    _draw_roads(gm, centers)
    if forest_track is not None:                    # a track links the hut to the network
        _draw_road(gm, forest_track, gm.spawn)
        _fill_road_gaps(gm)
    _thin_roads(gm)                                  # collapse diagonal-fill widenings
    _place_waypoints(gm)
    _populate_wildlife(gm, random.Random(seed + 131))
    return gm


def _scatter_wild_fruit(gm: GameMap, wild: np.ndarray, seed: int) -> None:
    """Scatter wild fruit trees (cherry/peach/apple/orange) through the wilds —
    free fruit to pick in season, like a natural orchard."""
    from ..world.crops import Tree
    rng = random.Random((seed + 321) & 0x7FFFFFFF)
    start_season = C.SEASONS[0]                       # a new game opens in spring
    placed, tries = 0, 0
    while placed < 200 and tries < 24000:
        tries += 1
        x, y = rng.randint(4, gm.width - 5), rng.randint(4, gm.height - 5)
        if wild[x, y] < C.TIER1_MAX:                  # only out in the edge/wilds
            continue
        if gm.tiles[x, y] not in (tile.GRASS, tile.MEADOW, tile.TALL_GRASS):
            continue
        if (x, y) in gm.trees or (x, y) in gm.crops:
            continue
        t = rng.choice(content.TREES)
        gm.tiles[x, y] = tile.GRASS
        # Stagger the opening crop so the wild orchard doesn't all ripen on the
        # same morning: a few days of jitter on when each first bears.
        ri = rng.randint(0, 6)
        in_season = (t.season == start_season)
        gm.trees[(x, y)] = Tree(t.name, t.fruit, t.fruit_color, t.season, t.days_to_mature,
                                age=t.days_to_mature,
                                has_fruit=(in_season and ri == 0), refruit_in=ri)
        placed += 1


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
    count = C.WILDLIFE_CAP
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
        gm.monsters.append(Mob(c.name, c.glyph, c.color, c.hp, c.hp, c.speed, c.behavior, x, y,
                               dv=c.dv, pv=c.pv, to_hit=c.to_hit, dmg=c.dmg,
                               kind="wildlife", diet=c.diet, seasons=c.seasons,
                               inflicts=c.inflicts))
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
        gm.monsters.append(Mob(b.name, b.glyph, b.color, b.hp, b.hp, b.speed, b.behavior, x, y,
                               dv=b.dv, pv=b.pv, to_hit=b.to_hit, dmg=b.dmg,
                               kind="wildlife", diet=b.diet, seasons=b.seasons,
                               inflicts=b.inflicts))
        bears += 1


def _draw_roads(gm: GameMap, centers: dict) -> None:
    hub = gm.spawn                       # the farm sits on the main road
    pts = list(centers.values())
    # One shared network, not a mesh of parallel roads: connect the farm and
    # villages with a minimum spanning tree (Prim's, rooted at the farm). Each
    # place joins via the nearest node already on the network, so roads branch
    # off shared trunks instead of each laying its own line — every village is
    # still reachable, just without the redundant parallel routes a full
    # every-pair mesh produced. Drawn tree-outward so each new road reuses (and
    # merges onto) the roads already laid.
    nodes = [hub] + pts
    in_tree = [0]
    while len(in_tree) < len(nodes):
        best = None
        for i in in_tree:
            for j in range(len(nodes)):
                if j in in_tree:
                    continue
                d = (nodes[i][0] - nodes[j][0]) ** 2 + (nodes[i][1] - nodes[j][1]) ** 2
                if best is None or d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        _draw_road(gm, nodes[j], nodes[i])
        in_tree.append(j)
    # Each dungeon is a spur off the nearest node (a village, or the farm) — one
    # road, so a dungeon tucked beside a village gets a short branch instead of a
    # second long road shadowing that village's trunk all the way to the farm.
    nodes = pts + [hub]
    for d in gm.dungeons:
        near = min(nodes, key=lambda c: (c[0] - d[0]) ** 2 + (c[1] - d[1]) ** 2)
        _draw_road(gm, near, d)
    # The West Pass: the Cinderhope road runs on to the map's western edge,
    # where the Westreach begins (walk off the edge to cross). It ends at a
    # walkable edge cell (the rim is often rock), and — with terrain-aware
    # costs — winds through the hill country rather than cutting a dead line.
    if "Cinderhope" in centers:
        ccx, ccy = centers["Cinderhope"]
        _draw_road(gm, (ccx, ccy), _west_gap(gm, ccy))
    _weld_road_gaps(gm)                  # reconnect diagonal breaks (esp. village squares)
    _fill_road_gaps(gm)


def _west_gap(gm: GameMap, near_y: int) -> tuple[int, int]:
    """The walkable cell on the map's western edge (x=0) nearest row `near_y` —
    the mouth of the West Pass. Falls back to (0, near_y) if the rim is solid."""
    walkable = [y for y in range(gm.height) if gm.walkable(0, y)]
    if not walkable:
        return (0, near_y)
    return (0, min(walkable, key=lambda y: abs(y - near_y)))


# --- building shells & interiors ---------------------------------------------
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
                    gm.village_gardens.append((xx, yy))    # the resident's plot
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
    # The village notice board — first spare corner of the square that took cobble.
    for dx, dy in ((1, -2), (-1, 2), (3, 1), (-3, -1)):
        x, y = vx + dx, vy + dy
        if gm.in_bounds(x, y) and gm.tiles[x, y] == tile.COBBLE:
            gm.tiles[x, y] = tile.NOTICE_BOARD
            break
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
    h = gm.height
    groups = content.village_npcs()

    salt_x = cx - 20
    salt_cy = int(coast[salt_x]) if 0 <= salt_x < len(coast) else int(h * 0.82)
    sites = {
        "Mossford":   (cx + 300, cy + 205, False),         # farming town, SE plains
        "Cinderhope": (cx - 300, cy + 215, False),         # mining outpost, SW hills
        "Saltmere":   (salt_x, salt_cy - 10, True),        # fishing village on the south coast
        "Fenwick":    (cx + 250, cy - 230, False),         # fen hamlet, NE marsh
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
    fx, fy = cx - 320, cy - 300                      # deep in the NW wood, past the village
    R = 78
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


def _carve_camp(gm: GameMap, seed: int):
    """A woodcutters' camp in the NW wood: canvas tents ringed round a campfire
    in a small rough clearing — no houses, gardens or shops. The folk work the
    wood by day and gather at the fire come evening. Returns the fireside spot
    (to hook into the road network), or None if the wood left no room."""
    import math
    rng = random.Random((seed + 5150) & 0x7FFFFFFF)
    cx, cy = C.WORLD_CENTER
    fx, fy = cx - 250, cy - 215                       # forest, nearer than the deep hut
    R = 9

    # a rough, organic clearing hacked out of the trees
    ph = [rng.uniform(0, 6.28) for _ in range(3)]
    for x in range(fx - R - 1, fx + R + 2):
        for y in range(fy - R - 1, fy + R + 2):
            if not gm.in_bounds(x, y) or tile.TILES[gm.tiles[x, y]].name not in _FOREST_OK:
                continue
            dx, dy = x - fx, y - fy
            ang = math.atan2(dy, dx)
            rr = R * (0.78 + 0.12 * math.sin(ang * 2 + ph[0]) + 0.08 * math.sin(ang * 3 + ph[1]))
            if dx * dx + dy * dy <= rr * rr:
                gm.tiles[x, y] = tile.GRASS
    if not gm.walkable(fx, fy):
        return None

    # the campfire at the heart, a couple of supply barrels beside it
    gm.tiles[fx, fy] = tile.CAMPFIRE
    for bx, by in ((fx + 2, fy), (fx - 2, fy + 1)):
        if gm.in_bounds(bx, by) and gm.tiles[bx, by] == tile.GRASS:
            gm.tiles[bx, by] = tile.BARREL
    fire_seat = next(((fx + dx, fy + dy) for dx, dy in ((0, 1), (1, 0), (-1, 0), (0, -1))
                      if gm.walkable(fx + dx, fy + dy)), (fx, fy))

    # tents ringed round the fire; each woodcutter sleeps at their tent door,
    # works the wood by day, and drifts back to the fire in the evening (their
    # inn/square/temple anchors all resolve to the fireside).
    npcs = content.camp_npcs()
    for i, npc in enumerate(npcs):
        a = 2 * math.pi * i / max(1, len(npcs)) + 0.4
        tent = None
        for r in (R - 3, R - 4, R - 2, R - 5):        # step inward to find open grass
            tx = int(round(fx + r * math.cos(a)))
            ty = int(round(fy + r * math.sin(a)))
            if gm.in_bounds(tx, ty) and gm.tiles[tx, ty] == tile.GRASS:
                tent = (tx, ty)
                break
        if tent is None:
            continue
        tx, ty = tent
        gm.tiles[tx, ty] = tile.TENT
        # doorstep faces the fire, on walkable ground
        sx = tx + ((fx > tx) - (fx < tx))
        sy = ty + ((fy > ty) - (fy < ty))
        door = next((c for c in ((sx, ty), (tx, sy), (sx, sy)) if gm.walkable(*c)), fire_seat)
        work = _camp_work_spot(gm, fx, fy, R, rng) or fire_seat
        npc.home, npc.work, npc.village = door, work, "Thornwake Camp"
        npc.spots = {"home": door, "work": work, "inn": fire_seat,
                     "temple": fire_seat, "square": fire_seat}
        npc.x, npc.y = work
        gm.buildings.append({"x": tx, "y": ty, "w": 1, "h": 1, "kind": "tent",
                             "village": "Thornwake Camp", "owner": npc.name,
                             "front": door, "inner": door, "door": (tx, ty)})
        gm.npcs.append(npc)
    return fire_seat


def _camp_work_spot(gm: GameMap, fx: int, fy: int, R: int, rng) -> tuple | None:
    """A walkable spot toward the edge of the camp clearing — where a woodcutter
    stands to their day's work."""
    import math
    for _ in range(30):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(R - 2, R)
        x, y = int(round(fx + r * math.cos(a))), int(round(fy + r * math.sin(a)))
        if gm.walkable(x, y) and gm.tiles[x, y] == tile.GRASS:
            return (x, y)
    return None


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
    #    On unlucky seeds the meander swings east across the footprint, which
    #    would punch river-holes in the walls and strand the spawn on water. So
    #    first scan the actual tiles across the whole homestead y-span, find the
    #    river's east-most x, and if the plot's west edge (fence at cx+1) isn't
    #    clear of it, shove the WHOLE homestead east by a matching offset.
    hw, hh, pw, ph = 6, 5, 6, 5
    y_top = cy - 7 - 2                                 # house top, with margin
    y_bot = cy + 1 + ph + 1 + 2                        # plot + fence, with margin
    river_max_x = -1
    for x in range(cx, gm.width):
        for y in range(y_top, y_bot + 1):
            if gm.in_bounds(x, y) and t[x, y] == tile.RIVER:
                river_max_x = max(river_max_x, x)
    offset = 0
    west_edge = cx + 1                                 # left fence of the plot
    if river_max_x >= 0 and west_edge <= river_max_x + 2:
        offset = (river_max_x + 2) - west_edge + 1
    # keep the shifted footprint (plot fence reaches cx+2+pw) inside bounds
    offset = max(0, min(offset, gm.width - 2 - (cx + 2 + pw)))
    hcx = cx + offset

    hx, hy = hcx + 2, cy - 7
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

    # A storage chest in the corner of the farmhouse — a place to stash a haul
    # so you're not carrying your whole life (see game.encumbrance).
    chest = (hx + hw - 2, hy + 1)
    if gm.in_bounds(*chest) and t[chest] == tile.HOUSE_FLOOR:
        gm.machines[chest] = Machine(kind="chest")

    # 3. shipping bin just outside the door, and a post box on the other side
    bin_pos = (door[0] + 1, door[1] + 1)
    if gm.in_bounds(*bin_pos):
        t[bin_pos] = tile.SHIP_BIN
        gm.bin = bin_pos
    box_pos = (door[0] - 1, door[1] + 1)
    if gm.in_bounds(*box_pos) and t[box_pos] not in (tile.RIVER, tile.SAND):
        t[box_pos] = tile.POST_BOX
        gm.post_box = box_pos

    # 4. fenced tilled plot below the house (also east of the river)
    px, py = hcx + 2, cy + 1
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

    # 5. spawn just below the door, on walkable ground. If that tile is blocked
    #    (a stray river/sand), search outward in expanding rings for the nearest
    #    walkable spot rather than blindly dropping the player on (cx, cy).
    sx, sy = door[0], door[1] + 1
    if not gm.walkable(sx, sy):
        sx, sy = None, None
        for r in range(1, 32):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:     # ring perimeter only
                        continue
                    x, y = door[0] + dx, door[1] + 1 + dy
                    if gm.walkable(x, y):
                        sx, sy = x, y
                        break
                if sx is not None:
                    break
            if sx is not None:
                break
        if sx is None:
            sx, sy = cx, cy
    gm.spawn = (sx, sy)


def _place_dungeons(gm: GameMap, wild: np.ndarray, flora: np.ndarray,
                    region: np.ndarray, centers: dict) -> None:
    """Root a dungeon mouth in each region that suits it: a mine in the rocky
    hills beside Cinderhope, a grotto deep in the NW wood, and a barrow out in
    the fen. Each picks the nearest fitting tile to its anchor (past a small
    stand-off), with a walkable neighbour to descend from."""
    t = gm.tiles
    cx, cy = C.WORLD_CENTER

    _SPREAD = 14        # keep two dungeon mouths from crowding each other

    def _drop(mask, kind, anchor, min_d):
        xs, ys = np.where(mask)          # (w,h) array -> (x_index, y_index)
        if len(xs) == 0:
            return
        ax, ay = anchor
        d = (xs - ax) ** 2 + (ys - ay) ** 2
        for i in np.argsort(d):
            x, y = int(xs[i]), int(ys[i])
            if d[i] < (min_d ** 2):      # a stand-off from the anchor
                continue
            if any(abs(x - ex) + abs(y - ey) < _SPREAD for ex, ey in gm.dungeons):
                continue                 # don't crowd an existing mouth
            if any(gm.walkable(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                _carve_dungeon_site(gm, x, y, kind)
                gm.dungeons.append((x, y))
                gm.dungeon_kind[(x, y)] = kind
                return

    stony = (t == tile.HILL) | (t == tile.SCREE)                     # walkable upland ground
    deep_wood = (region == REG_FOREST) & (wild >= C.TIER2_MAX)       # far in the wildwood
    fen = (region == REG_MARSH) & (wild >= C.TIER2_MAX) \
        & ((t == tile.MARSH) | (t == tile.MOOR) | (t == tile.FOG_GRASS))
    shore = (t == tile.SAND)                                         # the southern beach

    cinder = centers.get("Cinderhope", (cx, cy))
    moss = centers.get("Mossford", (cx, cy))
    salt = centers.get("Saltmere", (cx, cy))
    fenw = centers.get("Fenwick", (cx, cy))
    # More mouths, spread across the Vale — several of each biome's kinds, plus a
    # limestone cavern in the hills, a sunken crypt in the fen, and a sea cave on
    # the shore. Each _drop finds the nearest fitting, uncrowded tile to its
    # anchor; any that can't place simply doesn't (graceful on odd maps).
    _drop(stony, "mine", cinder, min_d=28)                           # the Cinderhope shafts
    _drop(stony, "mine", moss, min_d=34)                             # a second working
    _drop(stony, "cavern", salt, min_d=30)                           # a natural limestone cave
    _drop(deep_wood, "grotto", (cx, cy), min_d=int(0.30 * gm.width))
    _drop(deep_wood, "grotto", moss, min_d=26)                       # a second grotto
    _drop(fen, "barrow", (cx, cy), min_d=int(0.28 * gm.width))
    _drop(fen, "crypt", fenw, min_d=22)                              # a sunken crypt
    _drop(shore, "sea cave", salt, min_d=18)                         # a briny mouth on the coast


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
