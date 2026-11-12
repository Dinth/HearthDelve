"""A run or a rest stops for what you can see, not what is behind the rock."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestOnlySeenCreaturesStopARun(unittest.TestCase):
    """Runs and rests stopped for any monster within notice range, lit or
    not — naming a lurker through six tiles of solid wall."""

    def _below(self):
        from hearthdelve.entities.monster import Mob
        from hearthdelve.game import delve
        st = fresh_state(23)
        pos, kind = sorted(st.surface.dungeon_kind.items())[0]
        st.player.x, st.player.y = pos
        delve.enter(st, kind)
        w, p = st.world, st.player
        w.monsters[:] = []
        w.npcs[:] = []
        dx = 2 if w.in_bounds(p.x + 2, p.y) else -2
        m = Mob("Lurker", "l", (200, 200, 200), 20, 20, 2, "chase", p.x + dx, p.y)
        w.monsters.append(m)
        return st, m

    def test_a_monster_out_of_sight_is_not_named(self):
        from hearthdelve.game import commands
        st, m = self._below()
        st.world.visible[m.x, m.y] = False
        self.assertEqual(commands._notable_nearby(st, tiles=False), "")

    def test_one_in_sight_still_is(self):
        from hearthdelve.game import commands
        st, m = self._below()
        st.world.visible[m.x, m.y] = True
        self.assertEqual(commands._notable_nearby(st, tiles=False), "a lurker is nearby")

    def test_the_surface_has_no_dark_to_hide_in(self):
        from hearthdelve.entities.monster import Mob
        from hearthdelve.game import commands
        st = fresh_state(23)
        st.world.monsters[:] = []
        st.world.npcs[:] = []
        p = st.player
        st.world.monsters.append(Mob("Ash Wolf", "w", (200, 200, 200), 20, 20, 2, "chase",
                                     p.x + 2, p.y, kind="wildlife", hostile=True))
        self.assertEqual(commands._notable_nearby(st, tiles=False), "a ash wolf is nearby")


if __name__ == "__main__":
    unittest.main()
