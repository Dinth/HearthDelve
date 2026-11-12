"""A counter lists the price it charges."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _counters(st):
    from hearthdelve.game import village
    seen = {}
    for n in st.surface.npcs:
        shop = getattr(n, "shop", "")
        if shop and shop not in seen:
            seen[shop] = n
    for shop, npc in seen.items():
        for r in village._shop_entries(shop, st, npc):
            if r.kind == "buy" and r.item is not None:
                yield shop, r


class TestTheListPriceClearsTheBin(unittest.TestCase):
    """A good can't cost less than the bin could pay for it. Sixteen list
    prices sat under that floor — young stock, cloth garments, bows and shot —
    so the counter charged more than it listed (a 162g chick cost 171g) and a
    saint's tenth off, taken from the lower figure, never showed. They now
    list high enough that the tenth comes off and still clears the bin."""

    def test_every_list_price_is_at_or_over_the_floor(self):
        from hearthdelve.game import crafting
        st = fresh_state(23)
        rows = list(_counters(st))
        self.assertGreater(len(rows), 80)
        for shop, r in rows:
            with self.subTest(shop=shop, item=r.item.name):
                self.assertGreater(r.price, crafting.bin_ceiling(r.item))

    def test_a_neutral_buyer_pays_the_list_price(self):
        from hearthdelve.game import village
        st = fresh_state(23)
        st.player.karma = 0
        for shop in ("general", "blacksmith"):
            base = [r for r in village._shop_entries(shop, st, None) if r.kind == "buy"]
            paid = [r for r in village.shop_entries(shop, st, None) if r.kind == "buy"]
            self.assertEqual([r.price for r in base], [r.price for r in paid])

    def test_a_saint_s_tenth_off_shows_on_every_good(self):
        from hearthdelve.game import crafting, karma, village
        st = fresh_state(23)
        st.player.karma = 100
        for shop in ("general", "blacksmith"):
            base = [r for r in village._shop_entries(shop, st, None) if r.kind == "buy"]
            paid = [r for r in village.shop_entries(shop, st, None) if r.kind == "buy"]
            for b, p in zip(base, paid):
                with self.subTest(shop=shop, item=b.item.name):
                    self.assertEqual(p.price, max(1, round(b.price * karma.buy_mult(100))))
                    if b.price > 5:                       # a 3g arrow has no tenth to give
                        self.assertLess(p.price, b.price)
                    self.assertGreater(p.price, crafting.bin_ceiling(b.item))

    def test_the_room_left_is_the_haggle_karma_gives(self):
        from hearthdelve.data import content
        from hearthdelve.game import karma
        self.assertEqual(content.BEST_HAGGLE, karma.buy_mult(100))
        self.assertEqual(content.BEST_HAGGLE, karma.buy_mult(10_000))

    def test_the_bin_s_best_is_the_one_the_counter_allows_for(self):
        import math
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        for it in (items.CHICK, items.CALF, items.PIGLET, items.SLING, items.ARROW):
            self.assertEqual(content.counter_price(it, 1.0),
                             math.ceil((crafting.bin_ceiling(it) + 1) / content.BEST_HAGGLE))

    def test_what_each_standing_pays_for_a_chick(self):
        from hearthdelve.entities import items
        from hearthdelve.game import village
        st = fresh_state(23)
        got = []
        for k in (100, 0, -100):
            st.player.karma = k
            got.append(next(r.price for r in village.shop_entries("general", st, None)
                            if r.item is items.CHICK))
        self.assertEqual(got, [171, 190, 209])


if __name__ == "__main__":
    unittest.main()
