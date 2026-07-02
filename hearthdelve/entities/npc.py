"""Village residents: shopkeepers and folk to befriend.

NPCs have a daytime spot (work) and a night spot (home); friendship rises by
talking and (more) by gifting items they like. Positions are filled in by
worldgen once the villages are carved.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .items import Item

HEART_POINTS = 100          # points per heart
MAX_HEARTS = 10


@dataclass
class NPC:
    name: str
    glyph: str
    color: tuple[int, int, int]
    shop: str | None                 # "general" | "blacksmith" | None
    blurbs: tuple[str, ...]
    # friendship-gated lines: (min_hearts, text) — revealed as you grow closer,
    # so backstory unfolds the more you befriend them.
    heart_blurbs: tuple = ()
    loves: tuple[Item, ...] = ()
    likes: tuple[Item, ...] = ()
    dislikes: tuple[Item, ...] = ()
    # a CLOSED, in-character pool this NPC may gift as a friendship reward
    # (a blacksmith gives metal, a child gives flowers — never the reverse)
    gifts: tuple[Item, ...] = ()
    bio: str = ""                    # short "who & where" line for the relationships menu
    role: str = "villager"           # shopkeeper|blacksmith|innkeeper|priest|farmer|fisher|forager|carpenter|trader|villager
    village: str = ""                # set by worldgen
    met: bool = False                # has the player spoken to them?
    # positions (set by worldgen)
    x: int = 0
    y: int = 0
    home: tuple[int, int] = (0, 0)
    work: tuple[int, int] = (0, 0)
    # named daytime anchors filled by worldgen: home/work plus shared
    # landmarks (inn, temple, square) used by the hourly schedule.
    spots: dict = field(default_factory=dict)
    # state
    friendship: int = 0
    gifted_today: bool = False
    talked_today: bool = False
    _blurb_i: int = 0

    @property
    def hearts(self) -> int:
        return min(MAX_HEARTS, self.friendship // HEART_POINTS)

    def speak(self) -> str:
        """Next line from the pool that's unlocked at the current friendship —
        deeper, more personal lines surface as hearts rise."""
        pool = list(self.blurbs) + [t for (th, t) in self.heart_blurbs if self.hearts >= th]
        line = pool[self._blurb_i % len(pool)]
        self._blurb_i += 1
        return line

    def next_blurb(self) -> str:      # kept for compatibility
        return self.speak()

    def gift_reaction(self, item: Item) -> tuple[int, str]:
        """Return (friendship_points, reaction line) for being given item."""
        if item in self.loves:
            return 80, f"{self.name}: This is wonderful — I love it!"
        if item in self.likes:
            return 45, f"{self.name}: Oh, thank you! How thoughtful."
        if item in self.dislikes:
            return -20, f"{self.name}: ...thanks, I suppose."
        return 20, f"{self.name}: That's kind of you."
