"""Land ownership, claiming, and the weekly land tax.

Every surface tile has an owner, resolved on demand by :func:`owner_at`:

* **Village land** — building footprints, farmhouse fields and cottage gardens
  belong to a named resident (or, for shops/inn/temple, to the village itself).
  You may *take* from it (stealing/vandalising costs karma and the owner's
  regard) but you may *not* build on it.
* **The homestead grant** — a radius of freehold around your spawn, granted to
  you. Yours, and never taxed.
* **Your claims** — wilderness you improved (tilled, built on, or fenced in).
  Yours to use, but the crown levies a weekly land tax on every claimed tile.
* **Wilderness** — everything else is ownerless: build, farm, or fence it off to
  claim it.

Village ownership is *derived* from the world (buildings + field/garden tile
lists) and cached per-map, so it never needs saving. Only the player's claims
and tax standing live in the save.
"""
from __future__ import annotations

from ..world import tile
from . import karma

# Freehold you're granted around the homestead — yours, tax-free. Generous
# enough to cover the starting farm; expansion beyond it is what gets taxed.
HOMESTEAD_RADIUS = 20

# Weekly land tax on claimed wilderness.
TAX_PER_TILE = 2                 # gold per claimed tile, assessed weekly
TAX_INTERVAL = 7                 # days between assessments
KARMA_DRIP = 1                   # karma lost per week an unpaid balance is carried

# A fenced plot whose bounding box is larger than this isn't auto-claimed (a
# runaway guard — a fence run this big is almost certainly not one plot).
MAX_ENCLOSURE = 900

# Ground a player fence may be planted on.
FENCEABLE = {"grass", "meadow", "tall_grass", "path", "sand", "moor", "fog_grass"}


# --- ownership resolution ----------------------------------------------------
def _surf(state):
    return state.surface or state.world


def _village_owner(surf) -> dict:
    """(x, y) -> owner name for all village-owned tiles on this map, cached.

    A building with a named resident (cottage/farmhouse/hut) is owned by them;
    other village buildings (shop/inn/temple/forge) belong to the village.
    Fields and gardens go to the nearest named resident."""
    cache = getattr(surf, "_owner_cache", None)
    if cache is not None:
        return cache
    grid: dict = {}
    for b in getattr(surf, "buildings", ()):
        owner = b.get("owner") or (b.get("village") or None)
        if not owner:                      # player-built (no village, no owner)
            continue
        for x in range(b["x"], b["x"] + b["w"]):
            for y in range(b["y"], b["y"] + b["h"]):
                grid[(x, y)] = owner
    parcels = list(getattr(surf, "village_fields", ())) + list(getattr(surf, "village_gardens", ()))
    for (x, y) in parcels:
        who = _nearest_resident(surf, x, y)
        if who:
            grid[(x, y)] = who
    surf._owner_cache = grid
    return grid


def _nearest_resident(surf, x: int, y: int):
    """Name of the nearest building with a named resident (owns fields/gardens)."""
    best, best_d = None, None
    for b in getattr(surf, "buildings", ()):
        owner = b.get("owner")
        if not owner:
            continue
        cx, cy = b["x"] + b["w"] // 2, b["y"] + b["h"] // 2
        d = (cx - x) ** 2 + (cy - y) ** 2
        if best_d is None or d < best_d:
            best, best_d = owner, d
    return best


def invalidate(surf) -> None:
    """Drop the cached ownership grid (call when buildings change)."""
    if surf is not None:
        surf._owner_cache = None


def in_homestead(surf, x: int, y: int) -> bool:
    sx, sy = surf.spawn
    return max(abs(x - sx), abs(y - sy)) <= HOMESTEAD_RADIUS


def owner_at(state, x: int, y: int):
    """Owner of a surface tile: an NPC name, a village name, ``"player"``, or
    ``None`` for wilderness. Underground has no ownership."""
    surf = _surf(state)
    if getattr(surf, "is_dungeon", False):
        return None
    vo = _village_owner(surf).get((x, y))
    if vo is not None:                     # village land is never overridden
        return vo
    if (x, y) in state.claims:
        return "player"
    if in_homestead(surf, x, y):
        return "player"
    return None


def owned_by_other(state, x: int, y: int) -> bool:
    o = owner_at(state, x, y)
    return o is not None and o != "player"


def owner_label(state, x: int, y: int) -> str:
    """A possessive label for a tile's owner, e.g. ``"Marda's"`` / ``"the village's"``."""
    o = owner_at(state, x, y)
    if o is None:
        return "unclaimed"
    if o == "player":
        return "your"
    surf = _surf(state)
    names = {n.name for n in getattr(surf, "npcs", ())}
    if o in names:
        return f"{o}'s"
    return f"{o}'s"          # a village name reads fine possessively ("Mossford's")


# --- claiming ----------------------------------------------------------------
def claim(state, tiles) -> int:
    """Claim wilderness tiles for the player (skipping others' land and the
    tax-free homestead grant). Returns how many *new* tiles were claimed."""
    surf = _surf(state)
    new = 0
    for (x, y) in tiles:
        if not surf.in_bounds(x, y):
            continue
        if owned_by_other(state, x, y) or in_homestead(surf, x, y):
            continue
        if (x, y) not in state.claims:
            state.claims.add((x, y))
            new += 1
    return new


def note_claim(state, tiles, announce: bool = False) -> int:
    """Claim tiles, with a one-shot explainer the first time you ever claim wild
    land. Returns how many new tiles were claimed."""
    n = claim(state, tiles)
    if n and announce:
        state.log.add(f"{n} tile(s) of wild land are now your claim.", (200, 220, 160))
    if n and not state.stats.get("claimed_intro"):
        state.stats["claimed_intro"] = 1
        state.log.add("Claimed wild land is taxed weekly — a notice will reach your post box.",
                      (200, 220, 160))
    return n


def _fence_run(surf, start) -> set:
    """Every fence tile connected (orthogonally or diagonally) to ``start`` —
    the single run of fencing the player is building."""
    if tile.TILES[surf.tiles[start]].kind != "fence":
        return set()
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if (nx, ny) in seen or not surf.in_bounds(nx, ny):
                    continue
                if tile.TILES[surf.tiles[nx, ny]].kind == "fence":
                    seen.add((nx, ny))
                    stack.append((nx, ny))
    return seen


def enclosed_tiles(state, fence_xy) -> set:
    """The plot a fence run bounds. There are no gates, so a fence needn't form a
    closed loop: the run's bounding box IS the plot — a U or an L of 5-long sides
    bounds a 5×5, so you're charged for all 25 tiles. Tiles owned by others are
    left out (you can't fence in a neighbour's land)."""
    surf = _surf(state)
    run = _fence_run(surf, fence_xy)
    if len(run) < 2:                       # a lone panel bounds no plot
        return set()
    xs = [x for x, _ in run]
    ys = [y for _, y in run]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if (x1 - x0 + 1) * (y1 - y0 + 1) > MAX_ENCLOSURE:
        return set()                       # too sprawling to be one plot
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)
            if not owned_by_other(state, x, y)}


# --- theft / vandalism -------------------------------------------------------
def check_take(state, x: int, y: int, desc: str = "property") -> str:
    """Gate a take/destroy on a tile you may not own.

    Returns ``"free"`` (yours or wilderness — go ahead), ``"confirm"`` (owned by
    another; a warning was logged and the act should abort so a second press can
    confirm), or ``"steal"`` (already warned this morning — proceed, and the
    caller should call :func:`penalize` afterwards)."""
    if not owned_by_other(state, x, y):
        return "free"
    key = f"steal:{x},{y}"
    if state.warned.get(key):
        return "steal"
    state.warned[key] = 1
    from ..engine import constants as C
    state.log.add(f"That's {owner_label(state, x, y)} {desc} — press again to take it anyway.",
                  (224, 180, 120))
    return "confirm"


def penalize(state, x: int, y: int, desc: str = "property") -> None:
    """Apply the karma + relationship cost of taking/destroying owned property."""
    owner = owner_at(state, x, y)
    if owner is None or owner == "player":
        return
    karma.adjust(state, -3)
    state.bump("thefts")
    from . import village
    village.anger_owner(state, owner, 40)
    state.log.add(f"You take {owner_label(state, x, y)} {desc}. It won't be forgotten.",
                  (210, 150, 120))


# --- weekly land tax ---------------------------------------------------------
def _post_tax_notice(state) -> None:
    """Refresh the single standing tax notice in the post box."""
    state.mail = [m for m in state.mail if not m.get("tax")]
    n = len(state.claims)
    state.mail.append({
        "sender": "the Bailiff",
        "tax": True,
        "body": (f"Land tax on your claim of {n} tile{'s' if n != 1 else ''}.\n"
                 f"Balance due: {state.tax_owed}g.\n"
                 "Open this notice to settle what you can — no hurry, but the\n"
                 "parish does note who lets their dues run on."),
        "items": [],
    })


def weekly_tax(state) -> None:
    """Assess the land tax if a week has passed. Carrying an unpaid balance into
    a new week costs a little karma; gold and land are never seized."""
    if state.day - state.last_tax_day < TAX_INTERVAL:
        return
    state.last_tax_day = state.day
    if state.tax_owed > 0:                 # last week's bill went unpaid
        karma.adjust(state, -KARMA_DRIP)
        state.bump("tax_arrears_weeks")
    assess = TAX_PER_TILE * len(state.claims)
    state.tax_owed += assess
    if state.tax_owed <= 0:
        return
    _post_tax_notice(state)
    if assess > 0:
        state.log.add(f"The land tax falls due: {assess}g on {len(state.claims)} claimed "
                      f"tiles (you owe {state.tax_owed}g). Settle at your post box.",
                      (224, 190, 120))
    else:
        state.log.add(f"The Bailiff notes your {state.tax_owed}g of unpaid land tax.",
                      (224, 190, 120))


def settle_tax(state) -> None:
    """Pay down the land-tax balance from gold (as much as you can afford)."""
    p = state.player
    if state.tax_owed <= 0:
        state.log.add("You owe no land tax.", (200, 210, 180))
        return
    pay = min(p.gold, state.tax_owed)
    p.gold -= pay
    state.tax_owed -= pay
    state.bump("tax_paid", pay)
    if state.tax_owed <= 0:
        state.log.add(f"You settle your land tax ({pay}g) — paid in full.", (180, 230, 160))
    elif pay > 0:
        state.log.add(f"You pay {pay}g toward the land tax; {state.tax_owed}g still owed.",
                      (224, 190, 120))
    else:
        state.log.add("You haven't the gold to pay any of your land tax.", (224, 160, 120))
    # Refresh (or clear) the standing notice so it reflects the new balance.
    state.mail = [m for m in state.mail if not m.get("tax")]
    if state.tax_owed > 0:
        _post_tax_notice(state)
