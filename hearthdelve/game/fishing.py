"""Fishing: cast a rod at water, then play a little reel-it-in minigame.

When a fish bites, control passes to an interactive bracket you hold in place
against the fish's darting until a progress bar fills (Stardew-style). Landing
the fish — and how cleanly you did it — sets what you catch and its quality.
The minigame state lives in a ctx dict driven per-frame by ``update`` from the
main loop; ``begin`` opens it and ``resolve`` closes it out.
"""
from __future__ import annotations

import random
import time

from ..data import content
from ..engine import constants as C
from ..world import tile
from . import turns
from .state import GameState

# --- minigame tuning (rates are per real second; the loop passes dt) ---------
# A horizontal track: the bracket is slid left/right with the ←/→ arrows (no
# gravity), so it can be positioned precisely. The fish drifts calmly along the
# track — it should feel catchable.
TRACK_LEN = 30           # cells along the reel track
BAR_BASE_LEN = 7         # bracket width at Fishing 0 (grows with skill)
BAR_SPEED = 16.0         # how fast the bracket slides under the arrows (cells/s)
FILL_RATE = 0.28         # progress gained per second while the fish is bracketed
DRAIN_RATE = 0.37        # progress lost per second while it isn't
START_PROG = 0.12        # you start with little — the fight has to be earned
GRACE_SECS = 1.2         # can't lose the fish in the opening moment
TIME_LIMIT = 35.0        # the fish tires of the fight eventually


def _weighted(table):
    total = sum(w for _, w in table)
    r = random.uniform(0, total)
    acc = 0.0
    for item, w in table:
        acc += w
        if r <= acc:
            return item
    return table[0][0]


def _difficulty(fish) -> float:
    """Harder (rarer/pricier) fish dart faster and slip away quicker."""
    return max(0.8, min(1.6, 0.8 + fish.value / 420.0))


# --- which body of water is this? --------------------------------------------
# The map stores only two water tiles — RIVER for the flowing kind and WATER for
# everything standing — so the sea, the fen's bog pools and a village pond all
# share one tile id. Telling them apart from the tile alone used to hand out
# tuna and sea bass in a marsh puddle (and let Saltmere's lighthouse light it).
# Instead we read the world: the coastline says what's salt, and what crowds
# round a pool says whether it's fen or open water. Nothing new to save, and a
# pond dug in a meadow fishes differently from a pool out in the peat.
_MARSHY = (tile.MARSH, tile.MOOR, tile.FOG_GRASS, tile.REEDS)
_MARSH_RADIUS = 3       # how far around a pool we look
_MARSH_MIN = 6          # marshy tiles in that window before we call it fen water


def water_kind(state: GameState, x: int, y: int) -> str:
    """Which water body (x, y) belongs to: cave | river | sea | marsh | lake."""
    w = state.world
    if w.is_dungeon:
        return "cave"
    if w.tiles[x, y] == tile.RIVER:
        return "river"
    coast = getattr(w, "coast", None)             # per-column first sea row
    if coast is not None and 0 <= x < len(coast) and y >= int(coast[x]):
        return "sea"
    marshy = 0
    for xx in range(x - _MARSH_RADIUS, x + _MARSH_RADIUS + 1):
        for yy in range(y - _MARSH_RADIUS, y + _MARSH_RADIUS + 1):
            if w.in_bounds(xx, yy) and w.tiles[xx, yy] in _MARSHY:
                marshy += 1
    return "marsh" if marshy >= _MARSH_MIN else "lake"


# What each still water holds. The river is absent: it turns with the seasons,
# so it's resolved through content.fish_in_season instead.
_STILL_TABLES = {"cave": content.CAVE_FISH, "sea": content.SEA_FISH,
                 "marsh": content.MARSH_FISH, "lake": content.LAKE_FISH}


def _pan_river(state: GameState, tx: int, ty: int) -> None:
    """A single cast at the Underriver: sift the gravel for what the black water
    carries down. No minigame — a straight cast, time-bounded like fishing, so a
    trip yields a bounded haul. Richer eyes (Fishing skill) sift a touch better."""
    from . import skills
    p = state.player
    p.energy = max(0, p.energy - C.FISH_COST[0])
    turns.advance_time(state, random.randint(C.FISH_SECONDS_MIN, C.FISH_SECONDS_MAX))
    chance = 0.80 + skills.fishing_catch_bonus(state)
    if random.random() > chance:
        state.log.add("You pan the gravel... only cold silt this time.", C.DIM)
        return
    catch = _weighted(content.RIVER_PAN)
    p.inventory.add(catch, 1)
    skills.gain(state, "Fishing", 8)                     # panning trains the same patient eye
    state.bump("river_panned")
    state.log.add(f"You pan the Underriver and sift out {catch.name.lower()}!", (200, 214, 150))


def begin(state: GameState, tx: int, ty: int):
    """Roll for a bite and, if one comes, open the reel minigame. Returns a ctx
    dict (fed to update/resolve) or None if nothing's biting / can't fish."""
    p = state.player
    if p.energy <= 0:
        state.log.add("You're too exhausted to fish.", C.DIM)
        return None
    p.facing = (max(-1, min(1, tx - p.x)), max(-1, min(1, ty - p.y)))
    if getattr(state.world, "underriver", False):        # pan the ore-river — no minigame
        _pan_river(state, tx, ty)
        return None
    from . import skills
    kind = water_kind(state, tx, ty)
    table = (content.fish_in_season(state.season) if kind == "river"
             else _STILL_TABLES[kind])
    chance = content.FISH_CATCH_CHANCE + skills.fishing_catch_bonus(state)
    from . import collection, events                       # Hall of Wonders — completed Angler's Cabinet
    if collection.perk_earned(state, "Angler's Cabinet"):
        chance += 0.05
    chance += events.fishing_bonus(state)                  # a shoal run: the sea boils
    if state.player.sign == "heron":                       # born on a still-water morning
        chance += 0.04
    # The Saltmere lighthouse: the beam steadies the boats and draws the far
    # shoals in — sea casts bite more often, and moonfish rise to the light.
    # Salt water only; the beam does nothing for a bog pool inland.
    if kind == "sea":
        from . import projects
        from ..entities import items
        if projects.done(state, "lighthouse"):
            chance += 0.08
            table = table + [(items.MOONFISH, 6)]     # a local copy, never the module list
    if not table or random.random() > chance:
        # a "cast that finds nothing" still costs a little time & effort
        p.energy = max(0, p.energy - C.FISH_COST[0])
        turns.advance_time(state, random.randint(C.FISH_SECONDS_MIN, C.FISH_SECONDS_MAX // 2))
        state.happen("plop", tx, ty)                 # the float drops in, and nothing comes
        state.log.add("You cast your line... nothing's biting.", C.DIM)
        return None
    fish = _weighted(table)
    lvl = skills.skill_level(state, "Fishing")
    bar_len = min(TRACK_LEN // 2, BAR_BASE_LEN + lvl // 3)
    state.log.add("A bite! Reel it in — use ←/→ to keep the fish in the bracket.", (150, 200, 224))
    return {
        "fish": fish, "diff": _difficulty(fish), "bar_len": bar_len,
        "bar": float(TRACK_LEN - bar_len) / 2,
        # the fish starts off-centre and already on the move, so you must chase it
        "fish_pos": random.uniform(TRACK_LEN * 0.12, TRACK_LEN * 0.88),
        "tgt": random.uniform(0, TRACK_LEN - 1), "retarget": 0.35,
        "prog": START_PROG, "best": START_PROG, "elapsed": 0.0, "last_t": time.monotonic(),
        "at": (tx, ty),                               # where the line went in
    }


def update(state: GameState, ctx: dict, move_dir: int) -> str:
    """Advance one frame. ``move_dir`` is -1 (left) / 0 / +1 (right). Returns
    'running' | 'caught' | 'escaped'."""
    now = time.monotonic()
    dt = min(0.06, max(0.0, now - ctx["last_t"]))    # clamp so a stall can't teleport things
    ctx["last_t"] = now
    if dt <= 0:
        return "running"
    ctx["elapsed"] += dt
    L, bl = TRACK_LEN, ctx["bar_len"]

    # bracket — slid directly under the arrows, no gravity
    ctx["bar"] = max(0.0, min(L - bl, ctx["bar"] + move_dir * BAR_SPEED * dt))

    # fish drifts toward a shifting target, resting now and then; rarer fish jink
    # a little faster and more often
    diff = ctx["diff"]
    ctx["retarget"] -= dt
    if ctx["retarget"] <= 0:
        if random.random() < 0.12:                    # an occasional rest beat
            ctx["tgt"] = ctx["fish_pos"]
        elif random.random() < 0.7:                   # shy away from the bracket
            bc = ctx["bar"] + bl / 2
            ctx["tgt"] = (random.uniform(L * 0.55, L - 1) if bc < L / 2
                          else random.uniform(0, L * 0.45))
        else:                                         # a free wander
            spread = 0.6 + 0.4 * diff
            lo = L * (0.5 - 0.5 * spread)
            hi = L * (0.5 + 0.5 * spread)
            ctx["tgt"] = random.uniform(max(0, lo), min(L - 1, hi))
        ctx["retarget"] = random.uniform(0.9, 2.0) / diff
    speed = (3.4 + 3.6 * diff) * dt
    d = ctx["tgt"] - ctx["fish_pos"]
    ctx["fish_pos"] = max(0.0, min(L - 1, ctx["fish_pos"] + max(-speed, min(speed, d))))

    # progress: gain while the fish sits within the bracket, else bleed
    inside = ctx["bar"] - 0.5 <= ctx["fish_pos"] <= ctx["bar"] + bl - 0.5
    ctx["inside"] = inside
    if inside:
        ctx["prog"] = min(1.0, ctx["prog"] + FILL_RATE * dt)
    elif ctx["elapsed"] > GRACE_SECS:
        ctx["prog"] = max(0.0, ctx["prog"] - DRAIN_RATE * diff * dt)
    ctx["best"] = max(ctx["best"], ctx["prog"])

    if ctx["prog"] >= 1.0:
        return "caught"
    if ctx["prog"] <= 0.0 and ctx["elapsed"] > GRACE_SECS:
        return "escaped"
    if ctx["elapsed"] >= TIME_LIMIT:
        return "caught" if ctx["prog"] >= 0.5 else "escaped"
    return "running"


def resolve(state: GameState, ctx: dict, caught: bool) -> None:
    """Close the minigame: spend the effort/time, and land the fish or not."""
    from . import skills
    p = state.player
    p.energy = max(0, p.energy - C.FISH_COST[0])
    turns.advance_time(state, random.randint(C.FISH_SECONDS_MIN, C.FISH_SECONDS_MAX))
    at = ctx.get("at")
    if not caught:
        skills.gain(state, "Fishing", 6)          # you still learn from the ones that got away
        if at:
            state.happen("splash", *at)
        state.log.add("The line goes slack — it slipped the hook.", C.DIM)
        return
    fish = ctx["fish"]
    if at:
        state.happen("catch", *at, glyph=fish.glyph)  # out of the water and up to you
    q = skills.roll_quality(state, "Fishing")
    if ctx["elapsed"] < 6.0:                       # a swift, clean catch lands a finer fish
        q = min(5, q + 1)
    p.inventory.add(fish, 1, quality=q)
    state.bump("fish_caught")
    skills.gain(state, "Fishing", 24)              # a slow, patient skill — worth more per catch
    star = (" " + skills.stars(q)) if q else ""
    state.log.add(f"You land a {fish.name}{star}!", (150, 200, 224))
