"""Top-level mutable game state: world, player, clock, calendar, log."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..engine import constants as C
from ..entities.items import Inventory
from ..entities.player import Player
from ..world.gamemap import GameMap


class MessageLog:
    MAX = 400            # keep a bounded scrollback (see render_message_log)

    def __init__(self) -> None:
        self.messages: list[tuple[str, tuple[int, int, int]]] = []

    def add(self, text: str, color: tuple[int, int, int] = C.WHITE) -> None:
        self.messages.append((text, color))
        if len(self.messages) > self.MAX:
            del self.messages[:-self.MAX]

    def tail(self, n: int) -> list[tuple[str, tuple[int, int, int]]]:
        return self.messages[-n:]


def _starter_recipes() -> set:
    from ..data import content
    return set(content.STARTER_RECIPES)


def _fresh_projects() -> list:
    from . import projects
    return projects.fresh()


@dataclass
class GameState:
    world: GameMap
    player: Player
    log: MessageLog = field(default_factory=MessageLog)

    # seconds elapsed since DAY_START on the current day
    clock: int = 0
    # 0-based absolute day counter
    day: int = 0
    # current day's weather (Clear | Rain | Storm | Fog | Snow)
    weather: str = "Clear"
    # world seed — drives deterministic per-day weather
    seed: int = 0
    # goods queued in the shipping bin; sold overnight
    ship_bin: Inventory = field(default_factory=Inventory)
    storage: Inventory = field(default_factory=Inventory)   # home chest: stash goods off your back
    pack_bonus: int = 0                                     # extra carry capacity from crafted satchels

    # delving: surface is the persistent farm; world is the active map
    surface: GameMap | None = None
    # the Westreach — the volcanic frontier west of the map. Born lazily the
    # first time the player crosses the western edge, persistent thereafter.
    west: GameMap | None = None
    # the folk of Khazgrim (the dwarf town in the old mine): created on first
    # visit, re-seated on their floor each build; friendship persists in saves
    dwarves: list | None = None
    depth: int = 0                       # 0 = surface, >=1 = dungeon floor
    dungeon_kind: str = ""
    return_pos: tuple[int, int] = (0, 0)
    return_west: bool = False            # the active delve began on the Westreach

    # goals / journal
    stats: dict = field(default_factory=dict)          # lifetime counters
    quests_done: set = field(default_factory=set)      # completed goal ids
    cheats: dict = field(default_factory=dict)         # Konami menu toggles (transient)
    mail: list = field(default_factory=list)           # letters in the post box: {sender, body, items}
    # cook recipes the player has learned (recipe names): plain fare to start,
    # the rest gathered around the Vale (friends, taverns, practice, favours)
    known_recipes: set = field(default_factory=_starter_recipes)
    # item names donated to the Hall of Wonders (first-of-each specimen)
    donated: set = field(default_factory=set)
    # heart events already witnessed, keyed "NPC:hearts" (one scene per tier)
    seen_events: set = field(default_factory=set)
    # today's world event, or {} on an ordinary day: {"id", ...} (see game/events.py)
    event: dict = field(default_factory=dict)
    # open request-board favours: [{npc, item, qty, gold, expires, flavor}]
    requests: list = field(default_factory=list)
    # the market's current craving: {"kind", "mult", "until"} — {} in a lull
    demand: dict = field(default_factory=dict)
    # community restoration projects, one record per content.PROJECTS entry:
    # {id, village, state: open|building|done, gold_paid, mats: {name: qty}, site, ready_at}
    projects: list = field(default_factory=_fresh_projects)
    pending_build: str = ""        # outbuilding ordered from the carpenter, awaiting placement

    # land: wilderness tiles the player has claimed (fenced/farmed/built on), and
    # the weekly land-tax standing charged on them.
    claims: set = field(default_factory=set)           # {(x, y)} of claimed surface tiles
    tax_owed: int = 0                                  # unpaid land tax (gold)
    last_tax_day: int = 0                              # day the tax was last assessed

    # transient view/UI state (never serialized)
    cam_focus: tuple | None = None                     # camera centres here if set (look/aim modes)
    warned: dict = field(default_factory=dict)         # one-shot alert flags, reset each morning
    aim_target: object = None                          # last mob fired at; re-aims onto it if still alive
    # dungeon floors visited today, keyed by (kind, depth): re-entering a floor
    # the same day returns the SAME (already-looted) map so chests/gold/kills
    # don't respawn; cleared each new day so floors still re-roll daily. Transient.
    floor_cache: dict = field(default_factory=dict)
    floor_cache_day: int = -1

    def bump(self, key: str, amount: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + amount

    # --- calendar helpers ----------------------------------------------------
    @property
    def season(self) -> str:
        return C.SEASONS[(self.day // C.SEASON_LEN) % len(C.SEASONS)]

    @property
    def day_of_season(self) -> int:
        return self.day % C.SEASON_LEN + 1

    @property
    def year(self) -> int:
        return self.day // C.YEAR_LEN + 1

    @property
    def time_minutes(self) -> int:
        return C.DAY_START_MIN + self.clock // 60

    @property
    def abs_minutes(self) -> int:
        """Monotonic in-game minutes since the start, for machine timers."""
        return self.day * 1440 + self.time_minutes

    def time_str(self) -> str:
        m = self.time_minutes % (24 * 60)
        return f"{m // 60:02d}:{m % 60:02d}"

    def date_str(self) -> str:
        return f"{self.season} {self.day_of_season}"
