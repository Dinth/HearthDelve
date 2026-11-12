"""Bat wing is a membrane: stitched into a cloak as light as silk."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state


def _recipe(name):
    from hearthdelve.data import content
    return next(r for r in content.RECIPES if r.name == name)


class TestBatwingCloak(unittest.TestCase):
    """Bat wings fell from six bats in ten, and one villager wanted them."""

    def test_four_wings_and_fibre_make_it(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(51)
        inv = st.player.inventory
        inv.add(items.BAT_WING, 4)
        inv.add(items.FIBER, 2)
        self.assertTrue(crafting.craft(st, _recipe("Batwing Cloak")))
        cloak = content.make_gear("Cloak", "batwing")
        self.assertEqual(cloak.name, "Batwing Cloak")
        self.assertEqual(inv.count(cloak), 1)
        self.assertEqual(inv.count(items.BAT_WING), 0)

    def test_it_is_worth_more_than_its_wings(self):
        r = _recipe("Batwing Cloak")
        cost = sum(it.value * q for it, q in r.inputs)
        self.assertGreaterEqual(r.output.value, cost * 1.25)

    def test_it_dodges_like_silk_and_weighs_as_little(self):
        from hearthdelve.data import content
        bat, silk, fur = (content.make_gear("Cloak", m) for m in ("batwing", "silk", "fur"))
        self.assertEqual(content.ARMOR_STATS[bat], content.ARMOR_STATS[silk])
        self.assertGreater(content.ARMOR_STATS[bat][0], content.ARMOR_STATS[fur][0])
        self.assertLess(bat.weight, fur.weight)
        self.assertLess(bat.value, silk.value)       # the dear one is still the silk

    def test_worn_it_lifts_your_dodge(self):
        from hearthdelve.data import content
        from hearthdelve.game import combat, commands
        st = fresh_state(52)
        before = combat.player_dv(st)
        cloak = content.make_gear("Cloak", "batwing")
        st.player.inventory.add(cloak, 1)
        commands._equip(st, cloak)
        self.assertIs(st.player.equipment["cloak"], cloak)
        self.assertEqual(combat.player_dv(st), before + 1)

    def test_it_is_never_dungeon_loot_or_loom_work(self):
        from hearthdelve.data import content
        self.assertNotIn("batwing", content.SOFT_ARMOR_MATERIALS)
        self.assertNotIn("batwing", content.CLOTHS)

    def test_worn_or_packed_it_survives_a_save(self):
        from hearthdelve.data import content
        from hearthdelve.engine import save
        from hearthdelve.game import commands
        st = fresh_state(53)
        cloak = content.make_gear("Cloak", "batwing")
        st.player.inventory.add(cloak, 2)
        commands._equip(st, cloak)
        path = os.path.join(tempfile.mkdtemp(), "cloak.sav")
        save.save(st, path)
        back = save.load(path)
        self.assertIs(back.player.equipment["cloak"], cloak)
        self.assertEqual(back.player.inventory.count(cloak), 1)


if __name__ == "__main__":
    unittest.main()
