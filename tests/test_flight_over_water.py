"""What can see you across water can be shot across it."""
from __future__ import annotations

import unittest

from tests.common import fresh_state
from tests.test_sidestep import _arena, _mob


class TestAShotCrossesWater(unittest.TestCase):
    """A spitter across a pool could see you and shoot (water is see-through),
    but your own shot stopped at the water's edge — and so did a spear."""

    def _pool(self, st, kind=None):
        from hearthdelve.world import tile
        _arena(st)
        p = st.player
        for dx in (1, 2):
            st.world.tiles[p.x + dx, p.y] = kind if kind is not None else tile.WATER

    def test_an_arrow_flies_over_a_pool_to_the_foe(self):
        from hearthdelve.game import combat
        st = fresh_state(11)
        self._pool(st)
        m = _mob(st, 3)
        self.assertEqual(combat.projectile_landing(st, m.x, m.y, 6), (m.x, m.y))

    def test_a_wall_still_stops_it(self):
        from hearthdelve.game import combat
        from hearthdelve.world import tile
        st = fresh_state(11)
        self._pool(st, tile.HOUSE_WALL)
        m = _mob(st, 3)
        self.assertEqual(combat.projectile_landing(st, m.x, m.y, 6), (st.player.x, st.player.y))

    def test_a_spear_reaches_across_a_puddle(self):
        from hearthdelve.data import content
        from hearthdelve.game import combat
        from hearthdelve.world import tile
        st = fresh_state(11)
        _arena(st)
        p = st.player
        p.hotbar[p.active_slot] = content.make_gear("Spear", "iron", "", "", ())
        st.world.tiles[p.x + 1, p.y] = tile.WATER
        m = _mob(st, 2)
        self.assertIs(combat.reach_target(st, m.x, m.y), m)
        st.world.tiles[p.x + 1, p.y] = tile.HOUSE_WALL
        self.assertIsNone(combat.reach_target(st, m.x, m.y))

if __name__ == "__main__":
    unittest.main()
