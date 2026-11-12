"""Every churchyard has a gate you can walk through."""
from __future__ import annotations

import unittest

import numpy as np

from hearthdelve.world import tile
from tests.test_village_boards import SEEDS, _beside, _world


class TestAChurchyardCanBeEntered(unittest.TestCase):
    """The lychgate was cut one cell inside the fence ring, so every
    churchyard in the Vale was fenced shut."""

    def test_every_grave_can_be_stood_beside(self):
        for seed in SEEDS:
            gm, seen = _world(seed)
            graves = [(int(x), int(y)) for x, y in np.argwhere(gm.tiles == tile.GRAVE)]
            with self.subTest(seed=seed):
                self.assertTrue(graves)
                self.assertEqual([g for g in graves if not _beside(seen, *g)], [])

if __name__ == "__main__":
    unittest.main()
