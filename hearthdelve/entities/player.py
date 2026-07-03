"""The player character and core stats."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..engine import constants as C
from . import items
from .items import Inventory, Item


def _starter_hotbar() -> list[Item]:
    # tools on 1-6, seed pouch on 7, the held weapon on 8 — you swap to whatever
    # you want in hand; that item is used for both work and fighting.
    return [items.HOE, items.WATERING_CAN, items.AXE, items.PICKAXE,
            items.MACHETE, items.FISHING_ROD, items.SEED_POUCH, items.SWORD]


# ADOM-style worn/ranged slots (melee weapon is whatever you hold, above).
EQUIP_SLOTS = ("head", "body", "hands", "waist", "legs", "feet", "ranged", "ammo")


def _starter_equipment() -> dict:
    eq = {s: None for s in EQUIP_SLOTS}
    eq["ammo"] = items.BOMB       # bombs ride in the ammo slot, thrown by hand
    return eq


def _starter_inventory() -> Inventory:
    inv = Inventory()
    inv.add(items.PARSNIP_SEEDS, 15)        # lean & classic loadout, DESIGN §14
    return inv


def _starter_tiers() -> dict:
    return {t: 0 for t in items.TIERED_TOOLS}   # everyone starts Wooden (tier 0)


@dataclass
class Player:
    x: int
    y: int
    glyph: str = "@"

    hp: int = C.START_HP
    max_hp: int = C.START_HP
    energy: int = C.START_ENERGY
    max_energy: int = C.START_ENERGY
    stamina: int = C.START_STAMINA
    max_stamina: int = C.START_STAMINA
    gold: int = C.START_GOLD

    # facing direction (dx, dy) — used later by "use tool on facing tile"
    facing: tuple[int, int] = (0, 1)

    # quick-access tools (keys 1-9), the equipped weapon, and stacking goods
    hotbar: list[Item] = field(default_factory=_starter_hotbar)
    active_slot: int = 0
    weapon: Item | None = field(default_factory=lambda: items.SWORD)   # the held melee weapon in the hotbar
    equipment: dict = field(default_factory=_starter_equipment)        # worn armour + ranged/ammo slots
    mastery: dict = field(default_factory=dict)                        # weapon category -> mastery xp
    inventory: Inventory = field(default_factory=_starter_inventory)
    tool_tier: dict = field(default_factory=_starter_tiers)
    active_seed: Item = field(default_factory=lambda: items.PARSNIP_SEEDS)
    skills: dict = field(default_factory=dict)   # skill name -> xp
    level: int = 1                               # general character level
    xp: int = 0                                  # xp toward the next level
    karma: int = 0                               # -100 villainous .. +100 saintly
    buff: str = ""                               # active food buff key (see skills.BUFFS)
    buff_until: int = 0                          # abs in-game minute the buff wears off

    @property
    def active_tool(self) -> Item | None:
        if 0 <= self.active_slot < len(self.hotbar):
            return self.hotbar[self.active_slot]
        return None

    def display_name(self, item: Item) -> str:
        """Tool names take their material-tier prefix (e.g. 'Wooden Hoe')."""
        if item in self.tool_tier:
            return f"{C.TOOL_TIERS[self.tool_tier[item]]} {item.name}"
        return item.name
