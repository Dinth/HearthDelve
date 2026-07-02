"""The goal/journal layer — cozy objectives that reward progress (no hard win)."""
from __future__ import annotations

from ..data import content
from .state import GameState


def check(state: GameState) -> None:
    """Complete any newly-satisfied goals, granting their rewards once."""
    for q in content.QUESTS:
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
            if len(state.quests_done) == len(content.QUESTS):
                state.log.add("You've truly made a life in Hollowmere Vale. ♥", (236, 200, 210))


def active(state: GameState):
    """The next unfinished goal, or None when all are done."""
    for q in content.QUESTS:
        if q.id not in state.quests_done:
            return q
    return None


def progress(state: GameState) -> tuple[int, int]:
    return len(state.quests_done), len(content.QUESTS)
