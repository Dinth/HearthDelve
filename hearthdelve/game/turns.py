"""The shared turn scheduler.

Advances the world clock and steps the actors that live on the passing of time
(monsters underground; residents, wildlife, and farm animals on the surface).

Note: the clock and every caller work in SECONDS. Machine timers elsewhere use
in-game MINUTES via ``GameState.abs_minutes`` — don't confuse the two units.
"""
from __future__ import annotations

from ..engine import constants as C
from .state import GameState

# Longer tasks let the world act more than once (so mining beside a monster
# isn't free time), but capped so a single big advance can't hand nearby
# creatures dozens of turns at once. Animated actions tick one step per frame.
_MAX_STEPS = 6


def _step_actors(state: GameState) -> None:
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


def advance_time(state: GameState, seconds: int) -> None:
    state.clock += seconds
    steps = max(1, min(round(seconds / C.MOVE_SECONDS), _MAX_STEPS))
    for _ in range(steps):
        _step_actors(state)
