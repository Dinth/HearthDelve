"""A dungeon floor's outer ring is its edge: always solid wall.

Ore-vein growth used to pick neighbouring cells with no bounds check. It was
only kept off the edge because ordinary rooms never reach it; floor beside the
border (the Underriver's banks did) let a vein grow into the ring, opening the
map edge when mined, and the next step indexed off the grid and crashed.
"""
from __future__ import annotations

import random
import unittest

import numpy as np


def _ring(shape) -> np.ndarray:
    ring = np.ones(shape, bool)
    ring[1:-1, 1:-1] = False
    return ring


class TestVeinsStayInside(unittest.TestCase):
    def test_a_vein_beside_open_floor_at_the_edge_never_enters_the_ring(self):
        from hearthdelve.world import dungeon, tile
        wall, floor = tile.DUNGEON_WALL, tile.DUNGEON_FLOOR
        w, h = 30, 20
        for seed in range(200):
            # Floor and wall alternate in the cells just inside every edge, the
            # way the Underriver's banks meet it: a vein can step onto one of
            # those walls, and from there (unbounded) into the ring itself.
            tiles = np.full((w, h), wall, dtype=np.uint8)
            for y in range(1, h - 1, 2):
                tiles[w - 2, y] = tiles[1, y] = floor
            for x in range(1, w - 1, 2):
                tiles[x, h - 2] = tiles[x, 1] = floor
            rng = random.Random(seed)
            starts = [(x, y) for x in range(1, w - 1) for y in range(1, h - 1)
                      if (x in (1, w - 2) or y in (1, h - 2)) and tiles[x, y] == wall]
            dungeon._grow_vein(tiles, rng.choice(starts), 40, rng)
            with self.subTest(seed=seed):
                self.assertTrue((tiles[_ring(tiles.shape)] == wall).all())
                self.assertGreater(int((tiles == tile.ORE_VEIN).sum()), 0)


class TestEveryFloorKeepsItsEdge(unittest.TestCase):
    def test_the_outer_ring_is_wall_on_every_kind_and_the_underriver(self):
        from hearthdelve.world import dungeon
        floors = [(f"{kind} d{depth} s{seed}", dungeon.generate(seed * 7919 + depth, kind, depth))
                  for kind in ("mine", "grotto", "cavern", "sea cave", "barrow", "tomb",
                               "crypt", "dwarfhold")
                  for depth in (1, 6, 12) for seed in range(4)]
        floors += [(f"underriver {seed}", dungeon.generate_underriver(seed)) for seed in range(40)]
        for name, gm in floors:
            with self.subTest(floor=name):
                self.assertTrue((gm.tiles[_ring(gm.tiles.shape)] == gm.wall_tile).all())


if __name__ == "__main__":
    unittest.main()
