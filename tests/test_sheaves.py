"""Grain and flax come in by the sheaf."""
from __future__ import annotations

import unittest
from unittest import mock

from tests.common import fresh_state


def _ripe(st, crop):
    from hearthdelve.game.farming import CropPlot
    p = st.player
    pos = (p.x + 2, p.y + 2)
    st.world.crops[pos] = CropPlot(crop=crop, days_grown=crop.days_to_mature, watered=True)
    return pos


class TestSheaves(unittest.TestCase):
    """A plot of wheat earned 30g a season, a plot of flax nothing."""

    def test_grain_and_flax_come_in_twos_and_threes(self):
        from hearthdelve.data import content
        from hearthdelve.game import farming
        for crop in (content.WHEAT, content.BARLEY, content.RICE, content.FLAX,
                     content.CROP_BY_NAME["Tritordeum"]):
            got = set()
            for seed in range(40):
                st = fresh_state(131)
                pos = _ripe(st, crop)
                before = st.player.inventory.count(crop.produce)
                import random
                random.seed(seed)
                with mock.patch("hearthdelve.game.skills.extra_yield_chance", return_value=0.0):
                    self.assertTrue(farming.harvest(st, *pos))
                got.add(st.player.inventory.count(crop.produce) - before)
                if got == {2, 3}:
                    break
            with self.subTest(crop=crop.name):
                self.assertEqual(got, {2, 3})

    def test_everything_else_is_still_picked_one_at_a_time(self):
        from hearthdelve.data import content
        for crop in content.CROPS + content.HYBRIDS:
            if crop.name in ("Wheat", "Barley", "Rice", "Flax", "Tritordeum"):
                continue
            with self.subTest(crop=crop.name):
                self.assertEqual(content.harvest_measures(crop), (1, 1))

    def test_a_plot_of_grain_now_pays_its_way(self):
        from hearthdelve.data import content
        from hearthdelve.engine import constants as C
        price = dict(content.GENERAL_STOCK)
        for crop in (content.WHEAT, content.BARLEY, content.RICE, content.FLAX):
            sowings = (C.SEASON_LEN - 1) // crop.days_to_mature
            lo, hi = content.harvest_measures(crop)
            net = sowings * ((lo + hi) / 2 * crop.produce.value - price[crop.seed])
            with self.subTest(crop=crop.name):
                self.assertGreaterEqual(net / C.SEASON_LEN, 5.0)

    def test_the_whole_sheaf_shares_the_harvests_stars(self):
        from hearthdelve.data import content
        from hearthdelve.game import farming
        st = fresh_state(132)
        pos = _ripe(st, content.WHEAT)
        with mock.patch("hearthdelve.game.skills.roll_quality", return_value=3), \
                mock.patch("hearthdelve.game.skills.extra_yield_chance", return_value=0.0):
            farming.harvest(st, *pos)
        self.assertGreaterEqual(st.player.inventory.count(content.WHEAT.produce, 3), 2)


if __name__ == "__main__":
    unittest.main()
