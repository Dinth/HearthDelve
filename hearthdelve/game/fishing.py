"""Light fishing: cast a rod at water for a chance at a fish (M4 Stage 3)."""
from __future__ import annotations

import random

from ..data import content
from ..engine import constants as C
from . import turns
from .state import GameState


def _weighted(table):
    total = sum(w for _, w in table)
    r = random.uniform(0, total)
    acc = 0.0
    for item, w in table:
        acc += w
        if r <= acc:
            return item
    return table[0][0]


def cast(state: GameState) -> None:
    p = state.player
    if p.energy <= 0:
        state.log.add("You're too exhausted to fish.", C.DIM)
        return
    from . import skills
    p.energy = max(0, p.energy - C.FISH_COST[0])
    turns.advance_time(state, random.randint(C.FISH_SECONDS_MIN, C.FISH_SECONDS_MAX))
    table = content.CAVE_FISH if state.world.is_dungeon else content.fish_in_season(state.season)
    chance = content.FISH_CATCH_CHANCE + skills.fishing_catch_bonus(state)
    if not table or random.random() > chance:
        state.log.add("Your line comes up empty.", C.DIM)
        return
    fish = _weighted(table)
    q = skills.roll_quality(state, "Fishing")
    p.inventory.add(fish, 1, quality=q)
    state.bump("fish_caught")
    skills.gain(state, "Fishing", 12)
    star = (" " + skills.stars(q)) if q else ""
    state.log.add(f"A tug on the line — you reel in a {fish.name}{star}!", (150, 200, 224))
