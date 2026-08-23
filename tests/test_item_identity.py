"""Item identity must survive the crafting-margin pass.

``content._enforce_recipe_margins`` lifts ``Item.value`` in place on a *frozen*
dataclass. Before ``Item.__hash__`` was pinned to the name, that silently changed
the hash and orphaned the item in every dict already keyed by it — the tables in
``content`` are all built before the margin pass runs. Three items were lost that
way: Leather Armour and the Fur Cloak (unequippable, and no Protection even if
worn) and the Sling Stone (the sling could never be fired).

These tests guard the invariant rather than the three symptoms, so a new table or
a newly-lifted value can't reintroduce it.
"""
from __future__ import annotations

import unittest

from tests.common import fresh_state     # noqa: F401  (repo-root path bootstrap)

from hearthdelve.data import content
from hearthdelve.entities import items
from hearthdelve.entities.items import Inventory, Item


def _item_keyed_dicts():
    """Every module-level dict in content/items that is keyed by Item."""
    out = []
    for mod, modname in ((content, "content"), (items, "items")):
        for name, d in vars(mod).items():
            if isinstance(d, dict) and d and any(isinstance(k, Item) for k in d):
                out.append((f"{modname}.{name}", d))
    return out


class ItemIdentityTest(unittest.TestCase):
    def test_no_item_keyed_dict_has_an_orphaned_key(self):
        """The bug in one assertion: a key present in a dict that the dict can no
        longer find, because its hash moved after insertion."""
        orphaned = []
        for label, d in _item_keyed_dicts():
            for k in list(d):
                if isinstance(k, Item) and k not in d:
                    orphaned.append(f"{label}[{k.name}]")
        self.assertEqual(orphaned, [], f"items orphaned by a hash change: {orphaned}")

    def test_hash_survives_a_value_lift(self):
        probe = Item("Hash Probe", "?", "material", value=10)
        d = {probe: "found"}
        object.__setattr__(probe, "value", 999)      # what the margin pass does
        self.assertIn(probe, d)
        self.assertEqual(d[probe], "found")

    def test_the_three_regressions_stay_fixed(self):
        for name, slot in (("Leather Armour", "body"), ("Fur Cloak", "cloak")):
            it = items.by_name(name)
            self.assertIsNotNone(it, name)
            self.assertEqual(content.ARMOR_SLOT.get(it), slot,
                             f"{name} has no paperdoll slot — _equip would silently no-op")
            self.assertIsNotNone(content.ARMOR_STATS.get(it),
                                 f"{name} grants no DV/PV")
        self.assertIsNotNone(content.ammo_stat(items.SLING_STONE),
                            "Sling Stone has no AmmoStat — the sling can never fire")

    def test_a_sling_with_stones_is_loaded(self):
        stat = content.ranged_stat(items.by_name("Sling"))
        self.assertIsNotNone(stat)
        inv = Inventory()
        inv.add(items.SLING_STONE, 10)
        self.assertEqual(content.ammo_family(stat), "stone")
        self.assertIs(content.best_ammo(inv, content.ammo_family(stat)), items.SLING_STONE)

    def test_every_armour_slot_is_fillable_in_every_material(self):
        """A material whose piece is missing from ARMOR_STATS is a hole in the
        ladder — that is how the leather body piece went missing unnoticed."""
        bases = ("Armour", "Helm", "Leggings", "Boots", "Gauntlets", "Girdle", "Shield", "Cloak")
        holes = []
        for material in ("hide", "leather", "cotton", "wool", "linen", "silk",
                         "copper", "bronze", "iron", "steel", "silver", "mithril", "adamantium"):
            for base in bases:
                it = content.make_gear(base, material, "", "", ())
                if content.ARMOR_SLOT.get(it) is None or content.ARMOR_STATS.get(it) is None:
                    holes.append(f"{material} {base}")
        self.assertEqual(holes, [], f"armour pieces with no slot/stats: {holes}")


if __name__ == "__main__":
    unittest.main()
