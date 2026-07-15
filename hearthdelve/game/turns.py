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
    before = state.abs_minutes
    state.clock += seconds
    _announce_finished_machines(state, before, state.abs_minutes)
    steps = max(1, min(round(seconds / C.MOVE_SECONDS), _MAX_STEPS))
    for _ in range(steps):
        _step_actors(state)
    if state.player.status:                     # poison/bleed/burn bite as time passes
        from .combat import tick_player_status
        tick_player_status(state)


def _announce_finished_machines(state: GameState, before: int, now: int) -> None:
    """A one-line heads-up the moment a machine's timer crosses done — so the
    player isn't left polling every furnace and keg by hand."""
    surf = state.surface
    if surf is None or now <= before:
        return
    from ..data.content import MACHINES
    for m in surf.machines.values():
        if m.loaded_output is not None and before < m.ready_at <= now:
            mdef = MACHINES.get(m.kind)
            if mdef is not None:
                state.log.add(f"The {mdef.name.lower()} has finished — "
                              f"{m.loaded_output.name} is ready.", (200, 220, 160))
