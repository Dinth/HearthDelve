"""No counter may undercut the shipping bin.

Two rows did. Sling Stones were listed at a hard-coded 1g while
``_enforce_recipe_margins`` had lifted their value to 2g (one 4g Stone makes four,
so the +25% floor forces ``ceil(4 * 1.25 / 4) = 2``) — buy, post, sleep, repeat,
and gold doubled every round trip with no cap and no prerequisite. And every
livestock animal was priced at *exactly* its sell value, dormant only because
nothing multiplied it; a craving, a caravan or the Market Cross would each have
turned the drover into a pump.

The lesson is that a literal price and a derived value drift apart silently, so
the test guards the whole counter rather than the two rows that were wrong.
"""
from __future__ import annotations

import unittest

from tests.common import fresh_state

from hearthdelve.data import content
from hearthdelve.entities import items


def _all_rows():
    rows = [("general store", it, pr) for it, pr in content.GENERAL_STOCK]
    rows += [("blacksmith", it, pr) for it, pr in content.blacksmith_stock()]
    return rows


class ShopPriceTest(unittest.TestCase):
    def test_no_row_sells_for_less_than_the_bin_pays(self):
        underpriced = [(shop, it.name, pr, it.value)
                       for shop, it, pr in _all_rows()
                       if it.value > 0 and pr <= it.value]
        self.assertEqual(underpriced, [],
                         f"shop rows at or below their sell value: {underpriced}")

    def test_buying_and_posting_a_stock_item_never_turns_a_profit(self):
        """The exploit as the player would run it, priced end to end at baseline."""
        from hearthdelve.game import crafting
        st = fresh_state(3)
        losers = []
        for shop, it, price in _all_rows():
            if it.value <= 0:
                continue
            if crafting.bin_value(st, it, 0) >= price:
                losers.append((shop, it.name, price, crafting.bin_value(st, it, 0)))
        self.assertEqual(losers, [], f"buy-and-post is free money for: {losers}")

    def test_livestock_carries_a_real_markup(self):
        prices = dict((it.name, pr) for it, pr in content.GENERAL_STOCK)
        for name in ("Chick", "Duckling", "Lamb", "Goat Kid", "Calf", "Piglet"):
            it = items.by_name(name)
            with self.subTest(animal=name):
                self.assertGreater(prices[name], it.value,
                                   f"{name} is sold at cost, so re-posting it is free")

    def test_counter_price_always_clears_the_value(self):
        for v in (0, 1, 2, 3, 7, 100, 800):
            it = items.Item("Probe", "?", "material", value=v)
            self.assertGreater(content.counter_price(it), it.value,
                               f"counter_price({v}) does not clear the item's worth")


if __name__ == "__main__":
    unittest.main()
