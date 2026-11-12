"""A fair ribbon buys something off the prize table, or goes in the Hall."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _prizes(st):
    from hearthdelve.game import village
    return [r for r in village.shop_entries("tavern", st) if r.kind == "prize"]


class TestThePrizeTable(unittest.TestCase):
    def test_no_ribbon_no_table(self):
        self.assertEqual(_prizes(fresh_state(81)), [])

    def test_a_ribbon_opens_it(self):
        from hearthdelve.entities import items
        st = fresh_state(81)
        st.player.inventory.add(items.FAIR_RIBBON, 1)
        rows = _prizes(st)
        self.assertEqual(len(rows), 3)
        self.assertIn(items.BEE_QUEEN, [r.item for r in rows])
        self.assertTrue(any(r.item is not None and r.item.kind == "sapling" for r in rows))
        self.assertTrue(all(r.price == 0 for r in rows))

    def test_the_table_holds_still_within_a_week_and_turns_with_it(self):
        from hearthdelve.entities import items
        st = fresh_state(81)
        st.player.inventory.add(items.FAIR_RIBBON, 1)
        key = lambda: [(r.name, r.item) for r in _prizes(st)]
        st.day = 14
        first = key()
        st.day = 20
        self.assertEqual(key(), first)
        seen = set()
        for week in range(2, 30):
            st.day = week * 7
            seen.add(tuple(key()))
        self.assertGreater(len(seen), 3)

    def test_claiming_one_spends_the_ribbon(self):
        from hearthdelve.entities import items
        from hearthdelve.game import village
        st = fresh_state(81)
        inv = st.player.inventory
        inv.add(items.FAIR_RIBBON, 1)
        queens = inv.count(items.BEE_QUEEN)
        row = next(r for r in _prizes(st) if r.item is items.BEE_QUEEN)
        village.purchase(st, row)
        self.assertEqual(inv.count(items.FAIR_RIBBON), 0)
        self.assertEqual(inv.count(items.BEE_QUEEN), queens + 1)
        self.assertEqual(_prizes(st), [])

    def test_the_recipe_card_teaches_a_dish_you_lacked(self):
        from hearthdelve.entities import items
        from hearthdelve.game import village
        st = fresh_state(81)
        st.player.inventory.add(items.FAIR_RIBBON, 1)
        row = next(r for r in _prizes(st) if r.item is None)
        self.assertNotIn(row.name, st.known_recipes)
        village.purchase(st, row)
        self.assertIn(row.name, st.known_recipes)
        self.assertEqual(st.player.inventory.count(items.FAIR_RIBBON), 0)

    def test_no_card_when_every_dish_is_known(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        st = fresh_state(81)
        st.known_recipes |= {r.name for r in content.RECIPES if r.kind == "cook"}
        st.player.inventory.add(items.FAIR_RIBBON, 1)
        self.assertTrue(all(r.item is not None for r in _prizes(st)))

    def test_a_prize_cannot_be_claimed_twice_on_one_ribbon(self):
        from hearthdelve.entities import items
        from hearthdelve.game import village
        st = fresh_state(81)
        inv = st.player.inventory
        inv.add(items.FAIR_RIBBON, 1)
        row = next(r for r in _prizes(st) if r.item is items.BEE_QUEEN)
        queens = inv.count(items.BEE_QUEEN)
        village.purchase(st, row)
        village.purchase(st, row)
        self.assertEqual(inv.count(items.BEE_QUEEN), queens + 1)

    def test_the_shop_screen_draws_the_rows(self):
        from hearthdelve.engine import screens_render
        import inspect
        self.assertIn('e.kind == "prize"', inspect.getsource(screens_render))


class TestTheGrangeCase(unittest.TestCase):
    def test_the_hall_takes_one_ribbon(self):
        from hearthdelve.entities import items
        from hearthdelve.game import collection
        st = fresh_state(82)
        st.player.inventory.add(items.FAIR_RIBBON, 2)
        self.assertIn(items.FAIR_RIBBON, [it for it, _q in collection.donatable(st)])
        self.assertTrue(collection.donate(st, items.FAIR_RIBBON))
        self.assertEqual(st.player.inventory.count(items.FAIR_RIBBON), 1)
        self.assertEqual(collection.wing_of(items.FAIR_RIBBON.name), "Grange Case")
        self.assertTrue(collection.perk_earned(st, "Grange Case"))
        self.assertNotIn(items.FAIR_RIBBON, [it for it, _q in collection.donatable(st)])

    def test_the_boss_trophies_wing_is_untouched(self):
        from hearthdelve.data import content
        self.assertEqual(len(content.COLLECTION["Trophies"]), 5)

    def test_a_hall_finished_before_keeps_its_laurels(self):
        from hearthdelve.game import collection
        st = fresh_state(82)
        st.stats["collection_complete"] = 1
        st.stats["wing_done_Trophies"] = 1
        self.assertTrue(collection.perk_earned(st, "Trophies"))
        self.assertFalse(collection.perk_earned(st, "Grange Case"))

    def test_the_case_tips_the_judging(self):
        import inspect
        from hearthdelve.game import village
        self.assertGreater(village.GRANGE_CASE_EDGE, 0)
        self.assertIn("GRANGE_CASE_EDGE", inspect.getsource(village.enter_contest))


if __name__ == "__main__":
    unittest.main()
