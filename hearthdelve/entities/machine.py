"""A placed machine (furnace, jar, keg, sprinkler) living on a world tile.

Processing is time-based and resolved lazily: a machine started at ``ready_at``
absolute minutes is "working" until the game clock passes it, then "done".
"""
from __future__ import annotations

from dataclasses import dataclass

from .items import Item


@dataclass
class Machine:
    kind: str
    loaded_output: Item | None = None   # what it will yield once ready
    ready_at: int = 0                    # absolute in-game minute it completes

    def status(self, now: int) -> str:
        if self.loaded_output is None:
            return "empty"
        return "working" if now < self.ready_at else "done"
