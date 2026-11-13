"""Rain tires outdoor work a little; a cloak turns it, a batwing cloak all of it."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _outdoors(weather, cloak=None):
    from hearthdelve.data import content
    st = fresh_state(201)
    st.weather = weather
    p = st.player
    p.x, p.y = p.x + 12, p.y + 12                 # well clear of the farmhouse
    if cloak:
        p.equipment["cloak"] = content.make_gear("Cloak", cloak)
    return st


class TestWetWork(unittest.TestCase):
    """Weather never touched the farmer: rain watered the crops and that was all."""

    def test_a_dry_day_costs_nothing_extra(self):
        from hearthdelve.game import commands
        for weather in ("Clear", "Cloudy", "Fog", "Snow"):
            self.assertEqual(commands.rain_toll(_outdoors(weather)), 0)

    def test_rain_costs_a_point_and_a_storm_two(self):
        from hearthdelve.game import commands
        self.assertEqual(commands.rain_toll(_outdoors("Rain")), 1)
        self.assertEqual(commands.rain_toll(_outdoors("Storm")), 2)

    def test_any_cloak_sheds_a_point(self):
        from hearthdelve.game import commands
        for cloak in ("wool", "fur", "leather"):
            with self.subTest(cloak=cloak):
                self.assertEqual(commands.rain_toll(_outdoors("Rain", cloak)), 0)
                self.assertEqual(commands.rain_toll(_outdoors("Storm", cloak)), 1)

    def test_a_batwing_cloak_sheds_it_all(self):
        from hearthdelve.game import commands
        self.assertEqual(commands.rain_toll(_outdoors("Storm", "batwing")), 0)

    def test_not_under_your_own_roof_or_below_ground(self):
        from hearthdelve.game import commands
        from tests.test_noise import _below
        st = fresh_state(201)
        st.weather = "Storm"
        st.player.x, st.player.y = st.surface.bed
        self.assertEqual(commands.rain_toll(st), 0)
        deep = _below()
        deep.weather = "Storm"
        self.assertEqual(commands.rain_toll(deep), 0)

    def _till_cost(self, weather, cloak=None):
        from hearthdelve.entities import items
        from hearthdelve.game import commands, land
        from tests.test_anim import _clear_line
        st = _outdoors(weather, cloak)
        p = st.player
        dx, dy = _clear_line(st, 3)
        p.facing = (dx, dy)
        from hearthdelve.world import tile
        st.world.tiles[p.x + dx, p.y + dy] = tile.GRASS
        if land.owned_by_other(st, p.x + dx, p.y + dy):
            self.skipTest("that ground is someone's")
        p.hotbar[p.active_slot] = items.HOE
        before = p.energy
        commands.use_tool(st)
        return before - p.energy

    def test_a_hoe_in_the_rain_costs_that_much_more(self):
        dry = self._till_cost("Clear")
        self.assertGreater(dry, 0)
        self.assertEqual(self._till_cost("Rain"), dry + 1)
        self.assertEqual(self._till_cost("Storm"), dry + 2)
        self.assertEqual(self._till_cost("Storm", "batwing"), dry)

    def test_it_is_said_once_a_day(self):
        from hearthdelve.game import commands
        st = _outdoors("Rain")
        st.stats["rain_told"] = st.day
        self.assertEqual(commands.rain_toll(st), 1)


if __name__ == "__main__":
    unittest.main()
