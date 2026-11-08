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


class TheMarketsBestDayStillLoses(unittest.TestCase):
    """The rows above clear an item's *worth*, but the bin pays more than worth
    when its bonuses stack — a craving on the kind, the Market Cross, a caravan,
    the Coin sign — and a saint haggles 10% off the counter. Piglets (+161g),
    every animal, both bows and Willa's silk (+361g) could be bought and posted
    back at a profit. Every counter must now beat the bin's best."""

    def _best_day(self, item):
        """A state where the bin pays the most it ever can for ``item``."""
        from hearthdelve.game import requests
        st = fresh_state(3)
        for pr in st.projects:
            pr["state"] = "done"                            # the Market Cross among them
        st.event = {"id": "caravan"}
        st.player.sign = "coin"
        if item.kind in requests.DEMAND_KINDS:               # the only kinds it ever craves
            st.demand = {"kind": item.kind, "mult": requests.DEMAND_RANGE[1], "until": st.day + 9}
        return st

    def test_the_ceiling_is_what_the_bin_really_pays_on_its_best_day(self):
        from hearthdelve.game import crafting
        for it in (items.PIGLET, items.SILK_CLOTH, items.COOKIES, items.STONE, items.ARROW):
            with self.subTest(item=it.name):
                self.assertEqual(crafting.bin_value(self._best_day(it), it, 0),
                                 crafting.bin_ceiling(it))

    def test_no_counter_anywhere_can_be_bought_and_posted_at_a_profit(self):
        from hearthdelve.game import crafting, karma, village
        st = fresh_state(3)
        st.player.karma = karma.MAX_KARMA                  # the best haggle there is
        for pr in st.projects:
            pr["state"] = "done"                            # every counter fully stocked
        shops = list(st.surface.npcs) + list(content.dwarf_npcs())
        rows = [(npc.name, r) for npc in shops if npc.shop or npc.role == "trader"
                for r in village.shop_entries(npc.shop or "trader", st, npc)
                if r.kind in ("buy", "tradebuy") and r.item is not None]
        self.assertGreater(len(rows), 100)
        pumps = [(who, r.item.name, r.price, crafting.bin_ceiling(r.item))
                 for who, r in rows if crafting.bin_ceiling(r.item) >= r.price]
        self.assertEqual(pumps, [])


class NoMachineTurnsBoughtGoodsIntoProfit(unittest.TestCase):
    """The counter beats the bin for every good it sells — but not for what a
    machine makes of it. Coal at the smith's (22g at the best haggle) kilned
    into coke worth 28 posted back for up to 40g. Every machine recipe that
    can be fed wholly from a counter that never runs dry must lose at the
    bin's best. (The smiths' deep bars are counted out by the week, so what
    an anvil makes of them is bounded by design.)"""

    def test_no_unlimited_counter_good_crafts_into_a_profit(self):
        from hearthdelve.game import crafting, karma, village
        st = fresh_state(3)
        st.player.karma = karma.MAX_KARMA
        for pr in st.projects:
            pr["state"] = "done"
        shops = list(st.surface.npcs) + list(content.dwarf_npcs())
        cheapest = {}
        for npc in shops:
            if not (npc.shop or npc.role == "trader"):
                continue
            for r in village.shop_entries(npc.shop or "trader", st, npc):
                if r.kind in ("buy", "tradebuy") and r.item is not None and r.left < 0:
                    cheapest[r.item] = min(r.price, cheapest.get(r.item, r.price))
        self.assertIn(items.COAL, cheapest)
        for it in cheapest:
            st.player.inventory.add(it, 50)
        pumps = []
        for kind, mdef in content.MACHINES.items():
            for o in crafting.machine_load_options(st, mdef) or []:
                ins = o.get("inputs") or []
                if not ins or not all(it in cheapest for it, _q in ins):
                    continue
                cost = sum(cheapest[it] * q for it, q in ins)
                best = crafting.bin_ceiling(o["output"]) * o.get("out_qty", 1)
                if best >= cost:
                    pumps.append((kind, o["output"].name, cost, best))
        self.assertEqual(pumps, [])


class TheSmithsDeepBarsRunOut(unittest.TestCase):
    """A master smith's forge averaged well over what bought bars cost (an
    adamantium greatsword cleared ~990g at baseline), and the counter never ran
    dry, so bars could be flipped through the anvil without end. Each smith now
    sells only so many of each deep bar a week — enough for a tool upgrade."""

    def setUp(self):
        from hearthdelve.game import village
        self.st = fresh_state(3)
        self.st.player.gold = 10 ** 6
        for pr in self.st.projects:
            if pr["id"] == "deep_forge":
                pr["state"] = "done"
        self.bron = next(n for n in self.st.surface.npcs if n.shop == "blacksmith")
        self.thrunn = next(n for n in content.dwarf_npcs() if n.shop == "blacksmith")
        self.per_week = village.DEEP_BARS_PER_WEEK

    def _row(self, npc, bar):
        from hearthdelve.game import village
        return next((r for r in village.shop_entries("blacksmith", self.st, npc)
                     if r.kind == "buy" and r.item is bar), None)

    def _buy_all(self, npc, bar):
        from hearthdelve.game import village
        bought = 0
        while (r := self._row(npc, bar)) is not None and bought < 50:
            village.purchase(self.st, r)
            bought += 1
        return bought

    def test_a_week_holds_a_set_number_and_the_next_week_restocks(self):
        bar = items.ADAMANTIUM_BAR
        self.assertEqual(self._row(self.bron, bar).left, self.per_week)
        self.assertEqual(self._row(self.bron, bar).label, bar.name)
        self.assertEqual(self._buy_all(self.bron, bar), self.per_week)
        self.assertEqual(self.st.player.inventory.count(bar), self.per_week)
        self.assertIsNone(self._row(self.bron, bar))
        self.assertIsNotNone(self._row(self.bron, items.MITHRIL_BAR))   # each bar its own stock
        self.st.day += 7
        self.assertEqual(self._buy_all(self.bron, bar), self.per_week)

    def test_enough_for_the_dearest_tool_upgrade(self):
        dearest = max(content.upgrade_cost(t)[2] for t in range(len(content.TIER_BAR)))
        self.assertGreaterEqual(self.per_week, dearest)

    def test_each_smith_keeps_their_own_stock_and_a_reload_keeps_the_count(self):
        from hearthdelve.engine import save
        bar = items.SILVER_BAR
        self._buy_all(self.bron, bar)
        self.assertIsNotNone(self._row(self.thrunn, bar))               # Khazgrim's forge
        save.save(self.st)
        self.st = save.load()
        self.assertIsNone(self._row(self.bron, bar))

    def test_the_common_bars_never_run_out(self):
        from hearthdelve.game import village
        r = self._row(self.bron, items.IRON_BAR)
        for _ in range(self.per_week + 3):
            village.purchase(self.st, r)
        self.assertIsNotNone(self._row(self.bron, items.IRON_BAR))


if __name__ == "__main__":
    unittest.main()
