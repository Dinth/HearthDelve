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


_DUNGEON_WARM_IDS = (tile.LAMP, tile.CAMPFIRE, tile.HEARTH, tile.LAVA)


def _blur5(f: np.ndarray) -> np.ndarray:
    """A gentle 4-neighbour blur (weights .5 centre, .125 each side) that rubs
    out the hard cell-grid edges so steam reads as cloud, not squares."""
    out = f * 0.5
    out[1:, :] += 0.125 * f[:-1, :]
    out[:-1, :] += 0.125 * f[1:, :]
    out[:, 1:] += 0.125 * f[:, :-1]
    out[:, :-1] += 0.125 * f[:, 1:]
    return out


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


_WEATHER_ICON = {
    "Clear": ("☀", (245, 214, 110)),
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
        con.rgb["ch"][sx, sy] = ord(glyph)
        con.rgb["fg"][sx, sy] = (min(255, int(color[0] * dr)),
                                 min(255, int(color[1] * dg)),
                                 min(255, int(color[2] * db)))
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
                _draw(sx, sy, m.glyph, m.color, (36, 24, 24))
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
                _draw(sx, sy, m.glyph, m.color)
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
        con.rgb["ch"][px, py] = ord(state.player.glyph)
        con.rgb["fg"][px, py] = C.PLAYER_FG
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
        # A haze veil: blend the whole viewport toward soft grey so distance
        # washes out, then drift a few motes over the top.
        veil = np.array([150, 156, 164], dtype=np.float32)
        for chan, k in (("bg", 0.18), ("fg", 0.11)):
            buf = con.rgb[chan][:C.VIEW_W, :C.VIEW_H].astype(np.float32)
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


def render_all(con: tcod.console.Console, state: GameState, anim_time: float = 0.0) -> None:
    con.clear(bg=C.BLACK)
    occupied = render_world(con, state, anim_time)
    render_weather(con, state, anim_time, occupied)
    render_ambient(con, state, anim_time, occupied)
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


def describe(state: GameState, x: int, y: int) -> str:
    if (x, y) == (state.player.x, state.player.y):
        return "yourself, the new farmer of Hollowmere Vale."
    if not state.world.in_bounds(x, y):
        return "the edge of the known Vale."
    for m in state.world.monsters:
        if m.alive and (m.x, m.y) == (x, y):
            if getattr(m, "kind", "monster") == "wildlife":
                if m.hostile:
                    return f"a {m.name.lower()}, riled up and coming for you!"
                trait = ("minds its own business — but fights back if struck"
                         if m.behavior == "defensive"
                         else "skittish; it bolts if you get too close")
                return f"a {m.name.lower()} — {trait}."
            tier = f" (level {m.level})" if getattr(m, "level", 1) > 1 else ""
            return (f"a {m.name.lower()}{tier} — HP {m.hp}/{m.max_hp}, DV {m.dv}, PV {m.pv}. "
                    "Bump it to attack.")
    for npc in state.world.npcs:
        if (npc.x, npc.y) == (x, y):
            role = {"general": "shopkeeper", "blacksmith": "blacksmith"}.get(npc.shop, "villager")
            return f"{npc.name}, the {role}. {'♥' * npc.hearts}{'·' * (10 - npc.hearts)} (Shift+C talk, f gift)"
    from ..game.husbandry import animal_at, SPECIES, _is_adult
    a = animal_at(state, x, y)
    if a is not None:
        spec = SPECIES[a.kind]
        role = spec.grown_name if _is_adult(a) else spec.young_name
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
        if plot.dead:
            return f"a withered {name}. Clear it with g."
        if plot.mature:
            return f"{poss}{name} — ripe! Harvest it with g{theft}."
        water = "watered" if plot.watered else "needs watering"
        fert = ", fertilised" if plot.fertilized else ""
        days = max(0, plot.crop.days_to_mature - plot.days_grown)
        when = "ripe tomorrow" if days <= 1 else f"~{days} days to ripe"
        return f"{poss}{name}, still growing — {when} ({water}{fert}){theft}."
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


def render_message_log(con: tcod.console.Console, state: GameState, scroll: int) -> None:
    """Full scrollback of the message log (newest at the bottom)."""
    msgs = state.log.messages
    w, h = 72, C.SCREEN_H - 6
    body = h - 4
    m = ui.Modal(con, w, h, "Message Log")
    total = len(msgs)
    max_scroll = max(0, total - body)
    scroll = max(0, min(scroll, max_scroll))
    start = max(0, total - body - scroll)
    for i, (text, color) in enumerate(msgs[start:start + body]):
        m.text(2, 2 + i, text[:w - 4], fg=color)
    m.arrows(scroll < max_scroll, scroll > 0, 2, h - 3)
    m.footer("↑↓ scroll · Esc close")


def render_mail(con: tcod.console.Console, state: GameState, sel: int) -> None:
    mail = state.mail
    body = mail[min(sel, len(mail) - 1)]["body"].split("\n") if mail else []
    w = 60
    list_h = min(10, max(1, len(mail)))          # cap the letter list; it scrolls
    h = list_h + len(body) + 8
    m = ui.Modal(con, w, h, "Post Box")
    if not mail:
        m.text(2, 2, "The post box is empty.", fg=C.DIM)

    def row(i, dy, selected, bg):
        letter = mail[i]
        tag = " ⚖ tax due" if letter.get("tax") else " ✉+gift" if letter.get("items") else " ✉"
        m.text(2, dy, ui.cur(selected) + f"From {letter['sender']}{tag}", fg=C.WHITE, bg=bg)

    m.list(2, list_h, len(mail), sel, row, arrow_top=2, arrow_bottom=1 + list_h)
    for j, bl in enumerate(body):                # the open letter's text below the list
        m.text(3, 3 + list_h + j, bl[:w - 6], fg=(210, 205, 190))
    m.footer("↑↓ select   Enter settle tax / take letter   Esc close"
             if any(le.get("tax") for le in mail)
             else "↑↓ select   Enter take letter   Esc close")


def render_requests(con: tcod.console.Console, state: GameState, sel: int,
                    village: str = "") -> None:
    """The village notice board: pinned favours, who wants what, and the pay —
    plus this village's restoration project, if one is open or rising."""
    from ..game import requests as gamereq, projects as gameproj
    from ..data import content
    from ..entities import items as I
    reqs = state.requests
    proj = gameproj.for_village(state, village) if village else None
    if proj is not None and proj["state"] == "done":
        proj = None
    w = 66
    h = max(9, len(reqs) * 3 + (5 if proj else 0) + 6)
    h = min(C.SCREEN_H - 4, h)
    m = ui.Modal(con, w, h, f"{village + ' ' if village else ''}Notice Board")
    if not reqs and not proj:
        m.text(2, 2, "The board is bare today — favours come and go.", fg=C.DIM)
    n_rows = len(reqs) + (1 if proj else 0)
    sel = max(0, min(sel, n_rows - 1)) if n_rows else 0
    row = 0
    for i, r in enumerate(reqs):
        it = I.by_name(r["item"])
        have = state.player.inventory.count(it) if it else 0
        can = gamereq.can_fulfil(state, r)
        bg = ui.SEL_BG if i == sel else ui.BASE_BG
        if i == sel:
            m.highlight(2 + row)
        days = r["expires"] - state.day
        m.text(2, 2 + row, ui.cur(i == sel) + f"{r['npc']}: {r['qty']} {r['item']}",
               fg=C.WHITE if can else C.DIM, bg=bg)
        m.text(w - 20, 2 + row, f"have {have:>2}",
               fg=(150, 210, 150) if can else (150, 110, 110), bg=bg)
        m.text(w - 10, 2 + row, f"{r['gold']}g", fg=C.GOLD_COLOR, bg=bg)
        row += 1
        m.text(4, 2 + row, f"\"{r['flavor']}\""[:w - 20], fg=C.DIM)
        m.text(w - 16, 2 + row, f"{days} day{'s' if days != 1 else ''} left",
               fg=(160, 150, 130))
        row += 2
    if proj is not None:
        d = content.PROJECTS[proj["id"]]
        i = len(reqs)
        m.text(2, 2 + row, f"── Village project: {d.name} "
               + "─" * max(0, w - 26 - len(d.name)), fg=_HDR)
        row += 1
        bg = ui.SEL_BG if i == sel else ui.BASE_BG
        if i == sel:
            m.highlight(2 + row)
        if proj["state"] == "building":
            mins = proj.get("ready_at", 0) - state.abs_minutes
            days = max(1, round(mins / 1440))
            m.text(2, 2 + row, ui.cur(i == sel)
                   + f"Beams are rising — finished in ~{days} day{'s' if days != 1 else ''}.",
                   fg=(200, 220, 160), bg=bg)
        else:
            gold_left, mats_left = gameproj.remaining(state, proj)
            need = " · ".join([f"{q} {it.name}" for it, q in mats_left[:3]]
                              + ([f"{gold_left}g"] if gold_left else []))
            m.text(2, 2 + row, ui.cur(i == sel)
                   + f"Contribute — needs {need}"[:w - 4], fg=C.WHITE, bg=bg)
        row += 1
        m.text(4, 2 + row, d.perk[:w - 8], fg=(232, 200, 120))
        row += 1
    m.footer(("↑↓ · Enter deliver/give (500g) · Space all-in gold · Esc" if proj
              else "↑↓ select   Enter deliver   Esc close")[:w - 4])


def render_eat(con: tcod.console.Console, state: GameState, sel: int) -> None:
    from ..game import skills
    from ..game.crafting import edible_items
    foods = edible_items(state)
    w, h = 50, min(C.SCREEN_H - 4, max(8, len(foods) + 6))
    body = h - 4
    m = ui.Modal(con, w, h, "Eat  (restores stamina & health)")
    if not foods:
        m.text(2, 2, "Nothing to eat — cook a dish (c) or gather eggs/milk.", fg=C.DIM)

    def row(i, dy, selected, bg):
        it, q, ql = foods[i]
        star = (" " + skills.stars(ql)) if ql else ""
        gain = round(it.energy * (1 + 0.12 * ql))
        hp = (max(1, gain // 6) if it.energy else 0) + it.heal
        # Show the boon up front, so a Hearty meal can be chosen on purpose.
        buff = f" ↯{skills.BUFFS[it.buff]}" if it.buff in skills.BUFFS else ""
        m.text(2, dy, ui.cur(selected) + f"{q:>2} {it.name}{star}{buff}"[:w - 22],
               fg=C.WHITE, bg=bg)
        m.text(w - 18, dy, f"+{gain} st  +{hp} hp", fg=(150, 210, 150), bg=bg)

    m.list(2, body, len(foods), sel, row, arrow_top=2, arrow_bottom=h - 3)
    m.footer("↑↓ select   Enter eat   Esc close")


def render_load_machine(con: tcod.console.Console, state: GameState, ctx) -> None:
    """Choose-what-to-make menu for an empty machine (jam vs pickles, which bar…).

    A chooser whose options carry a ``group`` is shown two-step: first the group
    names, then that group's options — so a hundred metal×base forge rows collapse
    to a short list you pick your way into, rather than one endless scroll."""
    if not ctx:
        return
    from ..game import crafting
    rows, is_group = crafting.load_rows(ctx)
    sel, name = ctx["sel"], ctx["name"]
    w, h = 66, min(C.SCREEN_H - 4, max(8, len(rows) + 6))
    body = h - 4
    group = ctx.get("group")
    title = (f"Load {name} — {group}" if group else f"Load {name}  (choose what to make)")
    m = ui.Modal(con, w, h, title)
    from_col = 30                # inputs column — clear of the (wider) label column
    price_col = w - 9

    if is_group:
        counts = {}
        for o in ctx["options"]:
            counts[o["group"]] = counts.get(o["group"], 0) + 1

        def row(i, dy, selected, bg):
            gname = rows[i]
            m.text(2, dy, ui.cur(selected) + gname[:from_col - 3], fg=C.WHITE, bg=bg)
            n = counts[gname]
            m.text(from_col, dy, f"{n} option{'s' if n != 1 else ''} →",
                   fg=(160, 180, 205), bg=bg)
        footer = "↑↓ select   Enter open   Esc cancel"
    else:
        def row(i, dy, selected, bg):
            opt = rows[i]
            out = opt["output"]
            ins = ", ".join(f"{q} {it.name}" for it, q in opt["inputs"])
            oq = opt.get("out_qty", 1)
            label = opt.get("label") or (f"{oq}x {out.name}" if oq > 1 else out.name)
            m.text(2, dy, ui.cur(selected) + label[:from_col - 3], fg=C.WHITE, bg=bg)
            m.text(from_col, dy, f"from {ins}"[:price_col - from_col - 1],
                   fg=(160, 180, 205), bg=bg)
            m.text(price_col, dy, f"{out.value}g", fg=C.GOLD_COLOR, bg=bg)
        footer = ("↑↓ select   Enter load   Esc back" if group
                  else "↑↓ select   Enter load   Esc cancel")
    m.list(2, body, len(rows), sel, row, arrow_top=2, arrow_bottom=h - 3)
    m.footer(footer)


def render_cheats(con: tcod.console.Console, state: GameState, sel: int, locations) -> None:
    c = state.cheats
    rows = [f"Freeze Health:  {'ON ' if c.get('freeze_hp') else 'off'}",
            f"Freeze Stamina: {'ON ' if c.get('freeze_stamina') else 'off'}",
            "Add 1000 gold",
            "Add 100 of each building material"]
    rows += [f"Teleport → {name}" for name, _ in locations]
    h = len(rows) + 6
    m = ui.Modal(con, 52, h, "★ Cheats (up up down down ...) ★")
    m.text(2, 1, "The Konami whisper opens a little door.", fg=C.DIM)
    for i, text in enumerate(rows):
        hot = (i == sel)
        m.text(2, 3 + i, ("→ " if hot else "  ") + text,
               fg=(250, 230, 140) if hot else (210, 210, 220))
    m.footer("↑↓ move · Enter select · Esc close")


def render_quit(con: tcod.console.Console, state: GameState) -> None:
    m = ui.Modal(con, 48, 9, "Leave Hollowmere Vale?")
    rows = [
        ("The game auto-saves each morning you sleep.", C.DIM),
        ("", C.WHITE),
        ("[S] / [Enter] / [Q]   Save and quit", (180, 230, 160)),
        ("[Backspace]           Quit without saving", (232, 178, 120)),
        ("[Esc]                 Keep playing", (210, 210, 220)),
    ]
    for i, (text, colour) in enumerate(rows):
        m.text(3, 2 + i, text, fg=colour)


def render_intro(con: tcod.console.Console, state: GameState) -> None:
    """The opening page shown when a new game begins — the premise and the
    handful of controls a new farmer needs before their first morning."""
    gold, key = (236, 226, 180), (150, 200, 230)
    w = min(C.SCREEN_W - 2, 68)
    h = min(C.SCREEN_H - 2, 27)
    m = ui.Modal(con, w, h, "Hearthdelve — Hollowmere Vale")
    y = 2
    letter = [
        "A letter, in a familiar hand:",
        "",
        "  \"The old farm in the Vale is yours now. The fields have gone",
        "   to grass and the tools to rust, but the soil is good and the",
        "   folk are kind. There's iron in the dark below, if you've the",
        "   nerve for it. Make something of the place. — your grandfather\"",
    ]
    for ln in letter:
        m.text(3, y, ln, fg=gold if ln.startswith("A letter") else C.DIM)
        y += 1
    y += 1
    for ln in (
        "By day, work the surface: till and plant, tend your beasts, chop",
        "and forage, and turn the harvest into goods worth trading.",
        "By dark, delve the dungeons below for ore, gems and coin — but",
        "mind the depth; it tires you, and it bites.",
        "Sell and gift it all back to the villages, and grow.",
    ):
        m.text(3, y, ln, fg=C.WHITE)
        y += 1
    y += 1
    m.text(3, y, "The essentials", fg=gold)
    y += 1
    for k, v in (
        ("Arrows / numpad", "move  (numpad 7 9 1 3 step diagonally)"),
        ("Space", "use the held tool on the tile you face"),
        ("g", "gather · harvest · open · interact"),
        ("1–9, 0", "pick a tool or seed     ·   s   sleep, end the day"),
        ("c  ·  b", "craft & build      ·   ship goods to sell"),
        ("l · Shift+C · f", "look · talk & shop · give a gift"),
        ("?", "the codex — full help, any time"),
    ):
        m.text(4, y, k, fg=key)
        m.text(4 + 18, y, v, fg=C.DIM)
        y += 1
    m.footer("Press any key to step onto the farm")


def render_storage(con: tcod.console.Console, state: GameState, side: str, sel: int) -> None:
    """Two columns — your pack on the left, the home chest on the right — with
    the active side's selection marked. Stored goods weigh nothing on your back."""
    from ..game import skills
    pack = state.player.inventory.slots
    store = state.storage.slots
    w = 66
    body = min(C.SCREEN_H - 7, max(6, len(pack), len(store)))
    m = ui.Modal(con, w, body + 5, "Storage Chest")
    colw = (w - 5) // 2
    x_pack, x_store = 2, 3 + colw
    apack = side == "pack"
    m.text(x_pack, 1, "YOUR PACK" + ("  ◂ on your back" if apack else ""),
           fg=ui.HDR if apack else C.DIM)
    m.text(x_store, 1, "CHEST" + ("  ◂ stored, weightless" if not apack else ""),
           fg=ui.HDR if not apack else C.DIM)

    def draw(slots, x0, active):
        if not slots:
            m.text(x0, 3, "(empty)", fg=C.DIM)
            return
        start, end = ui.window(sel, len(slots), body) if active else (0, min(len(slots), body))
        for r, (it, q, ql) in enumerate(slots[start:end]):
            selrow = active and (start + r) == sel
            cnt = f"x{q}" + ((" " + skills.stars(ql)) if ql else "")
            fg = C.WHITE if selrow else ((210, 208, 196) if active else C.DIM)
            m.text(x0, 3 + r, (ui.cur(selrow) if active else "  ") + it.name[:colw - len(cnt) - 3],
                   fg=fg)
            m.text(x0 + colw - len(cnt), 3 + r, cnt, fg=fg)

    draw(pack, x_pack, apack)
    draw(store, x_store, not apack)
    m.footer("↑↓ pick · ←→/Tab switch · Enter move · Space stow all · Esc close")


def render_confirm(con: tcod.console.Console, state: GameState,
                   title: str, prompt: str, detail: str = "") -> None:
    """A small yes/no prompt for an action that can't easily be undone."""
    lines = [prompt] + ([detail] if detail else [])
    w = min(C.SCREEN_W - 4, max(40, max(len(s) for s in lines) + 6))
    m = ui.Modal(con, w, 6 + (1 if detail else 0), title)
    m.text(3, 2, prompt, fg=C.WHITE)
    if detail:
        m.text(3, 3, detail, fg=(232, 200, 120))
    m.text(3, 4 + (1 if detail else 0), "[Y] / [Enter]  yes      [N] / [Esc]  no",
           fg=(180, 230, 160))


_HDR = ui.HDR
_KEY = (150, 200, 230)


def build_codex_pages(state: GameState):
    """Assemble the help/encyclopedia pages from the content registries.

    Returns a list of (title, rows) where each row is (text, color).
    """
    from ..data import content
    from ..world import tile

    pages: list[tuple[str, list[tuple[str, tuple]]]] = []

    # --- Page: Controls ------------------------------------------------------
    controls = [
        ("Movement", _HDR),
        ("  Arrow keys       move (up / down / left / right)", C.WHITE),
        ("  Numpad 1-9       move, including diagonals", C.WHITE),
        ("  Numpad 5  /  .   wait a turn (30s)", C.WHITE),
        ("  w then a dir     run until something / path ends / 50 tiles", C.WHITE),
        ("  w then .         rest until something happens (up to 1h)", C.WHITE),
        ("", C.WHITE),
        ("Commands", _HDR),
        ("  Space            use active tool on the highlighted tile", C.WHITE),
        ("                   (it turns green when the tool can act there)", C.DIM),
        ("  1-9              select hotbar tool / seed", C.WHITE),
        ("  g                gather / harvest / use a machine", C.WHITE),
        ("  t                aim & fire: a readied bow/sling, else a bomb", C.WHITE),
        ("  c                craft, build machines, cook dishes", C.WHITE),
        ("  p                site a carpenter building (opens aiming)", C.WHITE),
        ("  x                eat (restores stamina & health)", C.WHITE),
        ("  b                shipping bin (sell) — stand beside it", C.WHITE),
        ("                   (the market's cravings pay extra some days)", C.DIM),
        ("  Shift+C          talk to a villager / open a shop", C.WHITE),
        ("  f                give a villager a gift", C.WHITE),
        ("  g at ‡ board     village notice board — favours for gold &", C.WHITE),
        ("                   friendship, and the village's great project:", C.DIM),
        ("                   fund it in instalments for a lasting landmark", C.DIM),
        ("                   & perk (j → Projects shows them anywhere)", C.DIM),
        ("  > / <            descend / climb a dungeon (on stairs)", C.WHITE),
        ("  s                sleep in bed -> next day", C.WHITE),
        ("  i                inventory  (a-z select; Shift+D drops the stack)", C.WHITE),
        ("  e                equipment", C.WHITE),
        ("  m                message log (scrollback)", C.WHITE),
        ("  v                character sheet (level & skills)", C.WHITE),
        ("  j                journal (goals)", C.WHITE),
        ("  r                relationships", C.WHITE),
        ("  l                look around (read any tile)", C.WHITE),
        ("  ?                this help / encyclopedia", C.WHITE),
        ("  Esc              quit / close a screen", C.WHITE),
    ]
    pages.append(("Controls", controls))

    # --- Page: Land & Home ---------------------------------------------------
    landpg = [
        ("Land & Ownership", _HDR),
        ("", C.WHITE),
        ("Every patch of ground has an owner.", C.WHITE),
        ("", C.WHITE),
        ("  Your homestead", _KEY),
        ("      The land around your farm is granted freehold — yours,", C.WHITE),
        ("      and never taxed. Build and farm freely here.", C.DIM),
        ("  Village land", _KEY),
        ("      Cottages, farm plots and gardens belong to their", C.WHITE),
        ("      residents; shops and greens to the village. You may not", C.DIM),
        ("      build there, and taking a villager's crop, fruit or", C.DIM),
        ("      berries is theft — it costs karma and their regard.", C.DIM),
        ("      (You'll be asked to confirm before you take.)", C.DIM),
        ("  Wilderness", _KEY),
        ("      Ownerless. Till it, build on it, or fence it off to", C.WHITE),
        ("      CLAIM it as your own. Craft Fence Panels (c), then", C.DIM),
        ("      'Set Fence' to lay them — no need to close the ring:", C.DIM),
        ("      the fence outline bounds the plot (a U of 5-long sides", C.DIM),
        ("      claims the whole 5x5).", C.DIM),
        ("", C.WHITE),
        ("Land tax", _HDR),
        ("      The crown levies a small weekly tax on your claimed", C.WHITE),
        ("      wilderness. A notice arrives at your post box — open it", C.DIM),
        ("      (g at the box) to settle up. Ignoring the bill costs a", C.DIM),
        ("      little karma each week, but your gold and land are safe.", C.DIM),
    ]
    pages.append(("Land & Home", landpg))

    # --- Page: Tools & Equipment --------------------------------------------
    tools = [("Tools  (energy cost per use)", _HDR), ("", C.WHITE)]
    for it in content.ALL_TOOLS:
        s = content.TOOL_STATS[it]
        tools.append((f" {it.glyph}  {it.name}", _KEY))
        tstr = f"{s.seconds // 60}m" if s.seconds >= 60 else f"{s.seconds}s"
        tools.append((f"      {s.verb} {s.target} · {s.stamina} stamina · {tstr} · {s.yields}", C.WHITE))
        tools.append((f"      {it.desc}", C.DIM))
    tools.append(("", C.WHITE))
    tools.append(("Weapons  (hold one; bump to attack)", _HDR))
    tools.append(("", C.WHITE))
    for it in content.ALL_WEAPONS:
        w = content.WEAPON_STATS[it]
        lo, hi = w.dmg
        tools.append((f" {it.glyph}  {it.name}   {w.category}  hit {w.to_hit:+d}  dmg {lo}-{hi}"
                      + (f"  DV {w.dv:+d}" if w.dv else ""), _KEY))
        tools.append((f"      {it.desc}", C.DIM))
    tools.append(("", C.WHITE))
    tools.append(("Ranged  (equip in the ranged slot; aim & fire with t)", _HDR))
    tools.append(("", C.WHITE))
    for it in content.ALL_RANGED:
        rs = content.RANGED[it]
        lo, hi = rs.dmg
        tools.append((f" {it.glyph}  {it.name}   hit {rs.to_hit:+d}  dmg {lo}-{hi}"
                      f"  range {rs.rng}  ({rs.ammo.name.lower()}s)", _KEY))
        tools.append((f"      {it.desc}", C.DIM))
    tools.append(("Bombs need no bow — thrown by hand from the ammo slot.", C.DIM))
    tools.append(("", C.WHITE))
    tools.append(("Any tool can fight too (badly); a weapon can do a tool's job", C.DIM))
    tools.append(("with penalties — a battle axe fells trees, a blade clears brush.", C.DIM))
    tools.append(("Combat: 1d20 + to-hit vs the foe's DV; damage - its PV. Armour", C.DIM))
    tools.append(("gives PV; Dodge & mastery give DV. Land hits to master a weapon.", C.DIM))
    tools.append(("", C.WHITE))
    tools.append(("Materials & affixes", _HDR))
    tools.append(("Every weapon & armour is made of a material — copper..adamantium", C.DIM))
    tools.append(("for metal, leather/hide & cloth for soft gear, birch..composite", C.DIM))
    tools.append(("for bows. Finer material = better. Deeper dungeon loot trends to", C.DIM))
    tools.append(("finer stuff (with a pinch of luck), and may carry a prefix/suffix", C.DIM))
    tools.append(("(Fine, Masterwork, of Slaying, of Warding...). Smelt ore to bars,", C.DIM))
    tools.append(("then forge gear of that metal at an Anvil (build it with 'c').", C.DIM))
    tools.append(("", C.WHITE))
    tools.append(("Fuel, gems & jewellery", _HDR))
    tools.append(("Fuels have heat: wood < charcoal < coal < coke. A metal needs a", C.DIM))
    tools.append(("minimum heat to smelt at all, and hotter fuel smelts faster. A Kiln", C.DIM))
    tools.append(("chars wood into charcoal, or bakes coal into coke.", C.DIM))
    tools.append(("Mine rough gems (finer the deeper you dig) and crack Geodes; cut", C.DIM))
    tools.append(("them at a Gemcutting Station. At a Jeweller's Bench, set a cut gem", C.DIM))
    tools.append(("into a metal band for a Ring or Amulet (neck/ring slots), or embed", C.DIM))
    tools.append(("it into a weapon, armour, or tool. Ruby/Sapphire/Topaz aid combat;", C.DIM))
    tools.append(("Emerald/Amethyst aid your work; Diamond does a bit of everything.", C.DIM))
    pages.append(("Tools & Equipment", tools))

    # --- Page: Seeds & Crops -------------------------------------------------
    crops = [("Crops", _HDR), ("", C.WHITE)]
    for c in content.CROPS:
        regrow = "regrows" if c.regrows else "single harvest"
        crops.append((f" {c.glyph}  {c.name}", _KEY))
        crops.append((f"      {c.season}  ·  matures {c.days_to_mature}d  ·  {regrow}  ·  sells {c.sell_price}g",
                      C.WHITE))
        crops.append((f"      from {c.seed.name}.  {c.desc}", C.DIM))
    crops.append(("", C.WHITE))
    crops.append(("How to farm:", _HDR))
    crops.append(("  Till soil (Hoe) -> select seeds (6) -> Space to plant", C.WHITE))
    crops.append(("  -> water daily (Can) -> sleep -> harvest (g) when ripe.", C.WHITE))
    crops.append(("  Rain waters for you. Crops die out of season.", C.DIM))
    crops.append(("", C.WHITE))
    crops.append(("Orchard trees (buy saplings at the store):", _HDR))
    for t in content.TREES:
        crops.append((f"  {t.name} — bears {t.fruit.name.lower()} each {t.season}"
                      f" (~{t.days_to_mature}d to grow)", C.WHITE))
    crops.append(("  Plant a sapling (pouch), wait, then pick fruit (g).", C.DIM))
    pages.append(("Seeds & Crops", crops))

    # --- Page: Crafting & Machines ------------------------------------------
    craftp = [("Recipes  (press c)", _HDR), ("", C.WHITE),
              ("Cooking is learned: you start with the plain fare and pick up", C.WHITE),
              ("the rest around the Vale — friends share their favourite dish", C.DIM),
              ("at 3♥, taverns sell house recipes, practice sparks a few, and", C.DIM),
              ("a filled notice-board favour sometimes has one folded in.", C.DIM),
              ("", C.WHITE)]
    for r in content.RECIPES:
        ins = ", ".join(f"{q} {it.name}" for it, q in r.inputs)
        craftp.append((f" {r.name}", _KEY))
        if r.kind == "build":
            tag = "build"
        elif r.kind == "cook":
            from ..game import skills
            e = r.output.energy if r.output else 0
            bf = f", {skills.BUFFS[r.output.buff]}" if (r.output and r.output.buff in skills.BUFFS) else ""
            tag = f"cook (+{e} stamina{bf})"
        else:
            tag = "craft"
        craftp.append((f"      {tag}:  {ins}", C.WHITE))
    craftp.append(("", C.WHITE))
    craftp.append(("Machines  (g to load / collect)", _HDR))
    craftp.append(("", C.WHITE))
    for mdef in content.MACHINES.values():
        if mdef.kind == "site":
            continue                         # internal construction placeholder
        craftp.append((f" {mdef.glyph}  {mdef.name}", _KEY))
        extra = f"  (~{mdef.minutes // 60}h)" if mdef.minutes else ""
        craftp.append((f"      {mdef.desc}{extra}", C.DIM))
    craftp.append(("", C.WHITE))
    craftp.append(("Animals  (buy chicks/calves at the general store)", _HDR))
    craftp.append(("  Build a little coop yourself, or have Tomas the carpenter", C.DIM))
    craftp.append(("  raise a roomy coop, barn, or greenhouse (order it, press p to site it).", C.DIM))
    craftp.append(("  A greenhouse grows any crop year-round — winter farming!", C.DIM))
    craftp.append(("  Settle young animals with g; bump them to pet or collect.", C.DIM))
    craftp.append(("  Pet daily to keep them happy — happier beasts give finer", C.DIM))
    craftp.append(("  eggs & milk. Churn milk into cheese.", C.DIM))
    craftp.append(("  They graze free on grass in the growing seasons; in winter", C.DIM))
    craftp.append(("  (or a paved-in yard) they eat straw — scythe tall grass", C.DIM))
    craftp.append(("  (machete), dry it on a fair day, then fork it into the coop/", C.DIM))
    craftp.append(("  barn trough (g). They shelter by the coop in a storm.", C.DIM))
    craftp.append(("", C.WHITE))
    craftp.append(("Gather wood (axe), stone & ore+coal (pickaxe).", C.DIM))
    craftp.append(("Value ladder: raw crop < jam < wine.", C.DIM))
    pages.append(("Crafting & Machines", craftp))

    # --- Page: Fish ---------------------------------------------------------
    fishp = [("Fish  (face water, cast the rod)", _HDR), ("", C.WHITE)]
    for f in content.FISH:
        rarity = "common" if f.weight >= 25 else "uncommon" if f.weight >= 8 else "rare"
        when = "all year" if not f.seasons else "/".join(f.seasons)
        fishp.append((f" {f.item.glyph}  {f.item.name:<9} {f.item.value:>4}g  {rarity:<8} {when}", C.WHITE))
    fishp.append(("", C.WHITE))
    fishp.append(("Underground lakes  (fish while delving)", _HDR))
    for it, w in content.CAVE_FISH:
        rarity = "common" if w >= 25 else "uncommon" if w >= 8 else "rare"
        fishp.append((f" {it.glyph}  {it.name:<10} {it.value:>4}g  {rarity}", C.WHITE))
    fishp.append(("", C.WHITE))
    fishp.append(("Sell them, or cook Fish Stew / Grilled Trout for energy.", C.DIM))
    pages.append(("Fish", fishp))

    # --- Page: Terrain & Features -------------------------------------------
    notes = {
        "water": "fish with a rod", "tree": "passable; chop with an axe",
        "ore": "mine with a pickaxe", "wall": "impassable",
        "soil": "plant seeds here", "bed": "sleep to end the day",
        "bin": "drop goods to sell", "stairs": "enter a dungeon",
        "door": "an open doorway", "fence": "impassable",
        "foliage": "machete to clear (fibre)", "shrub": "machete to clear (fibre)",
        "shrub_berry": "pick berries (g); regrows in days",
    }
    terrain = [("Terrain & Features  ( · walkable / x blocked )", _HDR), ("", C.WHITE)]
    seen = set()
    for t in tile.TILES:
        if t.name in seen:
            continue
        seen.add(t.name)
        mark = "·" if t.walkable else "x"
        note = notes.get(t.kind, "")
        label = f" {t.glyph} {mark}  {t.name.replace('_', ' '):<13}"
        terrain.append((label + (f"  {note}" if note else ""), C.WHITE))
    pages.append(("Terrain & Features", terrain))

    # --- Page: Monsters ------------------------------------------------------
    mon = [("Monsters", _HDR), ("", C.WHITE)]
    for m in content.MONSTERS:
        mon.append((f" {m.glyph}  {m.name}   HP {m.hp}  DV {m.dv} PV {m.pv}  "
                    f"dmg {m.dmg[0]}-{m.dmg[1]}  from floor {m.min_depth}", _KEY))
        mon.append((f"      {m.behavior}, from floor {m.min_depth}. {m.desc}", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("Bump to attack. Aim & throw a Bomb (t) to hit several at once.", C.DIM))
    mon.append(("Slain cave beasts may drop reagents (gel, wing, hide).", C.DIM))
    mon.append(("Faint in the dark → hauled home, minus loose loot & 10% gold.", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("Underground", _HDR))
    mon.append((" ■  chests — open with g for gold, ore, gems", _KEY))
    mon.append((" τ  cave mushrooms — gather (g); cook a Mushroom Stew", _KEY))
    mon.append((" ^  traps — hidden until spotted; step around them", _KEY))
    mon.append((" ░  rubble — loose footing, slow to cross", _KEY))
    mon.append((" ♠î glimmerwood grove — rare glowing wispwood & glowcaps", _KEY))
    mon.append(("      (a peaceful find; glowcaps cook a rich Glowcap Broth)", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("Going deep", _HDR))
    mon.append(("  The rock hardens with every band: veins past floor 1 suit a", C.WHITE))
    mon.append(("  Bronze pick, floor 4+ Iron, floor 6+ Steel, floor 8+ better", C.DIM))
    mon.append(("  still. A softer pick still bites — just slow, tiring, and", C.DIM))
    mon.append(("  prone to mangling the vein into rubble. Bron forges upgrades.", C.DIM))
    mon.append(("  And the dark weighs on you: work and fighting tire you more", C.DIM))
    mon.append(("  with each floor down — pack food, and jewellery that spares", C.DIM))
    mon.append(("  your strength.", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("Foraging (surface)", _HDR))
    mon.append((" τ  field mushrooms — button & parasol, in open grass", _KEY))
    mon.append((" τ  forest mushrooms — bolete & chanterelle, under the woods", _KEY))
    mon.append(("      sprout in summer & autumn only; gather (g) to cook", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("Wildlife (surface)", _HDR))
    for c in content.WILDLIFE:
        diet = {"crops": "raids crops", "berries": "eats berries"}.get(c.diet, "harmless")
        mon.append((f" {c.glyph}  {c.name}   {c.behavior}, {diet}", _KEY))
        mon.append((f"      {c.desc}", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("Fence your fields — critters can't reach crops behind a fence.", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("The Westreach (walk off the map's western edge)", _HDR))
    mon.append(("  Volcanic hill country: ore-rich crags, sulphur & nitre on the", C.WHITE))
    mon.append(("  mountain, and beasts that hunt on sight. No bed, no fields —", C.DIM))
    mon.append(("  an expedition, not a stroll. Walk east to come home.", C.DIM))
    for c in content.WEST_WILDLIFE:
        mon.append((f" {c.glyph}  {c.name}   {c.behavior}", _KEY))
        mon.append((f"      {c.desc}", C.DIM))
    pages.append(("Monsters", mon))

    # --- Page: Villagers ----------------------------------------------------
    vp = [("Folk of Hollowmere Vale", _HDR), ("", C.WHITE)]
    for npc in state.world.npcs:
        role = {"general": "General Store", "blacksmith": "Blacksmith"}.get(npc.shop, "villager")
        vp.append((f" {npc.glyph}  {npc.name} — {role}", _KEY))
        loves = ", ".join(i.name for i in npc.loves) or "—"
        vp.append((f"      {'♥' * npc.hearts}{'·' * (10 - npc.hearts)}   loves: {loves}", C.DIM))
    vp.append(("", C.WHITE))
    vp.append(("Shift+C talk · f gift. Mossford is the hamlet; Cinderhope the outpost.", C.DIM))
    vp.append(("Gifts they love raise friendship most (one gift each per day).", C.DIM))
    pages.append(("Villagers", vp))

    return pages


_codex_cache: list | None = None
_codex_sig: tuple | None = None


def render_codex(con: tcod.console.Console, state: GameState, page: int, scroll: int) -> None:
    # The pages are almost entirely static content; only the Villagers page moves
    # (friendship hearts). Rebuild solely when that signature changes, rather than
    # re-walking every crop/tool/recipe/machine on every frame the help is open.
    global _codex_cache, _codex_sig
    sig = tuple((n.name, n.friendship) for n in state.world.npcs)
    if _codex_cache is None or sig != _codex_sig:
        _codex_cache, _codex_sig = build_codex_pages(state), sig
    pages = _codex_cache
    page %= len(pages)
    title, rows = pages[page]

    w, h = 66, 44
    body_h = h - 5
    m = ui.Modal(con, w, h, f"Encyclopedia — {title}")

    max_scroll = max(0, len(rows) - body_h)
    scroll = max(0, min(scroll, max_scroll))
    for i in range(body_h):
        idx = scroll + i
        if idx >= len(rows):
            break
        text, color = rows[idx]
        m.text(2, 2 + i, text[:w - 4], fg=color)
    m.arrows(scroll > 0, scroll < max_scroll, 2, h - 3)
    m.footer(f" ← → page {page + 1}/{len(pages)}   ↑ ↓ scroll   Esc close ")


# Inventory categories, in the order they're listed (ADOM-style grouping).
_INV_ORDER = ("Cooked Food", "Animal Produce", "Artisan Goods", "Fruit", "Vegetables",
              "Flowers", "Fish", "Materials", "Seeds & Saplings", "Livestock",
              "Consumables", "Misc")


def _inv_category(item) -> str:
    from ..data import content
    k = item.kind
    simple = {"food": "Cooked Food", "animal": "Animal Produce", "artisan": "Artisan Goods",
              "fish": "Fish", "material": "Materials", "livestock": "Livestock",
              "bomb": "Consumables"}
    if k in simple:
        return simple[k]
    if k in ("seed", "sapling", "pouch"):
        return "Seeds & Saplings"
    if k == "crop":
        if content.is_fruit(item):
            return "Fruit"
        if content.PRODUCE_CATEGORY.get(item) == "flower":
            return "Flowers"
        return "Vegetables"
    return "Misc"


def inv_sort_key(item, quality: int):
    cat = _inv_category(item)
    rank = _INV_ORDER.index(cat) if cat in _INV_ORDER else len(_INV_ORDER)
    return (rank, cat, item.name, quality)


# ADOM-flavoured palette for the list screens.
_LETTER_FG = (224, 186, 108)      # item/slot selector letters
_SECTION_FG = (208, 146, 86)      # category / slot names
_BRACKET_FG = (140, 140, 152)     # right-hand [qty]/[tier] column
_CAP_FG = (150, 200, 150)         # the capacity/summary line
_FOOT_FG = (232, 192, 112)        # footer key hints
_INV_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def inv_letter(i: int) -> str:
    return _INV_LETTERS[i] if i < len(_INV_LETTERS) else " "


def render_inventory(con: tcod.console.Console, state: GameState, sel: int = 0) -> None:
    from ..game import skills
    slots = state.player.inventory.slots

    # Build the display list ADOM-style: a category header (with the group's
    # glyph in quotes) before each run of items, then the items themselves.
    rows: list = []                                  # ("head", cat, glyph) | ("item", slot_index)
    prev = None
    for i, (it, _q, _ql) in enumerate(slots):
        cat = _inv_category(it)
        if cat != prev:
            rows.append(("head", cat, it.glyph))
            prev = cat
        rows.append(("item", i))

    w, h = 62, min(C.SCREEN_H - 2, max(9, len(rows) + 5))
    body = h - 4
    m = ui.Modal(con, w, h, "PACK")
    from ..game import encumbrance as enc
    total = sum(q for _it, q, _ql in slots)
    etier = enc.tier(state)
    lbl = f"  ({enc.TIER_LABEL[etier]})" if etier else ""
    m.text(2, 1, f"Carrying {total} item(s)  ·  ⚖ {enc.carried_weight(state):.0f}/"
                 f"{enc.capacity(state):.0f}{lbl}",
           fg=(_CAP_FG, C.WARN_COLOR, C.DANGER_COLOR)[etier])
    gold = f"Gold: {state.player.gold}g"
    m.text(w - 2 - len(gold), 1, gold, fg=C.GOLD_COLOR)

    if not slots:
        m.text(2, 3, "(empty — grow and forage to fill it)", fg=C.DIM)
    else:
        sel = max(0, min(sel, len(slots) - 1))
        sel_row = next((r for r, rw in enumerate(rows) if rw[0] == "item" and rw[1] == sel), 0)
        start, end = ui.window(sel_row, len(rows), body)
        for r in range(start, end):
            dy = 3 + (r - start)
            rw = rows[r]
            if rw[0] == "head":
                m.text(2, dy, f"{rw[1]}  ('{rw[2]}')", fg=_SECTION_FG)
                continue
            i = rw[1]
            it, qty, ql = slots[i]
            picked = (i == sel)
            bg = ui.SEL_BG if picked else ui.BASE_BG
            if picked:
                m.highlight(dy)
            m.text(3, dy, f"{inv_letter(i)} -", fg=_LETTER_FG, bg=bg)
            star = ("  " + skills.stars(ql)) if ql else ""
            m.text(8, dy, f"{it.glyph} {it.name}{star}", fg=C.WHITE, bg=bg)
            qs = f"[x{qty}]"
            m.text(w - 2 - len(qs), dy, qs, fg=_BRACKET_FG, bg=bg)
        m.arrows(start > 0, end < len(rows), 2, h - 3, dx=-3, glyphs=("↑", "↓"))
    m.footer("[a-z] pick  [⇧D] drop  [e] equipment  [Esc] close", fg=_FOOT_FG)


_SLOT_LABEL = {"head": "Head", "body": "Body", "cloak": "Cloak", "hands": "Gauntlets",
               "waist": "Girdle", "legs": "Legs", "feet": "Feet", "shield": "Shield",
               "neck": "Amulet", "ring1": "Ring", "ring2": "Ring",
               "ranged": "Ranged", "ammo": "Ammo"}
# Worn slots in paperdoll order. Each is addressed on the equipment screen by a
# letter (a, b, …), continuing into the carried-gear list — one letter namespace
# for both take-off and equip. Shared with main's equipment-screen handler.
PAPERDOLL_SLOTS = ("head", "body", "cloak", "hands", "waist", "legs", "feet",
                   "shield", "neck", "ring1", "ring2", "ranged", "ammo")


def equippables(state: GameState) -> list:
    """Carried gear the equipment screen equips by letter: weapons, armour,
    jewellery, ranged launchers, and ammunition."""
    return [(it, q, ql) for it, q, ql in state.player.inventory.slots
            if it.kind in ("weapon", "armor", "jewelry", "ranged", "ammo", "bomb")]


def _jewel_desc(it, quality: int) -> str:
    """A short effect tag for a worn ring/amulet, scaled by its star quality."""
    from ..data import content
    from ..game import skills
    eff = content.JEWEL_EFFECT.get(it, {})
    qm = skills.value_mult(quality)
    def r(k):
        return eff.get(k, 0.0) * qm
    parts = []
    if r("dmg"):    parts.append(f"+{round(r('dmg'))} dmg")
    if r("to_hit"): parts.append(f"+{round(r('to_hit'))} hit")
    if r("dv"):     parts.append(f"+{round(r('dv'))} DV")
    if r("pv"):     parts.append(f"+{round(r('pv'))} PV")
    if r("crit"):   parts.append(f"+{round(r('crit') * 100)}% crit")
    if r("yield"):  parts.append(f"+{round(r('yield') * 100)}% yield")
    if r("energy"): parts.append(f"-{round(r('energy'))} energy")
    return "[" + ", ".join(parts) + "]" if parts else ""


def render_equipment(con: tcod.console.Console, state: GameState) -> None:
    from ..data import content
    from ..game import combat, skills
    p = state.player
    gear = equippables(state)
    nslots = len(PAPERDOLL_SLOTS)
    w, h = 60, min(C.SCREEN_H - 2, 8 + nslots + len(gear))   # stats + in-hand + worn slots + 2 headers + gear + footer
    m = ui.Modal(con, w, h, "PERSONAL EQUIPMENT")

    dv, pv, th = combat.player_dv(state), combat.player_pv(state), combat.player_to_hit(state)
    m.text(2, 1, f"DV {dv}   PV {pv}   To-hit {th:+d}", fg=_CAP_FG)
    g = f"Gold: {p.gold}g"
    m.text(w - 2 - len(g), 1, g, fg=C.GOLD_COLOR)

    # what's in hand doubles as your weapon
    prof = combat.held_profile(state)
    lo, hi = prof.dmg
    ml = skills.mastery_level(state, prof.category)
    row = 3
    m.text(2, row, "In hand", fg=_SECTION_FG)
    m.text(12, row, f": {p.display_name(p.active_tool) if p.active_tool else '-'}"
           f"  ({prof.category} {lo}-{hi}, mastery {ml})"[:w - 14], fg=C.WHITE)
    row += 1
    # Worn paperdoll (armour, jewellery, ranged/ammo). Each slot is lettered; the
    # letters continue into the carried list below — one namespace for both.
    for i, slot in enumerate(PAPERDOLL_SLOTS):
        it = p.equipment.get(slot)
        if slot == "ammo":
            n = p.inventory.count(it) if it else 0
            val = f"{it.name} x{n}" if it else "-"
        elif slot == "ranged":
            rs = content.ranged_stat(it) if it else None
            val = f"{it.name}  [dmg {rs.dmg[0]}-{rs.dmg[1]}, range {rs.rng}]" if rs else (
                it.name if it else "- (none yet)")
        elif slot in ("neck", "ring1", "ring2"):
            q = p.equip_quality.get(slot, 0)
            star = (" " + skills.stars(q)) if q else ""
            val = f"{it.name}{star}  {_jewel_desc(it, q)}" if it else "-"
        else:
            st = content.ARMOR_STATS.get(it)
            val = f"{it.name}  [DV {st[0]:+d}, PV +{st[1]}]" if (it and st) else "-"
            if slot == "shield" and it and content.is_two_handed(p.active_tool):
                val += "  (unused — two-handed weapon)"
        m.text(2, row, f"{inv_letter(i)} {_SLOT_LABEL[slot]}", fg=_SECTION_FG if it else C.DIM)
        m.text(14, row, ": " + val, fg=C.WHITE if it else C.DIM)
        row += 1

    row += 1
    m.text(2, row, "Carried gear — press a letter to equip / take off:", fg=_HDR)
    row += 1
    for i, (it, _q, _ql) in enumerate(gear):
        if row >= h - 2:
            break
        st = content.ARMOR_STATS.get(it)
        rs = content.ranged_stat(it)
        if it.kind == "jewelry":
            tag = _jewel_desc(it, _ql)
        elif st:
            tag = f"[DV {st[0]:+d}, PV +{st[1]}]"
        elif rs:
            tag = f"ranged  dmg {rs.dmg[0]}-{rs.dmg[1]}, range {rs.rng}"
        elif it.kind in ("ammo", "bomb"):
            tag = "ammo"
        else:
            pr = content.profile_of(it)
            tag = f"{pr.category}, dmg {pr.dmg[0]}-{pr.dmg[1]}"
        m.text(3, row, f"{inv_letter(nslots + i)} - {it.glyph} {it.name}", fg=C.WHITE)
        m.text(34, row, tag, fg=_BRACKET_FG)
        row += 1
    m.footer("[letter] equip / take off  [i] pack  [Esc] close", fg=_FOOT_FG)


def render_craft(con: tcod.console.Console, state: GameState, sel: int) -> None:
    from ..data import content
    from ..game import crafting

    recipes = crafting.visible_recipes(state)
    labels = [{"build": "Build", "cook": "Cook"}.get(r.kind, "Craft") for r in recipes]
    # Interleave category headers with the recipes into display rows, then show
    # a scrolling window — with every recipe learned the list far outgrows the
    # screen, and unscrolled rows used to clip silently past the frame.
    rows: list[tuple] = []            # ("hdr", label) | ("recipe", recipe, index)
    sel_row = 0
    last_label = None
    for i, r in enumerate(recipes):
        if labels[i] != last_label:
            last_label = labels[i]
            rows.append(("hdr", last_label))
        if i == sel:
            sel_row = len(rows)
        rows.append(("recipe", r, i))

    w = 56
    h = min(C.SCREEN_H - 2, len(rows) + 4)
    body = h - 4
    m = ui.Modal(con, w, h, "Craft  (build machines & cook)")
    start, end = ui.window(sel_row, len(rows), body)
    for row, entry in enumerate(rows[start:end]):
        dy = 2 + row
        if entry[0] == "hdr":
            m.text(2, dy, entry[1], fg=_HDR)
            continue
        _kind, r, i = entry
        ok = crafting.has_inputs(state, r)
        marker = "▸" if i == sel else " "
        color = C.WHITE if ok else C.DIM
        bg = ui.SEL_BG if i == sel else ui.BASE_BG
        if i == sel:
            m.highlight(dy)
        m.text(2, dy, f"{marker} {r.name}", fg=color, bg=bg)
        m.text(22, dy, f"[{crafting.inputs_str(r)}]"[:w - 24],
               fg=(160, 200, 150) if ok else (150, 110, 110), bg=bg)
    m.arrows(start > 0, end < len(rows), 2, h - 3)

    total_cook = sum(1 for r in content.RECIPES if r.kind == "cook")
    known = sum(1 for r in recipes if r.kind == "cook")
    hint = " — friends & taverns teach more" if known < total_cook else ""
    m.footer(f"↑↓ · Enter make · Esc · recipes {known}/{total_cook}{hint}"[:w - 4])


def render_ship(con: tcod.console.Console, state: GameState, sel: int) -> None:
    from ..game import crafting

    from ..game import skills
    from ..game import requests as gamereq
    items_ = crafting.sellable_items(state)
    pending = sum(crafting.bin_value(state, it, ql) * q for it, q, ql in state.ship_bin.slots)
    boom = state.demand if state.demand and state.day < state.demand.get("until", 0) else {}
    w, h = 52, max(8, len(items_) + 7 + (1 if boom else 0))
    m = ui.Modal(con, w, h, "Shipping Bin  (sells overnight)")
    top = 2
    if boom:
        pct = int(round((boom["mult"] - 1) * 100))
        banner = f"★ The market craves {gamereq.DEMAND_KINDS[boom['kind']]} (+{pct}%)!"
        m.text(2, top, banner[:w - 4], fg=(232, 200, 120))
        top += 1

    if not items_:
        m.text(2, top, "Nothing to sell — grow and gather first.", fg=C.DIM)
    sel = max(0, min(sel, len(items_) - 1)) if items_ else 0   # keep the cursor on-list as it shrinks
    for i, (it, q, ql) in enumerate(items_):
        marker = "▸" if i == sel else " "
        bg = ui.SEL_BG if i == sel else ui.BASE_BG
        if i == sel:
            m.highlight(top + i)
        star = (" " + skills.stars(ql)) if ql else ""
        hot = boom and it.kind == boom["kind"]
        m.text(2, top + i, f"{marker} {q:>3}  {it.name}{star}", fg=C.WHITE, bg=bg)
        m.text(w - 12, top + i, f"{crafting.bin_value(state, it, ql)}g ea",
               fg=(250, 220, 110) if hot else C.GOLD_COLOR, bg=bg)

    m.text(2, h - 3, f"In bin (sells tonight): {pending}g", fg=C.GOLD_COLOR)
    m.footer("↑↓ select · Enter stack · Space all · Esc close")


_JOURNAL_TABS = ("Goals", "Favours", "Market", "Homestead", "Projects")


def render_journal(con: tcod.console.Console, state: GameState, tab: int = 0) -> None:
    """The journal, in four pages (←→): quest goals, the open notice-board
    favours, the market's mood, and a homestead status overview — the planning
    surfaces that used to require a walk across the map."""
    from ..data import content
    from ..game import quests
    tab %= len(_JOURNAL_TABS)
    rows: list[tuple[int, str, tuple]] = []      # (indent, text, color)

    if tab == 0:
        for q in content.QUESTS:
            ok = q.id in state.quests_done
            mark = "✔" if ok else "○"
            note = "done" if ok else q.desc
            rows.append((0, f" {mark} {q.title:<20.20s}{note}  (+{q.gold}g)",
                         (150, 205, 150) if ok else C.WHITE))
    elif tab == 1:
        if not state.requests:
            rows.append((0, "The notice boards are bare today — favours come and go.", C.DIM))
        from ..game import requests as gamereq
        from ..entities import items as I
        for r in state.requests:
            it = I.by_name(r["item"])
            have = state.player.inventory.count(it) if it else 0
            can = gamereq.can_fulfil(state, r)
            days = r["expires"] - state.day
            rows.append((0, f"{r['npc']}: {r['qty']} {r['item']}  ·  {r['gold']}g  ·  "
                            f"{days} day{'s' if days != 1 else ''} left",
                         C.WHITE if can else C.DIM))
            rows.append((2, f"have {have}/{r['qty']} — deliver at a village notice board (g)",
                         (150, 210, 150) if can else C.DIM))
        rows.append((0, "", C.WHITE))
        rows.append((0, "Favours pay over the odds and warm a friendship.", C.DIM))
    elif tab == 2:
        from ..game.requests import DEMAND_KINDS
        d = state.demand
        if d and state.day < d.get("until", 0):
            pct = int(round((d["mult"] - 1) * 100))
            left = d["until"] - state.day
            rows.append((0, f"★ The market craves {DEMAND_KINDS[d['kind']]}: +{pct}% at the bin.",
                         (232, 200, 120)))
            rows.append((2, f"~{left} more day{'s' if left != 1 else ''} — ship while it lasts.",
                         C.WHITE))
        else:
            rows.append((0, "No particular craving — goods sell at their usual prices.", C.WHITE))
        rows.append((0, "", C.WHITE))
        rows.append((0, "Cravings come and go with the morning post; the shipping", C.DIM))
        rows.append((0, "bin pays the marked-up price the night you ship.", C.DIM))
    elif tab == 4:
        from ..game import projects as gameproj
        from ..data import content as _c
        for proj in state.projects:
            d = _c.PROJECTS[proj["id"]]
            if proj["state"] == "done":
                rows.append((0, f" ✔ {d.name}", (150, 205, 150)))
                rows.append((2, d.perk, (232, 200, 120)))
            elif proj["state"] == "building":
                days = max(1, round((proj.get("ready_at", 0) - state.abs_minutes) / 1440))
                rows.append((0, f" ▧ {d.name} — rising, ~{days} day{'s' if days != 1 else ''}",
                             (200, 220, 160)))
                rows.append((2, d.perk, C.DIM))
            else:
                gold_left, mats_left = gameproj.remaining(state, proj)
                need = " · ".join([f"{q} {it.name}" for it, q in mats_left[:3]]
                                  + ([f"{gold_left}g"] if gold_left else []))
                rows.append((0, f" ○ {d.name}  ({proj['village']})", C.WHITE))
                rows.append((2, f"needs {need}"[:56], C.DIM))
                rows.append((2, d.perk, C.DIM))
            rows.append((0, "", C.WHITE))
        rows.append((0, "Contribute at that village's notice board (g).", C.DIM))
    else:
        surf = state.surface
        now = state.abs_minutes
        if surf is None:
            rows.append((0, "No homestead yet.", C.DIM))
        else:
            from ..data.content import MACHINES
            ready, working, idle, soonest = [], 0, 0, None
            for m in surf.machines.values():
                mdef = MACHINES.get(m.kind)
                if mdef is None or m.kind in ("coop_small", "coop_big", "barn", "pen", "site"):
                    continue
                st = m.status(now)
                if st == "done":
                    ready.append(f"{mdef.name}: {m.loaded_output.name}")
                elif st == "working":
                    working += 1
                    if soonest is None or m.ready_at < soonest[0]:
                        soonest = (m.ready_at, mdef.name, m.loaded_output.name if m.loaded_output else "?")
                else:
                    idle += 1
            rows.append((0, "Machines", _HDR))
            for line in ready[:8]:
                rows.append((2, f"✔ {line} — ready!", (250, 220, 110)))
            if len(ready) > 8:
                rows.append((2, f"…and {len(ready) - 8} more ready.", (250, 220, 110)))
            rows.append((2, f"{working} working · {idle} idle", C.WHITE))
            if soonest is not None:
                from ..game.crafting import _fmt_remaining
                rows.append((2, f"next: {soonest[1]} ({soonest[2]}) in {_fmt_remaining(soonest[0] - now)}",
                             C.DIM))
            growing = ripe = dry = dead = 0
            for plot in surf.crops.values():
                if plot.dead:
                    dead += 1
                elif plot.mature:
                    ripe += 1
                else:
                    growing += 1
                    if not plot.watered and not plot.crop.paddy:
                        dry += 1
            rows.append((0, "", C.WHITE))
            rows.append((0, "Fields", _HDR))
            rows.append((2, f"{ripe} ripe · {growing} growing ({dry} need water)"
                            + (f" · {dead} withered" if dead else ""),
                         (224, 180, 120) if dry else C.WHITE))
            fruiting = sum(1 for tr in surf.trees.values() if tr.has_fruit)
            if surf.trees:
                rows.append((2, f"{fruiting} of {len(surf.trees)} trees bearing fruit", C.WHITE))
            if surf.animals:
                waiting = sum(1 for a in surf.animals if a.produce_ready)
                rows.append((0, "", C.WHITE))
                rows.append((0, "Animals", _HDR))
                rows.append((2, f"{len(surf.animals)} in your care · {waiting} with produce waiting",
                             C.WHITE))

    done, total = quests.progress(state)
    title = (f"Journal — Goals ({done}/{total})" if tab == 0
             else f"Journal — {_JOURNAL_TABS[tab]}")
    w = 62
    h = min(C.SCREEN_H - 4, max(10, len(rows) + 6))
    m = ui.Modal(con, w, h, title)
    tabs = "   ".join((f"[{n}]" if i == tab else f" {n} ") for i, n in enumerate(_JOURNAL_TABS))
    m.text(2, 1, tabs[:w - 4], fg=(224, 204, 128))
    body = h - 5
    for row, (indent, text, color) in enumerate(rows[:body]):
        m.text(2 + indent, 3 + row, text[:w - 4 - indent], fg=color)
    m.footer("← → page   j / Esc close")


_SPOT_LABEL = {"home": "at home", "work": "at work", "inn": "at the inn",
               "temple": "at the temple", "square": "about the square"}


def render_relationships(con: tcod.console.Console, state: GameState, scroll: int = 0) -> None:
    from ..data import content
    from ..game import village
    met = [n for n in state.surface.npcs if n.met] if state.surface else []
    w = 62
    h = min(C.SCREEN_H - 4, max(8, len(met) * 4 + 5))
    m = ui.Modal(con, w, h, "Relationships")
    if not met:
        m.text(2, 2, "You haven't met anyone yet.", C.WHITE)
        m.text(2, 3, "Visit a village and talk (Shift+C).", C.DIM)
    body = h - 4
    hour = (state.time_minutes // 60) % 24
    lines: list[tuple[int, str, tuple]] = []
    for n in met:
        hearts = "♥" * n.hearts + "·" * (10 - n.hearts)
        spot = village.scheduled_spot(n, hour, state.weather, state.season,
                                      state.day_of_season)
        where = _SPOT_LABEL.get(spot, "out and about")
        prog = "" if n.hearts >= 10 else f" {n.friendship % 100:>2d}%"
        tag = "  ✓ gift" if getattr(n, "gifted_today", False) else ""
        lines.append((0, f" {n.glyph} {n.name:<13.13s}{hearts}{prog}{tag}   {where}"[:w - 2],
                      n.color))
        lines.append((2, f"{n.village} · {n.bio}"[:w - 8], C.DIM))
        loves = ", ".join(it.name for it in n.loves) or "—"
        lines.append((2, f"loves: {loves}"[:w - 8], (220, 170, 170)))
        # If a loved dish is a cookable recipe you don't know, they'll share it.
        teach = next((it.name for it in n.loves if it.kind == "food"
                      and (r := content.recipe_for_dish(it)) is not None
                      and r.name not in state.known_recipes), None)
        if teach:
            note = (f"will share their {teach.lower()} recipe (at 3♥)" if n.hearts < 3
                    else f"talk to them — they'll share their {teach.lower()} recipe!")
            lines.append((2, note[:w - 8], (232, 200, 120)))
        else:
            lines.append((2, "", C.DIM))
    scroll = max(0, min(scroll, max(0, len(lines) - body)))
    for row, (indent, text, color) in enumerate(lines[scroll:scroll + body]):
        if text:
            m.text(2 + indent, 2 + row, text, fg=color)
    m.arrows(scroll > 0, scroll + body < len(lines), 2, h - 3)
    m.footer("r / Esc to close")


def render_character(con: tcod.console.Console, state: GameState) -> None:
    from ..game import skills, karma
    p = state.player
    w, h = 50, 12 + len(skills.SKILLS)          # skills list from row 10; grow to fit all of them
    m = ui.Modal(con, w, h, f"Character — Level {p.level}")
    nxt = skills.xp_to_next(p.level)
    xpbar = "█" * int(10 * p.xp / nxt) + "·" * (10 - int(10 * p.xp / nxt))
    m.text(2, 2, f"XP  {xpbar}  {p.xp}/{nxt}", fg=(210, 205, 150))
    m.text(2, 3, f"♥ HP      {p.hp}/{p.max_hp}", fg=C.HP_COLOR)
    m.text(2, 4, f"✦ Stamina {p.energy}/{p.max_energy}", fg=C.ENERGY_COLOR)
    m.text(2, 5, f"⛁ Gold    {p.gold}g", fg=C.GOLD_COLOR)
    m.text(2, 6, f"⚔ Weapon  {p.weapon.name if p.weapon else '-'}", fg=C.WHITE)
    ksign = f"+{p.karma}" if p.karma > 0 else str(p.karma)
    kcol = (160, 220, 160) if p.karma >= 8 else (220, 150, 140) if p.karma <= -8 else C.WHITE
    m.text(2, 7, f"☯ Karma   {ksign} ({karma.label(p.karma)})", fg=kcol)
    m.text(2, 9, "Skills", fg=_HDR)
    for i, s in enumerate(skills.SKILLS):
        lvl = skills.skill_level(state, s)
        xp = p.skills.get(s, 0)
        if lvl >= skills.MAX_LEVEL:
            bar = "█" * 10
        else:
            into = xp - lvl * skills.XP_PER_LEVEL
            filled = int(10 * into / skills.XP_PER_LEVEL)
            bar = "█" * filled + "·" * (10 - filled)
        m.text(2, 10 + i, f"{s:<9} L{lvl:<2} {bar}", fg=C.WHITE if lvl else C.DIM)
    m.footer("v / Esc to close")


def render_dialogue(con: tcod.console.Console, state: GameState, npc, line: str) -> None:
    parts = line.split("\n")                          # blurbs may be multi-line verse
    w = min(72, max(54, max((len(p) for p in parts), default=0) + 6))
    h = len(parts) + 7
    m = ui.Modal(con, w, h, f"{npc.name}")
    hearts = "♥" * npc.hearts + "·" * (10 - npc.hearts)
    m.text(2, 2, hearts, fg=(220, 130, 150))
    for i, part in enumerate(parts):
        m.text(2, 4 + i, part[:w - 4], fg=C.WHITE)
    m.footer("f to gift · any key to close")


def render_shop(con: tcod.console.Console, state: GameState, npc, sel: int, line: str = "") -> None:
    from ..game import village
    from ..data import content
    from ..entities import items as I

    shop = village.npc_shop(state, npc)
    entries = village.shop_entries(shop, state, npc)
    title = {"general": "General Store", "blacksmith": "Blacksmith",
             "tavern": "Tavern", "carpenter": "Carpentry",
             "trader": "Wagon"}.get(shop, "Shop")
    header = line.split("\n") if line else []             # the keeper's greeting
    w = 68 if shop == "carpenter" else 56
    h = min(C.SCREEN_H - 4, len(entries) + 6 + len(header))
    m = ui.Modal(con, w, h, f"{npc.name}'s {title}")
    p = state.player
    top = 2
    for hl in header:                                     # innkeeper's greeting
        m.text(2, top, hl[:w - 4], fg=(210, 205, 190))
        top += 1
    body = (h - 2) - top                                  # rows for the (scrolling) list

    def row(i, dy, selected, rowbg):
        e = entries[i]
        pre = ui.cur(selected)
        afford = p.gold >= e.price
        if e.kind == "meal":
            gains = f"+{e.stam}st" + (f" +{e.hp}hp" if e.hp else "")
            m.text(2, dy, pre + e.label, fg=C.WHITE if afford else C.DIM, bg=rowbg)
            m.text(w - 20, dy, gains, fg=(150, 210, 150), bg=rowbg)
            m.text(w - 8, dy, f"{e.price}g", fg=C.GOLD_COLOR if afford else C.DIM, bg=rowbg)
        elif e.kind == "buy":
            m.text(2, dy, pre + e.item.name, fg=C.WHITE if afford else C.DIM, bg=rowbg)
            m.text(w - 10, dy, f"{e.price}g", fg=C.GOLD_COLOR if afford else C.DIM, bg=rowbg)
        elif e.kind == "contest":
            m.text(2, dy, pre + f"Enter the produce contest ({e.name})"[:w - 12],
                   fg=(232, 200, 120), bg=rowbg)
            m.text(w - 8, dy, "fair!", fg=(232, 200, 120), bg=rowbg)
        elif e.kind == "tradebuy":
            m.text(2, dy, pre + e.item.name[:w - 14],
                   fg=(232, 200, 120) if afford else C.DIM, bg=rowbg)
            m.text(w - 10, dy, f"{e.price}g", fg=C.GOLD_COLOR if afford else C.DIM, bg=rowbg)
        elif e.kind == "recipe":
            m.text(2, dy, pre + f"Recipe: {e.name}",
                   fg=(232, 200, 120) if afford else C.DIM, bg=rowbg)
            m.text(w - 10, dy, f"{e.price}g", fg=C.GOLD_COLOR if afford else C.DIM, bg=rowbg)
        elif e.kind == "sellto":
            from ..game import skills
            star = (" " + skills.stars(e.quality)) if e.quality else ""
            m.text(2, dy, pre + f"Sell {e.item.name}{star}", fg=(200, 220, 160), bg=rowbg)
            m.text(w - 10, dy, f"+{e.price}g", fg=C.GOLD_COLOR, bg=rowbg)
        elif e.kind == "cancel_build":
            m.text(2, dy, pre + "Cancel current order", fg=(224, 180, 120), bg=rowbg)
            m.text(w - 12, dy, "refund", fg=(190, 180, 150), bg=rowbg)
        elif e.kind in ("commission", "housejob"):
            matstr = ", ".join(f"{q} {it.name.split()[0].lower()}" for it, q in e.mats)
            can = afford and all(p.inventory.count(it) >= q for it, q in e.mats)
            m.text(2, dy, pre + e.label, fg=C.WHITE if can else C.DIM, bg=rowbg)
            m.text(28, dy, matstr[:w - 40], fg=(190, 180, 150) if can else C.DIM, bg=rowbg)
            m.text(w - 10, dy, f"{e.price}g", fg=C.GOLD_COLOR if can else C.DIM, bg=rowbg)
        else:  # upgrade
            tier = p.tool_tier.get(e.tool, 0)
            if tier >= len(C.TOOL_TIERS) - 1:
                txt, cost = f"{e.tool.name}: Mithril (max)", ""
                col = C.DIM
            else:
                gold, bar, count = village.upgrade_price(state, tier)
                txt = f"{e.tool.name}: {C.TOOL_TIERS[tier]}→{C.TOOL_TIERS[tier + 1]}"
                cost = f"{gold}g +{count} {bar.name.split()[0]}"
                affordable = p.gold >= gold and p.inventory.count(bar) >= count
                col = C.WHITE if affordable else C.DIM
            m.text(2, dy, pre + txt, fg=col, bg=rowbg)
            m.text(w - 16, dy, cost, fg=(200, 190, 150), bg=rowbg)

    m.list(top, body, len(entries), sel, row, arrow_top=top, arrow_bottom=h - 3)
    m.footer(f"Gold {p.gold}g   ↑↓ Enter buy/upgrade   Esc close")


def render_contest(con: tcod.console.Console, state: GameState, sel: int) -> None:
    """Pick one fine good to set on the Grange judging table — stars decide."""
    from ..game import village, skills
    goods = village.contest_items(state)
    w, h = 52, min(C.SCREEN_H - 4, max(8, len(goods) + 6))
    body = h - 5
    m = ui.Modal(con, w, h, "The Produce Contest")
    m.text(2, 1, "One entry — your finest. The judges love stars.", fg=C.DIM)
    if not goods:
        m.text(2, 3, "Nothing on you is fine enough to show.", fg=C.DIM)

    def row(i, dy, selected, bg):
        it, q, ql = goods[i]
        stars = skills.stars(ql) or "·"
        m.text(2, dy, ui.cur(selected) + f"{it.name}"[:w - 14], fg=C.WHITE, bg=bg)
        m.text(w - 10, dy, f"{stars:>5}", fg=(250, 220, 110), bg=bg)

    m.list(3, body, len(goods), sel, row, arrow_top=3, arrow_bottom=h - 3)
    m.footer("↑↓ select   Enter show it   Esc back")


def render_gift(con: tcod.console.Console, state: GameState, npc, sel: int) -> None:
    from ..game import village, skills
    gifts = village.giftable_items(state, npc)
    w, h = 48, min(C.SCREEN_H - 4, max(7, len(gifts) + 5))
    body = h - 4
    m = ui.Modal(con, w, h, f"Give a gift to {npc.name}")
    if not gifts:
        m.text(2, 2, "You have nothing to give.", fg=C.DIM)

    def row(i, dy, selected, bg):
        it, q, ql = gifts[i]
        # Match the same family-aware taste logic the gift actually uses, so the
        # tag never lies (a "loves Jam" NPC tags any jam variant as loved).
        tag = (" (loves!)" if npc._matches(it, npc.loves)
               else " (likes)" if npc._matches(it, npc.likes)
               else " (dislikes)" if npc._matches(it, npc.dislikes) else "")
        star = (" " + skills.stars(ql)) if ql else ""
        m.text(2, dy, ui.cur(selected) + f"{q:>3} {it.name}{star}{tag}", fg=C.WHITE, bg=bg)

    m.list(2, body, len(gifts), sel, row, arrow_top=2, arrow_bottom=h - 3)
    m.footer("↑↓ select   Enter give   Esc close")
