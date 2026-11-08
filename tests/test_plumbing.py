"""The test plumbing itself: fresh_state hands out copies of one cached new game
per seed, and each must behave exactly like a newly generated one."""
from __future__ import annotations

import unittest

import numpy as np

from tests.common import fresh_state


class TestFreshStatesAreTrueCopies(unittest.TestCase):
    def test_two_states_share_nothing_mutable(self):
        from hearthdelve.entities import items
        a, b = fresh_state(2), fresh_state(2)
        b.player.inventory.add(items.WOOD, 7)
        b.surface.tiles[10, 10] = 0
        b.surface.npcs[0].friendship += 300
        self.assertEqual(a.player.inventory.count(items.WOOD), 0)
        self.assertNotEqual(a.surface.npcs[0].friendship, b.surface.npcs[0].friendship)
        self.assertIsNot(a.surface.tiles, b.surface.tiles)
        self.assertIs(a.world, a.surface)              # the copy keeps its own aliases

    def test_items_stay_the_game_s_own_objects(self):
        """Game code compares items by identity; a copy must not clone them."""
        from hearthdelve.entities import items
        st = fresh_state(2)
        for it, _q, _ql in st.player.inventory.slots:
            self.assertIs(it, items.BY_NAME[it.name])
        st.player.inventory.add(items.WOOD, 2)
        self.assertEqual(st.player.inventory.count(items.WOOD), 2)

    def test_a_copy_matches_a_newly_generated_game(self):
        from hearthdelve.main import new_game
        copy, made = fresh_state(4), new_game(4)
        self.assertTrue(np.array_equal(copy.surface.tiles, made.surface.tiles))
        self.assertEqual(sorted(copy.surface.dungeon_kind.items()),
                         sorted(made.surface.dungeon_kind.items()))
        self.assertEqual([(n.name, n.x, n.y) for n in copy.surface.npcs],
                         [(n.name, n.x, n.y) for n in made.surface.npcs])


if __name__ == "__main__":
    unittest.main()
