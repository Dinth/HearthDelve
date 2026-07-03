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

    # delving: surface is the persistent farm; world is the active map
    surface: GameMap | None = None
    depth: int = 0                       # 0 = surface, >=1 = dungeon floor
    dungeon_kind: str = ""
    return_pos: tuple[int, int] = (0, 0)

    # goals / journal
    stats: dict = field(default_factory=dict)          # lifetime counters
    quests_done: set = field(default_factory=set)      # completed goal ids
    cheats: dict = field(default_factory=dict)         # Konami menu toggles (transient)
    mail: list = field(default_factory=list)           # letters in the post box: {sender, body, items}
    pending_build: str = ""        # outbuilding ordered from the carpenter, awaiting placement

    # transient view/UI state (never serialized)
    cam_focus: tuple | None = None                     # camera centres here if set (look/aim modes)
    warned: dict = field(default_factory=dict)         # one-shot alert flags, reset each morning

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
