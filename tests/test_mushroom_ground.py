"""A picked mushroom leaves the ground it grew from."""
from __future__ import annotations

import unittest

from tests.common import fresh_state


class TestTheGroundStaysWhatItWas(unittest.TestCase):
    """Every pick left plain grass, though most mushroom spots are fen
    grass, moor or meadow: a season's foraging dotted the fen with lawn."""

    def test_a_fen_mushroom_leaves_fen(self):
        from hearthdelve.game import commands, land
        from hearthdelve.world import tile
        st = fresh_state(23)
        w, p = st.world, st.player
        for x, y, species, base in w.mushroom_spots:
            if base != tile.GRASS and w.walkable(x - 1, y) \
                    and not land.owned_by_other(st, x, y):
                break
        else:
            self.fail("no mushroom spot off plain grass")
        w.tiles[x, y] = species
        p.x, p.y, p.facing = x - 1, y, (1, 0)
        commands.do_grab(st)
        self.assertEqual(w.tiles[x, y], base)

    def test_one_planted_by_hand_still_leaves_grass(self):
        from hearthdelve.game import commands, land
        from hearthdelve.world import tile
        st = fresh_state(23)
        w, p = st.world, st.player
        spots = {(x, y) for x, y, _s, _b in w.mushroom_spots}
        species = w.mushroom_spots[0][2]
        x, y = p.x + 1, p.y
        self.assertNotIn((x, y), spots)
        w.tiles[x, y] = species
        p.facing = (1, 0)
        if not land.owned_by_other(st, x, y):
            commands.do_grab(st)
            self.assertEqual(w.tiles[x, y], tile.GRASS)


if __name__ == "__main__":
    unittest.main()
