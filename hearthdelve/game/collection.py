"""The Hall of Wonders — a cabinet of curiosities.

Once the ``hall_of_wonders`` project is raised, the player presents first-of-each
specimen to the curator at a display case. Each is catalogued forever (a name in
``state.donated``), sorted into one of four wings. Donating is a genuine sink for
that first find — you keep the rest of the stack to sell. Wing and capstone
rewards live in a later slice; this module is the catalogue + donation loop.
"""
from __future__ import annotations

from ..data import content
from ..engine import constants as C
from .state import GameState

_WING_COLOR = (214, 196, 150)


def is_open(state: GameState) -> bool:
    """True once the Hall of Wonders stands."""
    from . import projects
    return projects.done(state, "hall_of_wonders")


def wing_of(item_name: str) -> str | None:
    for wing, its in content.COLLECTION.items():
        if any(it.name == item_name for it in its):
            return wing
    return None


def donatable(state: GameState) -> list:
    """Carried items that belong in the collection and aren't catalogued yet, as
    (item, quality) — one entry per item (any quality qualifies)."""
    seen, out = set(), []
    for it, qty, ql in state.player.inventory.slots:
        if (qty > 0 and it.name in content.COLLECTED_NAMES
                and it.name not in state.donated and it.name not in seen):
            seen.add(it.name)
            out.append((it, ql))
    return out


def donate(state: GameState, item) -> bool:
    """Catalogue one of ``item`` (consumed). Returns True if it was accepted."""
    from . import karma
    inv = state.player.inventory
    if item.name in state.donated or inv.count(item) <= 0:
        return False
    inv.remove(item, 1)
    state.donated.add(item.name)
    state.bump("wonders_donated")
    karma.adjust(state, 1)
    wing = wing_of(item.name) or "collection"
    state.log.add(f"The curator sets your {item.name.lower()} in the {wing} — "
                  "catalogued among the Vale's wonders.", _WING_COLOR)
    return True


def wing_progress(state: GameState) -> dict:
    """{wing: (donated_count, total)} across the catalogue."""
    return {wing: (sum(1 for it in its if it.name in state.donated), len(its))
            for wing, its in content.COLLECTION.items()}


def total_progress(state: GameState) -> tuple[int, int]:
    have = sum(1 for n in content.COLLECTED_NAMES if n in state.donated)
    return have, len(content.COLLECTED_NAMES)
