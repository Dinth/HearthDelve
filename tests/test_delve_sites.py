"""Each dungeon mouth leads to floors of its own.

Floors were seeded and cached by kind and depth alone, so the Vale's two mines
(hundreds of tiles apart) opened onto the very same floor 1: a chest looted
through one was already gone through the other, the same day.
"""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _mouths(st, kind):
    return sorted(pos for pos, k in st.surface.dungeon_kind.items() if k == kind)


def _enter_at(st, pos, kind):
    from hearthdelve.game import delve
    st.world = st.surface
    st.player.x, st.player.y = pos
    delve.enter(st, kind)
    return st.world


class TestEachMouthHasItsOwnFloors(unittest.TestCase):
    def setUp(self):
        self.st = fresh_state(1)

    def test_two_mines_open_onto_different_floors(self):
        import numpy as np
        from hearthdelve.game import delve
        a_pos, b_pos = _mouths(self.st, "mine")[:2]
        a = _enter_at(self.st, a_pos, "mine")
        delve.leave_to_surface(self.st)
        b = _enter_at(self.st, b_pos, "mine")
        self.assertIsNot(a, b)
        self.assertFalse(np.array_equal(a.tiles, b.tiles))
        delve.leave_to_surface(self.st)
        self.assertEqual((self.st.player.x, self.st.player.y), b_pos)   # out where you went in

    def test_looting_one_mouth_leaves_the_other_alone(self):
        from hearthdelve.game import delve
        a_pos, b_pos = _mouths(self.st, "grotto")[:2]
        a = _enter_at(self.st, a_pos, "grotto")
        slain = list(a.monsters)
        a.monsters.clear()                                   # clear floor 1 of mouth A
        delve.leave_to_surface(self.st)
        b = _enter_at(self.st, b_pos, "grotto")
        self.assertTrue(b.monsters, "the other grotto's floor wasn't touched")
        delve.leave_to_surface(self.st)
        again = _enter_at(self.st, a_pos, "grotto")
        self.assertIs(again, a)                              # same floor all day…
        self.assertEqual(again.monsters, [])                 # …still cleared
        self.assertTrue(slain)

    def test_the_floor_seed_is_stable_and_depends_on_the_mouth(self):
        from hearthdelve.game import delve
        st = self.st
        st.dungeon_kind = "mine"
        a_pos, b_pos = _mouths(st, "mine")[:2]
        st.return_pos, st.return_west = a_pos, False
        a1 = delve._floor_seed(st, 3)
        self.assertEqual(a1, delve._floor_seed(st, 3))
        st.return_pos = b_pos
        b_vale = delve._floor_seed(st, 3)
        self.assertNotEqual(a1, b_vale)
        st.return_west = True                     # the same tile on the Westreach is elsewhere
        self.assertNotEqual(delve._floor_seed(st, 3), b_vale)


if __name__ == "__main__":
    unittest.main()
