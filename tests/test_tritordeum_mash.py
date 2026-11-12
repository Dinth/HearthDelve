"""Tritordeum has a use beyond the shipping bin."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestTheHybridGrainFerments(unittest.TestCase):
    """A grain no mill ground, no keg took and no jar would hold: the only
    hybrid with nowhere to go but the bin."""

    def test_one_ear_makes_a_mash_in_the_keg(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import crafting
        st = fresh_state(25)
        grain = content.CROP_BY_NAME["Tritordeum"].produce
        st.player.inventory.add(grain, 1)
        opts = crafting.machine_load_options(st, content.MACHINES["keg"])
        mash = [o for o in opts if o["output"] is items.GRAIN_MASH]
        self.assertEqual([o["inputs"] for o in mash], [[(grain, 1)]])

    def test_the_mash_is_worth_more_than_the_ear(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        grain = content.CROP_BY_NAME["Tritordeum"].produce
        self.assertGreaterEqual(items.GRAIN_MASH.value, grain.value * 1.2)
        wheat = content.MASH_SOURCES[items.WHEAT] * items.WHEAT.value
        self.assertEqual(content.MASH_SOURCES[grain] * grain.value, wheat)   # same as two of wheat


if __name__ == "__main__":
    unittest.main()
