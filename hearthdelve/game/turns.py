"""The shared turn scheduler.

In M1 this only advances the clock; later milestones hook crop growth,
machine completion, and monster turns through ``advance_time``.
"""
from __future__ import annotations

from .state import GameState


def advance_time(state: GameState, minutes: int) -> None:
    state.clock += minutes
    if state.world.is_dungeon:
        # in the dark, time passing is a combat turn for the monsters
        from .combat import monsters_act
        monsters_act(state)
    else:
        # residents follow their daily schedule as time passes
        from .village import update_npcs
        update_npcs(state)
        # wildlife roams the overworld
        from .wildlife import act as wildlife_act
        wildlife_act(state)
