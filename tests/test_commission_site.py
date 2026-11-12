"""The carpenter's outbuildings are sited in the Vale and nowhere else."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestACommissionIsOnlySitedInTheVale(unittest.TestCase):
    """The `p` key refused dungeons but not the Westreach, whose machines are
    never saved or finished: the order was taken and no barn ever rose."""

    def _on_the_westreach(self):
        from hearthdelve.world import westgen
        st = fresh_state(3)
        st.west = westgen.generate(st.seed)
        st.world = st.west
        st.player.x, st.player.y = st.west.spawn
        st.pending_build = "barn"
        return st

    def test_the_order_survives_a_try_on_the_westreach(self):
        from hearthdelve.game import husbandry
        from hearthdelve.world import tile
        st = self._on_the_westreach()
        before = st.west.tiles.copy()
        for dx in range(-8, 9):
            for dy in range(-8, 9):
                husbandry.place_commission_at(st, st.player.x + dx, st.player.y + dy)
        self.assertEqual(st.pending_build, "barn")
        self.assertFalse(st.west.machines)
        self.assertFalse(st.surface.machines.keys() - fresh_state(3).surface.machines.keys())
        self.assertTrue((st.west.tiles == before).all())
        self.assertFalse((st.west.tiles == tile.SCAFFOLD).any())

    def test_the_preview_says_why(self):
        from hearthdelve.game import husbandry
        st = self._on_the_westreach()
        ok, _cells, reason = husbandry.can_place_building(st, st.west.spawn, "barn")
        self.assertFalse(ok)
        self.assertIn("Vale", reason)

    def test_it_is_still_sited_at_home(self):
        from hearthdelve.game import husbandry
        st = fresh_state(3)
        st.pending_build = "barn"
        px, py = st.player.x, st.player.y
        placed = any(husbandry.place_commission_at(st, px + dx, py + dy)
                     for dx in range(-18, 19, 3) for dy in range(-18, 19, 3))
        self.assertTrue(placed)
        self.assertEqual(st.pending_build, "")


if __name__ == "__main__":
    unittest.main()
