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
    if wing in content.COLLECTION and wing_done(state, wing):    # this donation completed a wing
        _complete_wing(state, wing)
    if all_done(state):                                         # …and perhaps the whole hall
        _complete_all(state)
    return True


def wing_progress(state: GameState) -> dict:
    """{wing: (donated_count, total)} across the catalogue."""
    return {wing: (sum(1 for it in its if it.name in state.donated), len(its))
            for wing, its in content.COLLECTION.items()}


def total_progress(state: GameState) -> tuple[int, int]:
    have = sum(1 for n in content.COLLECTED_NAMES if n in state.donated)
    return have, len(content.COLLECTED_NAMES)


def wing_done(state: GameState, wing: str) -> bool:
    its = content.COLLECTION.get(wing, ())
    return bool(its) and all(it.name in state.donated for it in its)


def all_done(state: GameState) -> bool:
    have, tot = total_progress(state)
    return tot > 0 and have == tot


# A completed wing grants a lasting perk, queried via wing_done() at the relevant
# systems (foraging, fishing, gemcutting, combat).
WING_PERK = {
    "Herbarium": "the Vale's green bounty comes freely to your hand — foraging and herbalism yield more.",
    "Angler's Cabinet": "you read the water like a book — the fish bite more often.",
    "Lapidary": "a jeweller's eye is yours — you cut finer stones.",
    "Reliquary": "the deep's trophies have taught you — your blows earn more Combat mastery.",
}


def _complete_wing(state: GameState, wing: str) -> None:
    key = f"wing_done_{wing}"
    if state.stats.get(key):
        return
    state.stats[key] = 1
    from . import karma
    karma.adjust(state, 3)
    state.log.add(f"The {wing} is complete! {WING_PERK.get(wing, '')}", (240, 224, 150))


def _complete_all(state: GameState) -> None:
    if state.stats.get("collection_complete"):
        return
    state.stats["collection_complete"] = 1
    from . import karma
    from ..entities.npc import MAX_HEARTS
    karma.adjust(state, 10)
    if state.surface is not None:
        for n in state.surface.npcs:
            n.friendship = min(MAX_HEARTS * 100, n.friendship + 150)
    state.log.add("The Hall of Wonders is COMPLETE — every wonder of the Vale, catalogued and kept. "
                  "Your name will be spoken here for generations.", (248, 232, 160))
    state.mail.append({
        "sender": "The Curator",
        "body": ("It is done. Every fish, gem, herb and relic of the Vale sits in its case,\n"
                 "and the whole valley has come to see. This hall is your monument as much\n"
                 "as mine. Whatever wonders yet wait in the deep — I'll keep a case ready.\n"
                 "With boundless thanks, and awe."),
        "items": [],
    })
