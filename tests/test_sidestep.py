"""A mover in line with its quarry steps round a single obstacle."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


def _arena(st, block=None):
    """Open grass 9 wide and 5 deep east of the player, one tile optionally
    blocked two steps out on the player's own row."""
    from hearthdelve.world import tile
    p = st.player
    w = st.world
    for dx in range(-1, 9):
        for dy in range(-2, 3):
            w.tiles[p.x + dx, p.y + dy] = tile.GRASS
            w.crops.pop((p.x + dx, p.y + dy), None)
            w.machines.pop((p.x + dx, p.y + dy), None)
            w.trees.pop((p.x + dx, p.y + dy), None)
    w.monsters[:] = []
    w.npcs[:] = [n for n in w.npcs if abs(n.x - p.x) > 12 or abs(n.y - p.y) > 12]
    w.animals[:] = []
    if block is not None:
        w.tiles[p.x + 2, p.y] = block


def _mob(st, dx, dy=0, **kw):
    from hearthdelve.entities.monster import Mob
    p = st.player
    m = Mob("Stalker", "S", (200, 200, 200), 20, 20, 2, "chase", p.x + dx, p.y + dy, **kw)
    st.world.monsters.append(m)
    return m


class TestAChaserGetsRoundAPillar(unittest.TestCase):
    """In line with the player a chaser's three steps were all the same step,
    so one rock, brazier or packmate between them held it there for good."""

    def test_it_reaches_you_past_a_rock(self):
        from hearthdelve.game import combat
        from hearthdelve.world import tile
        for _ in range(20):                              # either side, whichever the coin says
            st = fresh_state(11)
            _arena(st, block=tile.ROCK)
            m = _mob(st, 4)
            for _step in range(6):
                if combat._dist(m, st.player) == 1:
                    break
                self.assertTrue(combat._move_toward(st, m))
            self.assertEqual(combat._dist(m, st.player), 1)

    def test_it_gets_round_a_packmate(self):
        from hearthdelve.game import combat
        st = fresh_state(11)
        _arena(st)
        front = _mob(st, 1)                              # already at your throat
        behind = _mob(st, 2)
        self.assertTrue(combat._move_toward(st, behind))
        self.assertEqual(combat._dist(behind, st.player), 1)
        self.assertNotEqual((behind.x, behind.y), (front.x, front.y))

    def test_it_never_paces_sideways_or_back(self):
        from hearthdelve.game import combat
        self.assertEqual(combat._sidesteps(1, 1), ())    # a diagonal has its own ways round
        self.assertEqual(combat._sidesteps(0, 0), ())
        for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for ax, ay in combat._sidesteps(sx, sy):
                self.assertEqual((ax if sx else ay), (sx or sy))   # always forward

    def test_a_walled_corridor_still_stops_it(self):
        from hearthdelve.game import combat
        from hearthdelve.world import tile
        st = fresh_state(11)
        _arena(st, block=tile.ROCK)
        p = st.player
        for dy in (-1, 1):
            st.world.tiles[p.x + 2, p.y + dy] = tile.ROCK
        m = _mob(st, 3)
        self.assertFalse(combat._move_toward(st, m))
        self.assertEqual((m.x, m.y), (p.x + 3, p.y))

    def test_wildlife_does_the_same(self):
        from hearthdelve.game import wildlife
        from hearthdelve.world import tile
        st = fresh_state(11)
        _arena(st, block=tile.ROCK)
        p = st.player
        m = _mob(st, 4, kind="wildlife", hostile=True)
        for _step in range(6):
            if max(abs(m.x - p.x), abs(m.y - p.y)) == 1:
                break
            self.assertTrue(wildlife._toward(st, m, p.x, p.y))
        self.assertEqual(max(abs(m.x - p.x), abs(m.y - p.y)), 1)


if __name__ == "__main__":
    unittest.main()
