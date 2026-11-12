"""A keg ferments in a day."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestKegPace(unittest.TestCase):
    """At 40 hours a keg earned a seventh of what a jar did per hour."""

    def test_wine_takes_a_day(self):
        from hearthdelve.data import content
        self.assertEqual(content.MACHINES["keg"].minutes, 24 * 60)

    def test_a_keg_is_still_the_slower_richer_road(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        keg, jar = content.MACHINES["keg"], content.MACHINES["jar"]
        self.assertGreater(keg.minutes, jar.minutes * 3)
        wine = content.FRUIT_WINE.get(items.GRAPE, items.WINE)
        self.assertGreaterEqual(wine.value, items.GRAPE.value * 2)

    def test_a_loaded_keg_is_ready_a_day_on(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.entities.machine import Machine
        from hearthdelve.game import crafting
        st = fresh_state(141)
        st.player.inventory.add(items.GRAPE, 1)
        mdef = content.MACHINES["keg"]
        m = Machine(kind="keg")
        opt = next(o for o in crafting.machine_load_options(st, mdef)
                   if o["inputs"][0][0] is items.GRAPE)
        crafting.load_machine_choice(st, m, mdef, opt)
        self.assertEqual(m.ready_at - st.abs_minutes, 24 * 60)

    def test_laying_mead_down_in_a_keg_is_still_slower_than_the_cellar(self):
        from hearthdelve.data import content
        from hearthdelve.game import crafting
        self.assertGreater(crafting.KEG_AGEING_MINUTES, content.MACHINES["cellar"].minutes)


if __name__ == "__main__":
    unittest.main()
