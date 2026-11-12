"""The traders' rotating wagons: window rotation, stock, and sold-out slots.

The window index is baked into the ``trader_<name>_<window>_<slot>`` stats keys
that remember a sold-out slot, so the rotation must stay bit-identical to the
original walk-the-calendar implementation forever — a drift would un-sell bought
slots (or mark unsold ones sold) in every existing save. `_reference_window`
below IS that original, kept as the oracle.
"""
from __future__ import annotations

import random
import time
import unittest

from tests.common import fresh_state


def _reference_window(seed: int, day: int) -> tuple[int, int]:
    """The original O(day) implementation, verbatim — the behavioural oracle."""
    n, start = 0, 0
    while True:
        length = 3 + random.Random((seed * 611_953 + n * 2_741) & 0x7FFFFFFF).randint(0, 3)
        if day < start + length:
            return n, (seed * 887 + n * 104_729) & 0x7FFFFFFF
        start += length
        n += 1


class TestTraderWindow(unittest.TestCase):
    def test_it_matches_the_original_walk_exactly(self):
        from hearthdelve.game import village
        for seed in (1, 1337, 99_991):
            for day in range(0, 400):
                self.assertEqual(village.trader_window(seed, day),
                                 _reference_window(seed, day),
                                 f"drifted at seed={seed} day={day}")

    def test_it_matches_far_out_and_out_of_order(self):
        # The memo is grown on demand; asking backwards must still be right.
        from hearthdelve.game import village
        for day in (5000, 12, 4999, 0, 2500, 5001, 7):
            self.assertEqual(village.trader_window(1337, day),
                             _reference_window(1337, day), f"day={day}")

    def test_windows_run_three_to_six_days_and_tile_the_calendar(self):
        from hearthdelve.game import village
        runs: dict[int, int] = {}
        prev = None
        for day in range(0, 600):
            n, _wseed = village.trader_window(4242, day)
            runs[n] = runs.get(n, 0) + 1
            if prev is not None:
                self.assertIn(n - prev, (0, 1), "windows must advance one at a time")
            prev = n
        # every window but the last (clipped by the loop) is 3-6 days long
        for n, length in sorted(runs.items())[:-1]:
            self.assertTrue(3 <= length <= 6, f"window {n} ran {length} days")
        self.assertGreater(len(runs), 90, "600 days should span many windows")

    def test_a_window_holds_its_stock_and_the_next_one_shifts_it(self):
        from hearthdelve.game import village
        st = fresh_state(1337)
        npc = next(n for n in st.surface.npcs if n.role == "trader")
        st.day = 0
        first = [r.label for r in village.trader_entries(st, npc)]
        self.assertTrue(first, "a wagon should carry something")
        # ...same window, same wagon
        while village.trader_window(st.seed, st.day + 1)[0] == 0:
            st.day += 1
            self.assertEqual([r.label for r in village.trader_entries(st, npc)], first)
        st.day += 1                                  # over the boundary
        self.assertNotEqual(village.trader_window(st.seed, st.day)[0], 0)

    def test_a_bought_slot_stays_sold_for_that_window(self):
        from hearthdelve.game import village
        st = fresh_state(1337)
        npc = next(n for n in st.surface.npcs if n.role == "trader")
        rows = village.trader_entries(st, npc)
        buys = [r for r in rows if r.kind == "tradebuy"]
        self.assertTrue(buys, "a wagon should offer gear to buy")
        st.player.gold = buys[0].price
        village.purchase(st, buys[0])
        self.assertEqual(st.player.inventory.count(buys[0].item), 1)
        left = [r.label for r in village.trader_entries(st, npc) if r.kind == "tradebuy"]
        self.assertNotIn(buys[0].label, left, "a sold slot must not restock this window")

    def test_the_lookup_does_not_get_slower_as_the_years_pass(self):
        """The regression this memo exists for: the original walked the calendar
        from day 0 on every call, so a late-game trader panel cost ~1ms a frame
        and climbed forever."""
        from hearthdelve.game import village

        def per_call(day: int) -> float:
            village.trader_window(777, day)          # warm the memo
            t0 = time.perf_counter()
            for _ in range(300):
                village.trader_window(777, day)
            return (time.perf_counter() - t0) / 300

        early, late = per_call(5), per_call(20_000)
        self.assertLess(late, max(early * 8, 5e-5),
                        f"day-20000 lookup {late * 1e6:.1f}us vs day-5 {early * 1e6:.1f}us")


class TestTheWagonsSaplingIsTheStoresPrice(unittest.TestCase):
    """Every general store sells every sapling, all year; the wagons asked a
    flat 1,050g for the cherry, peach or apple the store sells for 600-700."""

    def test_no_wagon_asks_more_than_the_store_for_a_sapling(self):
        from hearthdelve.data import content
        from hearthdelve.game import village
        st = fresh_state(1337)
        traders = [n for n in st.surface.npcs if n.role == "trader"]
        store = {r.item: r.price for r in village.shop_entries("general", st)}
        seen = 0
        for day in range(0, 120, 3):                  # many windows, every wagon
            st.day = day
            for npc in traders:
                for r in village.shop_entries("trader", st, npc):
                    if r.item in content.SAPLING_TO_TREE:
                        seen += 1
                        self.assertLessEqual(r.price, store[r.item], (npc.name, r.label))
        self.assertGreater(seen, 0)


class TestWillaBeforeTheCauseway(unittest.TestCase):
    """Her wagon did not open at all until the causeway stood. Now the
    flooded road only makes her load lighter and her prices higher."""

    def _willa(self, st):
        willa = next((n for n in st.surface.npcs if n.name == "Willa"), None)
        self.assertIsNotNone(willa, "Fenwick should have its trader")
        return willa

    def _stock(self, st):
        from hearthdelve.game import village
        return {r.label: r.price for r in village.trader_entries(st, self._willa(st))
                if r.kind == "tradebuy"}

    def test_she_trades_from_the_start(self):
        from hearthdelve.game import village
        st = fresh_state(1337)
        self.assertEqual(village.npc_shop(st, self._willa(st)), "trader")
        self.assertTrue(self._stock(st))

    def test_the_flooded_road_costs_a_quarter_more(self):
        from hearthdelve.game import projects, village
        for day in range(0, 60, 5):
            st = fresh_state(1337)
            st.day = day
            before = self._stock(st)
            projects.get(st, "causeway")["state"] = "done"
            after = self._stock(st)
            for name, price in before.items():
                if "Sapling" in name:                 # a sapling is always the store's price
                    self.assertEqual(price, after[name])
                    continue
                with self.subTest(day=day, item=name):
                    self.assertGreater(price, after[name])
                    self.assertAlmostEqual(price / after[name], village.FLOOD_ROAD_MARKUP,
                                           delta=0.06)

    def test_the_causeway_fills_her_wagon(self):
        from hearthdelve.entities import items
        from hearthdelve.game import projects
        seen_before, seen_after = set(), set()
        for day in range(0, 120, 4):
            st = fresh_state(1337)
            st.day = day
            seen_before |= set(self._stock(st))
            projects.get(st, "causeway")["state"] = "done"
            seen_after |= set(self._stock(st))
        self.assertNotIn(items.SILK_CLOTH.name, seen_before)
        self.assertIn(items.SILK_CLOTH.name, seen_after)


if __name__ == "__main__":
    unittest.main()
