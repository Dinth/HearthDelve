"""A dose of fertiliser feeds one harvest."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestFertiliserIsSpentByThePick(unittest.TestCase):
    """The flag stayed set on a regrowing plant: one 25g dose put a star on
    every later pick — for ever, in a greenhouse."""

    def test_a_regrower_must_be_dressed_again(self):
        from hearthdelve.data import content
        from hearthdelve.game import farming
        from hearthdelve.world.crops import CropPlot
        st = fresh_state(21)
        crop = next(c for c in content.CROPS if c.regrows and c.season == st.season)
        pos = (st.player.x + 1, st.player.y)
        st.surface.crops[pos] = CropPlot(crop=crop, days_grown=crop.days_to_mature, fertilized=True)
        soil = st.surface.soil.get(pos, 0)
        self.assertTrue(farming.harvest(st, *pos))
        plot = st.surface.crops[pos]
        self.assertFalse(plot.fertilized)
        self.assertGreater(st.surface.soil.get(pos, 0), soil)    # the ground keeps what it gained

    def test_the_dressed_pick_itself_still_gets_its_star(self):
        from unittest import mock
        from hearthdelve.data import content
        from hearthdelve.game import farming, skills
        from hearthdelve.world.crops import CropPlot
        st = fresh_state(21)
        crop = next(c for c in content.CROPS if c.regrows and c.season == st.season)
        pos = (st.player.x + 1, st.player.y)
        st.surface.crops[pos] = CropPlot(crop=crop, days_grown=crop.days_to_mature, fertilized=True)
        with mock.patch.object(skills, "roll_quality", return_value=1), \
                mock.patch.object(skills, "extra_yield_chance", return_value=0.0):
            farming.harvest(st, *pos)
        (entry,) = [e for e in st.player.inventory.slots if e[0] is crop.produce]
        self.assertEqual(entry[2], 2)


if __name__ == "__main__":
    unittest.main()
