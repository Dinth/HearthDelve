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
    # one-time scripted scenes at friendship tiers: (min_hearts, scene_text).
    # Shown once when you talk having reached that tier (see village._heart_event).
    heart_events: tuple = ()
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
    # the way back to the square while walking there (transient, never saved:
    # recomputed whenever its next step turns out blocked)
    route: list = field(default_factory=list, repr=False, compare=False)

    @property
    def hearts(self) -> int:
        return min(MAX_HEARTS, self.friendship // HEART_POINTS)

    def speak(self, seed: int | None = None) -> str:
        """Next line from the pool that's unlocked at the current friendship —
        deeper, more personal lines surface as hearts rise.

        Every line gets its turn, but each round of them comes in an order
        shuffled from the world's ``seed`` (and the count of lines spoken,
        which is saved, so a reload never re-rolls it). They used to come in
        the same fixed order, round after round, in every world."""
        pool = list(self.blurbs) + [t for (th, t) in self.heart_blurbs if self.hearts >= th]
        i = self._blurb_i
        self._blurb_i += 1
        if seed is None or len(pool) < 2:
            return pool[i % len(pool)]
        return self._round(pool, seed, i // len(pool))[i % len(pool)]

    def _round(self, pool: list, seed: int, n: int) -> list:
        """The order of the ``n``-th round of lines: a seeded shuffle, never
        opening on the line the previous round closed with."""
        import random
        import zlib

        def shuffled(k):
            order = list(pool)
            random.Random((seed * 92_821 + zlib.crc32(self.name.encode()) * 7 + k)
                          & 0x7FFFFFFF).shuffle(order)
            return order
        order = shuffled(n)
        if n > 0 and order[0] == shuffled(n - 1)[-1]:
            order[0], order[1] = order[1], order[0]
        return order

    def next_blurb(self) -> str:      # kept for compatibility
        return self.speak()

    def _matches(self, item: Item, pool: tuple) -> bool:
        """A taste matches the exact item, or any good of the same family — so
        'loves Jam' is satisfied by a raspberry jam, a strawberry jam, and so on."""
        if item in pool:
            return True
        if not item.family:
            return False
        # ...and a dish cooked as a named variant ("Beef Pie", family
        # "dish:Meat Pie") is the dish they named.
        return any(p.family == item.family or item.family == f"dish:{p.name}" for p in pool)

    def taste(self, item: Item) -> str:
        """How this villager takes ``item`` as a gift: "loves", "likes",
        "dislikes" or "" (indifferent). The one place taste is decided — the
        gift screen's tags, the reaction and the points all ask here.

        A bouquet is a present in itself: anyone is glad of one, whoever is
        fond of its flower loves it, and only someone who can't abide that
        flower turns it down."""
        if item.family == "bouquet" and item.source is not None:
            flower = item.source
            if self._matches(flower, self.dislikes):
                return "dislikes"
            if self._matches(flower, self.loves) or self._matches(flower, self.likes):
                return "loves"
            return "likes"
        for pool, word in ((self.loves, "loves"), (self.likes, "likes"),
                           (self.dislikes, "dislikes")):
            if self._matches(item, pool):
                return word
        return ""

    def gift_reaction(self, item: Item) -> tuple[int, str]:
        """Return (friendship_points, reaction line) for being given item."""
        taste = self.taste(item)
        if taste == "loves":
            # A loved but everyday trifle (a stick of wood, a lump of coal)
            # pleases without melting hearts — no farming friendship for 5g.
            if item.value < 20:
                return 50, f"{self.name}: Ah, you remembered! Thank you."
            return 80, f"{self.name}: This is wonderful — I love it!"
        if taste == "likes":
            return 45, f"{self.name}: Oh, thank you! How thoughtful."
        if taste == "dislikes":
            return -20, f"{self.name}: ...thanks, I suppose."
        return 20, f"{self.name}: That's kind of you."
