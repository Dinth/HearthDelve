"""Drawing: scrolling world viewport, status panel, and message log.

The console is created with ``order="F"`` so all arrays are indexed [x, y],
matching the world map and ``console.print(x, y, ...)``.
"""
from __future__ import annotations

import math
import random

import numpy as np
import tcod.console

from . import constants as C
from . import ui
from ..entities import items
from ..world import tile
from ..game.state import GameState

# Per-tile-id render arrays, built once.
_CH = np.array([ord(t.glyph) for t in tile.TILES], dtype=np.int32)
_FG = np.array([t.fg for t in tile.TILES], dtype=np.uint8)
_BG = np.array([t.bg for t in tile.TILES], dtype=np.uint8)

# Depth & texture: natural ground/veg/stone gets a stable per-tile brightness
# jitter so large flats read as organic texture rather than solid blocks; any
# non-walkable tile acts as an occluder that shades its neighbours (fake AO).
# Water and paved/built surfaces are left crisp (they have their own treatment).
_TEX_KINDS = {"terrain", "soil", "tree", "foliage", "shrub", "shrub_berry",
              "flower", "mushroom", "ore", "gem", "reeds", "wall", "rubble"}
_TEX_BY_ID = np.array([t.kind in _TEX_KINDS and t.name not in ("cobble", "path")
                       for t in tile.TILES], dtype=bool)
_OCCLUDER_BY_ID = np.array([not t.walkable for t in tile.TILES], dtype=bool)

# Tile-id groups that get ambient animation.
_GRASS_IDS = np.array([tile.GRASS, tile.MEADOW, tile.TALL_GRASS, tile.FOG_GRASS, tile.BUSH,
                       tile.FLOWER_RED, tile.FLOWER_YELLOW, tile.FLOWER_VIOLET, tile.FLOWER_WHITE])
_TREE_IDS = np.array([tile.TREE_OAK, tile.TREE_MAPLE, tile.TREE_BIRCH, tile.TREE_POPLAR,
                      tile.TREE_WILLOW, tile.TREE_PINE, tile.TREE_SPRUCE, tile.FOLIAGE])
_WATER_IDS = np.array([tile.WATER, tile.RIVER])
_ORE_IDS = np.array([tile.ORE_VEIN])


def _biome_group(t) -> int:
    """Coarse terrain family, for feathering seams between them. -1 = built or
    special (roads, houses, lava…): those keep crisp edges."""
    if t.kind == "water":
        return 2
    if t.kind == "sand" or t.name == "sand":
        return 1
    if t.kind == "tree":
        return 3
    if t.kind == "wall" or t.name in ("rock", "scree", "cliff", "ruins_wall"):
        return 4
    if t.kind in ("terrain", "soil", "foliage", "shrub", "shrub_berry", "flower",
                  "mushroom", "moor", "marsh", "reeds"):
        return 0
    return -1


_BIOME_BY_ID = np.array([_biome_group(t) for t in tile.TILES], dtype=np.int8)
# gem glitter colours: red, blue, orange, green, white
_GEM_PALETTE = np.array([[226, 84, 84], [92, 132, 232], [236, 150, 68],
                         [92, 202, 112], [236, 236, 236]], dtype=np.float32)

# --- Seasonal colour ---------------------------------------------------------
# Broadleaf foliage & open ground recolour with the season; conifers stay green.
_SEASON_VEG_IDS = np.array([
    tile.GRASS, tile.MEADOW, tile.TALL_GRASS, tile.FOG_GRASS, tile.BUSH, tile.MOOR,
    tile.FLOWER_RED, tile.FLOWER_YELLOW, tile.FLOWER_VIOLET, tile.FLOWER_WHITE,
    tile.SHRUB, tile.SHRUB_RASPBERRY, tile.SHRUB_GOOSEBERRY, tile.SHRUB_CURRANT,
    tile.TREE_OAK, tile.TREE_MAPLE, tile.TREE_BIRCH, tile.TREE_POPLAR, tile.TREE_WILLOW,
    tile.FOLIAGE, tile.MARSH, tile.REEDS,
])
# Open ground that gets a coat of snow in winter.
_SEASON_GROUND_IDS = np.array([
    tile.GRASS, tile.MEADOW, tile.TALL_GRASS, tile.FOG_GRASS, tile.DIRT_PATH,
    tile.MOOR, tile.SAND, tile.RUINS_FLOOR, tile.BUSH,
    tile.FLOWER_RED, tile.FLOWER_YELLOW, tile.FLOWER_VIOLET, tile.FLOWER_WHITE,
    tile.HILL, tile.SCREE, tile.MARSH,
])
# Per-season channel multiplier laid over the vegetation.
_SEASON_TINT = {
    "Spring": (1.00, 1.05, 0.98),   # fresh, faintly bright green
    "Summer": (0.92, 1.02, 0.78),   # deep, warm green
    "Fall":   (1.20, 0.90, 0.55),   # golds & russets
    "Winter": (0.82, 0.88, 1.00),   # cold and desaturated
}
_SNOW_FG = np.array([206, 216, 232], dtype=np.float32)
_SNOW_BG = np.array([182, 194, 214], dtype=np.float32)


def _apply_season(view, fg, bg, season: str) -> None:
    """Recolour natural terrain for the season (in place). Winter also lays snow
    over open ground and frosts the trees."""
    tint = _SEASON_TINT.get(season)
    if tint is None:
        return
    veg = np.isin(view, _SEASON_VEG_IDS)
    if veg.any():
        mul = np.array(tint, dtype=np.float32)
        fg[veg] *= mul
        bg[veg] *= mul
    if season == "Winter":
        ground = np.isin(view, _SEASON_GROUND_IDS)
        if ground.any():
            fg[ground] = fg[ground] * 0.35 + _SNOW_FG * 0.65
            bg[ground] = bg[ground] * 0.30 + _SNOW_BG * 0.70
        frost = np.isin(view, _TREE_IDS)           # snow dusts the canopies
        if frost.any():
            fg[frost] = fg[frost] * 0.6 + _SNOW_FG * 0.4


def _hash01(a, b):
    """Stable pseudo-random value in [0, 1) per (a, b) — the classic
    shader hash. Used to desync per-tile ore twinkles."""
    v = np.sin(a.astype(np.float64) * 127.1 + b.astype(np.float64) * 311.7) * 43758.5453
    return v - np.floor(v)


def _glow_from(view: np.ndarray, ids: tuple, rad: int, sigma2: float) -> np.ndarray:
    """A soft radial glow field (0..1) pooled around every tile in `ids` — the
    warm light a lamp, hearth, brazier or lava throws onto what's near it."""
    glow = np.zeros(view.shape, np.float32)
    for lx, ly in np.argwhere(np.isin(view, ids)):
        x0, x1 = max(0, lx - rad), min(view.shape[0], lx + rad + 1)
        y0, y1 = max(0, ly - rad), min(view.shape[1], ly + rad + 1)
        sx = (np.arange(x0, x1) - lx)[:, None].astype(np.float32)
        sy = (np.arange(y0, y1) - ly)[None, :].astype(np.float32)
        bump = np.exp(-(sx * sx + sy * sy) / sigma2)
        glow[x0:x1, y0:y1] = np.maximum(glow[x0:x1, y0:y1], bump)
    return glow


_DUNGEON_WARM_IDS = (tile.LAMP, tile.CAMPFIRE, tile.HEARTH, tile.LAVA, tile.BRAZIER)


def _blur5(f: np.ndarray) -> np.ndarray:
    """A gentle 4-neighbour blur (weights .5 centre, .125 each side) that rubs
    out the hard cell-grid edges so steam reads as cloud, not squares."""
    out = f * 0.5
    out[1:, :] += 0.125 * f[:-1, :]
    out[:-1, :] += 0.125 * f[1:, :]
    out[:, 1:] += 0.125 * f[:, :-1]
    out[:, :-1] += 0.125 * f[:, 1:]
    return out


def _h1(i: int, s: float) -> float:
    """A stable scalar hash in [0, 1) — for per-source particle phases."""
    v = math.sin(i * 12.9898 + s * 78.233) * 43758.5453
    return v - math.floor(v)


def _shift2d(a: np.ndarray, sx: int, sy: int) -> np.ndarray:
    """A copy of `a` translated by (sx, sy), vacated cells left at zero (no
    wrap). Used to stack a rising, drifting steam plume off the caldera."""
    out = np.zeros_like(a)
    xw, yw = a.shape[0] - abs(sx), a.shape[1] - abs(sy)
    if xw <= 0 or yw <= 0:
        return out
    xs_, xd_ = (0, sx) if sx >= 0 else (-sx, 0)
    ys_, yd_ = (0, sy) if sy >= 0 else (-sy, 0)
    out[xd_:xd_ + xw, yd_:yd_ + yw] = a[xs_:xs_ + xw, ys_:ys_ + yw]
    return out


# Per-channel light multiplier across the day: cool/dim at night, warm at
# dawn & dusk, neutral-bright at midday. Keyframes are (minute-of-day, rgb-mul).
_LIGHT_KEYS = [
    (0,    (0.50, 0.58, 0.80)),   # deep night (blue)
    (300,  (0.50, 0.58, 0.80)),   # 05:00
    (390,  (1.02, 0.86, 0.74)),   # 06:30 dawn (warm)
    (480,  (1.00, 1.00, 1.00)),   # 08:00 full day
    (1020, (1.00, 1.00, 1.00)),   # 17:00
    (1140, (1.03, 0.80, 0.66)),   # 19:00 dusk (warm)
    (1260, (0.50, 0.58, 0.80)),   # 21:00 night
    (1440, (0.50, 0.58, 0.80)),
]


def daylight_mul(time_minutes: int) -> tuple[float, float, float]:
    m = time_minutes % 1440
    for (m0, c0), (m1, c1) in zip(_LIGHT_KEYS, _LIGHT_KEYS[1:]):
        if m0 <= m <= m1:
            f = (m - m0) / (m1 - m0) if m1 > m0 else 0.0
            return tuple(c0[j] + (c1[j] - c0[j]) * f for j in range(3))
    return (1.0, 1.0, 1.0)


def sun_shadow(time_minutes: int):
    """The sun's cast-shadow this minute: (dir_x, dir_y, length, strength). The
    sun rises in the east and sets in the west, so shadows sweep from west
    (dawn) to east (dusk) and stretch long near the horizon, short at noon.
    Returns None while the sun is down (night lighting takes over)."""
    f = (time_minutes % 1440) / 1440.0
    midday, span = 0.55, 0.30                 # ~13:12; daylight roughly 05:40–21:40
    elev = 1.0 - abs(f - midday) / span
    if elev <= 0.04:
        return None
    dir_x = max(-1.0, min(1.0, (f - midday) / span))   # -1 dawn (west) → +1 dusk (east)
    length = int(round(1 + (1.0 - elev) * 4))          # 1 at noon … 5 near horizon
    strength = 0.18 + 0.30 * (1.0 - elev)              # faint at noon, long & soft at the edges
    return dir_x, 0.35, length, strength


_WEATHER_ICON = {
    "Clear": ("☀", (245, 214, 110)),
    "Cloudy": ("☁", (190, 194, 200)),
    "Rain":  ("☂", (150, 180, 225)),
    "Storm": ("⚡", (232, 220, 120)),
    "Fog":   ("≈", (182, 186, 192)),
    "Snow":  ("❄", (225, 235, 245)),
}


def camera_origin(state: GameState) -> tuple[int, int]:
    """Top-left world cell shown in the viewport, clamped to world bounds.

    Normally centred on the player; in look/aim modes it follows ``cam_focus``
    so the cursor can roam past the edge of where the player stands."""
    w = state.world
    fx, fy = state.cam_focus if state.cam_focus is not None else (state.player.x, state.player.y)
    cx = max(0, min(fx - C.VIEW_W // 2, w.width - C.VIEW_W))
    cy = max(0, min(fy - C.VIEW_H // 2, w.height - C.VIEW_H))
    return cx, cy


_STEAM_RNG = random.Random(0xC01DFACE)
# A steam blob: [world x, world y, vx, vy (tiles/s), age, life (s), radius].
_S_X, _S_Y, _S_VX, _S_VY, _S_AGE, _S_LIFE, _S_R = range(7)


def _steam(con, state: GameState, view, ox: int, oy: int, t: float,
           vw: int, vh: int, xs, ys) -> None:
    """Persistent, world-space steam over the Westreach.

    Blobs are born at the caldera while it rains, each takes its own heading,
    and they drift across the world over ~10-22s, swelling and fading — so a
    cloud bank keeps roaming even after you've walked past the lava. A dense
    column also boils straight off the vent whenever it's on screen. State
    lives on the west map (cosmetic, regenerated on load — never saved)."""
    gm = state.west
    if gm is None:
        return
    raining = state.weather in ("Rain", "Storm")
    storm = state.weather == "Storm"

    blobs = getattr(gm, "_steam_blobs", None)
    if blobs is None:
        blobs = gm._steam_blobs = []
    lava = getattr(gm, "_steam_lava", None)
    if lava is None:
        lava = gm._steam_lava = np.argwhere(gm.tiles == tile.LAVA)

    # Real-time delta (anim_time is monotonic wall-clock seconds). Clamp so the
    # first frame / a pause doesn't spawn or teleport a burst.
    last = getattr(gm, "_steam_t", t)
    dt = t - last
    gm._steam_t = t
    if not (0.0 < dt < 0.5):
        dt = 0.0

    # Spawn from random points on the caldera while it rains.
    if raining and len(lava):
        acc = getattr(gm, "_steam_acc", 0.0) + dt
        interval = 0.28 if storm else 0.5
        while acc >= interval and len(blobs) < 72:
            acc -= interval
            lx, ly = lava[_STEAM_RNG.randrange(len(lava))]
            ang = _STEAM_RNG.uniform(0.0, 6.2832)          # a random heading
            spd = _STEAM_RNG.uniform(0.8, 2.7)
            blobs.append([float(lx) + _STEAM_RNG.uniform(-1.5, 1.5),
                          float(ly) + _STEAM_RNG.uniform(-1.5, 1.5),
                          math.cos(ang) * spd,
                          math.sin(ang) * spd - 0.5,       # a faint buoyant rise
                          0.0, _STEAM_RNG.uniform(10.0, 22.0),
                          _STEAM_RNG.uniform(3.0, 5.5)])
        gm._steam_acc = acc

    # Advance and cull (blobs keep drifting and fading even once the rain stops).
    if dt and blobs:
        for b in blobs:
            b[_S_AGE] += dt
            b[_S_X] += b[_S_VX] * dt
            b[_S_Y] += b[_S_VY] * dt
        blobs = gm._steam_blobs = [b for b in blobs if b[_S_AGE] < b[_S_LIFE]]

    hot_mask = (view == tile.LAVA) if raining else None
    lava_vis = hot_mask is not None and bool(hot_mask.any())
    if not blobs and not lava_vis:
        return

    field = np.zeros((vw, vh), np.float32)

    # The dense column straight off the vent, when the lava is on screen.
    if lava_vis:
        hot = hot_mask.astype(np.float32)
        base = hot.copy()
        for k in range(1, 22):
            base = np.maximum(base, _shift2d(hot, int(round(k * 0.6)), -k) * (0.94 ** k))
        for _ in range(3):
            base = np.maximum(base, np.maximum(_shift2d(base, 1, 0),
                                               _shift2d(base, -1, 0)) * 0.82)
        turb = _hash01(np.floor(xs * 0.45 - t * 2.4), np.floor(ys * 0.45 - t * 3.2))
        field = np.maximum(field, base * (0.6 + 0.7 * turb))

    # The roaming blobs, each drawn in its own small window for speed.
    for b in blobs:
        sx, sy = b[_S_X] - ox, b[_S_Y] - oy
        age = b[_S_AGE] / b[_S_LIFE]
        r = b[_S_R] + 4.0 * age                            # swells as it travels
        if sx < -r - 2 or sx > vw + r + 2 or sy < -r - 2 or sy > vh + r + 2:
            continue
        op = max(0.0, math.sin(math.pi * age)) * 0.85      # fade in, then out
        x0, x1 = max(0, int(sx - r - 2)), min(vw, int(sx + r + 3))
        y0, y1 = max(0, int(sy - r - 2)), min(vh, int(sy + r + 3))
        if x0 >= x1 or y0 >= y1:
            continue
        lx = np.arange(x0, x1, dtype=np.float32)[:, None]
        ly = np.arange(y0, y1, dtype=np.float32)[None, :]
        field[x0:x1, y0:y1] += op * np.exp(
            -((lx - sx) ** 2 + (ly - sy) ** 2) / (2.0 * r * r))

    # Break up the blocky look. One blur rounds off the square cell-grid edges;
    # then drifting turbulence at two frequencies mottles the interior so a bank
    # of overlapping blobs reads as roiling cloud, not one flat grey slab. No
    # blur *after* the mottle — that would smooth the texture straight back into
    # squares (which is exactly what read as blocky before).
    field = _blur5(field)
    #   shape: cloud-scale mottle (drifts smoothly);  grain: a per-cell stipple
    #   (distinct every cell so it actually breaks the grid) that slides across
    #   the cells over time. floor() only on the coarse term — a sub-cell floor
    #   on the fine one would just make new little squares.
    shape = _hash01(np.floor(xs * 0.3 - t * 1.4), np.floor(ys * 0.3 - t * 1.9))
    grain = _hash01(xs + np.floor(t * 3.0), ys - np.floor(t * 2.0))
    field = field * (0.22 + 0.34 * shape + 0.6 * grain)

    # Steam is translucent — keep the cap below full so even the dense core
    # never saturates into one flat slab; the grain then mottles right through
    # it and terrain glimmers faintly behind, reading as vapour, not a wall.
    gain = 1.5 if storm else 1.3
    a = np.clip(field * gain, 0.0, 0.8)
    if lava_vis:
        a *= (1.0 - 0.5 * hot_mask.astype(np.float32))     # lava glows through its steam
    a = a[..., None]
    steam = np.array([212.0, 215.0, 218.0], np.float32)
    fgc = con.rgb["fg"][:vw, :vh].astype(np.float32)
    bgc = con.rgb["bg"][:vw, :vh].astype(np.float32)
    con.rgb["fg"][:vw, :vh] = (fgc * (1 - a) + steam * a).astype(np.uint8)
    con.rgb["bg"][:vw, :vh] = (bgc * (1 - a * 0.85) + steam * 0.8 * a).astype(np.uint8)


def _westreach_ambience(con, state: GameState, view, ox: int, oy: int, t: float) -> None:
    """Weather theatre for the volcano country, painted over the composed view
    (the player is drawn after, so you never vanish into your own weather)."""
    vw, vh = C.VIEW_W, C.VIEW_H
    xs = (ox + np.arange(vw, dtype=np.float32))[:, None]
    ys = (oy + np.arange(vh, dtype=np.float32))[None, :]

    # Rain on the caldera flashes to steam: a thick column boils off the vent,
    # and blobs of it keep detaching and drifting across the reach on their own
    # headings (see _steam) — so cloud banks roam even where no lava is in view.
    _steam(con, state, view, ox, oy, t, vw, vh, xs, ys)

    # Ashfall: on snow-weather days (it never snows white here) and on the
    # mountain's own restless days, grey flakes sift down the view.
    ashy = state.weather == "Snow" or (state.day * 7919 + state.seed) % 3 == 0
    if ashy and state.weather not in ("Rain", "Storm"):
        for i in range(44):
            h1 = (i * 2654435761) % 1000 / 1000.0
            h2 = (i * 40503 + 977) % 1000 / 1000.0
            x = int((h1 * vw + t * (1.5 + h2)) % vw)
            y = int((h2 * vh + t * (5.0 + 3.0 * h1)) % vh)
            con.rgb["ch"][x, y] = ord("∙" if (i % 3) else "·")
            con.rgb["fg"][x, y] = (158, 152, 148)

    # The eruption: every so often the caldera spits a fountain of sparks —
    # loud, bright, and entirely uninterested in you.
    if (t % 41.0) < 5.5:
        lava = np.argwhere(view == tile.LAVA)
        if len(lava):
            cx, cy = int(lava[:, 0].mean()), int(lava[:, 1].mean())
            for i in range(12):
                rise = (t * 6.0 + i * 1.31) % 7.0
                sx = cx + int(round(3.0 * np.sin(i * 2.4 + t * 0.9) * (rise / 7.0)))
                sy = cy - 1 - int(rise)
                if 0 <= sx < vw and 0 <= sy < vh:
                    heat = max(0.25, 1.0 - rise / 7.0)
                    con.rgb["ch"][sx, sy] = ord("*" if rise < 3 else "·")
                    con.rgb["fg"][sx, sy] = (255, int(120 + 120 * heat), int(50 * heat))


# Precedence when a mob carries more than one affliction — the most vivid wins
# the tile's background tint. Kept small; the log carries the detail.
_STATUS_TINT_ORDER = ("burn", "bleed", "poison")


def _status_bg(m, default):
    """A dim background tint marking an afflicted mob (burning/bleeding/poisoned),
    or ``default`` if it carries no damage-over-time."""
    st = getattr(m, "status", None)
    if not st:
        return default
    for kind in _STATUS_TINT_ORDER:
        if kind in st:
            from ..game.combat import STATUS
            r, g, b = STATUS[kind]["color"]
            return (r * 40 // 255 + 12, g * 40 // 255 + 8, b * 40 // 255 + 8)
    return default


def render_world(con: tcod.console.Console, state: GameState, anim_time: float = 0.0) -> None:
    w = state.world
    ox, oy = camera_origin(state)
    view = w.tiles[ox:ox + C.VIEW_W, oy:oy + C.VIEW_H]

    ch = _CH[view]
    fg = _FG[view].astype(np.float32)
    bg = _BG[view].astype(np.float32)

    # Seasonal recolour of natural terrain (surface only): autumn golds, a lush
    # summer, a snow-covered winter.
    if not w.is_dungeon:
        _apply_season(view, fg, bg, state.season)

    # World-space coordinate grids for the visible window (so waves flow
    # smoothly across the world, not just the screen).
    t = anim_time
    xs = (ox + np.arange(C.VIEW_W, dtype=np.float32))[:, None]
    ys = (oy + np.arange(C.VIEW_H, dtype=np.float32))[None, :]

    # --- Per-tile texture: a stable hash breaks up large flats of identical
    # terrain into organic light/shade. A fine jitter grains each tile; a
    # coarser hash drifts broad patches of sun and shadow across the ground.
    textured = _TEX_BY_ID[view]
    if textured.any():
        grain = 0.85 + 0.30 * _hash01(xs, ys)                       # ~±15% per tile
        patch = 0.93 + 0.14 * _hash01(np.floor(xs / 4.0), np.floor(ys / 4.0))
        tex = np.where(textured, grain * patch, 1.0).astype(np.float32)
        fg *= tex[..., None]
        bg *= tex[..., None]

    # --- Fake ambient occlusion: ground beside water, crags and walls sits in
    # their shadow. Count occluding neighbours (cardinals full, diagonals half)
    # and darken open ground a touch per neighbour, giving coasts & cliffs relief.
    solid = _OCCLUDER_BY_ID[view].astype(np.float32)
    occ = np.zeros_like(solid)
    occ[1:, :] += solid[:-1, :]; occ[:-1, :] += solid[1:, :]
    occ[:, 1:] += solid[:, :-1]; occ[:, :-1] += solid[:, 1:]
    occ[1:, 1:] += 0.5 * solid[:-1, :-1]; occ[:-1, 1:] += 0.5 * solid[1:, :-1]
    occ[1:, :-1] += 0.5 * solid[:-1, 1:]; occ[:-1, :-1] += 0.5 * solid[1:, 1:]
    ao = np.clip(occ / 6.0, 0.0, 1.0)
    shade = np.where(~_OCCLUDER_BY_ID[view], 1.0 - 0.34 * ao, 1.0).astype(np.float32)
    bg *= shade[..., None]
    fg *= (0.45 + 0.55 * shade)[..., None]              # glyphs dim less than their cell

    # --- Directional sun shadow: walls, trees & buildings throw a soft shadow
    # away from the sun — long and westward at dawn, short at noon, long and
    # eastward at dusk — so the surface has a moving sense of time and relief.
    if not w.is_dungeon:
        sun = sun_shadow(state.time_minutes)
        if sun is not None:
            dxs, dys, slen, sstr = sun
            cast = np.zeros_like(solid)
            for k in range(1, slen + 1):
                fade = 1.0 - (k - 1) / slen
                cast = np.maximum(cast, _shift2d(solid, int(round(k * dxs)),
                                                 int(round(k * dys))) * fade)
            cast *= (~_OCCLUDER_BY_ID[view]).astype(np.float32)   # only ground takes shadow
            sh = 1.0 - sstr * cast
            bg *= sh[..., None]
            fg *= (0.55 + 0.45 * sh)[..., None]

    # --- Cloudy: the whole scene sits a touch dimmer (overcast), and big soft
    # cloud shadows drift across the land on the wind, with brighter gaps where
    # the sun breaks through. Smooth low frequencies (not a floored hash) so the
    # shadows read as broad passing clouds, not a grid.
    if not w.is_dungeon and state.weather == "Cloudy":
        cs = (np.sin(xs * 0.11 - t * 0.6) + np.sin(ys * 0.085 + t * 0.40)
              + 0.6 * np.sin((xs - ys) * 0.07 + t * 0.5))   # several patches across the view
        cloud = np.clip((cs + 0.2) / 1.4, 0.0, 1.0)      # broad coverage, soft edges
        dim = (0.05 + 0.32 * cloud)[..., None]           # ~5% overcast .. ~37% under a cloud
        fg *= (1 - dim)
        bg *= (1 - dim)

    fg_mul = np.ones((C.VIEW_W, C.VIEW_H), dtype=np.float32)
    bg_mul = np.ones((C.VIEW_W, C.VIEW_H), dtype=np.float32)

    # Wind gusts. A narrow bright band — a line perpendicular to the wind
    # direction — sweeps across the map periodically, like a gust rippling over
    # a real field, brightening grass (and, more gently, trees) as it passes.
    grass = np.isin(view, _GRASS_IDS)
    trees = np.isin(view, _TREE_IDS)
    if grass.any() or trees.any():
        dirx, diry = 0.96, 0.28                 # wind direction (front is perpendicular)
        proj = xs * dirx + ys * diry            # distance along the wind
        perp = -xs * diry + ys * dirx           # distance across the front
        proj = proj + 2.0 * np.sin(perp * 0.12 + t * 0.25)   # semi-straight: gentle waver
        speed, period, width = 11.0, 70.0, 3.0  # tiles/s · gap between gusts · band half-width
        phase = (proj - speed * t) % period
        gust = np.exp(-(phase ** 2) / (2 * width ** 2))
        gust = np.maximum(gust, np.exp(-((phase - period) ** 2) / (2 * width ** 2)))
        ambient = 0.04 * np.sin((xs * 0.4 + ys * 0.25) - t * 1.1)
        # grass sways most; tree canopies rustle more subtly.
        fg_mul = np.where(grass, 1.0 + 0.27 * gust + ambient, fg_mul)
        fg_mul = np.where(trees, 1.0 + 0.17 * gust + 0.5 * ambient, fg_mul)

    # Water: two interfering wave trains shimmer the surface (fg + a little bg).
    water = np.isin(view, _WATER_IDS)
    if water.any():
        wave = (np.sin((xs * 0.70 - ys * 0.50) - t * 2.6)
                + 0.5 * np.sin((xs * 0.25 + ys * 0.60) - t * 1.5))
        fg_mul = np.where(water, 1.0 + 0.17 * wave, fg_mul)
        bg_mul = np.where(water, 1.0 + 0.10 * wave, bg_mul)

    # Ore: each vein twinkles independently — a short, bright shimmer at its
    # own pseudo-random time, so only a few flash at once.
    ore = np.isin(view, _ORE_IDS)
    if ore.any():
        offset = _hash01(xs, ys)                          # per-tile phase offset
        cycle = 12.0 + 16.0 * _hash01(xs + 5.2, ys + 1.3) # 12..28s between shimmers
        tau = (t / cycle + offset)
        tau = (tau - np.floor(tau)) * cycle               # seconds into this cycle
        pw = 0.13                                         # ~0.3s shimmer, fixed
        pulse = np.exp(-(tau ** 2) / (2 * pw * pw))
        pulse = np.maximum(pulse, np.exp(-((tau - cycle) ** 2) / (2 * pw * pw)))
        fg_mul = np.where(ore, 1.0 + 1.2 * pulse, fg_mul)

    # Campfire: a restless warm flicker so the flames never sit still.
    fire = view == tile.CAMPFIRE
    if fire.any():
        flick = (np.sin(t * 6.3 + xs * 2.1) + 0.6 * np.sin(t * 11.0 + ys * 1.7))
        fg_mul = np.where(fire, 1.0 + 0.22 * flick, fg_mul)

    fg *= fg_mul[..., None]
    bg *= bg_mul[..., None]

    # Coastal foam: SEA cells (not the river) that lap against land carry a
    # bright surf line that surges and recedes, so coasts read as living edges.
    sea = view == tile.WATER
    if not w.is_dungeon and sea.any():
        land = ~water                                    # water = sea|river; land = neither
        adj = np.zeros_like(sea)
        adj[1:, :] |= land[:-1, :]; adj[:-1, :] |= land[1:, :]
        adj[:, 1:] |= land[:, :-1]; adj[:, :-1] |= land[:, 1:]
        shore = sea & adj
        if shore.any():
            surge = np.clip(0.30 + 0.70 * np.sin((xs * 0.7 - ys * 0.5) - t * 2.6), 0.0, 1.0)
            f = (shore.astype(np.float32) * surge)[..., None]
            foam = np.array([224.0, 238.0, 246.0], np.float32)
            fg = fg * (1.0 - f * 0.72) + foam * (f * 0.72)
            bg = bg * (1.0 - f * 0.45) + foam * (f * 0.45)

    # Rain wets the world: still, cool puddles sit in fixed low spots on open
    # ground (they don't wander), and ripple rings spread from drops striking
    # any open water — river included.
    if not w.is_dungeon and state.weather in ("Rain", "Storm"):
        wet = _hash01(np.floor(xs * 0.5), np.floor(ys * 0.5))    # fixed patches, no drift
        puddle = (wet > 0.63) & _TEX_BY_ID[view]                 # only on open ground
        if puddle.any():
            for ci, mul in ((0, 0.66), (1, 0.78), (2, 1.02)):    # darker, cooler, faint sheen
                fac = np.where(puddle, mul, 1.0)
                fg[..., ci] *= fac
                bg[..., ci] = np.minimum(255.0, bg[..., ci] * fac)
        if water.any():
            wc = np.argwhere(water)                              # drops land ON water
            X = np.arange(C.VIEW_W, dtype=np.float32)[:, None]
            Y = np.arange(C.VIEW_H, dtype=np.float32)[None, :]
            rings = np.zeros((C.VIEW_W, C.VIEW_H), np.float32)
            r_max = 1.8                                          # tiny drop-splash rings
            for i in range(22 if state.weather == "Storm" else 14):
                per = 1.1 + _h1(i, 2.0)
                phase = t / per + _h1(i, 5.0)
                cyc = math.floor(phase)
                cx, cy = wc[int(_h1(i * 13 + cyc, 3.0) * len(wc)) % len(wc)]
                rr = (phase - cyc) * r_max
                d = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
                rings = np.maximum(rings, np.exp(-((d - rr) ** 2) / 0.5) * max(0.0, 1.0 - rr / r_max))
            rm = (water.astype(np.float32) * rings)[..., None]
            drop = np.array([206.0, 230.0, 250.0], np.float32)
            fg = fg * (1.0 - rm * 0.75) + drop * (rm * 0.75)
            bg = bg * (1.0 - rm * 0.45) + drop * (rm * 0.45)

    # Biome-edge dither: soften the hard seam between terrain families (grass ↔
    # sand ↔ water ↔ forest ↔ rock) by mixing a neighbour's colour into a
    # dithered half of the boundary cells, so borders feather instead of drawing
    # a hard line. Built tiles (group -1) keep crisp edges.
    grp = _BIOME_BY_ID[view]
    checker = ((xs.astype(np.int32) + ys.astype(np.int32)) % 2).astype(bool)
    for (dx, dy), take in (((1, 0), checker), ((0, 1), ~checker)):
        ng = np.full_like(grp, -1)
        nb = bg.copy()
        if dx:
            ng[:-1, :] = grp[1:, :]; nb[:-1, :] = bg[1:, :]
        else:
            ng[:, :-1] = grp[:, 1:]; nb[:, :-1] = bg[:, 1:]
        seam = (grp != ng) & (grp >= 0) & (ng >= 0) & take
        m = (seam.astype(np.float32) * 0.38)[..., None]
        bg = bg * (1.0 - m) + nb * m

    # Planted crops overlay (sparse — just the farm plots in view). Crops sit
    # on a fixed dark soil background so the glyph always has contrast, no
    # matter the terrain tint (damp soil reads a touch cooler/darker).
    for (cx, cy), plot in state.world.crops.items():
        sx, sy = cx - ox, cy - oy
        if 0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H:
            ch[sx, sy] = ord(plot.glyph())
            fg[sx, sy] = plot.color()
            if plot.crop.paddy:                       # rice sits in a flooded pool
                bg[sx, sy] = (40, 78, 108)
            elif plot.watered:                        # damp: an unmistakably cool blue
                bg[sx, sy] = (22, 40, 62)
            else:                                     # parched: warm and dusty, and the
                bg[sx, sy] = (62, 40, 18)             # plant itself looks thirsty too
                fg[sx, sy] = tuple(int(c * 0.75) for c in fg[sx, sy])

    # Orchard trees overlay (passable; fruited trees glow in the fruit's colour).
    for (tx, ty), tree in state.world.trees.items():
        sx, sy = tx - ox, ty - oy
        if 0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H:
            ch[sx, sy] = ord(tree.glyph())
            fg[sx, sy] = tree.color()

    # Placed machines overlay.
    if state.world.machines:
        from ..data.content import MACHINES
        now = state.abs_minutes
        for (mx, my), m in state.world.machines.items():
            sx, sy = mx - ox, my - oy
            if not (0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H):
                continue
            mdef = MACHINES[m.kind]
            status = m.status(now)
            ch[sx, sy] = ord(mdef.glyph)
            if status == "done":
                # ready: pulse between bright gold and white — pollable at a
                # glance across the whole farm, not a subtle tint
                pulse = (t % 1.0) < 0.5
                fg[sx, sy] = (255, 255, 220) if pulse else (250, 220, 110)
                bg[sx, sy] = (60, 50, 26)
            elif status == "working":
                fg[sx, sy] = tuple(int(c * 0.55) for c in mdef.color)
                bg[sx, sy] = (44, 38, 32)
            else:
                fg[sx, sy] = mdef.color
                bg[sx, sy] = (44, 38, 32)

    # Gems glitter: each a stable random colour (red/blue/orange/green/white)
    # with an occasional sparkle.
    gem_mask = view == tile.GEM_VEIN
    if gem_mask.any():
        idx = np.clip((_hash01(xs, ys) * 5).astype(np.int32), 0, 4)
        base = _GEM_PALETTE[idx]
        cyc = 2.0 + 3.0 * _hash01(xs + 9.0, ys + 2.0)
        ph = (t / cyc + _hash01(xs + 3.1, ys + 1.7))
        ph = ph - np.floor(ph)
        spark = np.maximum(np.exp(-(ph * ph) / 0.005),
                           np.exp(-((ph - 1.0) ** 2) / 0.005))
        gemfg = np.clip(base * (0.7 + 0.55 * spark)[..., None], 0, 255)
        fg = np.where(gem_mask[..., None], gemfg, fg)

    # The caldera breathes: lava pulses between ember-red and furnace-orange
    # (each tile on its own phase), and throws a warm halo on the rock beside it.
    lava_mask = view == tile.LAVA
    if lava_mask.any():
        lph = _hash01(xs + 5.0, ys + 8.0)
        pulse = (0.72 + 0.28 * np.sin(t * 2.4 + lph * 6.28)).astype(np.float32)
        bg = np.where(lava_mask[..., None],
                      np.stack([205 * pulse, 62 * pulse, 10 + 8 * pulse], axis=-1), bg)
        fg = np.where(lava_mask[..., None],
                      np.stack([np.full_like(pulse, 255.0), 140 + 80 * pulse, 30 + 30 * pulse],
                               axis=-1), fg)
        halo = np.zeros_like(lava_mask)
        halo[1:, :] |= lava_mask[:-1, :]; halo[:-1, :] |= lava_mask[1:, :]
        halo[:, 1:] |= lava_mask[:, :-1]; halo[:, :-1] |= lava_mask[:, 1:]
        halo &= ~lava_mask
        if halo.any():
            warm = np.array([64.0, 20.0, 4.0], np.float32) * (0.5 + 0.5 * pulse)[..., None]
            bg = np.where(halo[..., None], np.minimum(255.0, bg + warm), bg)

    if w.is_dungeon and w.visible is not None:
        from ..world.dungeon import FOV_RADIUS
        # Torchlight, not a flat floodlight: bright at your feet, guttering out
        # toward the edge of sight, with a gentle flicker — and lava, braziers,
        # hearths and luminous caps throw their own pools of light. Explored-but-
        # unseen ground keeps a dim, cool "from memory" glow.
        vis = w.visible[ox:ox + C.VIEW_W, oy:oy + C.VIEW_H]
        exp = w.explored[ox:ox + C.VIEW_W, oy:oy + C.VIEW_H]
        px, py = state.player.x - ox, state.player.y - oy
        X = np.arange(C.VIEW_W, dtype=np.float32)[:, None]
        Y = np.arange(C.VIEW_H, dtype=np.float32)[None, :]
        d = np.sqrt((X - px) ** 2 + (Y - py) ** 2)
        torch = 0.32 + 0.68 * np.clip(1.0 - d / (FOV_RADIUS + 1.0), 0.0, 1.0)
        flicker = 0.94 + 0.06 * np.sin(t * 6.0 + X * 0.7 + Y * 0.5)
        warm = _glow_from(view, _DUNGEON_WARM_IDS, rad=5, sigma2=10.0)
        cool = _glow_from(view, (tile.GLOWCAP, tile.GLOW_MOSS), rad=3, sigma2=6.0)
        litv = np.clip(torch * flicker + 0.65 * warm + 0.45 * cool, 0.0, 1.15)
        light = np.where(vis, litv, np.where(exp, 0.30, 0.0)).astype(np.float32)
        fg *= light[..., None]
        bg *= light[..., None]
        # Warm the lit near-field (torch + fire), cool the remembered dark.
        warmth = np.where(vis, np.clip(torch + 0.8 * warm, 0.0, 1.0), 0.0)
        for ch_i, cut in ((1, 0.08), (2, 0.24)):
            fg[..., ch_i] *= (1.0 - cut * warmth)
            bg[..., ch_i] *= (1.0 - cut * warmth)
        mem = (exp & ~vis).astype(np.float32)          # seen before, dark now
        fg[..., 0] *= (1.0 - 0.20 * mem)
        bg[..., 0] *= (1.0 - 0.20 * mem)
    else:
        # Day/night light tint over the whole viewport.
        dr, dg, db = daylight_mul(state.time_minutes)
        fg[..., 0] *= dr; fg[..., 1] *= dg; fg[..., 2] *= db
        bg[..., 0] *= dr; bg[..., 1] *= dg; bg[..., 2] *= db

        # Lamp posts (and the woodcutters' campfire) cast a warm glow after dark.
        night = max(0.0, 1.0 - (dr + dg + db) / 3.0)
        if night > 0.06:
            lamps = np.argwhere((view == tile.LAMP) | (view == tile.CAMPFIRE)
                                | (view == tile.HEARTH))
            if len(lamps):
                glow = np.zeros((C.VIEW_W, C.VIEW_H), np.float32)
                rad = 4
                for lx, ly in lamps:
                    x0, x1 = max(0, lx - rad), min(C.VIEW_W, lx + rad + 1)
                    y0, y1 = max(0, ly - rad), min(C.VIEW_H, ly + rad + 1)
                    sx = (np.arange(x0, x1) - lx)[:, None]
                    sy = (np.arange(y0, y1) - ly)[None, :]
                    bump = np.exp(-(sx * sx + sy * sy) / 8.0)
                    glow[x0:x1, y0:y1] = np.maximum(glow[x0:x1, y0:y1], bump)
                add = (glow * (night * 150.0))[..., None] * np.array([1.0, 0.82, 0.5], np.float32)
                fg += add
                bg += add * 0.5

            # The player carries a lantern: a warm pool of light after dark so
            # the night is navigable and cosy rather than a wall of black.
            px, py = state.player.x - ox, state.player.y - oy
            if 0 <= px < C.VIEW_W and 0 <= py < C.VIEW_H:
                rad = 6
                x0, x1 = max(0, px - rad), min(C.VIEW_W, px + rad + 1)
                y0, y1 = max(0, py - rad), min(C.VIEW_H, py + rad + 1)
                sx = (np.arange(x0, x1) - px)[:, None]
                sy = (np.arange(y0, y1) - py)[None, :]
                bump = np.exp(-(sx * sx + sy * sy) / 18.0)
                lantern = (bump * (night * 130.0))[..., None] * np.array([1.0, 0.86, 0.58], np.float32)
                fg[x0:x1, y0:y1] += lantern
                bg[x0:x1, y0:y1] += lantern * 0.55

    np.clip(fg, 0, 255, out=fg)
    np.clip(bg, 0, 255, out=bg)

    con.rgb["ch"][:C.VIEW_W, :C.VIEW_H] = ch
    con.rgb["fg"][:C.VIEW_W, :C.VIEW_H] = fg.astype(np.uint8)
    con.rgb["bg"][:C.VIEW_W, :C.VIEW_H] = bg.astype(np.uint8)

    # --- Dynamic entities, drawn last so nothing overwrites them and tinted to
    # match the time of day (villagers, wildlife and animals dim at night just
    # like the ground). Their cells are returned so weather stays off them. ---
    occupied: set[tuple[int, int]] = set()
    dr, dg, db = (1.0, 1.0, 1.0) if w.is_dungeon else daylight_mul(state.time_minutes)

    def _draw(sx: int, sy: int, glyph: str, color, cell_bg=None) -> None:
        # A faint breathing shimmer on each creature, phased by position so they
        # don't pulse in lockstep — enough that the world looks alive at rest,
        # not so much it distracts.
        sh = 1.0 + 0.09 * math.sin(t * 3.0 + sx * 1.3 + sy * 0.7)
        con.rgb["ch"][sx, sy] = ord(glyph)
        con.rgb["fg"][sx, sy] = (min(255, int(color[0] * dr * sh)),
                                 min(255, int(color[1] * dg * sh)),
                                 min(255, int(color[2] * db * sh)))
        if cell_bg is not None:
            con.rgb["bg"][sx, sy] = (min(255, int(cell_bg[0] * dr)),
                                     min(255, int(cell_bg[1] * dg)),
                                     min(255, int(cell_bg[2] * db)))
        occupied.add((sx, sy))

    if w.is_dungeon and w.visible is not None:
        # dungeon mobs only where currently visible
        for m in w.monsters:
            if not m.alive:
                continue
            sx, sy = m.x - ox, m.y - oy
            if 0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H and w.visible[m.x, m.y]:
                _draw(sx, sy, m.glyph, m.color, _status_bg(m, (36, 24, 24)))
        for npc in w.npcs:                           # underground folk (the dwarf town)
            sx, sy = npc.x - ox, npc.y - oy
            if 0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H and w.visible[npc.x, npc.y]:
                _draw(sx, sy, npc.glyph, npc.color, (42, 38, 50))
    elif not w.is_dungeon:
        season = state.season
        for npc in state.world.npcs:
            sx, sy = npc.x - ox, npc.y - oy
            if 0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H:
                _draw(sx, sy, npc.glyph, npc.color, (42, 38, 50))
        for m in w.monsters:                         # surface wildlife (no fog outdoors)
            if not m.alive or (m.seasons and season not in m.seasons):
                continue                             # out of season — not about
            sx, sy = m.x - ox, m.y - oy
            if 0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H:
                bg = _status_bg(m, None)
                if bg is None:
                    _draw(sx, sy, m.glyph, m.color)
                else:
                    _draw(sx, sy, m.glyph, m.color, bg)
        # farm animals; young ones are paler, a ready-to-collect one glints.
        from ..game.husbandry import SPECIES
        for a in w.animals:
            sx, sy = a.x - ox, a.y - oy
            if not (0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H):
                continue
            spec = SPECIES.get(a.kind)
            col = a.color
            if spec and a.age_days < spec.mature_days:
                col = spec.young_color
            elif a.produce_ready:
                col = (250, 240, 170)
            _draw(sx, sy, a.glyph, col)

    # Westreach ambience: rain boils off the caldera as clouds of steam that
    # blow downwind, ash sifts down on still days, and now and then the caldera
    # spits a (harmless, glorious) fountain of sparks.
    if state.west is not None and w is state.west:
        _westreach_ambience(con, state, view, ox, oy, t)

    # player, centered-ish — always full-bright so you never lose yourself
    px, py = state.player.x - ox, state.player.y - oy
    if 0 <= px < C.VIEW_W and 0 <= py < C.VIEW_H:
        pb = 0.90 + 0.10 * math.sin(t * 2.2)         # a gentle breathing pulse (dims, never lost)
        con.rgb["ch"][px, py] = ord(state.player.glyph)
        con.rgb["fg"][px, py] = tuple(min(255, int(c * pb)) for c in C.PLAYER_FG)
        occupied.add((px, py))

    return occupied


def _bar(con, x, y, label, cur, mx, color, width=12, low_frac=0.0):
    # Below the warning fraction the whole bar turns danger-red — a persistent
    # signal, unlike the one-shot log line that scrolls away.
    low = mx and low_frac and cur <= mx * low_frac
    con.print(x, y, f"{label}" + ("  LOW!" if low else ""),
              fg=C.DANGER_COLOR if low else C.WHITE)
    filled = int(round(width * cur / mx)) if mx else 0
    bar = "█" * filled + "·" * (width - filled)
    con.print(x, y + 1, bar, fg=C.DANGER_COLOR if low else color)
    con.print(x + width + 1, y + 1, f"{cur}/{mx}", fg=C.DIM)


def render_panel(con: tcod.console.Console, state: GameState) -> None:
    x0 = C.VIEW_W
    # background + separator
    con.draw_rect(x0, 0, C.PANEL_W, C.SCREEN_H, ch=ord(" "), bg=C.PANEL_BG)
    con.draw_rect(x0, 0, 1, C.SCREEN_H, ch=ord("│"), fg=C.SEP, bg=C.PANEL_BG)

    x = x0 + 2
    con.print(x, 1, state.date_str(), fg=(236, 226, 180))
    if state.world.is_dungeon:
        con.print(x, 2, f"⛏ {state.world.kind.title()} · floor {state.world.depth}", fg=(196, 186, 214))
    else:
        icon, wcolor = _WEATHER_ICON.get(state.weather, ("·", C.WHITE))
        con.print(x, 2, f"{icon} {state.weather}", fg=wcolor)
    # Clock reddens as the small hours close in (collapse waits at 02:00).
    tm = state.time_minutes
    clock_fg = (C.DANGER_COLOR if tm >= C.MIDNIGHT_MIN
                else C.WARN_COLOR if tm >= C.LATE_WARN_MIN else C.WHITE)
    con.print(x, 3, state.time_str(), fg=clock_fg)

    p = state.player
    _bar(con, x, 5, "♥ HP", p.hp, p.max_hp, C.HP_COLOR, low_frac=C.LOW_HP_FRAC)
    if p.status:                        # active damage-over-time: poison/bleed/burn
        from ..game.combat import STATUS
        col = 0
        for k in p.status:
            info = STATUS.get(k)
            if info:
                con.print(x + col, 7, info["tag"], fg=info["color"])
                col += len(info["tag"]) + 1
    _bar(con, x, 8, "✦ Stamina", p.energy, p.max_energy, C.ENERGY_COLOR,
         low_frac=C.LOW_ENERGY_FRAC)
    con.print(x, 11, f"⛁ Gold  {p.gold}g", fg=C.GOLD_COLOR)
    from ..game import encumbrance as enc
    load, cap, etier = enc.carried_weight(state), enc.capacity(state), enc.tier(state)
    load_fg = (C.WHITE, C.WARN_COLOR, C.DANGER_COLOR)[etier]
    label = enc.TIER_LABEL[etier]
    con.print(x, 12, f"⚖ Load {load:.0f}/{cap:.0f}{'  ' + label if label else ''}"[:C.PANEL_W - 2],
              fg=load_fg)
    from ..game import skills
    b = skills.active_buff(state)
    if b:
        mins = max(0, state.player.buff_until - state.abs_minutes)
        left = f"{mins // 60}h{mins % 60:02d}" if mins >= 60 else f"{mins}m"
        con.print(x, 13, f"↯ {skills.BUFFS.get(b, b)} {left}"[:C.PANEL_W - 2], fg=(180, 210, 250))
    # The market's current craving, visible while planning — not only at the bin.
    d = state.demand
    if d and state.day < d.get("until", 0):
        from ..game.requests import DEMAND_KINDS
        pct = int(round((d["mult"] - 1) * 100))
        con.print(x, 14, f"★ {DEMAND_KINDS[d['kind']].title()} +{pct}%"[:C.PANEL_W - 2],
                  fg=(232, 200, 120))

    # What Space/g would do on the tile you're facing — a live action preview.
    hint = facing_hint(state)
    if hint:
        con.print(x, 15, f"▸ {hint}"[:C.PANEL_W - 2], fg=(150, 200, 160))

    # --- hotbar (keys 1-9, 0) ---
    tool = p.active_tool
    if tool is items.SEED_POUCH:
        active_label = p.active_seed.name if p.active_seed else "Seed Pouch"
    else:
        active_label = p.display_name(tool) if tool else "-"
    con.print(x, 16, f"Tool ▸ {active_label}"[:C.PANEL_W - 2], fg=(236, 226, 180))
    for i, it in enumerate(p.hotbar):
        yy = 18 + i
        sel = i == p.active_slot
        rowbg = (54, 50, 36) if sel else C.PANEL_BG
        fg = C.WHITE if sel else C.DIM
        con.draw_rect(x0 + 1, yy, C.PANEL_W - 1, 1, ch=ord(" "), bg=rowbg)
        if it is items.SEED_POUCH:
            seed = p.active_seed
            nm = seed.name if seed else "Seeds"
            cnt = f"[{p.inventory.count(seed)}]" if seed else "[0]"
            name = f"{(i + 1) % 10} {nm}"[:C.PANEL_W - 3 - len(cnt)]
            con.print(x, yy, name, fg=fg, bg=rowbg)
            con.print(x0 + C.PANEL_W - 1 - len(cnt), yy, cnt, fg=fg, bg=rowbg)
        elif it.stackable:
            # right-align the carried amount, e.g.  "6 Parsnip Seeds  [15]"
            cnt = f"[{p.inventory.count(it)}]"
            name = f"{(i + 1) % 10} {p.display_name(it)}"[:C.PANEL_W - 3 - len(cnt)]
            con.print(x, yy, name, fg=fg, bg=rowbg)
            con.print(x0 + C.PANEL_W - 1 - len(cnt), yy, cnt, fg=fg, bg=rowbg)
        else:
            con.print(x, yy, f"{(i + 1) % 10} {p.display_name(it)}"[:C.PANEL_W - 3], fg=fg, bg=rowbg)
    row = 18 + len(p.hotbar) + 1            # a blank spacer below the hotbar
    if p.weapon:
        con.print(x, row, f"⚔ {p.weapon.name}"[:C.PANEL_W - 2], fg=C.DIM)
        row += 2                            # weapon line, then a spacer

    # goals progress — flows below the weapon line so it can't overdraw it
    from ..game import quests
    dn, tot = quests.progress(state)
    con.print(x, row, f"Goals {dn}/{tot}", fg=(224, 204, 128))
    goal = quests.active(state)
    if goal:
        con.print(x, row + 1, f"▸ {goal.title}"[:C.PANEL_W - 2], fg=C.DIM)

    con.print(x, C.SCREEN_H - 3, "Space use  ? help", fg=C.DIM)
    con.print(x, C.SCREEN_H - 2, "l look  i/e bags", fg=C.DIM)


def render_log(con: tcod.console.Console, state: GameState) -> None:
    y0 = C.VIEW_H
    con.draw_rect(0, y0, C.VIEW_W, 1, ch=ord("─"), fg=C.SEP, bg=C.HUD_BG)
    con.draw_rect(0, y0 + 1, C.VIEW_W, C.LOG_H - 1, ch=ord(" "), bg=C.HUD_BG)
    lines = state.log.tail(C.LOG_H - 1)
    for i, (text, color) in enumerate(lines):
        con.print(1, y0 + 1 + i, text[:C.VIEW_W - 2], fg=color)


def render_weather(con: tcod.console.Console, state: GameState, t: float, occupied=frozenset()) -> None:
    """Animated precipitation drawn over the world viewport (surface only).

    ``occupied`` is the set of screen cells holding the player/creatures, which
    weather skips so their glyphs never flicker under the rain."""
    if state.world.is_dungeon:
        return
    w = state.weather
    if w == "Fog":
        # Fog closes in: a clearish bubble around you fades to heavy grey toward
        # the edges, so you genuinely can't see far — not just a flat haze.
        veil = np.array([150, 156, 164], dtype=np.float32)
        ox, oy = camera_origin(state)
        px, py = state.player.x - ox, state.player.y - oy
        X = np.arange(C.VIEW_W, dtype=np.float32)[:, None]
        Y = np.arange(C.VIEW_H, dtype=np.float32)[None, :]
        d = np.sqrt((X - px) ** 2 + (Y - py) ** 2)
        kbg = np.clip((d - 4.0) / 12.0, 0.12, 0.74)[..., None]     # near clear, far socked in
        for chan, mul in (("bg", 1.0), ("fg", 0.7)):
            buf = con.rgb[chan][:C.VIEW_W, :C.VIEW_H].astype(np.float32)
            k = kbg * mul
            con.rgb[chan][:C.VIEW_W, :C.VIEW_H] = (buf * (1 - k) + veil * k).astype(np.uint8)
    if w == "Storm":
        # Occasional lightning: a brief, near-white flash over the whole view on
        # a slow cycle (a double-strike for that thunderclap feel).
        cyc = t % 6.5
        flash = np.exp(-(cyc ** 2) / 0.010) + 0.6 * np.exp(-((cyc - 0.22) ** 2) / 0.010)
        if flash > 0.03:
            add = np.array([min(130.0, flash * 150.0)] * 2 + [min(140.0, flash * 165.0)], np.float32)
            for chan in ("bg", "fg"):
                buf = con.rgb[chan][:C.VIEW_W, :C.VIEW_H].astype(np.float32)
                con.rgb[chan][:C.VIEW_W, :C.VIEW_H] = np.clip(buf + add, 0, 255).astype(np.uint8)
    if w in ("Rain", "Storm"):
        n, speed, drift = (95, 30, 0.5) if w == "Storm" else (55, 17, 0.25)
        glyph, color = ord("/"), (130, 160, 215)
        for i in range(n):
            cx = int(i * 37 + t * speed * drift) % C.VIEW_W
            cy = int(i * 0.139 * C.VIEW_H + t * speed) % C.VIEW_H
            if (cx, cy) in occupied:
                continue
            con.rgb["ch"][cx, cy] = glyph
            con.rgb["fg"][cx, cy] = color
    elif w == "Snow":
        glyph, color = ord("*"), (228, 234, 245)
        for i in range(48):
            cx = int(i * 53 + 2.2 * np.sin(t * 0.5 + i)) % C.VIEW_W
            cy = int(i * 0.17 * C.VIEW_H + t * 4.0) % C.VIEW_H
            if (cx, cy) in occupied:
                continue
            con.rgb["ch"][cx, cy] = glyph
            con.rgb["fg"][cx, cy] = color
    elif w == "Fog":
        glyph, color = ord("·"), (175, 180, 188)
        for i in range(34):
            cx = int(i * 41 + t * 3.0) % C.VIEW_W
            cy = int(i * 0.23 * C.VIEW_H + 1.5 * np.sin(t * 0.3 + i)) % C.VIEW_H
            if (cx, cy) in occupied:
                continue
            con.rgb["ch"][cx, cy] = glyph
            con.rgb["fg"][cx, cy] = color


# Tile kinds a gnat cloud won't hang over: indoors, built features, and walls.
_GNAT_SKIP = frozenset((
    "house_wall", "house_floor", "door", "bed", "hearth", "table", "counter",
    "barrel", "stall", "well", "statue", "altar", "grave", "tent",
    "shipping_bin", "bin", "post_box", "notice_board", "lamp", "wall", "chest",
    "coop", "coop_small", "coop_big", "barn", "pen",
))


def _wet_tomorrow(state: GameState) -> bool:
    """Is rain/storm forecast for tomorrow? (Drives the natural weather tells.)"""
    try:
        from ..game import farming
        return farming.forecast(state) in ("Rain", "Storm")
    except Exception:
        return False


def render_ambient(con: tcod.console.Console, state: GameState, t: float, occupied) -> None:
    """Drifting seasonal motes over the surface — petals in spring, lazy pollen
    (and fireflies after dark) in summer, tumbling leaves in autumn. Purely
    atmospheric; skipped underground and when the weather already fills the air.
    Winter is left to the snow in render_weather."""
    if state.world.is_dungeon or state.weather in ("Rain", "Storm", "Snow", "Fog"):
        return
    vw, vh = C.VIEW_W, C.VIEW_H
    season = state.season
    dr, dg, db = daylight_mul(state.time_minutes)
    night = (dr + dg + db) / 3.0 < 0.62

    # Nature's own forecast: on a calm day before rain, gnats rise and swarm in
    # a low, restless cloud over open ground — read it and you'll know the
    # morning brings wet. They keep out of doors: never inside a building.
    if season != "Winter" and _wet_tomorrow(state):
        ox, oy = camera_origin(state)
        # Density tracks nearby FRESH water — mosquitoes breed in still rivers,
        # ponds and bogs, not the salt sea. Big cloud by a river, a thin scatter
        # out on dry ground.
        gm = state.world
        px, py = state.player.x, state.player.y
        r = 11
        x0, x1 = max(0, px - r), min(gm.width, px + r + 1)
        y0, y1 = max(0, py - r), min(gm.height, py + r + 1)
        sub = gm.tiles[x0:x1, y0:y1]
        fresh = int((sub == tile.RIVER).sum())
        water = sub == tile.WATER
        if water.any():
            coast = getattr(gm, "coast", None)
            if coast is None:
                fresh += int(water.sum())            # no sea here (e.g. Westreach)
            else:
                cols = coast[x0:x1][:, None]
                ys = np.arange(y0, y1)[None, :]
                fresh += int((water & (ys < cols)).sum())   # inland (above coast) = fresh
        n_gnats = int(3 + 10 * min(1.0, fresh / 22.0))       # 3 far .. 13 by a river
        cx = vw * 0.5 + 10 * math.sin(t * 0.4)
        cy = vh * 0.6 + 7 * math.cos(t * 0.33)
        for i in range(n_gnats):
            gx = int(cx + 5 * math.sin(t * 3.1 + i * 1.7) + (_h1(i, 3.0) * 6 - 3))
            gy = int(cy + 4 * math.cos(t * 2.7 + i * 2.3) + (_h1(i, 7.0) * 5 - 2.5))
            if not (0 <= gx < vw and 0 <= gy < vh) or (gx, gy) in occupied:
                continue
            k = state.world.tile_at(ox + gx, oy + gy).kind
            if k in _GNAT_SKIP:                       # not indoors, not through walls
                continue
            con.rgb["ch"][gx, gy] = ord("·")
            con.rgb["fg"][gx, gy] = (74, 72, 60)       # a dark midge cloud

    if season == "Spring":
        specs, palette, driftx, drifty, glyphs, sway = (24, [(236, 186, 206), (232, 200, 214),
            (222, 170, 196)], 0.8, 1.3, "·,'", 2.4)
    elif season == "Summer" and night:
        specs, palette, driftx, drifty, glyphs, sway = (20, [(190, 240, 130), (220, 236, 150)],
            0.5, 0.4, "*·", 3.0)
    elif season == "Summer":
        specs, palette, driftx, drifty, glyphs, sway = (20, [(236, 224, 150), (226, 214, 140)],
            0.6, 0.5, "·", 1.6)
    elif season == "Fall":
        specs, palette, driftx, drifty, glyphs, sway = (28, [(214, 150, 70), (206, 108, 50),
            (190, 84, 62), (224, 188, 96)], 0.7, 2.2, "'°*,", 3.2)
    else:                                    # Winter clear day: quiet, no motes
        return

    fireflies = season == "Summer" and night
    for i in range(specs):
        h1 = ((i * 2654435761) % 1000) / 1000.0
        h2 = ((i * 40503 + 977) % 1000) / 1000.0
        x = int((h1 * vw + t * (driftx + h2) + sway * math.sin(t * 0.7 + i)) % vw)
        y = int((h2 * vh + t * (drifty + 1.4 * h1)) % vh)
        if (x, y) in occupied:
            continue
        col = palette[i % len(palette)]
        if fireflies:                        # blink on their own phase
            b = 0.25 + 0.75 * max(0.0, math.sin(t * 2.2 + i * 1.7))
            col = (int(col[0] * b), int(col[1] * b), int(col[2] * b))
        else:
            col = (int(col[0] * dr), int(col[1] * dg), int(col[2] * db))
        con.rgb["ch"][x, y] = ord(glyphs[i % len(glyphs)])
        con.rgb["fg"][x, y] = col


def render_fire(con: tcod.console.Console, state: GameState, t: float, occupied) -> None:
    """Living fire: embers rise and wink out above campfires, hearths and lava,
    and hearths trail a thin chimney plume — so fires flicker with real motion
    and villages read as lived-in."""
    w = state.world
    ox, oy = camera_origin(state)
    vw, vh = C.VIEW_W, C.VIEW_H
    view = w.tiles[ox:ox + vw, oy:oy + vh]

    def lit(lx, ly):        # in a dungeon, only currently-seen fires spark
        return not w.is_dungeon or (w.visible is not None and w.visible[lx + ox, ly + oy])

    # Embers: (source id, spark count, spawn gate, max rise).
    for src_id, n, gate, rise_h in ((tile.CAMPFIRE, 3, 1.0, 3.5),
                                    (tile.HEARTH, 2, 1.0, 3.0),
                                    (tile.LAVA, 1, 0.30, 2.5)):
        for lx, ly in np.argwhere(view == src_id):
            lx, ly = int(lx), int(ly)
            if not lit(lx, ly):
                continue
            for i in range(n):
                key = lx * 71 + ly * 131 + i
                if gate < 1.0 and _h1(key, 9.0) > gate:
                    continue
                rise = ((t * 2.4 + _h1(key, 2.0) * rise_h) % rise_h)
                ex = lx + int(round(1.1 * math.sin(t * 3.0 + i + lx * 0.5)))
                ey = ly - 1 - int(rise)
                if 0 <= ex < vw and 0 <= ey < vh and (ex, ey) not in occupied:
                    heat = 1.0 - rise / rise_h
                    con.rgb["ch"][ex, ey] = ord("*" if rise < rise_h * 0.4 else "·")
                    con.rgb["fg"][ex, ey] = (255, int(140 + 90 * heat), int(28 + 40 * heat))

    # Chimney smoke from hearths (surface only) — a thin plume leaning downwind.
    if not w.is_dungeon:
        for hx, hy in np.argwhere(view == tile.HEARTH):
            hx, hy = int(hx), int(hy)
            for j in range(3):
                key = hx * 53 + hy * 97 + j
                h = ((t * 1.3 + _h1(key, 5.0) * 6.0) % 6.0)
                sx = hx + int(round(0.55 * h + math.sin(t * 0.8 + j)))
                sy = hy - 1 - int(h)
                if 0 <= sx < vw and 0 <= sy < vh and (sx, sy) not in occupied:
                    g = int(70 + 130 * max(0.15, 1.0 - h / 6.0))
                    con.rgb["ch"][sx, sy] = ord("°" if h < 3 else "·")
                    con.rgb["fg"][sx, sy] = (g, g, max(0, g - 12))


def render_crossings(con: tcod.console.Console, state: GameState, t: float, occupied) -> None:
    """Occasional life crossing the view: a small flock of birds sweeping over
    by day, butterflies fluttering on clear spring & summer afternoons. Purely
    atmospheric, on long drifting cycles so it feels happened-upon, not timed."""
    if state.world.is_dungeon:
        return
    vw, vh = C.VIEW_W, C.VIEW_H
    dr, dg, db = daylight_mul(state.time_minutes)
    daytime = (dr + dg + db) / 3.0 > 0.72                 # excludes the blue of deep night

    low_flight = _wet_tomorrow(state)                     # birds fly low before rain
    if daytime and state.weather != "Storm":              # birds shelter in storms
        for f in range(2):
            per = 34.0 + 14.0 * _h1(f, 2.0)               # a flyover every ~34–48s…
            phase = t / per + _h1(f, 5.0)
            cyc = math.floor(phase)
            frac = phase - cyc
            if frac > 0.40:                               # …on-screen only while crossing
                continue
            travel = frac / 0.40
            rightward = _h1(f * 7 + cyc, 3.0) < 0.5
            headx = int(-4 + travel * (vw + 8)) if rightward else int(vw + 4 - travel * (vw + 8))
            # high across the sky normally; skimming the low third when rain nears
            row = (int(vh * 0.62 + _h1(f * 7 + cyc, 9.0) * (vh * 0.33)) if low_flight
                   else int(2 + _h1(f * 7 + cyc, 9.0) * (vh * 0.45)))
            flap = "v" if int(t * 6) % 2 else "^"
            for b in range(3 + int(_h1(f * 7 + cyc, 1.0) * 3)):   # a loose 3–5 bird V
                bx = headx - (1 if rightward else -1) * b * 2
                by = row + ((b + 1) // 2) * (-1 if b % 2 else 1)
                by += int(round(0.5 * math.sin(t * 1.5 + b)))
                if 0 <= bx < vw and 0 <= by < vh and (bx, by) not in occupied:
                    con.rgb["ch"][bx, by] = ord(flap)
                    con.rgb["fg"][bx, by] = (64, 60, 70)          # a dark silhouette

    if state.season in ("Spring", "Summer") and state.weather == "Clear" and daytime:
        for i in range(4):
            bx = int((_h1(i, 3.0) * vw + 9 * math.sin(t * 0.7 + i) + t * 2.0 * (_h1(i, 4.0) - 0.5)) % vw)
            by = int((_h1(i, 7.0) * vh + 6 * math.sin(t * 1.1 + i * 2.0)) % vh)
            if (bx, by) in occupied:
                continue
            con.rgb["ch"][bx, by] = ord("*" if int(t * 4 + i) % 2 else "x")
            con.rgb["fg"][bx, by] = (236, 228, 150) if i % 2 else (240, 200, 220)


def render_all(con: tcod.console.Console, state: GameState, anim_time: float = 0.0) -> None:
    con.clear(bg=C.BLACK)
    occupied = render_world(con, state, anim_time)
    render_weather(con, state, anim_time, occupied)
    render_ambient(con, state, anim_time, occupied)
    render_fire(con, state, anim_time, occupied)
    render_crossings(con, state, anim_time, occupied)
    render_panel(con, state)
    render_log(con, state)


def render_facing(con: tcod.console.Console, state: GameState) -> None:
    """Highlight the tile the player faces — the one Space would act on.

    Green when the active tool can act there, a neutral reticle otherwise, so
    the highlight doubles as a facing indicator and an action preview.
    """
    from ..game.actions import resolve_tool

    p = state.player
    fx, fy = p.facing
    tx, ty = p.x + fx, p.y + fy
    if not state.world.in_bounds(tx, ty):
        return
    ox, oy = camera_origin(state)
    sx, sy = tx - ox, ty - oy
    if not (0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H):
        return

    color = C.TARGET_HL
    tool = p.active_tool
    if tool is not None:
        ok, _new, _msg = resolve_tool(tool, state.world.tile_at(tx, ty))
        if ok:
            color = C.TARGET_OK
    con.rgb["bg"][sx, sy] = color


_TOOL_VERB = {
    items.HOE: "till", items.WATERING_CAN: "water", items.AXE: "chop",
    items.PICKAXE: "mine", items.MACHETE: "clear", items.FISHING_ROD: "fish",
}


def facing_hint(state: GameState) -> str:
    """A one-line preview of what acting on the faced tile would do — so the
    player learns the context verbs without opening Look mode every time."""
    from ..game.actions import resolve_tool
    p = state.player
    w = state.world
    tx, ty = p.x + p.facing[0], p.y + p.facing[1]
    if not w.in_bounds(tx, ty):
        return ""
    plot = w.crops.get((tx, ty))
    if plot is not None:
        if plot.dead:
            return "g: clear withered crop"
        if plot.mature:
            return f"g: harvest {plot.crop.name.lower()}"
        days = max(0, plot.crop.days_to_mature - plot.days_grown)
        return f"{plot.crop.name.lower()}: ~{days}d ripe{'' if plot.watered else ', dry'}"
    tree = w.trees.get((tx, ty))
    if tree is not None and tree.mature and tree.has_fruit:
        return f"g: pick {tree.fruit.name.lower()}"
    if (tx, ty) in w.machines:
        from ..data.content import MACHINES
        return f"g: use {MACHINES[w.machines[(tx, ty)].kind].name.lower()}"
    t = w.tile_at(tx, ty)
    named = {"bin": "b: ship goods", "notice_board": "g: read the board",
             "bed": "s: sleep here", "chest": "g: open the chest",
             "stairs": "> : descend", "dungeon_down": "> : enter"}
    if t.kind in named:
        return named[t.kind]
    if t.name in named:
        return named[t.name]
    tool = p.active_tool
    if tool is not None:
        ok, _new, _msg = resolve_tool(tool, t)
        if ok:
            verb = _TOOL_VERB.get(tool, "cut" if tool.kind == "weapon" else "use")
            return f"Space: {verb}"
    return ""


# --- Look mode ---------------------------------------------------------------
_TILE_DESC = {
    "grass": "grassy ground.",
    "meadow": "a meadow speckled with wildflowers.",
    "tall_grass": "tall, swaying grass.",
    "path": "a worn dirt path.",
    "sand": "a sandy riverbank.",
    "water": "open water — too deep to wade.",
    "river": "the river running through the Vale.",
    "tree": "a broadleaf tree. An axe would fell it.",
    "pine": "a dark pine of the old forest.",
    "bush": "a berry bush — forageable later.",
    "moor": "bleak, boggy moorland.",
    "fog_grass": "grey grass shrouded in fog.",
    "ruins_floor": "the cracked floor of old ruins.",
    "ruins_wall": "a crumbling ruin wall.",
    "rock": "solid rock. A pickaxe could break it.",
    "ore_vein": "an ore vein glinting with metal.",
    "house_wall": "the wall of your farmhouse.",
    "house_floor": "the floorboards of your home.",
    "door": "your front door.",
    "bed": "your bed. Sleep here (s) to end the day.",
    "shipping_bin": "the shipping bin. Ship goods here (b) to sell overnight.",
    "post_box": "your post box — letters, invitations and gifts arrive here (g).",
    "notice_board": "the village notice board — favours pinned by the villagers (g).",
    "altar": "a shrine altar — bump it to pray (a daily blessing once the shrine is raised).",
    "lectern": "a scriptorium lectern — bump it to study out a new recipe (once a day).",
    "bath": "a bathhouse basin — bump it to soak: sweat off sickness and restore stamina (takes a while).",
    "exhibit": "a glass display case — present your finds to the curator (g) for the collection.",
    "fence": "a wooden fence around the plot.",
    "tilled": "tilled soil, ready for seeds.",
    "dungeon_down": "a stairway leading down. Press > to descend.",
    "stairs_up": "a stairway leading up. Press < to climb out.",
    "dungeon_wall": "solid dungeon rock.",
    "dungeon_floor": "the dungeon floor.",
    "gem_vein": "a gem vein glinting in the rock — mine it with a pickaxe.",
    "sulphur_deposit": "a brimstone-yellow seam — sulphur, for powder-making (any pick bites it).",
    "nitre_deposit": "a pale nitre crust — saltpeter: powder, fertiliser or curing salt.",
    "lava": "molten rock, seething in the caldera. Keep well back.",
    "ash": "grey volcanic ash, soft underfoot.",
    "gold_pile": "a glittering pile of gold — step on it to grab it.",
    "chest": "a treasure chest — press g to pry it open.",
    "rubble": "loose rubble — slow going underfoot.",
    "trap": "a sprung-looking trap in the floor — best stepped around.",
    "herb": "a wild medicinal herb — gather it for the apothecary (g).",
    "bones": "a scatter of old bones.",
    "crystal": "a cluster of crystals, glinting in the dark.",
    "stalagmite": "a stone spire — you'll have to go around.",
    "pillar": "a standing pillar of worked stone.",
    "brazier": "a burning brazier, throwing warm light.",
    "mine_timber": "an old pit-prop, shoring up the rock.",
    "mushroom": "a cluster of cave mushrooms — gather them with g.",
    "button_mushroom": "button mushrooms — a common field mushroom. Forage (g).",
    "parasol_mushroom": "a parasol mushroom, tall with a broad cap. Forage (g).",
    "bolete": "boletes — fat-stemmed woodland mushrooms. Forage (g).",
    "chanterelle": "golden chanterelles nestled in the leaf litter. Forage (g).",
    "glow_moss": "soft luminous moss, glowing faintly underfoot.",
    "wispwood": "a wispwood — a pale, glowing tree of the deep grove.",
    "glowcap": "a giant glowcap, shining softly — gather it with g.",
    "road": "a packed road — travel here is twice as quick.",
    "bridge": "a wooden bridge over the water.",
    "well": "the village well.",
    "lamp": "a lamp post — it glows warm after dark.",
    "stall": "a market stall.",
    "signpost": "a signpost at the crossroads.",
    "cobble": "the cobbled market square.",
    "statue": "the old market cross, worn smooth by years.",
    "hearth": "a stone hearth, warm with embers.",
    "table": "a sturdy table.",
    "counter": "a shop counter.",
    "barrel": "a stout wooden barrel.",
    "altar": "a shrine's altar, laid with offerings.",
    "grave": "a weathered headstone. Rest easy.",
    "boat": "a little fishing boat, moored at the pier.",
    "wild_hive": "a wild bee hive in the tree — rob it (g) for honey and wax.",
}


def _building_at(world, x: int, y: int):
    for b in getattr(world, "buildings", ()):
        if b["x"] <= x < b["x"] + b["w"] and b["y"] <= y < b["y"] + b["h"]:
            return b
    return None


def _npc_by_name(state: GameState, nm: str):
    for n in state.world.npcs:
        if n.name == nm:
            return n
    return None


def _building_label(state: GameState, b: dict) -> str:
    """A signboard-style name for a village building."""
    v = b.get("village", "")
    kind = b.get("kind")
    if kind == "inn":
        return f"the {v} inn"
    if kind == "temple":
        return f"the chapel of {v}"
    if kind == "shop":
        return f"the {v} general store"
    if kind == "smithy":
        return f"the {v} smithy"
    from ..data import content as _c
    if kind in _c.PROJECTS:
        return f"the {_c.PROJECTS[kind].name} — raised by your hand"
    if kind == "tent":
        owner = b.get("owner")
        if owner:
            npc = _npc_by_name(state, owner)
            if npc and npc.met:
                return f"{owner}'s tent"
        return "a woodcutter's tent"
    # private dwelling
    owner = b.get("owner")
    if owner:
        npc = _npc_by_name(state, owner)
        if npc and npc.met:
            flavour = {"fisher": "fishing cottage", "farmer": "farmhouse",
                       "forager": "cottage", "trader": "lodging",
                       "forester": "hut"}.get(npc.role, "house")
            return f"{owner}'s {flavour}"
    if kind == "hut":
        return "a forester's hut"
    if kind == "coop_big":
        return "your coop"
    if kind == "barn":
        return "your barn"
    if kind == "greenhouse":
        return "your greenhouse"
    return "a farmhouse" if kind == "farmhouse" else "a house"


_COMPASS = ("E", "NE", "N", "NW", "W", "SW", "S", "SE")


def _compass(dx: int, dy: int) -> str:
    """8-wind bearing from a tile to a target (screen coords: +y is south)."""
    if dx == 0 and dy == 0:
        return "here"
    ang = math.degrees(math.atan2(-dy, dx)) % 360     # 0=E, 90=N
    return _COMPASS[int(((ang + 22.5) % 360) // 45)]


def _signpost_text(state: GameState, x: int, y: int) -> str:
    """A signpost names the notable places and which way each lies."""
    w = state.world
    dests = []
    for name, (cx, cy) in getattr(w, "village_centers", {}).items():
        dests.append((name, cx, cy))
    for (dx, dy) in getattr(w, "dungeons", []):
        dests.append((f"the {w.dungeon_kind.get((dx, dy), 'delve')}", dx, dy))
    if w.spawn:
        dests.append(("home", w.spawn[0], w.spawn[1]))
    ranked = sorted(((abs(tx - x) + abs(ty - y), f"{name} {_compass(tx - x, ty - y)}")
                     for name, tx, ty in dests), key=lambda e: e[0])
    if not ranked:
        return "a weathered signpost."
    return "A signpost points the way — " + ", ".join(s for _d, s in ranked) + "."


def _wrap(text: str, width: int) -> list[str]:
    """Greedy word-wrap to `width` columns."""
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        lines.append(cur)
    return lines


_STATUS_ADJ = {"burn": "burning", "poison": "poisoned", "bleed": "bleeding", "sick": "sick"}

# How enriched ground reads in look-mode (index = soil level 1..4).
_SOIL_WORDS = ("", " The soil is freshly worked.", " Good dark earth, well worked.",
               " Rich soil — years of care in it.", " Black, living loam — the finest ground.")


def _soil_word(state: GameState, x: int, y: int) -> str:
    lvl = state.world.soil.get((x, y), 0)
    return _SOIL_WORDS[min(lvl, 4)] if lvl > 0 else ""


def _afflictions(m) -> str:
    """A readable list of the DoTs currently on a mob (''  if none)."""
    st = getattr(m, "status", None)
    return ", ".join(_STATUS_ADJ.get(k, k) for k in st) if st else ""


def describe(state: GameState, x: int, y: int) -> str:
    if (x, y) == (state.player.x, state.player.y):
        return "yourself, the new farmer of Hollowmere Vale."
    if not state.world.in_bounds(x, y):
        return "the edge of the known Vale."
    for m in state.world.monsters:
        if m.alive and (m.x, m.y) == (x, y):
            aff = _afflictions(m)
            afftail = f" Currently {aff}." if aff else ""
            infl = (f" Its hits can leave you {_STATUS_ADJ.get(m.inflicts, m.inflicts)}."
                    if getattr(m, "inflicts", "") else "")
            if getattr(m, "kind", "monster") == "wildlife":
                if m.hostile:
                    return f"a {m.name.lower()}, riled up and coming for you!{infl}{afftail}"
                trait = ("minds its own business — but fights back if struck"
                         if m.behavior == "defensive"
                         else "skittish; it bolts if you get too close")
                return f"a {m.name.lower()} — {trait}.{infl}{afftail}"
            tier = f" (level {m.level})" if getattr(m, "level", 1) > 1 else ""
            elite = " An elite: tougher, and a richer kill." if getattr(m, "elite", "") else ""
            return (f"a {m.name.lower()}{tier} — HP {m.hp}/{m.max_hp}, DV {m.dv}, PV {m.pv}."
                    f"{elite}{infl}{afftail} Bump it to attack.")
    for npc in state.world.npcs:
        if (npc.x, npc.y) == (x, y):
            role = {"general": "shopkeeper", "blacksmith": "blacksmith"}.get(npc.shop, "villager")
            return f"{npc.name}, the {role}. {'♥' * npc.hearts}{'·' * (10 - npc.hearts)} (Shift+C talk, f gift)"
    from ..game.husbandry import animal_at, SPECIES, _is_adult
    a = animal_at(state, x, y)
    if a is not None:
        spec = SPECIES[a.kind]
        role = spec.grown_name if _is_adult(a) else spec.young_name
        if a.sick:
            return (f"{a.name}, your {role} — looks poorly: off its feed and shivering. "
                    "Dose it with a Herbal Tonic (bump), or it'll be a week mending.")
        mood = ("content" if a.happiness >= 80 else "happy" if a.happiness >= 55
                else "a little glum" if a.happiness >= 35 else "unhappy")
        tail = " — has produce ready (bump to collect)" if a.produce_ready and _is_adult(a) else ""
        return f"{a.name}, your {role} — {mood}{tail}. Bump to pet."
    # a village building? name it (community/commercial always; houses by owner)
    b = _building_at(state.world, x, y)
    if b is not None:
        tname = state.world.tile_at(x, y).name
        label = _building_label(state, b)
        if tname == "bed":
            owner = b.get("owner")
            npc = _npc_by_name(state, owner) if owner else None
            return f"{owner}'s bed." if (npc and npc.met) else "a bed."
        if tname == "door":
            return f"the door of {label}."
        if tname == "altar":
            return f"the altar of {label}."
        if tname in ("hearth", "counter", "table", "barrel"):
            return f"{_TILE_DESC.get(tname, tname)} — inside {label}."
        return f"{label}."
    from ..game import land
    theft = " — another's; taking it is theft" if land.owned_by_other(state, x, y) else ""
    plot = state.world.crops.get((x, y))
    if plot is not None:
        name = plot.crop.name.lower()
        poss = f"{land.owner_label(state, x, y)} " if theft else ""
        soil = _soil_word(state, x, y)
        if plot.dead:
            return f"a withered {name}. Clear it with g."
        if plot.mature:
            return f"{poss}{name} — ripe! Harvest it with g{theft}.{soil}"
        water = "watered" if plot.watered else "needs watering"
        fert = ", fertilised" if plot.fertilized else ""
        days = max(0, plot.crop.days_to_mature - plot.days_grown)
        when = "ripe tomorrow" if days <= 1 else f"~{days} days to ripe"
        return f"{poss}{name}, still growing — {when} ({water}{fert}){theft}.{soil}"
    tree = state.world.trees.get((x, y))
    if tree is not None:
        if not tree.mature:
            td = max(0, tree.days_to_mature - tree.age)
            return (f"a young {tree.name.lower()} sapling — "
                    f"{'bears next season' if td <= 1 else f'~{td} days to bear'}.")
        if tree.has_fruit:
            return f"a {tree.name.lower()} tree, heavy with fruit — pick it (g){theft}."
        return f"a {tree.name.lower()} tree; bears fruit in {tree.season}."
    m = state.world.machines.get((x, y))
    if m is not None:
        from ..data.content import MACHINES
        mdef = MACHINES[m.kind]
        if m.kind == "sprinkler":
            return "a sprinkler — waters nearby soil each morning."
        if m.kind == "weathervane":
            from ..game import farming
            return f"a weathervane — it points to tomorrow: {farming.weather_saying(farming.forecast(state))}"
        if m.kind == "chest":
            return "your storage chest — stash goods here (g) to carry less."
        if m.kind == "beehive":
            if not m.has_queen:
                return "a beehive — add a bee queen (g) to start a colony."
            if state.abs_minutes < m.ready_at:
                return "a beehive, humming — the colony is filling the combs."
            return "a beehive — honey ready to harvest! (g)"
        if m.kind in ("coop_small", "coop_big", "barn"):
            from ..game.husbandry import _flock
            n = len(_flock(state, (x, y)))
            return (f"your {mdef.name.lower()} — {n}/{mdef.capacity} animals, {m.feed} straw in "
                    "the trough. (g: settle a young one, or fork in straw)")
        st = m.status(state.abs_minutes)
        if st == "done":
            return f"{mdef.name} — {m.loaded_output.name} is ready! (g to collect)"
        if st == "working":
            from ..game.crafting import _fmt_remaining
            left = _fmt_remaining(m.ready_at - state.abs_minutes)
            out = m.loaded_output.name if m.loaded_output else "something"
            return f"{mdef.name}, working on {out} — {left} left."
        return f"{mdef.name}, empty. {mdef.desc} (g to load)"
    t = state.world.tile_at(x, y)
    if t.kind == "signpost":
        return _signpost_text(state, x, y)
    if t.kind == "tree":
        return f"a {t.name} tree — passable. Chop it with an axe for wood."
    if t.kind == "foliage":
        return "dense foliage blocking the way. Clear it with a machete (Space)."
    if t.kind == "shrub":
        return "a thick shrub. Clear it with a machete (Space)."
    if t.kind == "shrub_berry":
        from ..data.content import SHRUB_FRUIT
        fruit = SHRUB_FRUIT.get(t.name)
        fn = fruit.name.lower() if fruit else "berry"
        return f"a {fn} shrub, ripe — pick it (g) and it bears again; machete clears it{theft}."
    base = _TILE_DESC.get(t.name, f"{t.name.replace('_', ' ')}.")
    if t.name == "tilled":
        base = base.rstrip(".") + f".{_soil_word(state, x, y)}"
    # Whose ground is this? Note owned/claimed land on open, workable tiles.
    if t.walkable and t.kind in ("terrain", "soil", "road"):
        owner = land.owner_at(state, x, y)
        if owner == "player" and (x, y) in state.claims:
            return base.rstrip(".") + " — your claim (taxed weekly)."
        if owner is not None and owner != "player":
            return base.rstrip(".") + f" — {land.owner_label(state, x, y)} land; you can't build here."
    return base


def render_look(con: tcod.console.Console, state: GameState, lx: int, ly: int) -> None:
    ox, oy = camera_origin(state)
    p = state.player

    # A faint tether from you to the cursor, so the cursor is unmistakably YOURS
    # and easy to find again if it has roamed off across the map. Tints the path
    # cells' background (leaving their glyphs readable); skips the endpoints.
    from ..game.combat import _line
    path = _line(p.x, p.y, lx, ly)                    # excludes the start (you)
    for tx, ty in path[:-1]:                          # excludes the cursor itself
        tsx, tsy = tx - ox, ty - oy
        if 0 <= tsx < C.VIEW_W and 0 <= tsy < C.VIEW_H:
            con.rgb["bg"][tsx, tsy] = (66, 62, 44)

    sx, sy = lx - ox, ly - oy
    if 0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H:
        con.rgb["bg"][sx, sy] = (150, 135, 45)
        con.rgb["fg"][sx, sy] = (20, 20, 20)

    # A clear mode banner (not a log line) names the repurposed keys, so a new
    # player never wonders why "moving" doesn't move them. Below it, a
    # word-wrapped readout so long descriptions (a signpost's bearings) fit.
    banner = "» LOOK — arrows move the cursor, not you · Esc/l to exit"
    lines = _wrap(describe(state, lx, ly), C.VIEW_W - 2)[:5]
    h = len(lines) + 2
    con.draw_rect(0, 0, C.VIEW_W, h, ch=ord(" "), bg=(46, 52, 40))
    con.draw_rect(0, 0, C.VIEW_W, 1, ch=ord(" "), bg=(70, 96, 78))
    con.print(1, 0, banner[:C.VIEW_W - 1], fg=(238, 244, 210), bg=(70, 96, 78))
    for i, ln in enumerate(lines):
        con.print(1, i + 1, ln[:C.VIEW_W - 1], fg=(245, 235, 200), bg=(46, 52, 40))


def render_target(con: tcod.console.Console, state: GameState, ctx) -> None:
    """Aiming overlay: a reticle plus a preview of the affected tiles — the blast
    radius when throwing, the footprint when siting a building."""
    if not ctx:
        return
    from ..game import combat, husbandry
    ox, oy = camera_origin(state)

    def _paint(x: int, y: int, ok: bool) -> None:
        sx, sy = x - ox, y - oy
        if 0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H:
            con.rgb["bg"][sx, sy] = C.AIM_OK if ok else C.AIM_BAD

    cx, cy = ctx["cursor"]
    if ctx["purpose"] == "throw":
        ok = combat.in_bomb_range(state, cx, cy)
        lx, ly = combat.bomb_landing(state, cx, cy)
        for x in range(lx - 1, lx + 2):                # the 3x3 blast preview
            for y in range(ly - 1, ly + 2):
                _paint(x, y, ok)
        sx, sy = cx - ox, cy - oy                      # the reticle itself
        if 0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H:
            con.rgb["ch"][sx, sy] = ord("*")
            con.rgb["fg"][sx, sy] = (20, 20, 20)
        banner = (f" Aim — throw a bomb (range {combat.BOMB_RANGE})"
                  if ok else " Aim — out of range")
    elif ctx["purpose"] == "shoot":
        rng = combat.aim_range(state)
        ok = combat.in_range(state, cx, cy, rng)
        lx, ly = combat.projectile_landing(state, cx, cy, rng)
        _paint(lx, ly, ok)                             # the single struck tile
        sx, sy = cx - ox, cy - oy
        if 0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H:
            con.rgb["ch"][sx, sy] = ord("*")
            con.rgb["fg"][sx, sy] = (20, 20, 20)
        weap = state.player.equipment.get("ranged")
        banner = (f" Aim — loose the {weap.name.lower()} (range {rng})"
                  if ok else " Aim — out of range")
    else:  # build
        from ..data.content import MACHINES
        kind = ctx["build_kind"]
        ok, cells, reason = husbandry.can_place_building(state, (cx, cy), kind)
        for bx, by in cells:
            _paint(bx, by, ok)
        name = MACHINES[kind].name.lower()
        banner = f" Site your {name} — the door faces you" if ok else f" Can't build here: {reason}"

    con.draw_rect(0, 0, C.VIEW_W, 1, ch=ord(" "), bg=(40, 38, 30))
    con.print(0, 0, banner[:C.VIEW_W], fg=(245, 235, 200), bg=(40, 38, 30))
    swap = " · Tab bow/bomb" if (ctx["purpose"] in ("shoot", "throw")
                                 and combat.can_shoot(state) and combat.can_throw(state)) else ""
    hint = f"(move to aim · Enter/Space confirm{swap} · Esc cancel)"
    con.print(max(0, C.VIEW_W - len(hint) - 1), 0, hint, fg=C.DIM, bg=(40, 38, 30))


# --- Modal overlays (the skeleton lives in engine/ui.py) ----------------------


def render_fishing(con: tcod.console.Console, state: GameState, ctx) -> None:
    """The reel-it-in minigame: a horizontal track with a catch bracket, the
    darting fish, and a progress bar. ←/→ (fed by the loop) slide the bracket."""
    if not ctx:
        return
    from ..game import fishing
    L = fishing.TRACK_LEN
    w, h = L + 10, 9
    m = ui.Modal(con, w, h, "A bite!  Reel it in")
    inside = ctx.get("inside", False)
    green, amber = (120, 200, 140), (222, 182, 110)
    bar_col = green if inside else amber
    tx0 = (w - L) // 2                              # left edge of the track
    bar = int(round(ctx["bar"])); bl = ctx["bar_len"]
    fp = int(round(ctx["fish_pos"]))
    filled = int(round(L * ctx["prog"]))
    m.text(2, 1, "Keep the fish in the bracket:", fg=C.DIM)
    for c in range(L):                              # the track row
        in_bar = bar <= c < bar + bl
        m.text(tx0 + c, 3, "░" if in_bar else "·",
               fg=(70, 84, 70) if in_bar else (58, 66, 82))
    m.text(tx0 + bar, 3, "[", fg=bar_col)                          # bracket ends
    m.text(tx0 + min(L - 1, bar + bl - 1), 3, "]", fg=bar_col)
    m.text(tx0 + fp, 3, "»", fg=(150, 200, 224) if inside else (232, 150, 140))
    for c in range(L):                              # progress bar, filling left→right
        m.text(tx0 + c, 5, "█", fg=(120, 200, 140) if c < filled else (44, 52, 48))
    pct = int(ctx["prog"] * 100)
    m.text(tx0, 6, f"{pct}%", fg=green if pct >= 60 else amber)
    m.footer("←/→ move the bracket  ·  Esc to cut the line")


_HDR = ui.HDR
_KEY = (150, 200, 230)


# The encyclopedia (? screen) lives in engine/codex.py.



# The modal/menu overlays live in engine/screens_render.py; re-exported here
# so callers keep saying rendering.render_X.
from . import screens_render as _sr          # noqa: E402
render_message_log = _sr.render_message_log
render_mail = _sr.render_mail
render_requests = _sr.render_requests
render_eat = _sr.render_eat
render_load_machine = _sr.render_load_machine
render_cheats = _sr.render_cheats
render_quit = _sr.render_quit
render_intro = _sr.render_intro
render_storage = _sr.render_storage
render_confirm = _sr.render_confirm
inv_letter = _sr.inv_letter
render_inventory = _sr.render_inventory
render_equipment = _sr.render_equipment
render_craft = _sr.render_craft
render_ship = _sr.render_ship
render_journal = _sr.render_journal
render_relationships = _sr.render_relationships
render_character = _sr.render_character
render_dialogue = _sr.render_dialogue
render_shop = _sr.render_shop
render_contest = _sr.render_contest
render_world_map = _sr.render_world_map
render_chargen = _sr.render_chargen
render_donate = _sr.render_donate
render_gift = _sr.render_gift
_JOURNAL_TABS = _sr._JOURNAL_TABS
