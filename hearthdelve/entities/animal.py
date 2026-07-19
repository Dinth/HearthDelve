"""A farm animal living in the player's coop or barn.

Unlike dungeon mobs (ephemeral, re-rolled from seed) an animal is a persistent,
player-owned thing: it is bought young, settled into a housing building, roams
the farmyard near its home, and — once grown and cared for — yields produce each
morning. Care is the loop: pet it daily and its happiness climbs toward content,
lifting the quality of what it gives; neglect only drifts it back toward middling.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Animal:
    kind: str                      # "chicken" | "cow"
    name: str
    glyph: str
    color: tuple[int, int, int]
    x: int
    y: int
    home: tuple[int, int]          # the coop/barn anchor tile it belongs to
    happiness: int = 50            # 0..100 — drives produce quality
    age_days: int = 0              # grows up; only adults produce
    petted_today: bool = False
    produce_ready: bool = False
    sick: int = 0                  # days ill (0 = well); an ill beast gives nothing
    energy: int = 0                # roam-speed accumulator (transient)
