"""Drawing: scrolling world viewport, status panel, and message log.

The console is created with ``order="F"`` so all arrays are indexed [x, y],
matching the world map and ``console.print(x, y, ...)``.
"""
from __future__ import annotations

import math

import numpy as np
import tcod.console

from . import anim
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

# Trees and foliage: the wind rustles them (engine/effects.py) and winter frosts
# them (below).
_TREE_IDS = np.array([tile.TREE_OAK, tile.TREE_MAPLE, tile.TREE_BIRCH, tile.TREE_POPLAR,
                      tile.TREE_WILLOW, tile.TREE_PINE, tile.TREE_SPRUCE, tile.FOLIAGE])


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


_hash01 = anim.hash01          # the engine's stable per-tile hash (ground texture)


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


_shift2d = anim.shift2d        # (the sun's cast shadow)


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


def render_world(con: tcod.console.Console, state: GameState, anim_time: float = 0.0) -> set:
    """Draw the world view (without the overlays); returns the screen cells the
    creatures and the player hold."""
    f = _frame(con, state, anim_time)
    _draw_world(f)
    return f.occupied


def _frame(con, state: GameState, anim_time: float) -> anim.Frame:
    ox, oy = camera_origin(state)
    return anim.Frame(con=con, state=state, t=anim_time, ox=ox, oy=oy,
                      vw=C.VIEW_W, vh=C.VIEW_H, daylight=daylight_mul(state.time_minutes))


def _draw_world(f: anim.Frame) -> None:
    """The world view, in order: the ground's static shading, the animation
    engine's ground layers, crops, trees and machines, its late ground layer,
    lighting, the creatures, its veil layer, then the player. (The overlay
    layer is drawn over all of it by render_all.)"""
    con, state = f.con, f.state
    w = state.world
    ox, oy = f.ox, f.oy
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
    t = f.t
    xs = (ox + np.arange(C.VIEW_W, dtype=np.float32))[:, None]
    ys = (oy + np.arange(C.VIEW_H, dtype=np.float32))[None, :]
    f.view, f.xs, f.ys = view, xs, ys

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

    # The animation engine's ground layers: passing cloud shadows; wind in the
    # grass and trees, water shimmer, ore twinkle and campfire flicker; coastal
    # foam, puddles and rain ripples (engine/effects.py).
    f.fg, f.bg = fg, bg
    anim.run(anim.SHADE, f)
    anim.run(anim.TINT, f)
    anim.run(anim.GROUND, f)
    fg, bg = f.fg, f.bg

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
                pulse = anim.ready_glint(t, mx, my)    # each on its own beat
                fg[sx, sy] = (255, 255, 220) if pulse else (250, 220, 110)
                bg[sx, sy] = (60, 50, 26)
            elif status == "working":
                fg[sx, sy] = tuple(int(c * 0.55) for c in mdef.color)
                bg[sx, sy] = (44, 38, 32)
            else:
                fg[sx, sy] = mdef.color
                bg[sx, sy] = (44, 38, 32)

    # The engine's late ground layer: gem glitter and the breathing lava.
    f.fg, f.bg = fg, bg
    anim.run(anim.GROUND_LATE, f)
    fg, bg = f.fg, f.bg

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
        flicker = anim.torch_flicker(t, X, Y)
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
    occupied = f.occupied
    dr, dg, db = (1.0, 1.0, 1.0) if w.is_dungeon else daylight_mul(state.time_minutes)

    def _draw(sx: int, sy: int, glyph: str, color, cell_bg=None) -> None:
        # A faint breathing shimmer on each creature, phased by position so they
        # don't pulse in lockstep — enough that the world looks alive at rest,
        # not so much it distracts.
        sh = anim.breath(t, sx, sy)
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
            elif a.produce_ready:                 # waiting to be collected: it glints
                col = (255, 255, 228) if anim.ready_glint(t, a.x, a.y) else (250, 240, 170)
            _draw(sx, sy, a.glyph, col)

    # The engine's veil layer, over the creatures and under the player: the
    # Westreach's steam, ash and eruption.
    anim.run(anim.VEIL, f)

    # player, centered-ish — always full-bright so you never lose yourself
    px, py = state.player.x - ox, state.player.y - oy
    if 0 <= px < C.VIEW_W and 0 <= py < C.VIEW_H:
        pb = anim.player_pulse(t)                    # a gentle breathing pulse (dims, never lost)
        con.rgb["ch"][px, py] = ord(state.player.glyph)
        con.rgb["fg"][px, py] = tuple(min(255, int(c * pb)) for c in C.PLAYER_FG)
        occupied.add((px, py))


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


def render_panel(con: tcod.console.Console, state: GameState, t: float | None = None) -> None:
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
    if p.status:                        # active afflictions: wounds and illness
        from ..game.combat import STATUS, is_disease
        col = 0
        for k in p.status:
            info = STATUS.get(k)
            if info:
                # A disease runs on days, so show how many are left — you need it
                # to decide whether the illness is worth physicking away.
                tag = info["tag"] + (f" {p.status[k]}d" if is_disease(k) else "")
                con.print(x + col, 7, tag, fg=info["color"])
                col += len(tag) + 1
    _bar(con, x, 8, "✦ Stamina", p.energy, p.max_energy, C.ENERGY_COLOR,
         low_frac=C.LOW_ENERGY_FRAC)
    # Gold runs to its new amount rather than jumping — green as it rises, red
    # as it's spent (the animation engine's tally; no clock, no running).
    gold, rising = (p.gold, 0) if t is None else anim.tally(state, "gold", p.gold, t)
    con.print(x, 11, f"⛁ Gold  {gold}g",
              fg=C.GOLD_COLOR if not rising else (150, 230, 150) if rising > 0 else (232, 140, 120))
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
    # Wrapped, not cut: a long line ("…your armour holds, but it still bites
    # for N") used to lose its end — the number — at the pane's edge.
    lines = ui.log_tail(state.log.messages, C.VIEW_W - 2, C.LOG_H - 1)
    for i, (text, color) in enumerate(lines):
        con.print(1, y0 + 1 + i, text, fg=color)


def render_all(con: tcod.console.Console, state: GameState, anim_time: float = 0.0) -> None:
    con.clear(bg=C.BLACK)
    f = _frame(con, state, anim_time)
    _draw_world(f)
    anim.run(anim.OVERLAY, f)          # weather, motes, embers, flyovers, happenings
    render_panel(con, state, anim_time)
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
        ok, _new, _msg = resolve_tool(tool, state.world.tile_at(tx, ty), state.world)
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
        ok, _new, _msg = resolve_tool(tool, t, state.world)
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
    # Look reads what the screen shows, no more. It used to name a monster — HP,
    # DV, elite and all — anywhere on a dungeon floor, unexplored rooms included,
    # and describe surface critters that were hibernating out of season.
    w = state.world
    seen = True
    if w.is_dungeon and w.explored is not None:
        if not w.explored[x, y]:
            return "darkness you haven't explored."
        seen = w.visible is None or bool(w.visible[x, y])   # remembered, not watched
    for m in state.world.monsters:
        if (m.alive and (m.x, m.y) == (x, y) and seen
                and not (m.seasons and state.season not in m.seasons)):
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
        if (npc.x, npc.y) == (x, y) and seen:
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
        if plot.cross:                                   # the bees have been at it
            fert += f", crossed — its seed will carry {plot.cross}"
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
        if m.kind == "lift":
            return f"{mdef.name} — {mdef.desc} (g to ride)"
        if m.kind == "waystation":
            return f"{mdef.name} — {mdef.desc} (g to send)"
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
    if t.kind == "water":
        # Name the water, because which body it is decides what you'll pull out.
        from ..game.fishing import water_kind
        return {
            "river": "the river running through the Vale — cast here for its "
                     "seasonal fish.",
            "sea":   "the open sea, too deep to wade — sardine, mackerel, bass "
                     "and, if you're lucky, tuna.",
            "marsh": "a peaty fen pool, brown and still — eels, tench, and that "
                     "red crayfish nobody invited.",
            "lake":  "still, clear water — a pond's own fish: perch, rudd, bream "
                     "and the odd great carp.",
            "cave":  "a lightless underground pool. Pale things live in it.",
        }[water_kind(state, x, y)]
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
    lines = ui.wrap(describe(state, lx, ly), C.VIEW_W - 2)[:5]
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
    elif ctx["purpose"] == "reach":
        foe = combat.reach_target(state, cx, cy)
        ok = foe is not None
        if ok:
            _paint(foe.x, foe.y, True)                 # who the thrust would strike
        else:
            _paint(cx, cy, False)
        sx, sy = cx - ox, cy - oy
        if 0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H:
            con.rgb["ch"][sx, sy] = ord("*")
            con.rgb["fg"][sx, sy] = (20, 20, 20)
        held = state.player.active_tool
        banner = (f" Aim — thrust the {held.name.lower()} (reach {combat.POLEARM_REACH})" if ok
                  else f" Aim — nothing in reach there (a straight line, {combat.POLEARM_REACH} tiles)")
    elif ctx["purpose"] == "shoot":
        rng = combat.aim_range(state, "shoot")
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

    # The banner has the top row to itself and the key hint the row(s) below:
    # sharing one row, the hint was printed over the banner ("Aim — th…", so
    # "out of range" never showed) and, with bow and bomb both carried, ran
    # past the map onto the side panel.
    ways = combat.aim_purposes(state) if ctx["purpose"] in ("reach", "shoot", "throw") else []
    names = {"reach": "reach", "shoot": "bow", "throw": "bomb"}
    swap = f" · Tab {'/'.join(names[w] for w in ways)}" if len(ways) > 1 else ""
    hint = ui.wrap(f"move to aim · Enter/Space confirm{swap} · Esc cancel", C.VIEW_W - 2)
    bg = (40, 38, 30)
    con.draw_rect(0, 0, C.VIEW_W, 1 + len(hint), ch=ord(" "), bg=bg)
    con.print(0, 0, banner[:C.VIEW_W], fg=(245, 235, 200), bg=bg)
    for i, line in enumerate(hint):
        con.print(1, 1 + i, line, fg=C.DIM, bg=bg)


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
letter_index = _sr.letter_index
INV_LETTERS = _sr.INV_LETTERS
render_inventory = _sr.render_inventory
render_equipment = _sr.render_equipment
# The equipment screen's letter keys address the same rows the renderer draws.
PAPERDOLL_SLOTS = _sr.PAPERDOLL_SLOTS
equippables = _sr.equippables
render_craft = _sr.render_craft
render_ship = _sr.render_ship
render_journal = _sr.render_journal
render_ledger = _sr.render_ledger
render_lift = _sr.render_lift
render_waystation = _sr.render_waystation
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

# Every animation effect registers itself with the engine on import.
from . import effects as _effects            # noqa: E402,F401
