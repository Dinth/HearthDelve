"""A fish dish names its fish; its other wildcards are still ingredients."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestAFishDishStillWantsItsEggAndMilk(unittest.TestCase):
    """Choosing the fish pinned EVERY wildcard in the recipe to it: fish cakes
    cooked with no egg, a chowder with no milk, each priced as if all fish."""

    def _recipe(self, name):
        from hearthdelve.data import content
        return next(r for r in content.RECIPES if r.name == name)

    def test_no_egg_no_fish_cakes(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(6)
        inv = st.player.inventory
        inv.add(items.TUNA, 3)
        inv.add(items.FLOUR, 1)
        self.assertEqual(crafting.dish_choice_options(st, self._recipe("Fish Cakes")), [])

    def test_the_egg_is_spent_and_one_fish(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(6)
        inv = st.player.inventory
        inv.add(items.TUNA, 3)
        inv.add(items.FLOUR, 1)
        inv.add(items.EGG, 1)
        (opt,) = crafting.dish_choice_options(st, self._recipe("Fish Cakes"))
        crafting.cook_choice(st, opt)
        self.assertEqual((inv.count(items.TUNA), inv.count(items.EGG), inv.count(items.FLOUR)),
                         (2, 0, 0))
        self.assertEqual(inv.count(opt["output"]), self._recipe("Fish Cakes").out_qty)

    def test_a_chowder_takes_two_fish_and_the_milk(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(6)
        inv = st.player.inventory
        inv.add(items.TUNA, 2)
        inv.add(items.POTATO, 1)
        chowder = self._recipe("Seafood Chowder")
        self.assertEqual(crafting.dish_choice_options(st, chowder), [])
        inv.add(items.MILK, 1)
        (opt,) = crafting.dish_choice_options(st, chowder)
        crafting.cook_choice(st, opt)
        self.assertEqual((inv.count(items.TUNA), inv.count(items.MILK)), (0, 0))

    def test_the_dish_is_worth_its_real_ingredients(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        cakes = self._recipe("Fish Cakes")
        dish = content.cooked_dish(cakes, items.TUNA)
        egg = min(i.value for i in content._family_items("egg") if i.value > 0)
        made_of = items.TUNA.value + items.FLOUR.value + egg
        self.assertEqual(dish.value, round(made_of * content.COOK_MARGIN / cakes.out_qty))
        # dearer fish, dearer dish — and never below ingredients + 25%
        self.assertGreater(dish.value, content.cooked_dish(cakes, items.MINNOW).value)
        self.assertGreaterEqual(dish.value * cakes.out_qty, made_of * 1.25)

    def test_a_saved_variant_still_resolves(self):
        from hearthdelve.entities import items
        self.assertIsNotNone(items.by_name("Tuna Fish Cakes"))
        self.assertIsNotNone(items.by_name("Tuna Seafood Chowder"))


if __name__ == "__main__":
    unittest.main()
