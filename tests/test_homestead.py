"""Where worldgen sites the farm. It moved the farm east past the river's
FARTHEST crossing in the homestead's rows, anywhere on the map: in 24 of 40
worlds the farm landed over 30 tiles from its clearing, often out in the
north-east fen among bog pools (seed 23's by 199 tiles)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock


_FEN = ("water", "marsh", "moor", "reeds", "fog_grass")


class TestTheFarmStaysInItsClearing(unittest.TestCase):
    def test_it_sits_by_the_centre_on_open_ground(self):
        from hearthdelve.engine import constants as C
        from hearthdelve.world import tile, worldgen
        cx, _cy = C.WORLD_CENTER
        for seed in (4, 8, 23):                           # three the old siting sent far off
            gm = worldgen.generate(seed)
            hx, hy = gm.bed[0] - 1, gm.bed[1] - 1
            with self.subTest(seed=seed):
                self.assertLessEqual(hx - (cx + 2), 50)
                around = [tile.TILES[gm.tiles[x, y]].name
                          for x in range(hx - 4, hx + 12) for y in range(hy - 3, hy + 16)]
                self.assertFalse([n for n in around if n in _FEN])
                self.assertEqual(gm.home_layout, 2)

    def test_no_river_runs_through_the_farm(self):
        from hearthdelve.world import tile, worldgen
        gm = worldgen.generate(8)                         # a world whose river does cross it
        hx, hy = gm.bed[0] - 1, gm.bed[1] - 1
        self.assertFalse([1 for x in range(hx - 1, hx + 8) for y in range(hy, hy + 13)
                          if gm.tiles[x, y] == tile.RIVER])


class TestAnOldWorldKeepsItsFarm(unittest.TestCase):
    """Loading rebuilds the world from its seed, then lays the saved tiles on
    top: re-siting an old world's farm would put its bed, bin and door where
    the saved tiles have open fen."""

    def test_the_legacy_siting_is_unchanged(self):
        from hearthdelve.world import worldgen
        gm = worldgen.generate(23, legacy_home=True)
        self.assertEqual((gm.bed, gm.home_layout), ((714, 506), 1))

    def test_a_save_from_before_loads_its_old_farm_and_keeps_it(self):
        from hearthdelve import main
        from hearthdelve.engine import save
        from hearthdelve.world import worldgen
        real = worldgen.generate
        with mock.patch.object(worldgen, "generate",
                               lambda seed, **kw: real(seed, legacy_home=True, **kw)):
            old = main.new_game(23)                      # as the old build made it
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(old, path)
            with open(path) as fh:
                data = json.load(fh)
            del data["home_layout"]                      # a save from before the field
            with open(path, "w") as fh:
                json.dump(data, fh)
            back = save.load(path)
            self.assertEqual(back.surface.bed, (714, 506))
            self.assertEqual(back.surface.home_layout, 1)
            save.save(back, path)                        # and it stays old on the next save
            self.assertEqual(save.load(path).surface.bed, (714, 506))

    def test_a_new_world_s_save_keeps_its_new_farm(self):
        from hearthdelve.engine import save
        from tests.common import fresh_state
        st = fresh_state(23)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(st, path)
            back = save.load(path)
        self.assertEqual(back.surface.bed, st.surface.bed)
        self.assertNotEqual(back.surface.bed, (714, 506))


if __name__ == "__main__":
    unittest.main()
