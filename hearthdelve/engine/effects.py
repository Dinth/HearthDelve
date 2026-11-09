"""Every animation effect, registered with the animation engine (engine/anim.py).

Ongoing effects run each frame and decide for themselves whether anything
applies; one-off effects play when something happens in the game. They draw
only through the :class:`anim.Frame` they're handed.
"""
from __future__ import annotations

import math
import random

import numpy as np

from . import anim
from . import constants as C
from ..world import tile

# Tile-id groups that get ambient animation.
_GRASS_IDS = np.array([tile.GRASS, tile.MEADOW, tile.TALL_GRASS, tile.FOG_GRASS, tile.BUSH,
                       tile.FLOWER_RED, tile.FLOWER_YELLOW, tile.FLOWER_VIOLET, tile.FLOWER_WHITE])
_WATER_IDS = np.array([tile.WATER, tile.RIVER])
_ORE_IDS = np.array([tile.ORE_VEIN])
# gem glitter colours: red, blue, orange, green, white
_GEM_PALETTE = np.array([[226, 84, 84], [92, 132, 232], [236, 150, 68],
                         [92, 202, 112], [236, 236, 236]], dtype=np.float32)


def _rendering():
    """The renderer's shared tile tables (imported when first needed: the
    renderer imports this module)."""
    from . import rendering
    return rendering


# ==============================================================================
# SHADE — scale the ground's colours
# ==============================================================================
@anim.ongoing(anim.SHADE, 10)
def cloud_shadows(f: anim.Frame) -> None:
    """Cloudy: the whole scene sits a touch dimmer (overcast), and big soft
    cloud shadows drift across the land on the wind, with brighter gaps where
    the sun breaks through. Smooth low frequencies (not a floored hash) so the
    shadows read as broad passing clouds, not a grid."""
    if f.state.world.is_dungeon or f.state.weather != "Cloudy":
        return
    xs, ys, t = f.xs, f.ys, f.t
    cs = (np.sin(xs * 0.11 - t * 0.6) + np.sin(ys * 0.085 + t * 0.40)
          + 0.6 * np.sin((xs - ys) * 0.07 + t * 0.5))   # several patches across the view
    cloud = np.clip((cs + 0.2) / 1.4, 0.0, 1.0)      # broad coverage, soft edges
    dim = (0.05 + 0.32 * cloud)[..., None]           # ~5% overcast .. ~37% under a cloud
    f.fg *= (1 - dim)
    f.bg *= (1 - dim)


# ==============================================================================
# TINT — per-tile multipliers, gathered then applied together
# ==============================================================================
@anim.ongoing(anim.TINT, 10)
def wind(f: anim.Frame) -> None:
    """Wind gusts. A narrow bright band — a line perpendicular to the wind
    direction — sweeps across the map periodically, like a gust rippling over a
    real field, brightening grass (and, more gently, trees) as it passes."""
    grass = np.isin(f.view, _GRASS_IDS)
    trees = np.isin(f.view, _rendering()._TREE_IDS)
    if not (grass.any() or trees.any()):
        return
    xs, ys, t = f.xs, f.ys, f.t
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
    f.fg_mul = np.where(grass, 1.0 + 0.27 * gust + ambient, f.fg_mul)
    f.fg_mul = np.where(trees, 1.0 + 0.17 * gust + 0.5 * ambient, f.fg_mul)


@anim.ongoing(anim.TINT, 20)
def water_shimmer(f: anim.Frame) -> None:
    """Water: two interfering wave trains shimmer the surface (fg + a little bg)."""
    water = np.isin(f.view, _WATER_IDS)
    if not water.any():
        return
    xs, ys, t = f.xs, f.ys, f.t
    wave = (np.sin((xs * 0.70 - ys * 0.50) - t * 2.6)
            + 0.5 * np.sin((xs * 0.25 + ys * 0.60) - t * 1.5))
    f.fg_mul = np.where(water, 1.0 + 0.17 * wave, f.fg_mul)
    f.bg_mul = np.where(water, 1.0 + 0.10 * wave, f.bg_mul)


@anim.ongoing(anim.TINT, 30)
def ore_twinkle(f: anim.Frame) -> None:
    """Ore: each vein twinkles independently — a short, bright shimmer at its
    own pseudo-random time, so only a few flash at once."""
    ore = np.isin(f.view, _ORE_IDS)
    if not ore.any():
        return
    xs, ys, t = f.xs, f.ys, f.t
    offset = anim.hash01(xs, ys)                      # per-tile phase offset
    cycle = 12.0 + 16.0 * anim.hash01(xs + 5.2, ys + 1.3)   # 12..28s between shimmers
    tau = (t / cycle + offset)
    tau = (tau - np.floor(tau)) * cycle               # seconds into this cycle
    pw = 0.13                                         # ~0.3s shimmer, fixed
    pulse = np.exp(-(tau ** 2) / (2 * pw * pw))
    pulse = np.maximum(pulse, np.exp(-((tau - cycle) ** 2) / (2 * pw * pw)))
    f.fg_mul = np.where(ore, 1.0 + 1.2 * pulse, f.fg_mul)


@anim.ongoing(anim.TINT, 40)
def campfire_flicker(f: anim.Frame) -> None:
    """Campfire: a restless warm flicker so the flames never sit still."""
    fire = f.view == tile.CAMPFIRE
    if not fire.any():
        return
    xs, ys, t = f.xs, f.ys, f.t
    flick = (np.sin(t * 6.3 + xs * 2.1) + 0.6 * np.sin(t * 11.0 + ys * 1.7))
    f.fg_mul = np.where(fire, 1.0 + 0.22 * flick, f.fg_mul)


# ==============================================================================
# GROUND — blends over the ground
# ==============================================================================
@anim.ongoing(anim.GROUND, 10)
def coastal_foam(f: anim.Frame) -> None:
    """Coastal foam: SEA cells (not the river) that lap against land carry a
    bright surf line that surges and recedes, so coasts read as living edges."""
    sea = f.view == tile.WATER
    if f.state.world.is_dungeon or not sea.any():
        return
    water = np.isin(f.view, _WATER_IDS)
    land = ~water                                    # water = sea|river; land = neither
    adj = np.zeros_like(sea)
    adj[1:, :] |= land[:-1, :]; adj[:-1, :] |= land[1:, :]
    adj[:, 1:] |= land[:, :-1]; adj[:, :-1] |= land[:, 1:]
    shore = sea & adj
    if not shore.any():
        return
    xs, ys, t = f.xs, f.ys, f.t
    surge = np.clip(0.30 + 0.70 * np.sin((xs * 0.7 - ys * 0.5) - t * 2.6), 0.0, 1.0)
    k = (shore.astype(np.float32) * surge)[..., None]
    foam = np.array([224.0, 238.0, 246.0], np.float32)
    f.fg = f.fg * (1.0 - k * 0.72) + foam * (k * 0.72)
    f.bg = f.bg * (1.0 - k * 0.45) + foam * (k * 0.45)


@anim.ongoing(anim.GROUND, 20)
def rain_on_the_ground(f: anim.Frame) -> None:
    """Rain wets the world: still, cool puddles sit in fixed low spots on open
    ground (they don't wander), and ripple rings spread from drops striking any
    open water — river included."""
    st = f.state
    if st.world.is_dungeon or st.weather not in ("Rain", "Storm"):
        return
    xs, ys, t, view = f.xs, f.ys, f.t, f.view
    water = np.isin(view, _WATER_IDS)
    wet = anim.hash01(np.floor(xs * 0.5), np.floor(ys * 0.5))   # fixed patches, no drift
    puddle = (wet > 0.63) & _rendering()._TEX_BY_ID[view]       # only on open ground
    if puddle.any():
        for ci, mul in ((0, 0.66), (1, 0.78), (2, 1.02)):       # darker, cooler, faint sheen
            fac = np.where(puddle, mul, 1.0)
            f.fg[..., ci] *= fac
            f.bg[..., ci] = np.minimum(255.0, f.bg[..., ci] * fac)
    if water.any():
        wc = np.argwhere(water)                                 # drops land ON water
        X = np.arange(C.VIEW_W, dtype=np.float32)[:, None]
        Y = np.arange(C.VIEW_H, dtype=np.float32)[None, :]
        rings = np.zeros((C.VIEW_W, C.VIEW_H), np.float32)
        r_max = 1.8                                             # tiny drop-splash rings
        for i in range(22 if st.weather == "Storm" else 14):
            per = 1.1 + anim.h1(i, 2.0)
            phase = t / per + anim.h1(i, 5.0)
            cyc = math.floor(phase)
            cx, cy = wc[int(anim.h1(i * 13 + cyc, 3.0) * len(wc)) % len(wc)]
            rr = (phase - cyc) * r_max
            d = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
            rings = np.maximum(rings, np.exp(-((d - rr) ** 2) / 0.5) * max(0.0, 1.0 - rr / r_max))
        rm = (water.astype(np.float32) * rings)[..., None]
        drop = np.array([206.0, 230.0, 250.0], np.float32)
        f.fg = f.fg * (1.0 - rm * 0.75) + drop * (rm * 0.75)
        f.bg = f.bg * (1.0 - rm * 0.45) + drop * (rm * 0.45)


# ==============================================================================
# GROUND_LATE — after crops, trees and machines are laid down
# ==============================================================================
@anim.ongoing(anim.GROUND_LATE, 10)
def gem_glitter(f: anim.Frame) -> None:
    """Gems glitter: each a stable random colour (red/blue/orange/green/white)
    with an occasional sparkle."""
    gem_mask = f.view == tile.GEM_VEIN
    if not gem_mask.any():
        return
    xs, ys, t = f.xs, f.ys, f.t
    idx = np.clip((anim.hash01(xs, ys) * 5).astype(np.int32), 0, 4)
    base = _GEM_PALETTE[idx]
    cyc = 2.0 + 3.0 * anim.hash01(xs + 9.0, ys + 2.0)
    ph = (t / cyc + anim.hash01(xs + 3.1, ys + 1.7))
    ph = ph - np.floor(ph)
    spark = np.maximum(np.exp(-(ph * ph) / 0.005),
                       np.exp(-((ph - 1.0) ** 2) / 0.005))
    gemfg = np.clip(base * (0.7 + 0.55 * spark)[..., None], 0, 255)
    f.fg = np.where(gem_mask[..., None], gemfg, f.fg)


@anim.ongoing(anim.GROUND_LATE, 20)
def lava_breathes(f: anim.Frame) -> None:
    """The caldera breathes: lava pulses between ember-red and furnace-orange
    (each tile on its own phase), and throws a warm halo on the rock beside it."""
    lava_mask = f.view == tile.LAVA
    if not lava_mask.any():
        return
    xs, ys, t = f.xs, f.ys, f.t
    lph = anim.hash01(xs + 5.0, ys + 8.0)
    pulse = (0.72 + 0.28 * np.sin(t * 2.4 + lph * 6.28)).astype(np.float32)
    f.bg = np.where(lava_mask[..., None],
                    np.stack([205 * pulse, 62 * pulse, 10 + 8 * pulse], axis=-1), f.bg)
    f.fg = np.where(lava_mask[..., None],
                    np.stack([np.full_like(pulse, 255.0), 140 + 80 * pulse, 30 + 30 * pulse],
                             axis=-1), f.fg)
    halo = np.zeros_like(lava_mask)
    halo[1:, :] |= lava_mask[:-1, :]; halo[:-1, :] |= lava_mask[1:, :]
    halo[:, 1:] |= lava_mask[:, :-1]; halo[:, :-1] |= lava_mask[:, 1:]
    halo &= ~lava_mask
    if halo.any():
        warm = np.array([64.0, 20.0, 4.0], np.float32) * (0.5 + 0.5 * pulse)[..., None]
        f.bg = np.where(halo[..., None], np.minimum(255.0, f.bg + warm), f.bg)


# ==============================================================================
# VEIL — over the creatures, under the player
# ==============================================================================
_STEAM_RNG = random.Random(0xC01DFACE)
# A steam blob: [world x, world y, vx, vy (tiles/s), age, life (s), radius].
_S_X, _S_Y, _S_VX, _S_VY, _S_AGE, _S_LIFE, _S_R = range(7)


def _steam(f: anim.Frame) -> None:
    """Persistent, world-space steam over the Westreach.

    Blobs are born at the caldera while it rains, each takes its own heading,
    and they drift across the world over ~10-22s, swelling and fading — so a
    cloud bank keeps roaming even after you've walked past the lava. A dense
    column also boils straight off the vent whenever it's on screen. State
    lives on the west map (cosmetic, regenerated on load — never saved)."""
    state, con, view, ox, oy, t = f.state, f.con, f.view, f.ox, f.oy, f.t
    vw, vh, xs, ys = f.vw, f.vh, f.xs, f.ys
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

    # Real-time delta (the animation clock is monotonic wall-clock seconds).
    # Clamp so the first frame / a pause doesn't spawn or teleport a burst.
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
            base = np.maximum(base, anim.shift2d(hot, int(round(k * 0.6)), -k) * (0.94 ** k))
        for _ in range(3):
            base = np.maximum(base, np.maximum(anim.shift2d(base, 1, 0),
                                               anim.shift2d(base, -1, 0)) * 0.82)
        turb = anim.hash01(np.floor(xs * 0.45 - t * 2.4), np.floor(ys * 0.45 - t * 3.2))
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
    field = anim.blur5(field)
    #   shape: cloud-scale mottle (drifts smoothly);  grain: a per-cell stipple
    #   (distinct every cell so it actually breaks the grid) that slides across
    #   the cells over time. floor() only on the coarse term — a sub-cell floor
    #   on the fine one would just make new little squares.
    shape = anim.hash01(np.floor(xs * 0.3 - t * 1.4), np.floor(ys * 0.3 - t * 1.9))
    grain = anim.hash01(xs + np.floor(t * 3.0), ys - np.floor(t * 2.0))
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


@anim.ongoing(anim.VEIL, 10)
def westreach_weather(f: anim.Frame) -> None:
    """Weather theatre for the volcano country, painted over the composed view
    (the player is drawn after, so you never vanish into your own weather)."""
    state, con, t = f.state, f.con, f.t
    if state.west is None or state.world is not state.west:
        return
    vw, vh = f.vw, f.vh

    # Rain on the caldera flashes to steam: a thick column boils off the vent,
    # and blobs of it keep detaching and drifting across the reach on their own
    # headings (see _steam) — so cloud banks roam even where no lava is in view.
    _steam(f)

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
    if anim.eruption_age(t, state.seed) is not None:
        lava = np.argwhere(f.view == tile.LAVA)
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


# ==============================================================================
# OVERLAY — over everything in view
# ==============================================================================
@anim.ongoing(anim.OVERLAY, 10)
def weather(f: anim.Frame) -> None:
    """Animated weather over the surface view: the fog's veil, the storm's
    lightning, and falling rain, snow or drifting fog motes — which skip the
    cells creatures hold, so their glyphs never flicker under the rain."""
    state, con, t, occupied = f.state, f.con, f.t, f.occupied
    if state.world.is_dungeon:
        return
    w = state.weather
    if w == "Fog":
        # Fog closes in: a clearish bubble around you fades to heavy grey toward
        # the edges, so you genuinely can't see far — not just a flat haze.
        veil = np.array([150, 156, 164], dtype=np.float32)
        px, py = state.player.x - f.ox, state.player.y - f.oy
        X = np.arange(C.VIEW_W, dtype=np.float32)[:, None]
        Y = np.arange(C.VIEW_H, dtype=np.float32)[None, :]
        d = np.sqrt((X - px) ** 2 + (Y - py) ** 2)
        kbg = np.clip((d - 4.0) / 12.0, 0.12, 0.74)[..., None]     # near clear, far socked in
        for chan, mul in (("bg", 1.0), ("fg", 0.7)):
            buf = con.rgb[chan][:C.VIEW_W, :C.VIEW_H].astype(np.float32)
            k = kbg * mul
            con.rgb[chan][:C.VIEW_W, :C.VIEW_H] = (buf * (1 - k) + veil * k).astype(np.uint8)
    if w == "Storm":
        # Occasional lightning: a brief, near-white flash over the whole view at
        # irregular moments (a double-strike for that thunderclap feel).
        flash = anim.lightning(t, state.seed)
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


def _wet_tomorrow(state) -> bool:
    """Is rain/storm forecast for tomorrow? (Drives the natural weather tells.)"""
    try:
        from ..game import farming
        return farming.forecast(state) in ("Rain", "Storm")
    except Exception:
        return False


@anim.ongoing(anim.OVERLAY, 20)
def seasonal_motes(f: anim.Frame) -> None:
    """Drifting seasonal motes over the surface — petals in spring, lazy pollen
    (and fireflies after dark) in summer, tumbling leaves in autumn — and, on a
    calm day before rain, a cloud of gnats. Purely atmospheric; skipped
    underground and when the weather already fills the air. Winter is left to
    the snow."""
    state, con, t, occupied = f.state, f.con, f.t, f.occupied
    if state.world.is_dungeon or state.weather in ("Rain", "Storm", "Snow", "Fog"):
        return
    vw, vh = C.VIEW_W, C.VIEW_H
    season = state.season
    dr, dg, db = f.daylight
    night = (dr + dg + db) / 3.0 < 0.62

    # Nature's own forecast: on a calm day before rain, gnats rise and swarm in
    # a low, restless cloud over open ground — read it and you'll know the
    # morning brings wet. They keep out of doors: never inside a building.
    if season != "Winter" and _wet_tomorrow(state):
        ox, oy = f.ox, f.oy
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
            gx = int(cx + 5 * math.sin(t * 3.1 + i * 1.7) + (anim.h1(i, 3.0) * 6 - 3))
            gy = int(cy + 4 * math.cos(t * 2.7 + i * 2.3) + (anim.h1(i, 7.0) * 5 - 2.5))
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


@anim.ongoing(anim.OVERLAY, 30)
def living_fire(f: anim.Frame) -> None:
    """Living fire: embers rise and wink out above campfires, hearths and lava,
    and hearths trail a thin chimney plume — so fires flicker with real motion
    and villages read as lived-in."""
    state, con, t, occupied = f.state, f.con, f.t, f.occupied
    w = state.world
    ox, oy = f.ox, f.oy
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
                if gate < 1.0 and anim.h1(key, 9.0) > gate:
                    continue
                rise = ((t * 2.4 + anim.h1(key, 2.0) * rise_h) % rise_h)
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
                h = ((t * 1.3 + anim.h1(key, 5.0) * 6.0) % 6.0)
                sx = hx + int(round(0.55 * h + math.sin(t * 0.8 + j)))
                sy = hy - 1 - int(h)
                if 0 <= sx < vw and 0 <= sy < vh and (sx, sy) not in occupied:
                    g = int(70 + 130 * max(0.15, 1.0 - h / 6.0))
                    con.rgb["ch"][sx, sy] = ord("°" if h < 3 else "·")
                    con.rgb["fg"][sx, sy] = (g, g, max(0, g - 12))


@anim.ongoing(anim.OVERLAY, 40)
def crossings(f: anim.Frame) -> None:
    """Occasional life crossing the view: a small flock of birds sweeping over
    by day, butterflies fluttering on clear spring & summer afternoons. Purely
    atmospheric, crossing now and then rather than on a beat."""
    state, con, t, occupied = f.state, f.con, f.t, f.occupied
    if state.world.is_dungeon:
        return
    vw, vh = C.VIEW_W, C.VIEW_H
    dr, dg, db = f.daylight
    daytime = (dr + dg + db) / 3.0 > 0.72                 # excludes the blue of deep night

    low_flight = _wet_tomorrow(state)                     # birds fly low before rain
    if daytime and state.weather != "Storm":              # birds shelter in storms
        for fl in range(2):
            crossing = anim.flyover(fl, t, state.seed)    # now and then, never on a beat
            if crossing is None:
                continue
            travel, cyc = crossing
            rightward = anim.h1(fl * 7 + cyc, 3.0) < 0.5
            headx = int(-4 + travel * (vw + 8)) if rightward else int(vw + 4 - travel * (vw + 8))
            # high across the sky normally; skimming the low third when rain nears
            row = (int(vh * 0.62 + anim.h1(fl * 7 + cyc, 9.0) * (vh * 0.33)) if low_flight
                   else int(2 + anim.h1(fl * 7 + cyc, 9.0) * (vh * 0.45)))
            flap = "v" if int(t * 6) % 2 else "^"
            for b in range(3 + int(anim.h1(fl * 7 + cyc, 1.0) * 3)):   # a loose 3–5 bird V
                bx = headx - (1 if rightward else -1) * b * 2
                by = row + ((b + 1) // 2) * (-1 if b % 2 else 1)
                by += int(round(0.5 * math.sin(t * 1.5 + b)))
                if 0 <= bx < vw and 0 <= by < vh and (bx, by) not in occupied:
                    con.rgb["ch"][bx, by] = ord(flap)
                    con.rgb["fg"][bx, by] = (64, 60, 70)          # a dark silhouette

    if state.season in ("Spring", "Summer") and state.weather == "Clear" and daytime:
        for i in range(4):
            bx = int((anim.h1(i, 3.0) * vw + 9 * math.sin(t * 0.7 + i)
                      + t * 2.0 * (anim.h1(i, 4.0) - 0.5)) % vw)
            by = int((anim.h1(i, 7.0) * vh + 6 * math.sin(t * 1.1 + i * 2.0)) % vh)
            if (bx, by) in occupied:
                continue
            con.rgb["ch"][bx, by] = ord("*" if int(t * 4 + i) % 2 else "x")
            con.rgb["fg"][bx, by] = (236, 228, 150) if i % 2 else (240, 200, 220)


# ==============================================================================
# One-off effects — things that happen, played for a moment
# ==============================================================================
def _blend(con, sx: int, sy: int, chan: str, colour, k: float) -> None:
    """Mix `colour` into a cell's fg or bg by `k` (0..1)."""
    cur = con.rgb[chan][sx, sy].astype(np.float32)
    con.rgb[chan][sx, sy] = (cur * (1.0 - k) + np.array(colour, np.float32) * k).astype(np.uint8)


def _write(f: anim.Frame, x: int, y: int, text: str, colour) -> None:
    """Print `text` into the view from screen cell (x, y), clipped to it."""
    for i, ch in enumerate(text):
        cx = x + i
        if 0 <= cx < f.vw and 0 <= y < f.vh:
            f.con.rgb["ch"][cx, y] = ord(ch)
            f.con.rgb["fg"][cx, y] = colour


_HIT_FLASH = 0.22          # seconds the struck cell flashes


@anim.one_off("hit", life=0.9)
def hit(f: anim.Frame, h, age: float) -> None:
    """A blow or shot lands: the struck cell flashes (gold on a critical, red
    when it's you), and the damage floats up from it and fades."""
    cell = f.cell(h.x, h.y)
    if cell is None:
        return
    sx, sy = cell
    crit, yours = h.data.get("crit", False), h.data.get("on") == "you"
    if age < _HIT_FLASH:
        k = 1.0 - age / _HIT_FLASH
        flash = (255, 236, 150) if crit else (230, 70, 60) if yours else (245, 245, 240)
        _blend(f.con, sx, sy, "bg", flash, (0.85 if crit else 0.6) * k)
    text = f"{h.data.get('amount', 0)}" + ("!" if crit else "")
    colour = (255, 120, 100) if yours else (255, 226, 110) if crit else (245, 242, 232)
    fade = 1.0 if age < 0.5 else max(0.35, 1.0 - (age - 0.5) / 0.4)
    _write(f, sx - len(text) // 2, sy - 1 - int(age / 0.3),
           text, tuple(int(c * fade) for c in colour))


@anim.one_off("wake", life=0.9)
def wake(f: anim.Frame, h, age: float) -> None:
    """A monster notices you: a "!" over it, steady for a moment, then
    blinking out."""
    cell = f.cell(h.x, h.y)
    if cell is None:
        return
    if age > 0.45 and int(age * 10) % 2:
        return                                    # blinking out
    sx, sy = cell
    _write(f, sx, sy - 1, "!", (255, 214, 72))


# A harvest's sparkle, by star quality: pale leaf, green, sky, gold, amber —
# and a 5-star crop runs through every one of them.
_QUALITY_SPARK = ((210, 226, 190), (170, 225, 130), (140, 210, 245),
                  (250, 214, 100), (255, 160, 80))


@anim.one_off("harvest", life=0.8)
def harvest(f: anim.Frame, h, age: float) -> None:
    """A crop is harvested or fruit picked: a burst of sparks flies out from
    it, more of them and brighter the finer it is, coloured by its stars."""
    cell = f.cell(h.x, h.y)
    if cell is None:
        return
    sx, sy = cell
    q = max(0, min(5, int(h.data.get("quality", 0))))
    n = 4 + q
    life = 0.8
    r = 1.0 + 2.0 * (age / life)
    fade = 1.0 if age < 0.4 else max(0.3, 1.0 - (age - 0.4) / 0.4)
    spin = anim.h1(h.x * 31 + h.y, 1.7) * 6.2832
    for i in range(n):
        ang = spin + i * 6.2832 / n
        ri = r * (0.8 + 0.4 * anim.h1(i, 3.3))             # not one perfect ring
        x = sx + int(round(math.cos(ang) * ri * 1.3))     # cells are taller than wide
        y = sy + int(round(math.sin(ang) * ri * 0.8))
        if (x, y) == (sx, sy) or (x, y) in f.occupied:
            continue
        colour = _QUALITY_SPARK[(i + int(age * 10)) % 5] if q == 5 else _QUALITY_SPARK[q]
        glyph = ("*" if q >= 3 else "+") if age < 0.35 else "·"
        _write(f, x, y, glyph, tuple(int(c * fade) for c in colour))


def _sign(v: int) -> int:
    return (v > 0) - (v < 0)


_SHOT_GLYPH = {(1, 0): "-", (-1, 0): "-", (0, 1): "|", (0, -1): "|",
               (1, 1): "\\", (-1, -1): "\\", (1, -1): "/", (-1, 1): "/"}


def _flight_cell(f: anim.Frame, h, age: float):
    """Where a projectile is along its recorded path at `age`, with the step
    it took to get there — or None once it has landed or is out of view."""
    path, per = h.data.get("path", []), h.data.get("per", 0.03)
    k = int(age / per)
    if not path or k >= len(path):
        return None
    x, y = path[k]
    px, py = (h.x, h.y) if k == 0 else path[k - 1]
    cell = f.cell(x, y)
    return None if cell is None else (cell, (_sign(x - px), _sign(y - py)))


@anim.one_off("shot", life=0.5)
def shot(f: anim.Frame, h, age: float) -> None:
    """A loosed arrow (or sling stone) flies its line, pointing the way it
    goes; its hit lands when it arrives."""
    at = _flight_cell(f, h, age)
    if at is None:
        return
    (sx, sy), step = at
    if h.data.get("stone"):
        _write(f, sx, sy, "∙", (190, 186, 176))
    else:
        _write(f, sx, sy, _SHOT_GLYPH.get(step, "-"), (232, 218, 176))


@anim.one_off("lob", life=0.8)
def lob(f: anim.Frame, h, age: float) -> None:
    """A thrown bomb arcs out, its fuse fizzing; the blast waits for it."""
    at = _flight_cell(f, h, age)
    if at is None:
        return
    (sx, sy), _step = at
    if h.data.get("firecracker"):
        _write(f, sx, sy, "¡", (240, 120, 90))
    else:
        _write(f, sx, sy, "●", (120, 112, 104))
        if sy - 1 >= 0 and int(age * 20) % 2 == 0:
            _write(f, sx, sy - 1, "'", (255, 196, 90))     # the fuse spits


@anim.one_off("blast", life=0.5)
def blast(f: anim.Frame, h, age: float) -> None:
    """A bomb goes off: a white-hot flash at its heart and a ring of fire
    racing out past the blast's reach."""
    cell = f.cell(h.x, h.y)
    if cell is None:
        return
    sx, sy = cell
    reach = h.data.get("radius", 1) + 1
    r = reach * age / 0.5
    fade = 1.0 - age / 0.5
    for dx in range(-reach - 1, reach + 2):
        for dy in range(-reach - 1, reach + 2):
            x, y = sx + dx, sy + dy
            if not (0 <= x < f.vw and 0 <= y < f.vh):
                continue
            d = math.hypot(dx * 0.75, dy)                 # cells are taller than wide
            ring = max(0.0, 1.0 - abs(d - r) / 0.8)
            core = max(0.0, 1.0 - age / 0.15) if d < 0.5 else 0.0
            k = max(ring * fade, core)
            if k <= 0.05:
                continue
            _blend(f.con, x, y, "bg", (255, 236, 200) if core > ring else (240, 140, 50), 0.85 * k)
            if ring > 0.6:
                _write(f, x, y, "*", (255, 214, 120))


@anim.one_off("crack", life=0.35)
def crack(f: anim.Frame, h, age: float) -> None:
    """A firecracker pops: a bright flash and a scatter of coloured sparks."""
    cell = f.cell(h.x, h.y)
    if cell is None:
        return
    sx, sy = cell
    if age < 0.1:
        _blend(f.con, sx, sy, "bg", (255, 240, 200), 0.8)
    colours = ((255, 120, 120), (120, 220, 255), (255, 230, 120), (180, 255, 150))
    for i in range(4):
        ang = i * 1.5708 + 0.7
        x = sx + int(round(math.cos(ang) * (1 + 2.5 * age / 0.35) * 1.3))
        y = sy + int(round(math.sin(ang) * (1 + 2.5 * age / 0.35) * 0.8))
        _write(f, x, y, "*", colours[i])


@anim.one_off("shake", life=0.2, order=999)
def shake(f: anim.Frame, h, age: float) -> None:
    """The ground jumps under a blast: the whole view jolts a cell this way
    and that for a moment (drawn last, so everything in view shakes)."""
    steps = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 0))
    dx, dy = steps[min(len(steps) - 1, int(age / 0.04))]
    n = h.data.get("strength", 1)
    view = f.con.rgb[:f.vw, :f.vh]
    f.con.rgb[:f.vw, :f.vh] = np.roll(view, shift=(dx * n, dy * n), axis=(0, 1))


# What flies off a tool's work: (fresh, settling, colour) — wood chips, sparks
# from rock, green bits from brush.
_STRIKE_BITS = {"Axe": ("'", ",", (176, 128, 74)), "Pickaxe": ("*", "·", (255, 226, 150)),
                "Machete": ("'", "`", (128, 196, 96))}
_PIP = "▁▂▃▄▅▆▇█"


@anim.one_off("strike", life=0.3)
def strike(f: anim.Frame, h, age: float) -> None:
    """A beat of chopping, mining or clearing: a couple of chips (or sparks)
    fly up and out from the work, and a pip beyond it fills as it goes."""
    cell = f.cell(h.x, h.y)
    if cell is None:
        return
    sx, sy = cell
    fresh, settled, colour = _STRIKE_BITS.get(h.data.get("tool"), ("'", ",", (200, 190, 170)))
    done = h.data.get("done", 0.0)
    seed = int(h.at) * 7 + int(done * 97)
    fade = 1.0 if age < 0.15 else 0.6
    for i in range(2):
        ang = -1.5708 + (anim.h1(seed + i, 2.3) - 0.5) * 2.6        # mostly upward
        r = 0.7 + 2.0 * age / 0.3
        x = sx + int(round(math.cos(ang) * r * 1.3))
        y = sy + int(round(math.sin(ang) * r * 0.8))
        if (x, y) == (sx, sy) or (x, y) in f.occupied:
            continue
        _write(f, x, y, fresh if age < 0.15 else settled, tuple(int(c * fade) for c in colour))
    p = f.state.player
    px, py = sx + (h.x - p.x), sy + (h.y - p.y)     # beyond the work, never on you
    if (px, py) not in f.occupied:
        _write(f, px, py, _PIP[min(len(_PIP) - 1, int(done * len(_PIP)))], (232, 222, 170))


@anim.one_off("fell", life=0.9)
def fell(f: anim.Frame, h, age: float) -> None:
    """A tree comes down: it leans away from you, then crashes over, trunk and
    crown lying where it fell before the stump is all that's left."""
    cell = f.cell(h.x, h.y)
    if cell is None:
        return
    sx, sy = cell
    dx, dy = h.data.get("away", (1, 0))
    if (dx, dy) == (0, 0):
        dx = 1
    trunk, crown = (130, 94, 60), h.data.get("colour", (90, 150, 80))
    if age < 0.3:
        lean = "/" if (dx > 0 or dy < 0) else "\\"
        _write(f, sx, sy, lean, trunk)
        if (sx + dx, sy + dy) not in f.occupied:
            _write(f, sx + dx, sy + dy, h.data.get("glyph", "♣"), crown)
        return
    fade = max(0.3, 1.0 - (age - 0.3) / 0.6)
    bar = "═" if dx else "║"
    for k in (1, 2):
        if (sx + dx * k, sy + dy * k) not in f.occupied:
            _write(f, sx + dx * k, sy + dy * k, bar, tuple(int(c * fade) for c in trunk))
    if (sx + dx * 3, sy + dy * 3) not in f.occupied:
        _write(f, sx + dx * 3, sy + dy * 3, h.data.get("glyph", "♣"),
               tuple(int(c * fade) for c in crown))


@anim.one_off("water", life=0.6)
def water(f: anim.Frame, h, age: float) -> None:
    """The watering can tips: drops fall into the ground and spatter, and a
    planted cell darkens from dusty to damp rather than all at once."""
    cell = f.cell(h.x, h.y)
    if cell is None:
        return
    sx, sy = cell
    if h.data.get("crop") and age < 0.5:
        _blend(f.con, sx, sy, "bg", (62, 40, 18), 1.0 - age / 0.5)   # it was parched a moment ago
    drop = (150, 196, 240)
    if age < 0.3:
        fall = int(age / 0.1)                       # three rows down into the soil
        for x in (sx - 1, sx, sx + 1):
            y = sy - 3 + fall + (x - sx) % 2
            if y < sy and (x, y) not in f.occupied:
                _write(f, x, y, "'", drop)
    else:
        for x, y in ((sx - 1, sy), (sx + 1, sy)):
            if (x, y) not in f.occupied:
                _write(f, x, y, "·", drop)


@anim.one_off("emote", life=1.0)
def emote(f: anim.Frame, h, age: float) -> None:
    """A creature shows how it feels: a ♥ for a petted animal or a loved gift,
    an "…" for a gift that missed — rising off it and fading."""
    cell = f.cell(h.x, h.y)
    if cell is None:
        return
    sx, sy = cell
    fade = 1.0 if age < 0.6 else max(0.3, 1.0 - (age - 0.6) / 0.4)
    colour = h.data.get("colour", (255, 128, 168))
    _write(f, sx, sy - 1 - int(age / 0.5), h.data.get("glyph", "♥"),
           tuple(int(c * fade) for c in colour))


@anim.ongoing(anim.OVERLAY, 50)
def songs_at_the_inn(f: anim.Frame) -> None:
    """Evenings at the inn: now and then a "♪" rises over someone there —
    each on their own time, never in chorus."""
    st = f.state
    if st.world.is_dungeon or not (19 * 60 <= st.time_minutes % 1440 < 22 * 60):
        return
    for npc in st.world.npcs:
        inn = npc.spots.get("inn")
        if inn is None or (npc.x, npc.y) != tuple(inn):
            continue
        age = anim.burst_age(f.t, 6.0, 0.45, 1.4, sum(map(ord, npc.name)) % 997 + 0.5)
        if age is None:
            continue
        cell = f.cell(npc.x, npc.y)
        if cell is not None:
            sx, sy = cell
            _write(f, sx, sy - 1 - int(age / 0.7), "♪", (240, 212, 140))


_SPRAY = (196, 226, 250)


@anim.one_off("plop", life=1.0)
def plop(f: anim.Frame, h, age: float) -> None:
    """A cast that finds nothing: the float drops in and a ripple spreads out
    from it and fades."""
    cell = f.cell(h.x, h.y)
    if cell is None:
        return
    sx, sy = cell
    if age < 0.25:
        _write(f, sx, sy, "o", (232, 96, 80))         # the red float, just landed
    r = 2.2 * age
    for dx in range(-3, 4):
        for dy in range(-2, 3):
            x, y = sx + dx, sy + dy
            if not (0 <= x < f.vw and 0 <= y < f.vh):
                continue
            ring = max(0.0, 1.0 - abs(math.hypot(dx * 0.75, dy) - r) / 0.6)
            if ring > 0.1:
                _blend(f.con, x, y, "bg", _SPRAY, 0.45 * ring * (1.0 - age))


@anim.one_off("splash", life=0.6)
def splash(f: anim.Frame, h, age: float) -> None:
    """The fish slips the hook: a splash of spray where the line went slack."""
    cell = f.cell(h.x, h.y)
    if cell is None:
        return
    sx, sy = cell
    spread = 1 if age < 0.25 else 2
    for x, y in ((sx - spread, sy), (sx + spread, sy), (sx, sy - 1)):
        if (x, y) not in f.occupied:
            _write(f, x, y, "~" if age < 0.3 else "·", _SPRAY)


@anim.one_off("catch", life=0.6)
def catch(f: anim.Frame, h, age: float) -> None:
    """A fish is landed: it leaps out of the water and arcs up to you."""
    cell = f.cell(h.x, h.y)
    if cell is None:
        return
    sx, sy = cell
    p = f.state.player
    tx, ty = p.x - f.ox, p.y - f.oy
    u = min(1.0, age / 0.5)
    x = int(round(sx + (tx - sx) * u))
    y = int(round(sy + (ty - sy) * u - 2.0 * math.sin(math.pi * u)))   # a leap, not a slide
    if age < 0.2 and (sx, sy - 1) not in f.occupied:
        _write(f, sx, sy - 1, "~", _SPRAY)
    if u < 1.0 and (x, y) != (tx, ty):
        _write(f, x, y, h.data.get("glyph", "≈"), (150, 212, 236))
