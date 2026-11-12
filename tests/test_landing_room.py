"""Arriving on a floor never leaves a monster on your own tile."""
from __future__ import annotations

import unittest
from unittest import mock

from tests.common import fresh_state


class TestAMonsterOnTheStairsIsShovedAside(unittest.TestCase):
    """A monster standing where the stairs (or the lift) set you down shared
    your tile: a bump needs a neighbour, so it could not be struck, and it
    only attacked at a distance of exactly one, so it never struck you."""

    def _down_onto(self):
        from hearthdelve.entities.monster import Mob
        from hearthdelve.game import delve
        st = fresh_state(24)
        st.player.x, st.player.y = st.surface.dungeons[0]
        delve.enter(st, st.surface.dungeon_kind[st.surface.dungeons[0]])
        build = delve.build_floor

        def with_a_squatter(state, kind, site, depth):
            gm = build(state, kind, site, depth)
            gm.monsters.append(Mob("Squatter", "S", (200, 200, 200), 30, 30, 2, "chase",
                                   *gm.stairs_up))
            return gm

        with mock.patch.object(delve, "build_floor", with_a_squatter):
            delve.descend(st)
        return st, next(m for m in st.world.monsters if m.name == "Squatter")

    def test_it_ends_up_beside_you_and_awake(self):
        st, m = self._down_onto()
        p = st.player
        self.assertEqual(max(abs(m.x - p.x), abs(m.y - p.y)), 1)
        self.assertTrue(st.world.walkable(m.x, m.y))
        self.assertTrue(m.awake)
        self.assertEqual(len([o for o in st.world.monsters if (o.x, o.y) == (m.x, m.y)]), 1)

    def test_one_on_your_tile_anyway_still_fights(self):
        from hearthdelve.game import combat
        st, m = self._down_onto()
        m.x, m.y = st.player.x, st.player.y              # however it got there
        with mock.patch.object(combat, "_attack_player") as blow:
            combat._step(st, m)
        blow.assert_called_once()


if __name__ == "__main__":
    unittest.main()
