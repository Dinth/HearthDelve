"""Bonuses from worn jewellery and gems embedded in tools.

Worn rings/amulet contribute their gem's effect, scaled by the piece's star
quality. Gems embedded in the *held weapon / worn armour* need no code here —
their bonus is already baked into the item's stats by the gear factory. Only
tools (singletons, not factory items) carry embeds, via ``player.tool_gem``.
"""
from __future__ import annotations

from ..data import content
from . import skills
from .state import GameState

_JEWEL_SLOTS = ("neck", "ring1", "ring2")
_COMBAT_STATS = ("to_hit", "dmg", "dv", "pv", "crit")


def _worn_effects(state: GameState):
    """(effect_dict, quality_multiplier) for each worn ring/amulet."""
    p = state.player
    for slot in _JEWEL_SLOTS:
        it = p.equipment.get(slot)
        if it is None:
            continue
        eff = content.JEWEL_EFFECT.get(it)
        if eff:
            yield eff, skills.value_mult(p.equip_quality.get(slot, 0))   # 1.0 .. 2.0


def combat_bonus(state: GameState) -> dict:
    """Summed combat contributions from worn jewellery (to_hit/dmg/dv/pv/crit)."""
    tot = {k: 0.0 for k in _COMBAT_STATS}
    for eff, qm in _worn_effects(state):
        for k in _COMBAT_STATS:
            tot[k] += eff.get(k, 0.0) * qm
    return tot


def cozy_bonus(state: GameState, kind: str) -> float:
    """A cozy stat summed from worn jewellery — 'yield' (extra double-drop
    chance) or 'energy' (action-energy discount)."""
    return sum(eff.get(kind, 0.0) * qm for eff, qm in _worn_effects(state))


def tool_gem_bonus(state: GameState, tool, kind: str) -> float:
    """A cozy stat from gems embedded in the given tool ('yield' or 'energy')."""
    return sum(content.gem_embed_delta(g, "tool").get(kind, 0.0)
               for g in state.player.tool_gem.get(tool, ()))
