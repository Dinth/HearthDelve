"""Carried weight and its cost on the day's stamina & pace.

A load is never a wall (you can always pick up one more thing) — it's a cost
gradient, per the design creed. Below capacity you walk as normal. Over it you
tire faster and move slower; well over it, much more so. Ore, bars and stone are
the heavy hauls; seeds, gems and jewellery barely register.

Weight comes from the item's kind (an explicit ``item.weight`` overrides it), so
no per-item bookkeeping is needed and it stays save-safe (items persist by name).
"""
from __future__ import annotations

from ..engine import constants as C
from .state import GameState

# Per-unit weight by item kind. Tuned so the default loadout sits comfortably
# under capacity and a real mining/smelting haul is what weighs you down.
_KIND_WEIGHT = {
    "material": 1.5,   # ore, bars, stone, wood, cloth — the bulk of a heavy pack
    "tool": 2.0,
    "weapon": 2.5,
    "armor": 3.0,
    "artisan": 0.6,
    "food": 0.4,
    "crop": 0.4,
    "seed": 0.1,
    "gem": 0.05,
    "jewelry": 0.1,
}
_DEFAULT_WEIGHT = 1.0

CARRY_BASE = 50.0          # base capacity before you're weighed down
CARRY_PER_LEVEL = 4.0      # a seasoned character hauls a little more (efficiency)


def weight_of(item) -> float:
    if item is None:
        return 0.0
    if getattr(item, "weight", 0.0):
        return item.weight
    return _KIND_WEIGHT.get(item.kind, _DEFAULT_WEIGHT)


def carried_weight(state: GameState) -> float:
    """Everything on the character: pack, belt (hotbar), held weapon, and worn
    armour/jewellery/ammo."""
    p = state.player
    total = sum(weight_of(e[0]) * e[1] for e in p.inventory.slots)
    total += sum(weight_of(it) for it in p.hotbar if it is not None)   # weapon rides here
    total += sum(weight_of(it) for it in p.equipment.values() if it is not None)
    return total


def capacity(state: GameState) -> float:
    return (CARRY_BASE + CARRY_PER_LEVEL * max(0, state.player.level - 1)
            + getattr(state, "pack_bonus", 0))   # crafted satchels raise the ceiling


def load_ratio(state: GameState) -> float:
    cap = capacity(state)
    return carried_weight(state) / cap if cap > 0 else 0.0


def tier(state: GameState) -> int:
    """0 = fine, 1 = encumbered (over capacity), 2 = over-encumbered (2x+)."""
    r = load_ratio(state)
    return 2 if r > 2.0 else 1 if r > 1.0 else 0


TIER_LABEL = ("", "Encumbered", "Over-encumbered")


def time_mult(ratio: float) -> float:
    """How much slower each step is under load (1.0 = normal pace)."""
    if ratio <= 1.0:
        return 1.0
    if ratio <= 2.0:
        return 1.0 + (ratio - 1.0) * 0.5           # up to 1.5x at capacity x2
    return min(2.2, 1.5 + (ratio - 2.0) * 0.5)     # steeper, capped so it stays playable


def load_stamina(ratio: float) -> float:
    """Extra stamina per step from the load alone (on top of normal walking).
    Zero until over capacity, then rising — sharply once over-encumbered."""
    if ratio <= 1.0:
        return 0.0
    if ratio <= 2.0:
        return (ratio - 1.0) * 4.0                  # up to +4/step at x2
    return 4.0 + (ratio - 2.0) * 6.0                # over-encumbered bites hard
