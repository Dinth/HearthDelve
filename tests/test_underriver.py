"""The Underriver: a persistent ore-river cavern below Khazgrim, panned by rod."""
from __future__ import annotations

import random
import unittest

import numpy as np

from tests.common import fresh_state


class TestUnderriverFloor(unittest.TestCase):
    def test_it_is_persistent_and_a_river(self):
        from hearthdelve.world import dungeon, tile, dwarftown
        gm = dungeon.generate_underriver(12345)
        self.assertTrue(gm.underriver)
        self.assertEqual(gm.depth, dwarftown.UNDERRIVER_DEPTH)
        water = int((gm.tiles == tile.RIVER).sum()) + int((gm.tiles == tile.WATER).sum())
        self.assertGreater(water, 20, "the cavern should have a real river")
        # world-seeded: the same river every visit, a different one per world
        self.assertTrue(np.array_equal(gm.tiles, dungeon.generate_underriver(12345).tiles))
        self.assertFalse(np.array_equal(gm.tiles, dungeon.generate_underriver(999).tiles))

    def test_it_sits_one_floor_below_the_town(self):
        from hearthdelve.world import dwarftown
        self.assertEqual(dwarftown.UNDERRIVER_DEPTH, dwarftown.TOWN_DEPTH + 1)


class TestPanning(unittest.TestCase):
    def _river_bank(self, gm):
        for x in range(gm.width):
            for y in range(gm.height):
                if gm.tile_at(x, y).kind == "water" and gm.walkable(x, y - 1):
                    return x, y
        return None

    def test_casting_pans_minerals_with_no_minigame(self):
        from hearthdelve.world import dungeon
        from hearthdelve.game import fishing
        st = fresh_state(50)
        gm = dungeon.generate_underriver(2024)
        gm.is_dungeon = True
        st.world = gm
        rx, ry = self._river_bank(gm)
        st.player.x, st.player.y = rx, ry - 1
        got = 0
        for s in range(40):
            random.seed(s)
            st.player.energy = 200
            before = sum(q for _, q, _ in st.player.inventory.slots)
            ctx = fishing.begin(st, rx, ry)
            self.assertIsNone(ctx, "panning must never open the reel minigame")
            if sum(q for _, q, _ in st.player.inventory.slots) > before:
                got += 1
        self.assertGreater(got, 15, "the river should yield often")
        # what it yielded is ore/gems, not fish
        kinds = {it.kind for it, _q, _ql in st.player.inventory.slots}
        self.assertFalse(kinds & {"fish"})

    def test_pan_table_is_ore_and_gems_weighted_to_the_common(self):
        from hearthdelve.data import content
        names = {it.name for it, _w in content.RIVER_PAN}
        self.assertIn("Copper Ore", names)
        self.assertIn("Diamond", names)
        # the humble ore outweighs the diamond
        weights = dict((it.name, w) for it, w in content.RIVER_PAN)
        self.assertGreater(weights["Copper Ore"], weights["Diamond"])


if __name__ == "__main__":
    unittest.main()
