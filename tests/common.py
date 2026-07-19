"""Shared test plumbing: repo-root imports and a cached fresh game state.

Run the suite from the repo root:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_STATES: dict = {}


def fresh_state(seed: int = 1):
    """A brand-new game state (never cached — for tests that mutate freely)."""
    from hearthdelve.main import new_game
    return new_game(seed)


def shared_state(seed: int = 1):
    """A cached state for read-mostly tests (worldgen layout, catalogues).
    Do NOT mutate it — take fresh_state() when a test changes the world."""
    if seed not in _STATES:
        _STATES[seed] = fresh_state(seed)
    return _STATES[seed]
