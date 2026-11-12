"""A regrowing crop survives the night after it is picked."""
from __future__ import annotations

import os
import tempfile
import unittest

from tests.common import fresh_state


class TestAPickedRegrowerSurvivesTheNight(unittest.TestCase):
    """A ripe plant never asks for water, so nobody waters the one they are
    about to pick; the pick made it a growing plant again, and a clear dawn
    then withered it outright."""

    def _picked(self, weather):
        from hearthdelve.data import content
        from hearthdelve.game import farming
        from hearthdelve.world.crops import CropPlot
        st = fresh_state(4)
        crop = next(c for c in content.CROPS if c.regrows and c.season == st.season)
        pos = (st.player.x + 1, st.player.y)
        st.surface.crops[pos] = CropPlot(crop=crop, days_grown=crop.days_to_mature)
        st.weather = weather
        self.assertTrue(farming.harvest(st, *pos))
        return st, st.surface.crops[pos], crop

    def test_one_dry_clear_dawn_leaves_it_alive(self):
        from hearthdelve.world.crops import advance_growth
        from hearthdelve.game.farming import _WITHER_DAYS
        _st, plot, crop = self._picked("Clear")
        advance_growth(plot, crop.season, _WITHER_DAYS["Clear"])
        self.assertFalse(plot.dead)

    def test_but_a_second_one_still_withers_it(self):
        from hearthdelve.world.crops import advance_growth
        from hearthdelve.game.farming import _WITHER_DAYS
        _st, plot, crop = self._picked("Clear")
        advance_growth(plot, crop.season, _WITHER_DAYS["Clear"])
        advance_growth(plot, crop.season, _WITHER_DAYS["Clear"])
        self.assertTrue(plot.dead)

    def test_through_a_whole_dawn(self):
        from hearthdelve.game import farming
        st, plot, _crop = self._picked("Clear")
        farming.new_day(st)
        self.assertFalse(plot.dead)

    def test_the_grace_survives_a_save(self):
        from hearthdelve.engine import save
        st, plot, _crop = self._picked("Clear")
        self.assertEqual(plot.thirst, -1)
        path = os.path.join(tempfile.mkdtemp(prefix="hd-thirst-"), "s.json")
        save.save(st, path)
        back = save.load(path)
        self.assertEqual([p.thirst for p in back.surface.crops.values() if p.thirst], [-1])


if __name__ == "__main__":
    unittest.main()
