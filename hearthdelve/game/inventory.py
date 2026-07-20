"""How the pack is organised — the categories, display order and filtering the
inventory & equipment screens read.

This is game logic (what category an item belongs to, how the pack sorts and
filters), deliberately kept out of the rendering layer so non-UI code can reuse
it. The screens import from here; rendering only draws what these return.
"""
from __future__ import annotations

from ..data import content
from .state import GameState

# The order categories appear in the pack, weapons-first (ADOM-flavoured).
ORDER = ("Weapons", "Armour", "Jewellery", "Ammunition", "Gems",
         "Cooked Food", "Animal Produce", "Artisan Goods", "Fruit", "Vegetables",
         "Flowers", "Fish", "Materials", "Seeds & Saplings", "Livestock",
         "Consumables", "Misc")


def category(item) -> str:
    """The pack category an item is filed under."""
    k = item.kind
    simple = {"food": "Cooked Food", "animal": "Animal Produce", "artisan": "Artisan Goods",
              "fish": "Fish", "material": "Materials", "livestock": "Livestock",
              "bomb": "Consumables", "weapon": "Weapons", "ranged": "Weapons",
              "armor": "Armour", "jewelry": "Jewellery", "ammo": "Ammunition",
              "gem": "Gems"}
    if k in simple:
        return simple[k]
    if k in ("seed", "sapling", "pouch"):
        return "Seeds & Saplings"
    if k == "crop":
        if content.is_fruit(item):
            return "Fruit"
        if content.PRODUCE_CATEGORY.get(item) == "flower":
            return "Flowers"
        return "Vegetables"
    return "Misc"


def sort_key(item, quality: int):
    cat = category(item)
    rank = ORDER.index(cat) if cat in ORDER else len(ORDER)
    return (rank, cat, item.name, quality)


def visible(state: GameState, filt: str | None = None) -> list[int]:
    """Slot indices the inventory screen currently shows (all, or one category
    when Tab-filtered)."""
    return [i for i, (it, _q, _ql) in enumerate(state.player.inventory.slots)
            if filt is None or category(it) == filt]


def categories(state: GameState) -> list[str]:
    """The categories present in the pack, in display order (for Tab cycling)."""
    seen: list[str] = []
    for it, _q, _ql in state.player.inventory.slots:
        cat = category(it)
        if cat not in seen:
            seen.append(cat)
    return seen
