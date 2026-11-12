"""A night away from home: an inn's bed for gold, or the ground for nothing."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _keeper(st):
    return next(n for n in st.surface.npcs if n.role == "innkeeper")


def _room(st):
    from hearthdelve.game import village
    return next((r for r in village.shop_entries("tavern", st, _keeper(st))
                 if r.kind == "room"), None)


class TestSleepingRough(unittest.TestCase):
    """Away from your bed there was nothing to do but stay up till you dropped
    at two in the morning, and lose a tenth of your gold for it."""

    def _away(self):
        st = fresh_state(161)
        p = st.player
        p.x, p.y = p.x + 30, p.y + 30
        p.gold, p.energy, p.hp = 500, 12, 9
        return st

    def test_the_ground_gives_most_of_a_nights_rest(self):
        from hearthdelve.game import farming
        st = self._away()
        p = st.player
        day, where = st.day, (p.x, p.y)
        self.assertFalse(farming.can_sleep(st))
        self.assertTrue(farming.can_sleep_rough(st))
        farming.sleep_rough(st)
        self.assertEqual(st.day, day + 1)
        self.assertEqual((p.x, p.y), where)                       # you wake where you lay
        self.assertEqual(p.energy, round(p.max_energy * farming.ROUGH_REST))
        self.assertEqual(p.hp, round(p.max_hp * farming.ROUGH_REST))
        self.assertEqual(p.gold, 500)                             # and keep your purse

    def test_it_beats_collapsing_and_loses_to_a_bed(self):
        from hearthdelve.game import farming
        self.assertGreater(farming.ROUGH_REST, 0.5)
        self.assertLess(farming.ROUGH_REST, 1.0)

    def test_the_ground_has_no_quilt(self):
        from hearthdelve.game import farming, home
        st = self._away()
        st.stats[home.QUILT] = 5
        farming.sleep_rough(st)
        self.assertEqual(st.player.energy, round(st.player.max_energy * farming.ROUGH_REST))

    def test_not_underground(self):
        from hearthdelve.game import farming
        from tests.test_noise import _below
        self.assertFalse(farming.can_sleep_rough(_below()))

    def test_the_crops_still_grow_that_night(self):
        from hearthdelve.data import content
        from hearthdelve.game import farming
        from hearthdelve.game.farming import CropPlot
        st = self._away()
        pos = (st.player.x + 2, st.player.y)
        st.surface.crops[pos] = CropPlot(crop=content.PARSNIP, days_grown=0, watered=True)
        farming.sleep_rough(st)
        self.assertEqual(st.surface.crops[pos].days_grown, 1)


class TestARoomAtTheInn(unittest.TestCase):
    def test_every_inn_lets_a_room(self):
        from hearthdelve.game import farming
        st = fresh_state(162)
        row = _room(st)
        self.assertIsNotNone(row)
        self.assertEqual(row.price, farming.INN_ROOM_PRICE)

    def test_it_is_a_full_nights_rest_for_the_price(self):
        from hearthdelve.game import village
        st = fresh_state(162)
        p = st.player
        p.gold, p.energy, p.hp = 200, 3, 4
        row, day = _room(st), st.day
        village.purchase(st, row, _keeper(st))
        self.assertEqual(st.day, day + 1)
        self.assertEqual((p.energy, p.hp), (p.max_energy, p.max_hp))
        self.assertEqual(p.gold, 200 - row.price)

    def test_an_inns_bed_is_not_your_own(self):
        from hearthdelve.game import home, village
        st = fresh_state(162)
        st.player.gold = 200
        st.stats[home.QUILT] = 5
        village.purchase(st, _room(st), _keeper(st))
        self.assertEqual(st.player.energy, st.player.max_energy)

    def test_no_coin_no_bed(self):
        from hearthdelve.game import village
        st = fresh_state(162)
        st.player.gold = 5
        day = st.day
        village.purchase(st, _room(st), _keeper(st))
        self.assertEqual((st.day, st.player.gold), (day, 5))

    def test_a_saint_pays_less_for_it(self):
        from hearthdelve.game import farming
        st = fresh_state(162)
        st.player.karma = 100
        self.assertLess(_room(st).price, farming.INN_ROOM_PRICE)

    def test_your_own_bed_still_rests_you_best(self):
        from hearthdelve.game import farming, home
        st = fresh_state(162)
        st.stats[home.QUILT] = 1
        st.player.x, st.player.y = st.surface.bed
        farming.sleep(st)
        self.assertGreater(st.player.energy, st.player.max_energy)


if __name__ == "__main__":
    unittest.main()
