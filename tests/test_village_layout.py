"""Villages stand clear of the river — and an old world keeps its old ones."""
from __future__ import annotations

import collections
import json
import os
import tempfile
import unittest
from unittest import mock

from hearthdelve.world import tile, worldgen

_ROLE = {"innkeeper": "inn", "priest": "temple", "shopkeeper": "shop", "blacksmith": "smithy"}
_WORLDS: dict = {}


def _world(seed, legacy=False):
    key = (seed, legacy)
    if key not in _WORLDS:
        _WORLDS[key] = worldgen.generate(seed, legacy_villages=legacy)
    return _WORLDS[key]


def _river_in_clearing(gm, name) -> bool:
    vx, vy = gm.village_centers[name]
    R = 16 if name == "Saltmere" else 21
    return bool((gm.tiles[vx - R:vx + R + 1, vy - R:vy + R + 1] == tile.RIVER).any())


def _missing_role_buildings(gm) -> list:
    from hearthdelve.data import content
    have = collections.defaultdict(set)
    for b in gm.buildings:
        if b.get("village"):
            have[b["village"]].add(b["kind"])
    return [(name, _ROLE[r]) for name, npcs in content.village_npcs().items()
            if name in gm.village_centers
            for r in sorted({n.role for n in npcs} & set(_ROLE)) if _ROLE[r] not in have[name]]


class TestSaltmereStandsClearOfTheRiver(unittest.TestCase):
    """Saltmere sat at a fixed column while the river wandered to the sea:
    about one world in nine it came down through the village — the square
    under water, no room for the inn. Seeds 2 and 56 are two such worlds."""

    def test_the_old_siting_had_the_river_through_it(self):
        gm = _world(2, legacy=True)
        self.assertTrue(_river_in_clearing(gm, "Saltmere"))
        self.assertIn(("Saltmere", "inn"), _missing_role_buildings(gm))

    def test_the_new_siting_moves_along_the_coast(self):
        for seed in (2, 56):
            gm = _world(seed)
            vx, vy = gm.village_centers["Saltmere"]
            with self.subTest(seed=seed):
                self.assertNotEqual(vx, _world(seed, legacy=True).village_centers["Saltmere"][0])
                self.assertFalse(_river_in_clearing(gm, "Saltmere"))
                self.assertEqual(vy, int(gm.coast[vx]) - 10)       # still on the shore
                self.assertEqual(gm.village_layout, 2)

    def test_it_stays_put_where_the_river_keeps_away(self):
        self.assertEqual(_world(1337).village_centers, _world(1337, legacy=True).village_centers)


class TestEveryVillageKeepsItsTradeAndItsGround(unittest.TestCase):
    def test_no_river_through_any_square_and_no_keeper_without_a_roof(self):
        for seed in (2, 42, 56):                         # 42: Cinderhope had no smithy
            gm = _world(seed)
            with self.subTest(seed=seed):
                self.assertEqual(_missing_role_buildings(gm), [])
                self.assertEqual([n for n in ("Mossford", "Cinderhope", "Saltmere", "Fenwick")
                                  if _river_in_clearing(gm, n)], [])

    def test_the_river_keeps_to_the_middle_ground(self):
        for seed in (2, 42, 56):
            gm = _world(seed)
            xs = (gm.tiles == tile.RIVER).any(axis=1).nonzero()[0]
            mid = gm.width // 2
            with self.subTest(seed=seed):
                self.assertLessEqual(max(abs(int(xs.min()) - mid), abs(int(xs.max()) - mid)),
                                     worldgen._RIVER_ROAM + 8)


class TestAnOldWorldKeepsItsVillages(unittest.TestCase):
    """Loading rebuilds the world from its seed and lays the saved tiles on
    top: moving an old world's Saltmere would put its folk, doors and roads
    where the saved tiles have open shore."""

    def test_a_save_from_before_loads_its_old_saltmere_and_keeps_it(self):
        from hearthdelve import main
        from hearthdelve.engine import save
        real = worldgen.generate
        with mock.patch.object(worldgen, "generate",
                               lambda seed, **kw: real(seed, legacy_villages=True, **kw)):
            old = main.new_game(2)                       # as the old build made it
        where = old.surface.village_centers["Saltmere"]
        homes = [(n.name, tuple(n.home)) for n in old.surface.npcs]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(old, path)
            with open(path) as fh:
                data = json.load(fh)
            del data["village_layout"]                   # a save from before the field
            with open(path, "w") as fh:
                json.dump(data, fh)
            back = save.load(path)
            self.assertEqual(back.surface.village_layout, 1)
            self.assertEqual(back.surface.village_centers["Saltmere"], where)
            self.assertEqual([(n.name, tuple(n.home)) for n in back.surface.npcs], homes)
            self.assertTrue((back.surface.tiles == old.surface.tiles).all())
            save.save(back, path)                        # and it stays old on the next save
            self.assertEqual(save.load(path).surface.village_centers["Saltmere"], where)

    def test_a_new_world_s_save_keeps_its_new_saltmere(self):
        from hearthdelve import main
        from hearthdelve.engine import save
        st = main.new_game(2)
        where = st.surface.village_centers["Saltmere"]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            save.save(st, path)
            back = save.load(path)
            self.assertEqual(back.surface.village_layout, 2)
            self.assertEqual(back.surface.village_centers["Saltmere"], where)


if __name__ == "__main__":
    unittest.main()
