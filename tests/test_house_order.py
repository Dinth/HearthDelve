"""The house order: each inn wants one dish a week and pays over the bin."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state


def _keepers(st):
    return sorted((n for n in st.surface.npcs if n.role == "innkeeper"), key=lambda n: n.name)


def _order_rows(st, npc):
    from hearthdelve.game import village
    return [r for r in village.shop_entries("tavern", st, npc) if r.kind == "order"]


class TestWhatIsWanted(unittest.TestCase):
    """A cooked dish had the bin, a favour, or one villager who loved it."""

    def test_no_two_inns_want_the_same_dish(self):
        from hearthdelve.game import village
        st = fresh_state(101)
        for week in range(12):
            st.day = week * 7
            wants = [village.tavern_order(st, n).name for n in _keepers(st)]
            with self.subTest(week=week):
                self.assertEqual(len(set(wants)), len(wants))

    def test_it_holds_for_the_week_then_changes(self):
        from hearthdelve.game import village
        st = fresh_state(101)
        inn = _keepers(st)[0]
        st.day = 21
        first = village.tavern_order(st, inn)
        st.day = 27
        self.assertIs(village.tavern_order(st, inn), first)
        seen = set()
        for week in range(40):
            st.day = week * 7
            seen.add(village.tavern_order(st, inn).name)
        self.assertGreater(len(seen), 15)          # it drifts, it doesn't cycle a short list

    def test_staples_are_never_ordered(self):
        from hearthdelve.game import village
        names = {it.name for it in village._order_pool()}
        self.assertFalse(names & {"Noodles", "Mayonnaise", "Ketchup"})
        self.assertIn("Quiche", names)

    def test_the_counter_says_what_is_wanted_when_you_carry_none(self):
        from hearthdelve.game import village
        st = fresh_state(101)
        inn = _keepers(st)[0]
        rows = _order_rows(st, inn)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].item)
        self.assertEqual(rows[0].label, village.tavern_order(st, inn).name)
        gold = st.player.gold
        village.purchase(st, rows[0], inn)
        self.assertEqual(st.player.gold, gold)


class TestFillingIt(unittest.TestCase):
    def _carrying(self, n=1, quality=0):
        from hearthdelve.game import village
        st = fresh_state(102)
        inn = _keepers(st)[0]
        dish = village.tavern_order(st, inn)
        st.player.inventory.add(dish, n, quality=quality)
        return st, inn, dish

    def test_it_pays_over_the_bin(self):
        from hearthdelve.game import crafting, village
        st, inn, dish = self._carrying()
        row = _order_rows(st, inn)[0]
        self.assertIs(row.item, dish)
        self.assertGreater(row.price, crafting.bin_value(st, dish, 0))
        gold = st.player.gold
        village.purchase(st, row, inn)
        self.assertEqual(st.player.gold, gold + row.price)
        self.assertEqual(st.player.inventory.count(dish), 0)

    def test_stars_pay_more(self):
        st, inn, dish = self._carrying()
        st.player.inventory.add(dish, 1, quality=4)
        rows = _order_rows(st, inn)
        self.assertEqual([r.quality for r in rows], [4, 0])     # the dearer serving first
        self.assertGreater(rows[0].price, rows[1].price)

    def test_the_table_fills_and_then_takes_no_more(self):
        from hearthdelve.game import village
        st, inn, dish = self._carrying(n=village.ORDER_SERVINGS + 3)
        for _ in range(village.ORDER_SERVINGS + 3):
            for row in _order_rows(st, inn)[:1]:
                village.purchase(st, row, inn)
        self.assertEqual(st.player.inventory.count(dish), 3)
        self.assertEqual(village.order_left(st, inn), 0)
        self.assertIsNone(_order_rows(st, inn)[0].item)

    def test_a_stale_row_cannot_oversell(self):
        from hearthdelve.game import village
        st, inn, dish = self._carrying(n=village.ORDER_SERVINGS + 2)
        row = _order_rows(st, inn)[0]
        for _ in range(village.ORDER_SERVINGS + 2):
            village.purchase(st, row, inn)
        self.assertEqual(st.player.inventory.count(dish), 2)

    def test_next_week_the_table_is_empty_again(self):
        from hearthdelve.game import village
        st, inn, dish = self._carrying(n=1)
        village.purchase(st, _order_rows(st, inn)[0], inn)
        self.assertEqual(village.order_left(st, inn), village.ORDER_SERVINGS - 1)
        st.day += 7
        self.assertEqual(village.order_left(st, inn), village.ORDER_SERVINGS)

    def test_one_inns_order_is_not_anothers(self):
        from hearthdelve.game import village
        st, inn, dish = self._carrying()
        other = _keepers(st)[1]
        self.assertIsNone(_order_rows(st, other)[0].item)

    def test_a_named_variant_fills_it_and_pays_as_itself(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import village
        st = fresh_state(103)
        inn = _keepers(st)[0]
        sashimi = next(r for r in content.RECIPES if r.name == "Sashimi")
        tuna = content.cooked_dish(sashimi, items.TUNA)
        self.assertIsNot(tuna, sashimi.output)
        self.assertTrue(village.fills_order(tuna, sashimi.output))
        self.assertFalse(village.fills_order(items.PIZZA, sashimi.output))
        for week in range(400):                      # a week this inn wants sashimi
            st.day = week * 7
            if village.tavern_order(st, inn) is sashimi.output:
                break
        else:
            self.fail("sashimi never ordered")
        st.player.inventory.add(tuna, 1)
        st.player.inventory.add(sashimi.output, 1)
        rows = _order_rows(st, inn)
        self.assertIs(rows[0].item, tuna)
        self.assertGreater(rows[0].price, rows[1].price)

    def test_the_tally_survives_a_save(self):
        from hearthdelve.engine import save
        from hearthdelve.game import village
        st, inn, dish = self._carrying(n=2)
        village.purchase(st, _order_rows(st, inn)[0], inn)
        path = os.path.join(tempfile.mkdtemp(), "order.sav")
        save.save(st, path)
        back = save.load(path)
        binn = next(n for n in back.surface.npcs if n.name == inn.name)
        self.assertEqual(village.order_left(back, binn), village.ORDER_SERVINGS - 1)


if __name__ == "__main__":
    unittest.main()
