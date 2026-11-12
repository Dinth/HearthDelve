"""Running through the fen breathes its miasma like walking does."""
from __future__ import annotations

import unittest
from unittest import mock

from tests.common import fresh_state


class TestARunThroughTheMarshCanSicken(unittest.TestCase):
    """`w` + a direction skipped the surface tile effects, so the whole fen
    could be crossed at a run with no risk of the wasting sickness at all."""

    def _in_the_fen(self, ground):
        from hearthdelve.world import tile
        st = fresh_state(13)
        p, w = st.player, st.world
        for dx in range(-2, 12):
            for dy in range(-2, 3):
                w.tiles[p.x + dx, p.y + dy] = ground
                for layer in (w.crops, w.machines, w.trees):
                    layer.pop((p.x + dx, p.y + dy), None)
        w.monsters[:] = []
        w.animals[:] = []
        w.npcs[:] = [n for n in w.npcs if abs(n.x - p.x) > 20 or abs(n.y - p.y) > 20]
        return st

    def _run(self, st, luck):
        from hearthdelve.game import commands
        ctx = commands.start_run(st, 1, 0)
        with mock.patch.object(commands.random, "random", return_value=luck):
            for _ in range(5):
                if not commands.run_step(st, ctx):
                    break
        return ctx

    def test_off_road_through_marsh(self):
        from hearthdelve.world import tile
        st = self._in_the_fen(tile.MARSH)
        ctx = self._run(st, 0.0)                         # the unlucky breath
        self.assertGreater(ctx["steps"], 0)
        self.assertIn("sick", st.player.status)

    def test_luck_still_spares_you(self):
        from hearthdelve.world import tile
        st = self._in_the_fen(tile.MARSH)
        self._run(st, 0.99)
        self.assertNotIn("sick", st.player.status)

    def test_dry_ground_is_safe(self):
        from hearthdelve.world import tile
        st = self._in_the_fen(tile.GRASS)
        self._run(st, 0.0)
        self.assertNotIn("sick", st.player.status)

    def test_a_warding_tea_still_wards(self):
        from hearthdelve.game import skills
        from hearthdelve.world import tile
        st = self._in_the_fen(tile.MARSH)
        with mock.patch.object(skills, "active_buff", return_value="warded"):
            self._run(st, 0.0)
        self.assertNotIn("sick", st.player.status)


if __name__ == "__main__":
    unittest.main()
