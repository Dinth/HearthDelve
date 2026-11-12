"""A dish is worth what went into it: cheese, meat, egg and milk as fish already was."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state


def _recipe(name):
    from hearthdelve.data import content
    return next(r for r in content.RECIPES if r.name == name)


def _varying():
    from hearthdelve.data import content
    return [r for r in content.RECIPES
            if content.dish_varies(r) and content.dish_wildcard(r).family != "fish"]


class TestTheIngredientCarriesThrough(unittest.TestCase):
    """Any egg, any cheese, any meat made one fixed-price dish: a Cheese
    Omelette of duck eggs and aged goat cheese sold for 263g against 375g of
    ingredients, and a beef pie for no more than a chicken one."""

    def test_no_dish_sells_for_less_than_its_named_ingredient_cost(self):
        from hearthdelve.data import content
        for r in _varying():
            wc = content.dish_wildcard(r)
            for src in content._family_items(wc.family):
                dish = content.cooked_dish(r, src)
                cost = sum((src.value if it is wc else
                            content._family_floor(it.family) if isinstance(it, content.AnyOf)
                            else it.value) * q for it, q in r.inputs)
                with self.subTest(dish=dish.name):
                    self.assertGreater(dish.value * r.out_qty, cost)

    def test_a_finer_source_is_worth_more_and_never_less_than_plain(self):
        from hearthdelve.data import content
        for r in _varying():
            fam = sorted(content._family_items(content.dish_wildcard(r).family),
                         key=lambda i: i.value)
            vals = [content.cooked_dish(r, s).value for s in fam]
            with self.subTest(recipe=r.name):
                self.assertEqual(vals, sorted(vals))
                self.assertEqual(vals[0], r.output.value)
                self.assertGreater(vals[-1], vals[0])

    def test_the_humblest_makes_the_plain_dish(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        self.assertIs(content.cooked_dish(_recipe("Omelette"), items.EGG), items.OMELETTE)
        self.assertIs(content.cooked_dish(_recipe("Pizza"), items.CHEESE), items.PIZZA)
        self.assertIs(content.cooked_dish(_recipe("Meat Pie"), items.MEAT), items.MEAT_PIE)

    def test_the_names_read_as_dishes(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        want = {("Meat Pie", items.BEEF): "Beef Pie",
                ("Fried Egg", items.DUCK_EGG): "Fried Duck Egg",
                ("Bacon & Eggs", items.DUCK_EGG): "Bacon & Duck Eggs",
                ("Egg Sandwich", items.DUCK_EGG): "Duck Egg Sandwich",
                ("Cheese Omelette", items.AGED_GOAT_CHEESE): "Aged Goat Cheese Omelette",
                ("Cake", items.DUCK_EGG): "Duck Egg Cake"}
        for (rname, src), name in want.items():
            self.assertEqual(content.cooked_dish(_recipe(rname), src).name, name)

    def test_no_two_dishes_share_a_name(self):
        from hearthdelve.data import content
        seen: dict = {}
        for r in content.RECIPES:
            if not content.dish_varies(r):
                continue
            for src in content._family_items(content.dish_wildcard(r).family):
                d = content.cooked_dish(r, src)
                self.assertIs(seen.setdefault(d.name, d), d)
        plain = {r.output.name for r in content.RECIPES if r.output is not None}
        self.assertFalse({n for n, d in seen.items() if d.family.startswith("dish:")} & plain)

    def test_a_dish_is_named_for_one_family(self):
        from hearthdelve.data import content
        self.assertEqual(content.dish_wildcard(_recipe("Cheese Omelette")).family, "cheese")
        self.assertEqual(content.dish_wildcard(_recipe("Custard")).family, "egg")
        self.assertEqual(content.dish_wildcard(_recipe("Fish Cakes")).family, "fish")


class TestCookingOne(unittest.TestCase):
    def _kitchen(self, *stock):
        st = fresh_state(23)
        st.player.inventory.slots[:] = []
        for it, n in stock:
            st.player.inventory.add(it, n)
        return st

    def test_each_source_held_is_an_option(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = self._kitchen((items.EGG, 2), (items.DUCK_EGG, 2))
        opts = crafting.dish_choice_options(st, _recipe("Omelette"))
        self.assertEqual([o["output"].name for o in opts], ["Omelette", "Duck Egg Omelette"])
        crafting.cook_choice(st, opts[1])
        inv = st.player.inventory
        self.assertEqual((inv.count(items.DUCK_EGG), inv.count(items.EGG)), (0, 2))
        self.assertEqual(inv.count(opts[1]["output"]), 1)

    def test_the_other_wildcards_fill_cheapest_first(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = self._kitchen((items.EGG, 1), (items.DUCK_EGG, 1), (items.AGED_CHEESE, 1))
        opts = crafting.dish_choice_options(st, _recipe("Cheese Omelette"))
        self.assertEqual([o["output"].name for o in opts], ["Aged Cheese Omelette"])
        self.assertEqual(sorted(i.name for i, _q in opts[0]["inputs"]),
                         ["Aged Cheese", "Duck Egg", "Egg"])

    def test_two_cuts_that_make_the_plain_pie_are_one_option(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = self._kitchen((items.CHICKEN_MEAT, 1), (items.MEAT, 1), (items.BEEF, 1),
                           (items.FLOUR, 1), (items.POTATO, 1))
        opts = crafting.dish_choice_options(st, _recipe("Meat Pie"))
        self.assertEqual([o["output"].name for o in opts], ["Meat Pie", "Beef Pie"])

    def _press_cook(self, st, name):
        from hearthdelve import screens
        from hearthdelve.game import crafting

        class _UI:
            state, pushed = st, []

            def replace(self, scr):
                self.pushed.append(scr)

            def pop(self):
                pass
        st.known_recipes.add(name)
        scr, ui = screens.CraftScreen(), _UI()
        scr.sel = [r.name for r in crafting.visible_recipes(st)].index(name)
        scr.handle(ui, "confirm", ("confirm",))
        return ui.pushed

    def test_one_possible_source_cooks_without_asking(self):
        from hearthdelve.entities import items
        st = self._kitchen((items.DUCK_EGG, 2))
        self.assertEqual(self._press_cook(st, "Omelette"), [])
        self.assertEqual([it.name for it, _n, _q in st.player.inventory.slots],
                         ["Duck Egg Omelette"])

    def test_a_mixed_handful_cooks_the_plain_dish(self):
        from hearthdelve.entities import items
        st = self._kitchen((items.EGG, 1), (items.DUCK_EGG, 1))
        self.assertEqual(self._press_cook(st, "Omelette"), [])
        self.assertEqual([it.name for it, _n, _q in st.player.inventory.slots], ["Omelette"])

    def test_a_choice_of_sources_asks(self):
        from hearthdelve.entities import items
        st = self._kitchen((items.EGG, 2), (items.DUCK_EGG, 2))
        self.assertEqual(len(self._press_cook(st, "Omelette")), 1)


class TestAVariantIsStillTheDish(unittest.TestCase):
    def test_someone_who_loves_the_dish_loves_the_finer_one(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        st = fresh_state(23)
        fans = [n for n in st.surface.npcs if items.CAKE in n.loves]
        self.assertTrue(fans)
        cake = content.cooked_dish(_recipe("Cake"), items.DUCK_EGG)
        self.assertEqual(fans[0].gift_reaction(cake)[0], fans[0].gift_reaction(items.CAKE)[0])
        other = content.cooked_dish(_recipe("Pizza"), items.GOAT_CHEESE)
        cold = [n for n in st.surface.npcs if not n._matches(items.PIZZA, n.loves)]
        self.assertFalse(cold[0]._matches(other, cold[0].loves))

    def test_it_fills_a_favour_for_the_dish(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import requests
        st = fresh_state(23)
        pie = content.cooked_dish(_recipe("Meat Pie"), items.BEEF)
        st.player.inventory.add(pie, 2)
        self.assertTrue(requests.can_fulfil(st, {"item": "Meat Pie", "qty": 2}))

    def test_it_survives_a_save(self):
        from hearthdelve.data import content
        from hearthdelve.engine import save
        from hearthdelve.entities import items
        st = fresh_state(23)
        dishes = [content.cooked_dish(_recipe("Meat Pie"), items.BEEF),
                  content.cooked_dish(_recipe("Fried Egg"), items.DUCK_EGG),
                  content.cooked_dish(_recipe("Quiche"), items.AGED_GOAT_CHEESE)]
        for d in dishes:
            st.player.inventory.add(d, 1, quality=2)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(st, path)
            back = save.load(path)
        for dish in dishes:
            self.assertEqual(back.player.inventory.count(dish, 2), 1)


class TestTheOvenBakesThemToo(unittest.TestCase):
    def test_a_batch_per_source_and_the_plain_one(self):
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(23)
        inv = st.player.inventory
        inv.slots[:] = []
        st.known_recipes.add("Meat Pie")
        for it, n in ((items.BEEF, 2), (items.CHICKEN_MEAT, 2), (items.FLOUR, 4), (items.POTATO, 4)):
            inv.add(it, n)
        opts = crafting.machine_load_options(st, crafting.MACHINES["oven"])
        self.assertEqual(sorted(o["label"] for o in opts), ["Beef Pie", "Meat Pie"])


if __name__ == "__main__":
    unittest.main()
