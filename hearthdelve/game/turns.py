"""The shared turn scheduler.

Advances the world clock and steps the actors that live on the passing of time
(monsters underground; residents, wildlife, and farm animals on the surface).

Note: the clock and every caller work in SECONDS. Machine timers elsewhere use
in-game MINUTES via ``GameState.abs_minutes`` — don't confuse the two units.
"""
from __future__ import annotations

from .state import GameState


def advance_time(state: GameState, seconds: int) -> None:
    state.clock += seconds
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
        # farm animals amble around their coop/barn
        from .husbandry import act as husbandry_act
        husbandry_act(state)
