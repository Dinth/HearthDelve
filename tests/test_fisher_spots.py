"""A fisher can reach the water they work."""
from __future__ import annotations

import collections
import unittest

import numpy as np

from hearthdelve.world import worldgen
from hearthdelve.world.gamemap import _WALKABLE


def _unreachable_workers(seed):
    gm = worldgen.generate(seed)
    walk = _WALKABLE[gm.tiles]
    seen = np.zeros_like(walk)
    seen[gm.spawn] = True
    todo = collections.deque([gm.spawn])
    while todo:
        x, y = todo.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = x + dx, y + dy
                if gm.in_bounds(nx, ny) and walk[nx, ny] and not seen[nx, ny]:
                    seen[nx, ny] = True
                    todo.append((nx, ny))
    return [n.name for n in gm.npcs if not seen[tuple(n.work)]]


class TestTheFishersCanGetToWork(unittest.TestCase):
    def test_old_pells_pond_is_not_walled_in_rock(self):
        """Seed 34: the hills' rock counted as clear ground, so the pond was
        carved into solid stone and Old Pell stood inside it to fish."""
        self.assertEqual(_unreachable_workers(34), [])

    def test_saltmeres_piers_reach_the_shore(self):
        """Seed 18: the river's mouth met a pier's foot, the planks stopped
        short of it, and three fishers worked a pier adrift."""
        self.assertEqual(_unreachable_workers(18), [])


if __name__ == "__main__":
    unittest.main()
