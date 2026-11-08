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


def _within_reach(gm) -> set:
    """Every tile a player standing on the up-stairs can get to: walking in
    eight directions, and opening chests or digging rock and veins on the
    way (all ordinary work — only walls, water and lava truly bar the way)."""
    from hearthdelve.world import tile
    passable = [t.walkable or t.name in ("chest", "rock", "ore_vein", "gem_vein", "ruins_wall",
                                         "sulphur_deposit", "nitre_deposit")
                for t in tile.TILES]
    w, h = gm.tiles.shape
    start = tuple(gm.stairs_up)
    seen, stack = {start}, [start]
    while stack:
        x, y = stack.pop()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if 0 <= n[0] < w and 0 <= n[1] < h and n not in seen and passable[gm.tiles[n]]:
                    seen.add(n)
                    stack.append(n)
    return seen


class TestNothingIsSealedAwayByDecor(unittest.TestCase):
    """Blocking décor (a mine's pit-props, a cave's stalagmites, a crypt's
    pillars) was only checked against the stairs and the room centres. A
    pit-prop across a chamber's narrow end could seal off a sliver of floor,
    and the monsters placed afterwards could land in it — beyond reach, and
    unable to come out — on about one mine floor in seven hundred."""

    # Floors where a monster was sealed behind a pit-prop.
    SEALED = ((190066, "mine", 10), (316763, "mine", 3), (324680, "mine", 1),
              (411802, "mine", 14))

    def _assert_all_within_reach(self, seed, kind, depth):
        from hearthdelve.world import dungeon
        gm = dungeon.generate(seed, kind, depth)
        reach = _within_reach(gm)
        stranded = [(m.name, (m.x, m.y)) for m in gm.monsters if (m.x, m.y) not in reach]
        self.assertEqual(stranded, [], (seed, kind, depth))

    def test_the_floors_that_sealed_a_monster_away(self):
        for seed, kind, depth in self.SEALED:
            with self.subTest(seed=seed):
                self._assert_all_within_reach(seed, kind, depth)

    def test_a_sweep_of_every_kind_with_blocking_decor(self):
        for kind in ("mine", "grotto", "sea cave", "cavern", "crypt", "tomb", "dwarfhold"):
            for seed in range(12):
                for depth in (1, 6, 10):
                    with self.subTest(kind=kind, seed=seed, depth=depth):
                        self._assert_all_within_reach(seed * 7919 + depth, kind, depth)


if __name__ == "__main__":
    unittest.main()
