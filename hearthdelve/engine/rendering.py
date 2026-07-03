"""Drawing: scrolling world viewport, status panel, and message log.

The console is created with ``order="F"`` so all arrays are indexed [x, y],
matching the world map and ``console.print(x, y, ...)``.
"""
from __future__ import annotations

import math

import numpy as np
import tcod.console

from . import constants as C
from ..entities import items
from ..world import tile
from ..game.state import GameState

# Per-tile-id render arrays, built once.
_CH = np.array([ord(t.glyph) for t in tile.TILES], dtype=np.int32)
_FG = np.array([t.fg for t in tile.TILES], dtype=np.uint8)
_BG = np.array([t.bg for t in tile.TILES], dtype=np.uint8)

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
    tile.FOLIAGE,
])
# Open ground that gets a coat of snow in winter.
_SEASON_GROUND_IDS = np.array([
    tile.GRASS, tile.MEADOW, tile.TALL_GRASS, tile.FOG_GRASS, tile.DIRT_PATH,
    tile.MOOR, tile.SAND, tile.RUINS_FLOOR, tile.BUSH,
    tile.FLOWER_RED, tile.FLOWER_YELLOW, tile.FLOWER_VIOLET, tile.FLOWER_WHITE,
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
            bg[sx, sy] = (26, 34, 46) if plot.watered else (44, 30, 20)

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
                fg[sx, sy] = (250, 240, 160)               # ready: bright
            elif status == "working":
                fg[sx, sy] = tuple(int(c * 0.55) for c in mdef.color)
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

    if w.is_dungeon and w.visible is not None:
        # Fog of war: lit where visible, dim where explored, black otherwise.
        vis = w.visible[ox:ox + C.VIEW_W, oy:oy + C.VIEW_H]
        exp = w.explored[ox:ox + C.VIEW_W, oy:oy + C.VIEW_H]
        light = np.where(vis, 1.0, np.where(exp, 0.32, 0.0)).astype(np.float32)
        fg *= light[..., None]
        bg *= light[..., None]
    else:
        # Day/night light tint over the whole viewport.
        dr, dg, db = daylight_mul(state.time_minutes)
        fg[..., 0] *= dr; fg[..., 1] *= dg; fg[..., 2] *= db
        bg[..., 0] *= dr; bg[..., 1] *= dg; bg[..., 2] *= db

        # Lamp posts cast a warm glow once it gets dark.
        night = max(0.0, 1.0 - (dr + dg + db) / 3.0)
        if night > 0.06:
            lamps = np.argwhere(view == tile.LAMP)
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

    # player, centered-ish — always full-bright so you never lose yourself
    px, py = state.player.x - ox, state.player.y - oy
    if 0 <= px < C.VIEW_W and 0 <= py < C.VIEW_H:
        con.rgb["ch"][px, py] = ord(state.player.glyph)
        con.rgb["fg"][px, py] = C.PLAYER_FG
        occupied.add((px, py))

    return occupied


def _bar(con, x, y, label, cur, mx, color, width=12):
    con.print(x, y, f"{label}", fg=C.WHITE)
    filled = int(round(width * cur / mx)) if mx else 0
    bar = "█" * filled + "·" * (width - filled)
    con.print(x, y + 1, bar, fg=color)
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
    _bar(con, x, 5, "♥ HP", p.hp, p.max_hp, C.HP_COLOR)
    _bar(con, x, 8, "✦ Stamina", p.energy, p.max_energy, C.ENERGY_COLOR)
    con.print(x, 11, f"⛁ Gold  {p.gold}g", fg=C.GOLD_COLOR)
    from ..game import skills
    b = skills.active_buff(state)
    if b:
        mins = max(0, state.player.buff_until - state.abs_minutes)
        left = f"{mins // 60}h{mins % 60:02d}" if mins >= 60 else f"{mins}m"
        con.print(x, 13, f"↯ {skills.BUFFS.get(b, b)} {left}"[:C.PANEL_W - 2], fg=(180, 210, 250))

    # --- hotbar (keys 1-9) ---
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
            name = f"{i + 1} {nm}"[:C.PANEL_W - 3 - len(cnt)]
            con.print(x, yy, name, fg=fg, bg=rowbg)
            con.print(x0 + C.PANEL_W - 1 - len(cnt), yy, cnt, fg=fg, bg=rowbg)
        elif it.stackable:
            # right-align the carried amount, e.g.  "6 Parsnip Seeds  [15]"
            cnt = f"[{p.inventory.count(it)}]"
            name = f"{i + 1} {p.display_name(it)}"[:C.PANEL_W - 3 - len(cnt)]
            con.print(x, yy, name, fg=fg, bg=rowbg)
            con.print(x0 + C.PANEL_W - 1 - len(cnt), yy, cnt, fg=fg, bg=rowbg)
        else:
            con.print(x, yy, f"{i + 1} {p.display_name(it)}"[:C.PANEL_W - 3], fg=fg, bg=rowbg)
    if p.weapon:
        con.print(x, 18 + len(p.hotbar) + 1, f"⚔ {p.weapon.name}", fg=C.DIM)

    # goals progress
    from ..game import quests
    dn, tot = quests.progress(state)
    con.print(x, 27, f"Goals {dn}/{tot}", fg=(224, 204, 128))
    goal = quests.active(state)
    if goal:
        con.print(x, 28, f"▸ {goal.title}"[:C.PANEL_W - 2], fg=C.DIM)

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


def render_all(con: tcod.console.Console, state: GameState, anim_time: float = 0.0) -> None:
    con.clear(bg=C.BLACK)
    occupied = render_world(con, state, anim_time)
    render_weather(con, state, anim_time, occupied)
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
    "bed": "your bed. Sleep here to end the day (coming soon).",
    "shipping_bin": "the shipping bin. Drop goods to sell (coming soon).",
    "post_box": "your post box — letters, invitations and gifts arrive here (g).",
    "fence": "a wooden fence around the plot.",
    "tilled": "tilled soil, ready for seeds.",
    "dungeon_down": "a stairway leading down. Press > to descend.",
    "stairs_up": "a stairway leading up. Press < to climb out.",
    "dungeon_wall": "solid dungeon rock.",
    "dungeon_floor": "the dungeon floor.",
    "gem_vein": "a gem vein glinting in the rock — mine it with a pickaxe.",
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
            return f"a {m.name.lower()} — HP {m.hp}/{m.max_hp}. Bump it to attack."
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
    plot = state.world.crops.get((x, y))
    if plot is not None:
        name = plot.crop.name.lower()
        if plot.dead:
            return f"a withered {name}. Clear it with g."
        if plot.mature:
            return f"{name} — ripe! Harvest it with g."
        water = "watered" if plot.watered else "needs watering"
        return f"{name}, still growing ({water})."
    tree = state.world.trees.get((x, y))
    if tree is not None:
        if not tree.mature:
            return f"a young {tree.name.lower()} sapling, still growing."
        if tree.has_fruit:
            return f"a {tree.name.lower()} tree, heavy with fruit — pick it (g)."
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
        st = m.status(state.abs_minutes)
        if st == "done":
            return f"{mdef.name} — {m.loaded_output.name} is ready! (g to collect)"
        if st == "working":
            return f"{mdef.name}, working away... (g to check)"
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
        return f"a {fn} shrub, ripe — pick it (g) and it bears again; machete clears it."
    return _TILE_DESC.get(t.name, f"{t.name.replace('_', ' ')}.")


def render_look(con: tcod.console.Console, state: GameState, lx: int, ly: int) -> None:
    ox, oy = camera_origin(state)
    sx, sy = lx - ox, ly - oy
    if 0 <= sx < C.VIEW_W and 0 <= sy < C.VIEW_H:
        con.rgb["bg"][sx, sy] = (120, 110, 40)
        con.rgb["fg"][sx, sy] = (20, 20, 20)
    # Word-wrapped readout box across the top of the viewport, so long
    # descriptions (a signpost's directions, say) aren't clipped to one row.
    lines = _wrap("Look: " + describe(state, lx, ly), C.VIEW_W - 2)[:5]
    h = len(lines) + 1
    con.draw_rect(0, 0, C.VIEW_W, h, ch=ord(" "), bg=(40, 38, 30))
    for i, ln in enumerate(lines):
        con.print(1, i, ln[:C.VIEW_W - 1], fg=(245, 235, 200), bg=(40, 38, 30))
    con.print(1, len(lines), "(move cursor · Esc/l to close)", fg=C.DIM, bg=(40, 38, 30))


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
    hint = "(move to aim · Enter/Space confirm · Esc cancel)"
    con.print(max(0, C.VIEW_W - len(hint) - 1), 0, hint, fg=C.DIM, bg=(40, 38, 30))


# --- Modal overlays ----------------------------------------------------------
def _modal(con, w, h, title):
    x = (C.SCREEN_W - w) // 2
    y = (C.SCREEN_H - h) // 2
    con.draw_rect(x, y, w, h, ch=ord(" "), fg=C.WHITE, bg=(20, 22, 32))
    con.draw_frame(x, y, w, h, title=title, fg=(236, 226, 180), bg=(20, 22, 32))
    return x, y


def _window(sel: int, total: int, height: int) -> tuple[int, int]:
    """First/last row index to show so `sel` stays visible in a `height`-row list."""
    if total <= height:
        return 0, total
    start = max(0, min(sel - height // 2, total - height))
    return start, start + height


def render_message_log(con: tcod.console.Console, state: GameState, scroll: int) -> None:
    """Full scrollback of the message log (newest at the bottom)."""
    msgs = state.log.messages
    w, h = 72, C.SCREEN_H - 6
    body = h - 4
    x, y = _modal(con, w, h, "Message Log")
    total = len(msgs)
    max_scroll = max(0, total - body)
    scroll = max(0, min(scroll, max_scroll))
    start = max(0, total - body - scroll)
    for i, (text, color) in enumerate(msgs[start:start + body]):
        con.print(x + 2, y + 2 + i, text[:w - 4], fg=color)
    if scroll < max_scroll:
        con.print(x + w - 4, y + 2, "▲", fg=_HDR)
    if scroll > 0:
        con.print(x + w - 4, y + h - 3, "▼", fg=_HDR)
    con.print(x + 2, y + h - 2, "↑↓ scroll · Esc close", fg=C.DIM)


def render_mail(con: tcod.console.Console, state: GameState, sel: int) -> None:
    mail = state.mail
    body = mail[min(sel, len(mail) - 1)]["body"].split("\n") if mail else []
    w = 60
    list_h = min(10, max(1, len(mail)))          # cap the letter list; it scrolls
    h = list_h + len(body) + 8
    x, y = _modal(con, w, h, "Post Box")
    if not mail:
        con.print(x + 2, y + 2, "The post box is empty.", fg=C.DIM)
    sel = max(0, min(sel, len(mail) - 1)) if mail else 0
    start, end = _window(sel, len(mail), list_h)
    for row, letter in enumerate(mail[start:end]):
        i = start + row
        bg = (54, 50, 36) if i == sel else (20, 22, 32)
        if i == sel:
            con.draw_rect(x + 1, y + 2 + row, w - 2, 1, ch=ord(" "), bg=bg)
        tag = " ✉+gift" if letter.get("items") else " ✉"
        con.print(x + 2, y + 2 + row, ("▸ " if i == sel else "  ") + f"From {letter['sender']}{tag}",
                  fg=C.WHITE, bg=bg)
    if start > 0:
        con.print(x + w - 4, y + 2, "▲", fg=_HDR)
    if end < len(mail):
        con.print(x + w - 4, y + 1 + list_h, "▼", fg=_HDR)
    # the open letter's text below the list
    ly = y + 3 + list_h
    for j, bl in enumerate(body):
        con.print(x + 3, ly + j, bl[:w - 6], fg=(210, 205, 190))
    con.print(x + 2, y + h - 2, "↑↓ select   Enter take letter   Esc close", fg=C.DIM)


def render_eat(con: tcod.console.Console, state: GameState, sel: int) -> None:
    from ..game import skills
    from ..game.crafting import edible_items
    foods = edible_items(state)
    w, h = 50, min(C.SCREEN_H - 4, max(8, len(foods) + 6))
    body = h - 4
    x, y = _modal(con, w, h, "Eat  (restores stamina & health)")
    if not foods:
        con.print(x + 2, y + 2, "Nothing to eat — cook a dish (c) or gather eggs/milk.", fg=C.DIM)
    sel = max(0, min(sel, len(foods) - 1)) if foods else 0
    start, end = _window(sel, len(foods), body)
    for row, (it, q, ql) in enumerate(foods[start:end]):
        i = start + row
        bg = (54, 50, 36) if i == sel else (20, 22, 32)
        if i == sel:
            con.draw_rect(x + 1, y + 2 + row, w - 2, 1, ch=ord(" "), bg=bg)
        star = (" " + skills.stars(ql)) if ql else ""
        gain = round(it.energy * (1 + 0.12 * ql))
        hp = max(1, gain // 6)
        con.print(x + 2, y + 2 + row, ("▸ " if i == sel else "  ") + f"{q:>2} {it.name}{star}", fg=C.WHITE, bg=bg)
        con.print(x + w - 18, y + 2 + row, f"+{gain} st  +{hp} hp", fg=(150, 210, 150), bg=bg)
    if start > 0:
        con.print(x + w - 4, y + 2, "▲", fg=_HDR)
    if end < len(foods):
        con.print(x + w - 4, y + h - 3, "▼", fg=_HDR)
    con.print(x + 2, y + h - 2, "↑↓ select   Enter eat   Esc close", fg=C.DIM)


def render_load_machine(con: tcod.console.Console, state: GameState, ctx) -> None:
    """Choose-what-to-make menu for an empty machine (jam vs pickles, which bar…)."""
    if not ctx:
        return
    opts, sel, name = ctx["options"], ctx["sel"], ctx["name"]
    w, h = 56, min(C.SCREEN_H - 4, max(8, len(opts) + 6))
    body = h - 4
    x, y = _modal(con, w, h, f"Load {name}  (choose what to make)")
    sel = max(0, min(sel, len(opts) - 1)) if opts else 0
    start, end = _window(sel, len(opts), body)
    for row, opt in enumerate(opts[start:end]):
        i = start + row
        bg = (54, 50, 36) if i == sel else (20, 22, 32)
        if i == sel:
            con.draw_rect(x + 1, y + 2 + row, w - 2, 1, ch=ord(" "), bg=bg)
        out = opt["output"]
        ins = ", ".join(f"{q} {it.name}" for it, q in opt["inputs"])
        con.print(x + 2, y + 2 + row, ("▸ " if i == sel else "  ") + out.name, fg=C.WHITE, bg=bg)
        con.print(x + 20, y + 2 + row, f"from {ins}"[:w - 30], fg=(160, 180, 205), bg=bg)
        con.print(x + w - 8, y + 2 + row, f"{out.value}g", fg=C.GOLD_COLOR, bg=bg)
    if start > 0:
        con.print(x + w - 4, y + 2, "▲", fg=_HDR)
    if end < len(opts):
        con.print(x + w - 4, y + h - 3, "▼", fg=_HDR)
    con.print(x + 2, y + h - 2, "↑↓ select   Enter load   Esc cancel", fg=C.DIM)


def render_cheats(con: tcod.console.Console, state: GameState, sel: int, locations) -> None:
    c = state.cheats
    rows = [f"Freeze Health:  {'ON ' if c.get('freeze_hp') else 'off'}",
            f"Freeze Stamina: {'ON ' if c.get('freeze_stamina') else 'off'}",
            "Add 1000 gold",
            "Add 100 of each building material"]
    rows += [f"Teleport → {name}" for name, _ in locations]
    h = len(rows) + 6
    x, y = _modal(con, 52, h, "★ Cheats (up up down down ...) ★")
    con.print(x + 2, y + 1, "The Konami whisper opens a little door.", fg=C.DIM)
    for i, text in enumerate(rows):
        hot = (i == sel)
        con.print(x + 2, y + 3 + i, ("→ " if hot else "  ") + text,
                  fg=(250, 230, 140) if hot else (210, 210, 220))
    con.print(x + 2, y + h - 2, "↑↓ move · Enter select · Esc close", fg=C.DIM)


def render_quit(con: tcod.console.Console, state: GameState) -> None:
    x, y = _modal(con, 48, 9, "Leave Hollowmere Vale?")
    rows = [
        ("The game auto-saves each morning you sleep.", C.DIM),
        ("", C.WHITE),
        ("[S] / [Enter] / [Q]   Save and quit", (180, 230, 160)),
        ("[Backspace]           Quit without saving", (232, 178, 120)),
        ("[Esc]                 Keep playing", (210, 210, 220)),
    ]
    for i, (text, colour) in enumerate(rows):
        con.print(x + 3, y + 2 + i, text, fg=colour)


_HDR = (236, 226, 180)
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
        ("  t                aim & throw a bomb (move to aim, Enter to throw)", C.WHITE),
        ("  c                craft, build machines, cook dishes", C.WHITE),
        ("  p                site a carpenter building (opens aiming)", C.WHITE),
        ("  x                eat (restores stamina & health)", C.WHITE),
        ("  b                shipping bin (sell) — stand beside it", C.WHITE),
        ("  Shift+C          talk to a villager / open a shop", C.WHITE),
        ("  f                give a villager a gift", C.WHITE),
        ("  > / <            descend / climb a dungeon (on stairs)", C.WHITE),
        ("  s                sleep in bed -> next day", C.WHITE),
        ("  i                inventory  (d drops the selected stack)", C.WHITE),
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

    # --- Page: Tools & Equipment --------------------------------------------
    tools = [("Tools  (energy cost per use)", _HDR), ("", C.WHITE)]
    for it in content.ALL_TOOLS:
        s = content.TOOL_STATS[it]
        tools.append((f" {it.glyph}  {it.name}", _KEY))
        tstr = f"{s.seconds // 60}m" if s.seconds >= 60 else f"{s.seconds}s"
        tools.append((f"      {s.verb} {s.target} · {s.stamina} stamina · {tstr} · {s.yields}", C.WHITE))
        tools.append((f"      {it.desc}", C.DIM))
    tools.append(("", C.WHITE))
    tools.append(("Weapons  (bump-attack)", _HDR))
    tools.append(("", C.WHITE))
    for it in content.ALL_WEAPONS:
        w = content.WEAPON_STATS[it]
        tools.append((f" {it.glyph}  {it.name}   ATK {w.atk}", _KEY))
        tools.append((f"      {it.desc}  ({w.note})", C.DIM))
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
    craftp = [("Recipes  (press c)", _HDR), ("", C.WHITE)]
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
    craftp.append(("  (or a paved-in yard) they need straw — scythe the tall grass", C.DIM))
    craftp.append(("  that grows near home (machete) and dry it on a fair day.", C.DIM))
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
        mon.append((f" {m.glyph}  {m.name}   HP {m.hp}  ATK {m.atk}  SPD {m.speed}", _KEY))
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


def render_codex(con: tcod.console.Console, state: GameState, page: int, scroll: int) -> None:
    pages = build_codex_pages(state)
    page %= len(pages)
    title, rows = pages[page]

    w, h = 66, 44
    body_h = h - 5
    x, y = _modal(con, w, h, f"Encyclopedia — {title}")

    max_scroll = max(0, len(rows) - body_h)
    scroll = max(0, min(scroll, max_scroll))
    for i in range(body_h):
        idx = scroll + i
        if idx >= len(rows):
            break
        text, color = rows[idx]
        con.print(x + 2, y + 2 + i, text[:w - 4], fg=color)
    if scroll < max_scroll:
        con.print(x + w - 4, y + h - 3, "▼", fg=_HDR)
    if scroll > 0:
        con.print(x + w - 4, y + 2, "▲", fg=_HDR)

    footer = f" ← → page {page + 1}/{len(pages)}   ↑ ↓ scroll   Esc close "
    con.print(x + 2, y + h - 2, footer, fg=C.DIM)


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
    x, y = _modal(con, w, h, "PACK")
    total = sum(q for _it, q, _ql in slots)
    con.print(x + 2, y + 1, f"Carrying {total} item(s)", fg=_CAP_FG)
    gold = f"Gold: {state.player.gold}g"
    con.print(x + w - 2 - len(gold), y + 1, gold, fg=C.GOLD_COLOR)

    if not slots:
        con.print(x + 2, y + 3, "(empty — grow and forage to fill it)", fg=C.DIM)
    else:
        sel = max(0, min(sel, len(slots) - 1))
        sel_row = next((r for r, rw in enumerate(rows) if rw[0] == "item" and rw[1] == sel), 0)
        start, end = _window(sel_row, len(rows), body)
        for r in range(start, end):
            yy = y + 3 + (r - start)
            rw = rows[r]
            if rw[0] == "head":
                con.print(x + 2, yy, f"{rw[1]}  ('{rw[2]}')", fg=_SECTION_FG)
                continue
            i = rw[1]
            it, qty, ql = slots[i]
            picked = (i == sel)
            bg = (54, 50, 36) if picked else (20, 22, 32)
            if picked:
                con.draw_rect(x + 1, yy, w - 2, 1, ch=ord(" "), bg=bg)
            con.print(x + 3, yy, f"{inv_letter(i)} -", fg=_LETTER_FG, bg=bg)
            star = ("  " + skills.stars(ql)) if ql else ""
            con.print(x + 8, yy, f"{it.glyph} {it.name}{star}", fg=C.WHITE, bg=bg)
            qs = f"[x{qty}]"
            con.print(x + w - 2 - len(qs), yy, qs, fg=_BRACKET_FG, bg=bg)
        if start > 0:
            con.print(x + w - 3, y + 2, "↑", fg=_HDR)
        if end < len(rows):
            con.print(x + w - 3, y + h - 3, "↓", fg=_HDR)
    con.print(x + 2, y + h - 2, "[a-z] pick  [⇧D] drop  [e] equipment  [Esc] close", fg=_FOOT_FG)


_EQUIP_TOOLS = (items.HOE, items.WATERING_CAN, items.AXE, items.PICKAXE, items.MACHETE, items.FISHING_ROD)


def render_equipment(con: tcod.console.Console, state: GameState) -> None:
    from ..data import content
    from ..game import skills
    p = state.player
    tool = p.active_tool
    w, h = 58, len(_EQUIP_TOOLS) + 9
    x, y = _modal(con, w, h, "PERSONAL EQUIPMENT")
    con.print(x + 2, y + 1, f"Character level {p.level}", fg=_CAP_FG)
    gold = f"Gold: {p.gold}g"
    con.print(x + w - 2 - len(gold), y + 1, gold, fg=C.GOLD_COLOR)

    # fixed slots (ADOM lists Right Hand / Rings / Boots …; ours is simpler)
    watk = content.WEAPON_STATS[p.weapon].atk if p.weapon in content.WEAPON_STATS else 0
    atk = C.BASE_ATK + watk + skills.combat_atk_bonus(state)
    fixed = (("Wielded", f"{p.weapon.name}  (ATK {atk})" if p.weapon else "-"),
             ("Accessory", "-"))
    row = y + 3
    for name, val in fixed:
        con.print(x + 4, row, name, fg=_SECTION_FG)
        con.print(x + 18, row, ": " + val, fg=C.WHITE if val != "-" else C.DIM)
        row += 1

    row += 1
    con.print(x + 2, row, "In hand — press a letter to hold:", fg=_HDR)
    row += 1
    for j, t in enumerate(_EQUIP_TOOLS):
        held = t is tool
        tier = C.TOOL_TIERS[p.tool_tier[t]] if t in p.tool_tier else "—"
        bg = (54, 50, 36) if held else (20, 22, 32)
        if held:
            con.draw_rect(x + 1, row, w - 2, 1, ch=ord(" "), bg=bg)
        con.print(x + 3, row, f"{inv_letter(j)} -", fg=_LETTER_FG, bg=bg)
        con.print(x + 8, row, f"{t.glyph} {t.name}", fg=C.WHITE if held else (200, 200, 210), bg=bg)
        con.print(x + 30, row, tier, fg=_BRACKET_FG, bg=bg)
        if held:
            con.print(x + w - 11, row, "in hand", fg=_CAP_FG, bg=bg)
        row += 1

    con.print(x + 2, y + h - 2, "[a-f] hold tool  [i] pack  [Esc] close", fg=_FOOT_FG)


def render_craft(con: tcod.console.Console, state: GameState, sel: int) -> None:
    from ..data import content
    from ..game import crafting

    recipes = content.RECIPES
    w, h = 56, len(recipes) + 8
    x, y = _modal(con, w, h, "Craft  (build machines & cook)")

    last_kind = None
    row = 0
    for i, r in enumerate(recipes):
        if r.kind != last_kind:
            last_kind = r.kind
            label = {"build": "Build", "cook": "Cook"}.get(r.kind, "Craft")
            con.print(x + 2, y + 2 + row, label, fg=_HDR)
            row += 1
        ok = crafting.has_inputs(state, r)
        marker = "▸" if i == sel else " "
        color = C.WHITE if ok else C.DIM
        if i == sel:
            con.draw_rect(x + 1, y + 2 + row, w - 2, 1, ch=ord(" "), bg=(54, 50, 36))
        con.print(x + 2, y + 2 + row, f"{marker} {r.name}", fg=color,
                  bg=(54, 50, 36) if i == sel else (20, 22, 32))
        con.print(x + 22, y + 2 + row, f"[{crafting.inputs_str(r)}]"[:w - 24],
                  fg=(160, 200, 150) if ok else (150, 110, 110),
                  bg=(54, 50, 36) if i == sel else (20, 22, 32))
        row += 1

    con.print(x + 2, y + h - 2, "↑↓ select   Enter make   Esc close", fg=C.DIM)


def render_ship(con: tcod.console.Console, state: GameState, sel: int) -> None:
    from ..game import crafting

    from ..game import skills
    items_ = crafting.sellable_items(state)
    pending = sum(crafting.slot_value(it, ql) * q for it, q, ql in state.ship_bin.slots)
    w, h = 52, max(8, len(items_) + 7)
    x, y = _modal(con, w, h, "Shipping Bin  (sells overnight)")

    if not items_:
        con.print(x + 2, y + 2, "Nothing to sell — grow and gather first.", fg=C.DIM)
    for i, (it, q, ql) in enumerate(items_):
        marker = "▸" if i == sel else " "
        if i == sel:
            con.draw_rect(x + 1, y + 2 + i, w - 2, 1, ch=ord(" "), bg=(54, 50, 36))
        bg = (54, 50, 36) if i == sel else (20, 22, 32)
        star = (" " + skills.stars(ql)) if ql else ""
        con.print(x + 2, y + 2 + i, f"{marker} {q:>3}  {it.name}{star}", fg=C.WHITE, bg=bg)
        con.print(x + w - 12, y + 2 + i, f"{crafting.slot_value(it, ql)}g ea", fg=C.GOLD_COLOR, bg=bg)

    con.print(x + 2, y + h - 3, f"In bin (sells tonight): {pending}g", fg=C.GOLD_COLOR)
    con.print(x + 2, y + h - 2, "↑↓ select   Enter ship stack   Esc close", fg=C.DIM)


def render_journal(con: tcod.console.Console, state: GameState) -> None:
    from ..data import content
    from ..game import quests
    done, total = quests.progress(state)
    w, h = 62, len(content.QUESTS) + 6
    x, y = _modal(con, w, h, f"Journal — Goals ({done}/{total})")
    for i, q in enumerate(content.QUESTS):
        ok = q.id in state.quests_done
        mark = "✔" if ok else "○"
        con.print(x + 2, y + 2 + i, f" {mark} {q.title}",
                  fg=(150, 205, 150) if ok else _HDR)
        note = q.desc if not ok else "done"
        con.print(x + 22, y + 2 + i, f"{note}  (+{q.gold}g)"[:w - 24],
                  fg=C.DIM if ok else C.WHITE)
    con.print(x + 2, y + h - 2, "Reach goals as you play — no rush. (j / Esc close)", C.DIM)


def render_relationships(con: tcod.console.Console, state: GameState) -> None:
    met = [n for n in state.surface.npcs if n.met] if state.surface else []
    w, h = 62, max(8, len(met) * 2 + 5)
    x, y = _modal(con, w, h, "Relationships")
    if not met:
        con.print(x + 2, y + 2, "You haven't met anyone yet.", C.WHITE)
        con.print(x + 2, y + 3, "Visit Mossford or Cinderhope and talk (t).", C.DIM)
    row = 0
    for n in met:
        hearts = "♥" * n.hearts + "·" * (10 - n.hearts)
        con.print(x + 2, y + 2 + row, f" {n.glyph} {n.name}", fg=n.color)
        con.print(x + 16, y + 2 + row, hearts, fg=(220, 130, 150))
        row += 1
        con.print(x + 4, y + 2 + row, f"{n.village} · {n.bio}"[:w - 6], fg=C.DIM)
        row += 1
    con.print(x + 2, y + h - 2, "r / Esc to close", C.DIM)


def render_character(con: tcod.console.Console, state: GameState) -> None:
    from ..game import skills, karma
    p = state.player
    w, h = 50, 18
    x, y = _modal(con, w, h, f"Character — Level {p.level}")
    nxt = skills.xp_to_next(p.level)
    xpbar = "█" * int(10 * p.xp / nxt) + "·" * (10 - int(10 * p.xp / nxt))
    con.print(x + 2, y + 2, f"XP  {xpbar}  {p.xp}/{nxt}", fg=(210, 205, 150))
    con.print(x + 2, y + 3, f"♥ HP      {p.hp}/{p.max_hp}", fg=C.HP_COLOR)
    con.print(x + 2, y + 4, f"✦ Stamina {p.energy}/{p.max_energy}", fg=C.ENERGY_COLOR)
    con.print(x + 2, y + 5, f"⛁ Gold    {p.gold}g", fg=C.GOLD_COLOR)
    con.print(x + 2, y + 6, f"⚔ Weapon  {p.weapon.name if p.weapon else '-'}", fg=C.WHITE)
    ksign = f"+{p.karma}" if p.karma > 0 else str(p.karma)
    kcol = (160, 220, 160) if p.karma >= 8 else (220, 150, 140) if p.karma <= -8 else C.WHITE
    con.print(x + 2, y + 7, f"☯ Karma   {ksign} ({karma.label(p.karma)})", fg=kcol)
    con.print(x + 2, y + 9, "Skills", fg=_HDR)
    for i, s in enumerate(skills.SKILLS):
        lvl = skills.skill_level(state, s)
        xp = p.skills.get(s, 0)
        if lvl >= skills.MAX_LEVEL:
            bar = "█" * 10
        else:
            into = xp - lvl * skills.XP_PER_LEVEL
            filled = int(10 * into / skills.XP_PER_LEVEL)
            bar = "█" * filled + "·" * (10 - filled)
        con.print(x + 2, y + 10 + i, f"{s:<9} L{lvl:<2} {bar}",
                  fg=C.WHITE if lvl else C.DIM)
    con.print(x + 2, y + h - 2, "v / Esc to close", C.DIM)


def render_dialogue(con: tcod.console.Console, state: GameState, npc, line: str) -> None:
    parts = line.split("\n")                          # blurbs may be multi-line verse
    w = min(72, max(54, max((len(p) for p in parts), default=0) + 6))
    h = len(parts) + 7
    x, y = _modal(con, w, h, f"{npc.name}")
    hearts = "♥" * npc.hearts + "·" * (10 - npc.hearts)
    con.print(x + 2, y + 2, hearts, fg=(220, 130, 150))
    for i, part in enumerate(parts):
        con.print(x + 2, y + 4 + i, part[:w - 4], fg=C.WHITE)
    con.print(x + 2, y + h - 2, "f to gift · any key to close", fg=C.DIM)


def render_shop(con: tcod.console.Console, state: GameState, npc, sel: int, line: str = "") -> None:
    from ..game import village
    from ..data import content
    from ..entities import items as I

    entries = village.shop_entries(npc.shop, state)
    title = {"general": "General Store", "blacksmith": "Blacksmith",
             "tavern": "Tavern", "carpenter": "Carpentry"}.get(npc.shop, "Shop")
    header = line.split("\n") if (npc.shop in ("tavern", "carpenter") and line) else []
    w = 68 if npc.shop == "carpenter" else 56
    h = len(entries) + 6 + len(header)
    x, y = _modal(con, w, h, f"{npc.name}'s {title}")
    p = state.player
    top = y + 2
    for hl in header:                                     # innkeeper's greeting
        con.print(x + 2, top, hl[:w - 4], fg=(210, 205, 190))
        top += 1

    for i, e in enumerate(entries):
        yy = top + i
        rowbg = (54, 50, 36) if i == sel else (20, 22, 32)
        if i == sel:
            con.draw_rect(x + 1, yy, w - 2, 1, ch=ord(" "), bg=rowbg)
        if e[0] == "meal":
            _, label, price, stam, hp = e
            afford = p.gold >= price
            gains = f"+{stam}st" + (f" +{hp}hp" if hp else "")
            con.print(x + 2, yy, ("▸ " if i == sel else "  ") + label, fg=C.WHITE if afford else C.DIM, bg=rowbg)
            con.print(x + w - 20, yy, gains, fg=(150, 210, 150), bg=rowbg)
            con.print(x + w - 8, yy, f"{price}g", fg=C.GOLD_COLOR if afford else C.DIM, bg=rowbg)
        elif e[0] == "buy":
            _, item, price = e
            afford = p.gold >= price
            con.print(x + 2, yy, ("▸ " if i == sel else "  ") + item.name, fg=C.WHITE if afford else C.DIM, bg=rowbg)
            con.print(x + w - 10, yy, f"{price}g", fg=C.GOLD_COLOR if afford else C.DIM, bg=rowbg)
        elif e[0] == "sellto":
            _, item, price, q = e
            from ..game import skills
            star = (" " + skills.stars(q)) if q else ""
            con.print(x + 2, yy, ("▸ " if i == sel else "  ") + f"Sell {item.name}{star}",
                      fg=(200, 220, 160), bg=rowbg)
            con.print(x + w - 10, yy, f"+{price}g", fg=C.GOLD_COLOR, bg=rowbg)
        elif e[0] == "commission":
            _, label, kind, price, mats = e
            matstr = ", ".join(f"{q} {it.name.split()[0].lower()}" for it, q in mats)
            afford = p.gold >= price and all(p.inventory.count(it) >= q for it, q in mats)
            con.print(x + 2, yy, ("▸ " if i == sel else "  ") + label,
                      fg=C.WHITE if afford else C.DIM, bg=rowbg)
            con.print(x + 28, yy, matstr[:w - 40], fg=(190, 180, 150) if afford else C.DIM, bg=rowbg)
            con.print(x + w - 10, yy, f"{price}g", fg=C.GOLD_COLOR if afford else C.DIM, bg=rowbg)
        else:  # upgrade
            tool = e[1]
            tier = p.tool_tier.get(tool, 0)
            if tier >= len(C.TOOL_TIERS) - 1:
                txt, cost = f"{tool.name}: Mithril (max)", ""
                col = C.DIM
            else:
                gold, bar, count = content.upgrade_cost(tier)
                txt = f"{tool.name}: {C.TOOL_TIERS[tier]}→{C.TOOL_TIERS[tier + 1]}"
                cost = f"{gold}g +{count} {bar.name.split()[0]}"
                affordable = p.gold >= gold and p.inventory.count(bar) >= count
                col = C.WHITE if affordable else C.DIM
            con.print(x + 2, yy, ("▸ " if i == sel else "  ") + txt, fg=col, bg=rowbg)
            con.print(x + w - 16, yy, cost, fg=(200, 190, 150), bg=rowbg)

    con.print(x + 2, y + h - 2, f"Gold {p.gold}g   ↑↓ Enter buy/upgrade   Esc close", fg=C.DIM)


def render_gift(con: tcod.console.Console, state: GameState, npc, sel: int) -> None:
    from ..game import village, skills
    gifts = village.giftable_items(state)
    w, h = 48, min(C.SCREEN_H - 4, max(7, len(gifts) + 5))
    body = h - 4
    x, y = _modal(con, w, h, f"Give a gift to {npc.name}")
    if not gifts:
        con.print(x + 2, y + 2, "You have nothing to give.", fg=C.DIM)
    sel = max(0, min(sel, len(gifts) - 1)) if gifts else 0
    start, end = _window(sel, len(gifts), body)
    for row, (it, q, ql) in enumerate(gifts[start:end]):
        i = start + row
        yy = y + 2 + row
        rowbg = (54, 50, 36) if i == sel else (20, 22, 32)
        if i == sel:
            con.draw_rect(x + 1, yy, w - 2, 1, ch=ord(" "), bg=rowbg)
        tag = " (loves!)" if it in npc.loves else " (likes)" if it in npc.likes else " (dislikes)" if it in npc.dislikes else ""
        star = (" " + skills.stars(ql)) if ql else ""
        con.print(x + 2, yy, ("▸ " if i == sel else "  ") + f"{q:>3} {it.name}{star}{tag}", fg=C.WHITE, bg=rowbg)
    if start > 0:
        con.print(x + w - 4, y + 2, "▲", fg=_HDR)
    if end < len(gifts):
        con.print(x + w - 4, y + h - 3, "▼", fg=_HDR)
    con.print(x + 2, y + h - 2, "↑↓ select   Enter give   Esc close", fg=C.DIM)
