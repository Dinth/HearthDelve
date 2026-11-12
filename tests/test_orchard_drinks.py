"""Cider and perry are wine to anyone who loves wine."""
from __future__ import annotations

import unittest

from tests.common import shared_state


class TestAWineLoverTakesCider(unittest.TestCase):
    """Tastes match by family. Apples and pears ferment into Cider and Perry,
    each on a family of its own that no villager named — so sixteen people
    loved a strawberry wine and not one cared for a cider."""

    def test_they_are_received_like_any_fruit_wine(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        st = shared_state(23)
        wine = content.FRUIT_WINE[items.STRAWBERRY]
        fond = 0
        for npc in st.surface.npcs:
            for drink in (items.CIDER, items.PERRY, content.AGED_DRINK[items.CIDER]):
                with self.subTest(npc=npc.name, drink=drink.name):
                    self.assertEqual(npc._matches(drink, npc.loves), npc._matches(wine, npc.loves))
                    self.assertEqual(npc._matches(drink, npc.dislikes),
                                     npc._matches(wine, npc.dislikes))
            fond += npc._matches(items.CIDER, npc.loves)
        self.assertGreater(fond, 5)

    def test_they_keep_their_names_and_prices(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        self.assertIs(content.FRUIT_WINE[items.APPLE], items.CIDER)
        self.assertEqual(items.CIDER.value, round(items.APPLE.value * content.WINE_MULT))


if __name__ == "__main__":
    unittest.main()
