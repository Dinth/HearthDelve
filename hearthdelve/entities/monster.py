"""A live monster in a dungeon.

Stats are copied from a template (data/content.py) at spawn time; this object
carries the mutable per-instance state (position, current HP, whether it has
noticed the player, and a speed accumulator).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Mob:
    name: str
    glyph: str
    color: tuple[int, int, int]
    hp: int
    max_hp: int
    speed: int          # action points gained per world turn (2 == player speed)
    behavior: str       # dungeon: "chase"|"erratic"|"charge"; wildlife: "skittish"|"defensive"
    x: int
    y: int
    # ADOM-style combat stats
    dv: int = 0             # Defensive Value — how hard it is to hit
    pv: int = 0             # Protection Value — flat damage it soaks
    to_hit: int = 0         # its bonus to hit the player
    dmg: tuple = (1, 3)     # (min, max) damage it deals
    level: int = 1          # dungeon depth-scaled power (see content.make_mob);
                            # differentiates same-kind mobs & drives loot
    energy: int = 0     # accumulates by speed; acts when >= 2
    awake: bool = False
    boss: bool = False
    kind: str = "monster"   # "monster" (dungeon) | "wildlife" (surface critter)
    diet: str = ""          # wildlife only: "" | "crops" | "berries"
    hostile: bool = False   # a defensive critter roused into fighting back
    seasons: tuple = ()     # wildlife only: seasons it's active in ("" = all year)
    inflicts: str = ""      # a status a hit may leave on the player (poison/bleed/burn)
    status: dict = field(default_factory=dict)  # active DoTs ON this mob {kind: turns}
    elite: str = ""         # an elite affix ("Dire", "Venomous", ...) or "" for a common mob
    base: str = ""          # the template (un-prefixed) name, for drop/bestiary lookup
                            # without re-parsing the elite prefix out of `name`
    reach: int = 0          # ranged attackers strike & kite from up to this many tiles
    summons: str = ""       # a "summon"-behavior mob raises this template by name
    summon_cd: int = 0      # turns until it may summon again (transient)

    @property
    def alive(self) -> bool:
        return self.hp > 0
