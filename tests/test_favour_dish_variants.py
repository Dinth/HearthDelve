"""A favour for a fish dish is filled by any plate of that dish."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestAFavourForSashimiTakesAnySashimi(unittest.TestCase):
    """The board asked for plain "Sashimi", which nobody can cook: the pan
    only ever gives a named variant (Tuna Sashimi…), and the favour matched
    the exact item — so it could never be filled."""

    def _asked(self, st, qty=2):
        req = {"npc": st.surface.npcs[0].name, "item": "Sashimi", "qty": qty,
               "gold": 100, "expires": st.day + 5, "flavor": ""}
        st.requests.append(req)
        return req

    def _plate(self, fish):
        from hearthdelve.data import content
        sashimi = next(r for r in content.RECIPES if r.name == "Sashimi")
        return content.cooked_dish(sashimi, fish)

    def test_variants_count_together(self):
        from hearthdelve.entities import items
        from hearthdelve.game import requests
        st = fresh_state(9)
        req = self._asked(st)
        inv = st.player.inventory
        inv.add(self._plate(items.TUNA), 1)
        self.assertFalse(requests.can_fulfil(st, req))
        inv.add(self._plate(items.MINNOW), 1)
        self.assertTrue(requests.can_fulfil(st, req))

    def test_the_humble_plate_goes_first_and_stars_are_paid(self):
        from hearthdelve.entities import items
        from hearthdelve.game import requests
        st = fresh_state(9)
        req = self._asked(st, qty=2)
        inv = st.player.inventory
        tuna, minnow = self._plate(items.TUNA), self._plate(items.MINNOW)
        inv.add(tuna, 2, quality=4)
        inv.add(minnow, 1, quality=2)
        gold = st.player.gold
        self.assertTrue(requests.deliver(st, req))
        self.assertEqual((inv.count(minnow), inv.count(tuna)), (0, 1))
        self.assertEqual(st.player.gold - gold, 100 + round(100 * 0.2 * 3))   # (2★ + 4★) / 2
        self.assertNotIn(req, st.requests)

    def test_another_dish_does_not_count(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import requests
        st = fresh_state(9)
        req = self._asked(st, qty=1)
        sushi = next(r for r in content.RECIPES if r.name == "Sushi")
        st.player.inventory.add(content.cooked_dish(sushi, items.TUNA), 3)
        self.assertFalse(requests.can_fulfil(st, req))
        self.assertFalse(requests.deliver(st, req))

    def test_an_ordinary_favour_is_unchanged(self):
        from hearthdelve.entities import items
        from hearthdelve.game import requests
        st = fresh_state(9)
        req = {"npc": st.surface.npcs[0].name, "item": "Egg", "qty": 2, "gold": 80,
               "expires": st.day + 5, "flavor": ""}
        st.requests.append(req)
        st.player.inventory.add(items.DUCK_EGG, 5)
        self.assertFalse(requests.can_fulfil(st, req))
        st.player.inventory.add(items.EGG, 2)
        self.assertTrue(requests.deliver(st, req))
        self.assertEqual(st.player.inventory.count(items.DUCK_EGG), 5)


if __name__ == "__main__":
    unittest.main()
