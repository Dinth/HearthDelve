"""The eight birth attributes (ADOM's own): St Le Wi Dx To Ch Ap Pe.

Rolled once at character generation (3d6 each, reroll at will) and never a
gate — each is a small passive modifier on a system that already exists,
centred on 10 so an average roll changes nothing at all:

  Strength    melee damage (+1 per 3 over 10), carry weight (+1 per point),
              and anvil stints cost less wind
  Learning    skill XP (+2% per point over 10)
  Willpower   foes' poison/fever land less often (-3% odds per point)
  Dexterity   Dodge and bow aim (+1 per 3 over 10); deft hands nudge cooked,
              processed and gem-cut quality (slightly, both ways)
  Toughness   max HP (+1 per point, applied once at birth)
  Charisma    talk warms friendships faster (+4% per point)
  Appearance  gifts please more (+4% per point)
  Perception  sight in the dark (+1 tile per 3) and trap-spotting

Old saves have no attributes and read 10 everywhere — nothing changes for them.
"""
from __future__ import annotations

from .state import GameState

ATTRS = ("St", "Le", "Wi", "Dx", "To", "Ch", "Ap", "Pe")
NAMES = {"St": "Strength", "Le": "Learning", "Wi": "Willpower", "Dx": "Dexterity",
         "To": "Toughness", "Ch": "Charisma", "Ap": "Appearance", "Pe": "Perception"}
EFFECTS = {"St": "melee, carry & the smith's wind", "Le": "quicker skill learning",
           "Wi": "shrugs off poison & fever", "Dx": "dodge, bows & deft crafting",
           "To": "a sturdier frame (max HP)", "Ch": "warmer talk",
           "Ap": "gifts please more", "Pe": "sight in the dark, trap-spotting"}


def get(state: GameState, key: str) -> int:
    return int(state.player.attrs.get(key, 10))


def mod(state: GameState, key: str) -> int:
    """The attribute's swing around the human average (…-2, -1, 0, +1, +2…)."""
    return get(state, key) - 10


def roll(rng) -> dict:
    """A fresh set: honest 3d6 per attribute, the bell curve and all."""
    return {k: rng.randint(1, 6) + rng.randint(1, 6) + rng.randint(1, 6) for k in ATTRS}


# The one way an attribute ever climbs after birth: a very rare treat (see
# content.ATTRIBUTE_TREATS). A soft ceiling keeps it a windfall, not a grind.
CEILING = 18


def raise_attr(state: GameState, key: str, n: int = 1) -> int:
    """Permanently raise an attribute (from a treat), clamped to CEILING. Returns
    the points actually gained (0 if already at the ceiling). Toughness feeds max
    HP, exactly as it does at birth, so a To gain widens the health bar at once."""
    p = state.player
    cur = int(p.attrs.get(key, 10))
    new = min(CEILING, cur + n)
    gained = new - cur
    if gained:
        p.attrs[key] = new
        if key == "To":
            p.max_hp += gained
            p.hp += gained
    return gained
