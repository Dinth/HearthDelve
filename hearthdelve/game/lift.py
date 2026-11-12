"""The dwarven lift: Khazgrim's old ore-shaft, worked again for a fare.

A deep delve used to mean walking down from the first floor every time. The
dwarves' cage rides the shaft from their town to every fifth floor below it
that you have reached on foot, and back up from a station beside the
stairs on each of those floors. It saves the walk, never replaces it: a floor
you haven't reached isn't a stop, and the stairs still go everywhere.
"""
from __future__ import annotations

from ..engine import constants as C
from .state import GameState

LIFT_STEP = 5              # the cage stops on every fifth floor
FARE_PER_FLOOR = 15        # gold per floor ridden, down or up
MINUTES_BASE = 10          # waiting for the cage, and the doors
MINUTES_PER_FLOOR = 2      # ...and the long rattle down the shaft


def deepest(state: GameState) -> int:
    """The deepest floor you've reached in the old dwarven mine. (A save from
    before this was kept counts its deepest floor anywhere, if it ever found
    the Underriver — generous, as old saves should be treated.)"""
    rec = state.stats.get("dwarfhold_deepest")
    if rec is None:
        rec = state.stats.get("deepest_depth", 0) if state.stats.get("found_underriver") else 0
    return rec


def stops(state: GameState) -> list:
    """Where the cage will take you from here: Khazgrim, and every fifth
    floor below it you've reached."""
    from ..world import dwarftown
    floors = [dwarftown.TOWN_DEPTH] + [d for d in range(LIFT_STEP, deepest(state) + 1, LIFT_STEP)
                                       if d > dwarftown.TOWN_DEPTH]
    return [d for d in floors if d != state.depth]


def fare(state: GameState, to: int) -> int:
    return FARE_PER_FLOOR * abs(to - state.depth)


def ride_minutes(state: GameState, to: int) -> int:
    return MINUTES_BASE + MINUTES_PER_FLOOR * abs(to - state.depth)


def station(gm):
    """Where the lift stands on a floor, or None."""
    return next((pos for pos, m in gm.machines.items() if m.kind == "lift"), None)


def ride(state: GameState, to: int) -> bool:
    """Pay the fare and ride to floor `to`, stepping out beside the cage."""
    from . import delve, turns
    from ..world import dwarftown
    if to not in stops(state):
        return False
    cost = fare(state, to)
    if state.player.gold < cost:
        state.log.add(f"The lift-ward shakes her head — it's {cost}g to ride that far.", C.DIM)
        return False
    state.player.gold -= cost
    down = to > state.depth
    turns.advance_time(state, ride_minutes(state, to) * 60, actors=False)
    state.depth = to
    delve._go_to_floor(state, to, descending=down)
    at = station(state.world)
    if at is not None:                                 # step out beside the cage
        w = state.world
        for dx, dy in ((0, 1), (1, 0), (-1, 0), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)):
            x, y = at[0] + dx, at[1] + dy
            if w.walkable(x, y) and (x, y) not in w.machines:
                state.player.x, state.player.y = x, y
                break
        delve.make_room(state)
        delve.update_fov(state)
    where = "Khazgrim" if to == dwarftown.TOWN_DEPTH else f"floor {to}"
    state.log.add(f"The cage rattles {'down' if down else 'up'} the old shaft to {where}. ({cost}g)",
                  (214, 176, 108))
    return True


def place_station(gm) -> None:
    """Stand a lift station on a deep floor, beside its stairs up (so you
    arrive by the cage and can always call it back)."""
    if gm.stairs_up is None:
        return
    from .. entities.machine import Machine
    sx, sy = gm.stairs_up
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)):
        x, y = sx + dx, sy + dy
        if gm.walkable(x, y) and (x, y) != gm.stairs_down and (x, y) not in gm.machines:
            gm.machines[(x, y)] = Machine(kind="lift")
            return
