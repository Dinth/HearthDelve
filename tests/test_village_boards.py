"""Every village has a notice board you can reach."""
from __future__ import annotations

import collections
import unittest

import numpy as np

from hearthdelve.world import tile, worldgen
from hearthdelve.world.gamemap import _WALKABLE

# 2: the river runs through Saltmere's square and no corner took cobble.
# 42: Cinderhope's chapel backs onto rock. 1337: the world every old save has.
SEEDS = (2, 42, 1337)
_WORLDS: dict = {}


def _world(seed):
    if seed not in _WORLDS:
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
        _WORLDS[seed] = (gm, seen)
    return _WORLDS[seed]


def _beside(seen, x, y) -> bool:
    return any(seen[x + dx, y + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1))


class TestEveryVillageHasANoticeBoard(unittest.TestCase):
    """With no board a village pins no favours and its restoration projects
    can never be funded — they're paid in at the board — which made the
    "every project" goal unwinnable in that world."""

    def test_one_reachable_board_on_each_square(self):
        from hearthdelve.data import content
        hosts = {p.village for p in content.PROJECTS.values()}
        for seed in SEEDS:
            gm, seen = _world(seed)
            boards = [(int(x), int(y)) for x, y in np.argwhere(gm.tiles == tile.NOTICE_BOARD)]
            for name in hosts:
                vx, vy = gm.village_centers[name]
                near = [b for b in boards if max(abs(b[0] - vx), abs(b[1] - vy)) <= 22]
                with self.subTest(seed=seed, village=name):
                    self.assertEqual(len(near), 1)
                    self.assertTrue(_beside(seen, *near[0]))

if __name__ == "__main__":
    unittest.main()
