"""Land ownership belongs to the Vale and to no other map."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestNobodyOwnsTheWestreach(unittest.TestCase):
    """The Vale's deeds were read at the same coordinates of whatever map you
    stood on: spots of the Westreach "belonged" to a villager a world away,
    so tilling there was refused and chopping there was theft."""

    def test_no_tile_of_the_westreach_has_an_owner(self):
        from hearthdelve.game import land
        from hearthdelve.world import westgen
        st = fresh_state(1337)
        owned = [pos for pos in land._village_owner(st.surface)
                 if pos[0] < 320 and pos[1] < 320] + [st.surface.spawn]
        st.claims.add((5, 5))
        st.west = westgen.generate(st.seed)
        st.world = st.west
        for x, y in owned + [(5, 5)]:
            self.assertIsNone(land.owner_at(st, x, y))
            self.assertFalse(land.owned_by_other(st, x, y))

    def test_the_vale_keeps_its_deeds(self):
        from hearthdelve.game import land
        st = fresh_state(1337)
        (x, y), who = next(iter(land._village_owner(st.surface).items()))
        self.assertEqual(land.owner_at(st, x, y), who)
        self.assertTrue(land.owned_by_other(st, x, y))
        self.assertEqual(land.owner_at(st, *st.surface.spawn), "player")

    def test_nor_does_anyone_own_a_dungeon_floor(self):
        from hearthdelve.game import delve, land
        st = fresh_state(1337)
        st.player.x, st.player.y = st.surface.dungeons[0]
        delve.enter(st, st.surface.dungeon_kind[st.surface.dungeons[0]])
        for x in range(0, st.world.width, 7):
            for y in range(0, st.world.height, 5):
                self.assertIsNone(land.owner_at(st, x, y))


if __name__ == "__main__":
    unittest.main()
