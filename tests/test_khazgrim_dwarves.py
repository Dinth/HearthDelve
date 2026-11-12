"""You cannot walk onto a dwarf in Khazgrim."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestADwarfHoldsTheirGround(unittest.TestCase):
    """Khazgrim is a dungeon floor, and villagers were only looked for above
    ground: you could step onto Thrunn at his forge and stand in him."""

    def _beside_a_dwarf(self):
        from hearthdelve.game import commands
        st = fresh_state(22)
        commands._cheat_go(st, "west:khazgrim")
        w, p = st.world, st.player
        self.assertTrue(w.is_dungeon and w.npcs)
        for n in w.npcs:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                x, y = n.x + dx, n.y + dy
                if w.walkable(x, y) and not any((o.x, o.y) == (x, y) for o in w.npcs):
                    p.x, p.y = x, y
                    return st, n, (-dx, -dy)
        self.fail("no dwarf with a free tile beside them")

    def test_a_step_into_one_is_a_greeting(self):
        from hearthdelve.game import commands
        st, dwarf, (dx, dy) = self._beside_a_dwarf()
        here = (st.player.x, st.player.y)
        commands.try_move(st, dx, dy)
        self.assertEqual((st.player.x, st.player.y), here)
        self.assertIn(dwarf.name, st.log.messages[-1][0])

    def test_a_run_stops_short_of_one(self):
        from hearthdelve.game import commands
        st, dwarf, _d = self._beside_a_dwarf()
        self.assertTrue(commands._entity_at(st, dwarf.x, dwarf.y))


if __name__ == "__main__":
    unittest.main()
