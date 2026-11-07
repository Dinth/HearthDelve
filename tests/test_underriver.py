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


class TestTheRiverRespectsTheFloor(unittest.TestCase):
    """The river used to be cut across a finished floor: it tunnelled over the
    up-stairs in every world (fainting was the only way out), drowned the down-
    stairs in some, and left monsters, chests and traps in the water. It is now
    carved before anything is placed."""

    def _reach(self, gm, start):
        from hearthdelve.world import tile
        seen, stack = {start}, [start]
        while stack:
            x, y = stack.pop()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (0 <= nx < gm.width and 0 <= ny < gm.height and (nx, ny) not in seen
                        and tile.TILES[gm.tiles[nx, ny]].walkable):
                    seen.add((nx, ny))
                    stack.append((nx, ny))
        return seen

    def test_both_stairs_stand_and_join_up_in_every_world(self):
        from hearthdelve.world import dungeon, tile
        for seed in range(80):
            gm = dungeon.generate_underriver(seed)
            with self.subTest(seed=seed):
                self.assertEqual(gm.tiles[gm.stairs_up], tile.STAIRS_UP)
                self.assertEqual(gm.tiles[gm.stairs_down], tile.DUNGEON_DOWN)
                self.assertEqual(gm.spawn, gm.stairs_up)
                reach = self._reach(gm, gm.stairs_up)
                self.assertIn(gm.stairs_down, reach)
                self.assertTrue({r.center for r in gm.rooms} <= reach)

    def test_nothing_is_left_standing_in_the_water(self):
        from hearthdelve.world import dungeon, tile
        for seed in range(80):
            gm = dungeon.generate_underriver(seed)
            with self.subTest(seed=seed):
                for m in gm.monsters:
                    self.assertTrue(tile.TILES[gm.tiles[m.x, m.y]].walkable, m.name)
                for t in gm.hidden_traps:
                    self.assertEqual(gm.tiles[t], gm.floor_tile)
                # the banks wear the cavern's own floor, not a stripe of mine floor
                self.assertFalse((gm.tiles == tile.DUNGEON_FLOOR).any())
                self.assertGreater(int((gm.tiles == tile.RIVER).sum()), 40)
                self.assertGreaterEqual(int((gm.tiles == tile.BRIDGE).sum()), 2)

    def test_an_ordinary_floor_has_no_river(self):
        from hearthdelve.world import dungeon, tile
        gm = dungeon.generate(4242, "cavern", 8)
        self.assertFalse((gm.tiles == tile.RIVER).any())
        self.assertFalse((gm.tiles == tile.BRIDGE).any())


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
