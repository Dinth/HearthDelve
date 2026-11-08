"""The animation engine: everything that moves on screen, in one place.

Every animation is an *effect*. An effect draws into one *layer* of the frame,
and the renderer runs the layers in order, at fixed points in composing the
view (see rendering.render_all):

  SHADE        scale the ground's colours (passing cloud shadows)
  TINT         per-tile colour multipliers, gathered then applied together
               (wind through grass and trees, water shimmer, ore twinkle,
               campfire flicker)
  GROUND       blends over the ground (coastal foam, puddles, rain ripples)
  GROUND_LATE  after crops, trees and machines are laid down (gem glitter,
               lava)
  VEIL         over the creatures but under the player (the Westreach's
               steam, ash and eruption)
  OVERLAY      over everything in view (weather, seasonal motes, embers and
               chimney smoke, flyovers, and the one-off effects)

There are two lifetimes, one engine:

* **Ongoing** effects (``@ongoing``) run every frame and decide for themselves
  whether anything applies — rain only while it rains, lava only where lava
  is in view.
* **One-off** effects (``@one_off``) are things that *happen*: the game layer
  records a happening on the state (``state.happen("hit", x, y, amount=7)``,
  never saved, never importing the renderer), and the engine plays the
  matching effect for its short life, timed from the frame it first shows on,
  then drops it.

Both get the same :class:`Frame` — the state, the animation clock, the camera,
the visible tiles, the colour buffers and the cells creatures already hold —
and the same timing helpers below, which are the only place a time-varying
formula lives. The effects themselves are in ``engine/effects.py``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

SHADE = "shade"
TINT = "tint"
GROUND = "ground"
GROUND_LATE = "ground_late"
VEIL = "veil"
OVERLAY = "overlay"
LAYERS = (SHADE, TINT, GROUND, GROUND_LATE, VEIL, OVERLAY)

# A happening older than this (in game minutes) when the screen first gets to
# it — a long rest, a night's sleep — has nothing left worth showing.
STALE_MINUTES = 2


@dataclass
class Frame:
    """One frame of the world view, shared by every effect drawn in it."""
    con: object
    state: object
    t: float                       # the animation clock (wall-clock seconds)
    ox: int                        # camera origin (world coordinates)
    oy: int
    vw: int                        # the view's size in cells
    vh: int
    daylight: tuple                # (r, g, b) light multipliers at this hour
    view: np.ndarray = None        # tile ids in view, [x, y]
    xs: np.ndarray = None          # world x of each column, (vw, 1)
    ys: np.ndarray = None          # world y of each row, (1, vh)
    fg: np.ndarray = None          # the ground's float colour buffers, (vw, vh, 3),
    bg: np.ndarray = None          #   while the ground layers run
    fg_mul: np.ndarray = None      # TINT's gathered multipliers, (vw, vh)
    bg_mul: np.ndarray = None
    occupied: set = field(default_factory=set)   # screen cells creatures hold

    def screen(self, x: int, y: int):
        """A world position's cell in the view, or None when it's off screen."""
        sx, sy = x - self.ox, y - self.oy
        return (sx, sy) if 0 <= sx < self.vw and 0 <= sy < self.vh else None


@dataclass(frozen=True)
class _OneOff:
    kind: str
    life: float                    # seconds it plays for
    layer: str
    draw: object                   # draw(frame, happening, age_seconds)


_ONGOING: dict = {layer: [] for layer in LAYERS}
_ONE_OFFS: dict = {}


def ongoing(layer: str, order: int):
    """Register an ongoing effect, drawn every frame in `layer` (lowest
    `order` first): ``draw(frame)``."""
    def deco(fn):
        _ONGOING[layer].append((order, fn))
        _ONGOING[layer].sort(key=lambda e: e[0])
        return fn
    return deco


def one_off(kind: str, life: float, layer: str = OVERLAY):
    """Register the effect a happening of `kind` plays for `life` seconds:
    ``draw(frame, happening, age)``."""
    def deco(fn):
        _ONE_OFFS[kind] = _OneOff(kind, life, layer, fn)
        return fn
    return deco


def run(layer: str, f: Frame) -> None:
    """Draw every effect in `layer`: the ongoing ones in order, then the
    one-offs whose happenings belong to it."""
    if layer == TINT:
        f.fg_mul = np.ones((f.vw, f.vh), dtype=np.float32)
        f.bg_mul = np.ones((f.vw, f.vh), dtype=np.float32)
    for _order, fn in _ONGOING[layer]:
        fn(f)
    if layer == TINT:                          # the multipliers land together
        f.fg *= f.fg_mul[..., None]
        f.bg *= f.bg_mul[..., None]
    _play_one_offs(layer, f)


def _play_one_offs(layer: str, f: Frame) -> None:
    fx = getattr(f.state, "fx", None)
    if not fx:
        return
    now_game = f.state.abs_minutes
    keep = []
    for h in fx:
        spec = _ONE_OFFS.get(h.kind)
        if spec is None:                       # nothing plays for it: let it go
            continue
        if spec.layer != layer:
            keep.append(h)
            continue
        if h.start is None:
            if now_game - h.at > STALE_MINUTES:
                continue                       # long past by the time we saw it
            h.start = f.t
        age = f.t - h.start
        if age >= spec.life:
            continue                           # played out
        keep.append(h)
        if h.world is f.state.world:           # only where you can see it happen
            spec.draw(f, h, age)
    fx[:] = keep


# --- timing helpers -------------------------------------------------------------
# Every time-varying formula the view uses lives here, so ongoing effects,
# one-off effects and the few things the renderer animates in place (a
# creature's breathing, the torches' flicker) all keep the one clock.
def hash01(a, b):
    """Stable pseudo-random value in [0, 1) per (a, b) — the classic shader
    hash, for desyncing per-tile phases."""
    v = np.sin(a.astype(np.float64) * 127.1 + b.astype(np.float64) * 311.7) * 43758.5453
    return v - np.floor(v)


def h1(i: int, s: float) -> float:
    """A stable scalar hash in [0, 1) — for per-source particle phases."""
    v = math.sin(i * 12.9898 + s * 78.233) * 43758.5453
    return v - math.floor(v)


def burst_age(t: float, window: float, chance: float, span: float, salt: float):
    """Seconds since the burst in this window of time began, or None if this
    window has none (or it hasn't started yet). A burst lands somewhere in the
    window, early enough to finish inside it (`span` long), on a `chance` of
    windows — so a recurring thing happens now and then, never on a beat."""
    k = math.floor(t / window)
    if h1(k, salt + 0.37) >= chance:
        return None
    start = k * window + h1(k, salt + 0.71) * max(0.0, window - span)
    age = t - start
    return age if 0.0 <= age < span else None


def lightning(t: float, seed: int) -> float:
    """The storm's flash brightness at time `t`: a double strike at irregular
    moments, 0 most of the time."""
    age = burst_age(t, 6.5, 0.8, 0.6, (seed % 1009) + 0.11)
    if age is None:
        return 0.0
    return float(np.exp(-(age ** 2) / 0.010) + 0.6 * np.exp(-((age - 0.22) ** 2) / 0.010))


def eruption_age(t: float, seed: int):
    """Seconds into the caldera's current spitting fit, or None while it's quiet."""
    span = 4.0 + 3.0 * h1(math.floor(t / 41.0), (seed % 1009) + 0.53)
    return burst_age(t, 41.0, 0.85, span, (seed % 1009) + 0.29)


def machine_lit(t: float, mx: int, my: int) -> bool:
    """A finished machine's glint: on its own phase and a beat of its own
    (0.8-1.2s), so a yard of them twinkles rather than flashing as one."""
    h = mx * 7 + my * 13
    beat = 0.8 + 0.4 * h1(h, 6.7)
    return ((t / beat + h1(h, 4.1)) % 1.0) < 0.5


def flyover(f: int, t: float, seed: int):
    """How far flock `f` is across the view (0..1), or None while none is
    crossing: a crossing takes 40% of its window, starts somewhere within it,
    and some windows pass without birds. Returns (travel, window index)."""
    per = 34.0 + 14.0 * h1(f, 2.0)
    phase = t / per + h1(f, 5.0)
    cyc = math.floor(phase)
    if h1(f * 7 + cyc, (seed % 1009) + 11.0) >= 0.75:
        return None
    local = (phase - cyc) - 0.55 * h1(f * 7 + cyc, (seed % 1009) + 13.0)
    if not 0.0 <= local <= 0.40:
        return None
    return local / 0.40, cyc


def breath(t: float, sx: int, sy: int) -> float:
    """A creature's faint breathing shimmer, phased by where it stands so they
    don't pulse in lockstep."""
    return 1.0 + 0.09 * math.sin(t * 3.0 + sx * 1.3 + sy * 0.7)


def player_pulse(t: float) -> float:
    """The player's gentle breathing pulse (dims, never lost)."""
    return 0.90 + 0.10 * math.sin(t * 2.2)


def torch_flicker(t: float, X, Y):
    """The underground torchlight's gentle flicker across the view."""
    return 0.94 + 0.06 * np.sin(t * 6.0 + X * 0.7 + Y * 0.5)


def shift2d(a: np.ndarray, sx: int, sy: int) -> np.ndarray:
    """A copy of `a` translated by (sx, sy), vacated cells left at zero (no
    wrap)."""
    out = np.zeros_like(a)
    xw, yw = a.shape[0] - abs(sx), a.shape[1] - abs(sy)
    if xw <= 0 or yw <= 0:
        return out
    xs_, xd_ = (0, sx) if sx >= 0 else (-sx, 0)
    ys_, yd_ = (0, sy) if sy >= 0 else (-sy, 0)
    out[xd_:xd_ + xw, yd_:yd_ + yw] = a[xs_:xs_ + xw, ys_:ys_ + yw]
    return out


def blur5(f: np.ndarray) -> np.ndarray:
    """A gentle 4-neighbour blur (weights .5 centre, .125 each side) that rubs
    out hard cell-grid edges."""
    out = f * 0.5
    out[1:, :] += 0.125 * f[:-1, :]
    out[:-1, :] += 0.125 * f[1:, :]
    out[:, 1:] += 0.125 * f[:, :-1]
    out[:, :-1] += 0.125 * f[:, 1:]
    return out
