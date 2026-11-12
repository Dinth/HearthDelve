"""Slime gel is a glue: it holds a fletching and laminates a composite bow."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _recipe(name):
    from hearthdelve.data import content
    return next(r for r in content.RECIPES if r.name == name)


class TestGluedArrows(unittest.TestCase):
    """Slime gel dropped from seven slimes in ten and went nowhere but the
    bin, one villager and the odd favour."""

    def test_a_gel_stretches_the_wood(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(31)
        inv = st.player.inventory
        inv.add(items.WOOD, 1)
        inv.add(items.SLIME_GEL, 1)
        self.assertTrue(crafting.craft(st, _recipe("Glued Arrows")))
        self.assertEqual(inv.count(items.ARROW), 12)
        self.assertEqual(inv.count(items.SLIME_GEL), 0)
        self.assertEqual(inv.count(items.WOOD), 0)

    def test_it_beats_selling_the_gel(self):
        from hearthdelve.entities import items
        glued, plain = _recipe("Glued Arrows"), _recipe("Arrows")
        cost = items.WOOD.value + items.SLIME_GEL.value
        self.assertGreaterEqual(glued.out_qty * items.ARROW.value, cost * 1.25)
        self.assertGreater(glued.out_qty, plain.out_qty * 2)

    def test_no_gel_no_glued_arrows(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(31)
        st.player.inventory.add(items.WOOD, 1)
        self.assertFalse(crafting.craft(st, _recipe("Glued Arrows")))
        self.assertEqual(st.player.inventory.count(items.ARROW), 0)


class TestCompositeBow(unittest.TestCase):
    """The best bow could only be bought or found; now it can be built up
    from a yew bow, horn, sinew and glue."""

    def test_a_yew_bow_is_built_up_into_one(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(32)
        inv = st.player.inventory
        inv.add(items.LONG_BOW, 1)
        inv.add(items.ANTLER, 2)
        inv.add(items.SLIME_GEL, 3)
        inv.add(items.FIBER, 2)
        self.assertTrue(crafting.craft(st, _recipe("Composite Long Bow")))
        bow = content.make_ranged("Long Bow", "composite")
        self.assertEqual(inv.count(bow), 1)
        self.assertEqual(inv.count(items.LONG_BOW), 0)
        self.assertEqual(inv.count(items.SLIME_GEL), 0)

    def test_it_outshoots_and_outsells_what_went_in(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        r = _recipe("Composite Long Bow")
        yew, comp = content.RANGED[items.LONG_BOW], content.RANGED[r.output]
        self.assertGreater(comp.rng, yew.rng)
        self.assertGreater(comp.dmg[1], yew.dmg[1])
        bought = sum(content.counter_price(it) * q if it is items.LONG_BOW else it.value * q
                     for it, q in r.inputs)
        self.assertGreater(r.output.value, bought)

    def test_the_bow_survives_a_save(self):
        import os, tempfile
        from hearthdelve.data import content
        from hearthdelve.engine import save
        st = fresh_state(33)
        bow = content.make_ranged("Long Bow", "composite")
        st.player.inventory.add(bow, 1)
        path = os.path.join(tempfile.mkdtemp(), "bow.sav")
        save.save(st, path)
        back = save.load(path)
        self.assertEqual(back.player.inventory.count(bow), 1)


if __name__ == "__main__":
    unittest.main()
