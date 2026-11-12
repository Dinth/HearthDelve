"""Each new game draws a world seed of its own."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from tests.common import fresh_state


class TestANewLifeGetsItsOwnVale(unittest.TestCase):
    """Every new game was seed 1337: one map, one weather calendar, the same
    floors below, for every player and every `--new`."""

    def test_seeds_differ(self):
        from hearthdelve import main
        with mock.patch.dict(os.environ, {"HEARTHDELVE_SEED": ""}):
            seeds = {main.fresh_seed() for _ in range(40)}
        self.assertGreater(len(seeds), 30)
        self.assertTrue(all(1 <= s < 1_000_000 for s in seeds))

    def test_a_seed_can_be_asked_for(self):
        from hearthdelve import main
        with mock.patch.dict(os.environ, {"HEARTHDELVE_SEED": "4242"}):
            self.assertEqual(main.fresh_seed(), 4242)
        with mock.patch.dict(os.environ, {"HEARTHDELVE_SEED": "not a number"}):
            self.assertNotEqual(main.fresh_seed(), 0)

    def test_new_game_uses_it_and_remembers_it(self):
        from hearthdelve import main
        with mock.patch.object(main, "fresh_seed", return_value=77) as drawn:
            st = main.new_game()
        drawn.assert_called_once()
        self.assertEqual(st.seed, 77)
        self.assertTrue((st.surface.tiles == fresh_state(77).surface.tiles).all())


if __name__ == "__main__":
    unittest.main()
