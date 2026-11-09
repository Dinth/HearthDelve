"""The goal/journal layer — cozy objectives that reward progress (no hard win).

Goals come a year at a time: the first year's set from the start, then a
fresh, harder set as each new year begins (``Quest.year``)."""
from __future__ import annotations

from ..data import content
from .state import GameState


def unlocked(state: GameState) -> list:
    """The goals in the journal by now: this year's and every year before."""
    return [q for q in content.QUESTS if q.year <= state.year]


def check(state: GameState) -> None:
    """Complete any newly-satisfied goals, granting their rewards once."""
    for q in unlocked(state):
        if q.id in state.quests_done:
            continue
        try:
            done = q.check(state)
        except Exception:  # noqa: BLE001 - a bad check should never crash play
            done = False
        if done:
            state.quests_done.add(q.id)
            state.player.gold += q.gold          # reward gold isn't counted toward "earned"
            from . import skills
            skills.gain_char_xp(state, 60)       # goals grant a chunk of experience
            state.log.add(f"Goal complete — {q.title}!  (+{q.gold}g)", (240, 220, 120))
            if all(g.id in state.quests_done for g in content.QUESTS):
                state.log.add("You've truly made a life in Hollowmere Vale. ♥", (236, 200, 210))


def active(state: GameState):
    """The next unfinished goal in the journal, or None when all are done."""
    for q in unlocked(state):
        if q.id not in state.quests_done:
            return q
    return None


def progress(state: GameState) -> tuple[int, int]:
    """(done, in the journal) — the goals of the years so far."""
    goals = unlocked(state)
    return sum(1 for q in goals if q.id in state.quests_done), len(goals)


def new_this_year(state: GameState) -> list:
    """The goals that join the journal this year."""
    return [q for q in content.QUESTS if q.year == state.year]
