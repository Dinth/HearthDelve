"""A live monster in a dungeon.

Stats are copied from a template (data/content.py) at spawn time; this object
carries the mutable per-instance state (position, current HP, whether it has
noticed the player, and a speed accumulator).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Mob:
    name: str
    glyph: str
    color: tuple[int, int, int]
    hp: int
    max_hp: int
    atk: int
    defense: int
    speed: int          # action points gained per world turn (2 == player speed)
    behavior: str       # dungeon: "chase"|"erratic"|"charge"; wildlife: "skittish"|"defensive"
    x: int
    y: int
    energy: int = 0     # accumulates by speed; acts when >= 2
    awake: bool = False
    boss: bool = False
    kind: str = "monster"   # "monster" (dungeon) | "wildlife" (surface critter)
    diet: str = ""          # wildlife only: "" | "crops" | "berries"
    hostile: bool = False   # a defensive critter roused into fighting back

    @property
    def alive(self) -> bool:
        return self.hp > 0
