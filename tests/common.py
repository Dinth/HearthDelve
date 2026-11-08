"""Shared test plumbing: repo-root imports and a cached fresh game state.

Run the suite from the repo root:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_STATES: dict = {}
_NEW_GAMES: dict = {}


def _shared_defs() -> dict:
    """A deepcopy memo of the game's shared definitions — every Item, crop,
    tree, machine, monster and tile defined at module level in the content
    tables — mapped to themselves, so a copied state still holds the very
    same objects. Game code compares items by identity (`e[0] is item`);
    a copy with cloned items would quietly stop matching them. Rebuilt per
    copy (a few milliseconds), so gear registered since is kept too."""
    from hearthdelve.data import content
    from hearthdelve.entities import items
    from hearthdelve.world import tile
    memo: dict = {}

    def keep(obj, depth=0):
        if isinstance(obj, (str, int, float, bool, bytes, type(None))) or id(obj) in memo:
            return
        if isinstance(obj, dict):
            if depth < 2:
                for k, v in obj.items():
                    keep(k, depth + 1)
                    keep(v, depth + 1)
            return
        if isinstance(obj, (list, tuple, set, frozenset)):
            if depth < 2:
                for v in obj:
                    keep(v, depth + 1)
            return
        if type(obj).__module__.startswith("hearthdelve."):
            memo[id(obj)] = obj

    for module in (items, content, tile):
        for value in vars(module).values():
            keep(value)
    return memo


def fresh_state(seed: int = 1):
    """A brand-new game state, never shared — for tests that mutate freely.

    Generating a world takes about a second, and the suite asks for a few
    hundred states, so each seed's new game is built once and every caller
    gets its own deep copy (the shared definitions kept as they are)."""
    from hearthdelve.main import new_game
    if seed not in _NEW_GAMES:
        _NEW_GAMES[seed] = new_game(seed)
    return copy.deepcopy(_NEW_GAMES[seed], _shared_defs())


def shared_state(seed: int = 1):
    """A cached state for read-mostly tests (worldgen layout, catalogues).
    Do NOT mutate it — take fresh_state() when a test changes the world."""
    if seed not in _STATES:
        _STATES[seed] = fresh_state(seed)
    return _STATES[seed]
