"""Bait: a likelier bite, and the shy fish come to it."""
from __future__ import annotations

import random
import unittest
from unittest import mock

from tests.common import fresh_state


def _at_water(st):
    from hearthdelve.world import tile
    from tests.test_anim import _clear_line
    p = st.player
    dx, dy = _clear_line(st, 4)
    st.world.tiles[p.x + dx, p.y + dy] = tile.RIVER
    p.facing = (dx, dy)
    return p.x + dx, p.y + dy


class TestBait(unittest.TestCase):
    def test_a_minnow_makes_four(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(191)
        st.player.inventory.add(items.MINNOW, 1)
        r = next(r for r in content.RECIPES if r.name == "Bait")
        self.assertTrue(crafting.craft(st, r))
        self.assertEqual(st.player.inventory.count(items.BAIT), 4)
        self.assertGreaterEqual(items.BAIT.value * 4, items.MINNOW.value * 1.25)

    def test_each_cast_spends_one(self):
        from hearthdelve.entities import items
        from hearthdelve.game import fishing
        st = fresh_state(191)
        spot = _at_water(st)
        st.player.inventory.add(items.BAIT, 3)
        fishing.begin(st, *spot)
        self.assertEqual(st.player.inventory.count(items.BAIT), 2)

    def test_no_bait_no_change(self):
        from hearthdelve.entities import items
        from hearthdelve.game import fishing
        st = fresh_state(191)
        spot = _at_water(st)
        self.assertIsNotNone(fishing.begin(st, *spot))
        self.assertEqual(st.player.inventory.count(items.BAIT), 0)

    def test_a_baited_hook_bites_where_a_bare_one_would_not(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import fishing
        st = fresh_state(191)
        spot = _at_water(st)
        chance, _t = fishing.bite_odds(st, fishing.water_kind(st, *spot))
        roll = chance + content.BAIT_BITE / 2            # just past a bare hook's reach
        with mock.patch("random.random", return_value=roll):
            self.assertFalse(fishing.begin(st, *spot)["bite"])
            st.player.inventory.add(items.BAIT, 1)
            self.assertTrue(fishing.begin(st, *spot)["bite"])

    def test_the_shy_fish_come_twice_as_readily(self):
        from hearthdelve.data import content
        table = content.fish_in_season("Summer")
        baited = dict(content.baited_table(table))
        for fish, w in table:
            with self.subTest(fish=fish.name):
                want = w * 2 if w <= content.BAIT_SHY_WEIGHT else w
                self.assertEqual(baited[fish], want)
        shy = [f for f, w in table if w <= content.BAIT_SHY_WEIGHT]
        self.assertTrue(shy)
        share = lambda t: sum(w for f, w in t if f in shy) / sum(w for _f, w in t)
        self.assertGreater(share(content.baited_table(table)), share(table))

    def test_the_tables_themselves_are_never_changed(self):
        from hearthdelve.data import content
        before = list(content.SEA_FISH)
        content.baited_table(content.SEA_FISH)
        self.assertEqual(content.SEA_FISH, before)


if __name__ == "__main__":
    unittest.main()
