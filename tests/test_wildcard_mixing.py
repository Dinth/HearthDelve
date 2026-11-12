"""A wildcard ingredient is filled across its family."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _recipe(name):
    from hearthdelve.data import content
    return next(r for r in content.RECIPES if r.name == name)


class TestAnyEggTimesTwoTakesAHenAndADuck(unittest.TestCase):
    """"Any egg ×2" wanted two of ONE kind: a hen's egg and a duck's egg in
    the pack could not make an omelette."""

    def test_one_of_each_makes_an_omelette(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(14)
        inv = st.player.inventory
        inv.add(items.EGG, 1)
        inv.add(items.DUCK_EGG, 1)
        st.known_recipes.add("Omelette")
        self.assertTrue(crafting.has_inputs(st, _recipe("Omelette")))
        self.assertTrue(crafting.craft(st, _recipe("Omelette")))
        self.assertEqual((inv.count(items.EGG), inv.count(items.DUCK_EGG)), (0, 0))
        self.assertEqual(inv.count(items.OMELETTE), _recipe("Omelette").out_qty)

    def test_the_cheap_ones_go_first(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(14)
        inv = st.player.inventory
        inv.add(items.DUCK_EGG, 3)
        inv.add(items.EGG, 1)
        got = crafting.resolve_inputs(inv, _recipe("Omelette").inputs)
        self.assertEqual(got, [(items.EGG, 1), (items.DUCK_EGG, 1)])

    def test_one_egg_is_still_not_two(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(14)
        st.player.inventory.add(items.DUCK_EGG, 1)
        st.known_recipes.add("Omelette")
        self.assertIsNone(crafting.resolve_inputs(st.player.inventory, _recipe("Omelette").inputs))
        self.assertFalse(crafting.craft(st, _recipe("Omelette")))
        self.assertEqual(st.player.inventory.count(items.DUCK_EGG), 1)

    def test_a_wildcard_never_counts_on_what_is_asked_for_by_name(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(14)
        inv = st.player.inventory
        quiche = _recipe("Quiche")                       # 2 Duck Egg by name + any cheese + flour
        fake = ((items.DUCK_EGG, 2), (_recipe("Omelette").inputs[0][0], 1))
        inv.add(items.DUCK_EGG, 2)
        self.assertIsNone(crafting.resolve_inputs(inv, fake))
        inv.add(items.EGG, 1)
        self.assertEqual(crafting.resolve_inputs(inv, fake), [(items.DUCK_EGG, 2), (items.EGG, 1)])
        self.assertIsNotNone(quiche)


if __name__ == "__main__":
    unittest.main()
