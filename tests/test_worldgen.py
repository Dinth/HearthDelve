"""Worldgen invariants: determinism, dungeon connectivity, entrances, NPCs."""
from __future__ import annotations

import unittest

import numpy as np

from tests.common import fresh_state, shared_state


class TestDeterminism(unittest.TestCase):
    def test_same_seed_same_world(self):
        a, b = fresh_state(7), fresh_state(7)
        self.assertTrue(np.array_equal(a.surface.tiles, b.surface.tiles))
        self.assertEqual([(n.name, n.x, n.y) for n in a.surface.npcs],
                         [(n.name, n.x, n.y) for n in b.surface.npcs])


class TestDungeons(unittest.TestCase):
    KINDS = ("mine", "grotto", "sea cave", "cavern", "barrow", "tomb", "crypt", "dwarfhold")

    @staticmethod
    def _reachable(gm):
        from hearthdelve.world import tile
        walk = np.array([t.walkable for t in tile.TILES])
        seen = {gm.stairs_up}
        stack = [gm.stairs_up]
        while stack:
            x, y = stack.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if (0 <= nx < gm.width and 0 <= ny < gm.height
                        and (nx, ny) not in seen and walk[gm.tiles[nx, ny]]):
                    seen.add((nx, ny))
                    stack.append((nx, ny))
        return seen

    def test_every_kind_stays_connected(self):
        from hearthdelve.world import dungeon
        for kind in self.KINDS:
            for depth in (1, 5, 8):
                for seed in (11, 222):
                    gm = dungeon.generate(seed, kind, depth)
                    self.assertIn(gm.stairs_down, self._reachable(gm),
                                  f"{kind} d{depth} seed {seed} disconnected")

    def test_hidden_traps_are_off_grid(self):
        from hearthdelve.world import dungeon, tile
        gm = dungeon.generate(5, "grotto", 6)
        self.assertGreater(len(gm.hidden_traps), 0)
        self.assertEqual(int((gm.tiles == tile.TRAP_HIDDEN).sum()), 0)
        for (x, y) in gm.hidden_traps:
            self.assertEqual(gm.tiles[x, y], gm.floor_tile)

    def test_kinds_have_distinct_palettes(self):
        from hearthdelve.world import dungeon
        floors = {k: dungeon.generate(3, k, 4).floor_tile for k in self.KINDS}
        # mine keeps the default; every themed kind differs from it
        self.assertGreaterEqual(len(set(floors.values())), 6)

    def test_rosters_never_empty(self):
        from hearthdelve.data import content
        for kind in self.KINDS:
            for depth in (1, 4, 7, 10):
                self.assertTrue(content.monsters_for(kind, depth),
                                f"empty roster: {kind} d{depth}")


class TestSurface(unittest.TestCase):
    def test_entrances_and_kinds(self):
        st = shared_state()
        kinds = sorted(st.surface.dungeon_kind.values())
        self.assertEqual(len(kinds), 8)
        for expected in ("mine", "grotto", "barrow", "crypt", "cavern", "sea cave"):
            self.assertIn(expected, kinds)

    def test_npcs_unique_named_and_housed(self):
        st = shared_state()
        names = [n.name for n in st.surface.npcs]
        self.assertEqual(len(names), len(set(names)), "duplicate NPC names")
        for newcomer in ("Perrin", "Lark", "Kesk", "Neri", "Tolly"):
            npc = next((n for n in st.surface.npcs if n.name == newcomer), None)
            self.assertIsNotNone(npc, f"{newcomer} missing")
            self.assertNotEqual((npc.x, npc.y), (0, 0), f"{newcomer} stranded")

    def test_herbs_are_a_scattered_find(self):
        st = shared_state()
        self.assertGreater(len(st.surface.herb_spots), 200)
        from hearthdelve.world import tile
        herb_ids = [tid for tid, t in enumerate(tile.TILES) if t.kind == "herb"]
        standing = int(np.isin(st.surface.tiles, herb_ids).sum())
        self.assertTrue(300 < standing < 3000, f"herb abundance off: {standing}")


class TestDungeonSitesSpareTheVillages(unittest.TestCase):
    """A mouth's clearing flattened everything within its radius: Cinderhope
    cottages, fences and fields (seed 23), Saltmere's piers and streets (seeds 1,
    7, 8, 555, 2024). It must go round anything built, without moving the
    mouths."""

    def test_the_clearing_never_overwrites_anything_built(self):
        from hearthdelve.world import tile, worldgen
        orig = worldgen._carve_dungeon_site
        spared = []

        def watched(gm, ex, ey, kind):
            R = worldgen._SITE_R
            built = {(x, y): int(gm.tiles[x, y])
                     for x in range(ex - R, ex + R + 1) for y in range(ey - R, ey + R + 1)
                     if gm.in_bounds(x, y) and int(gm.tiles[x, y]) in worldgen._BUILT}
            orig(gm, ex, ey, kind)
            for (x, y), t in built.items():
                self.assertEqual(int(gm.tiles[x, y]), t,
                                 f"{kind} at {(ex, ey)} overwrote {tile.TILES[t].name} at {(x, y)}")
            spared.append(len(built))
            self.assertEqual(gm.tiles[ex, ey], tile.DUNGEON_DOWN)

        worldgen._carve_dungeon_site = watched
        try:
            for seed in (23, 8):
                worldgen.generate(seed)
        finally:
            worldgen._carve_dungeon_site = orig
        self.assertGreater(sum(spared), 0, "these seeds do put a mouth beside a village")


def _another_machine(also_stable=False):
    """Stand in for a different CPU (or NumPy build): NumPy's default sort
    isn't stable, and Intel and Apple chips run different code for it, so
    tied values come out in a different order — here, last index first.
    `also_stable` reorders stable sorts too, for a world built by rules that
    have since changed."""
    from unittest import mock
    real = np.argsort

    def argsort(a, *args, kind=None, **kw):
        if kind == "stable" and not also_stable:
            return real(a, kind="stable")
        a = np.asarray(a)
        return np.lexsort((-np.arange(len(a)), a))
    return mock.patch.object(np, "argsort", argsort)


class TestTheSameSeedIsTheSameValeEverywhere(unittest.TestCase):
    """Where several tiles were the same distance from a mouth's anchor, the
    one chosen was left to NumPy's default sort, which orders ties
    differently on Intel and Apple chips: on CI (Linux, Intel) seed 7 put
    three of its eight mouths elsewhere than on a Mac. Loading a save
    regenerates the world from its seed, so a save could come back with its
    mouths re-picked under its saved ground."""

    SEED_7 = [((189, 711), "mine"), ((312, 136), "grotto"), ((462, 864), "cavern"),
              ((485, 881), "sea cave"), ((510, 68), "grotto"), ((578, 654), "mine"),
              ((812, 196), "barrow"), ((820, 190), "crypt")]

    def test_a_new_world_places_its_mouths_alike_on_every_machine(self):
        from hearthdelve.world import worldgen
        here = sorted(worldgen.generate(7).dungeon_kind.items())
        with _another_machine():
            there = sorted(worldgen.generate(7).dungeon_kind.items())
        self.assertEqual(here, self.SEED_7)
        self.assertEqual(there, here)

    def test_a_save_brings_its_own_mouths_back(self):
        from hearthdelve.engine import save
        st = fresh_state(7)
        save.save(st)
        with _another_machine(also_stable=True):
            again = save.load()
        self.assertEqual(sorted(again.surface.dungeon_kind.items()),
                         sorted(st.surface.dungeon_kind.items()))
        self.assertEqual(again.surface.dungeons, st.surface.dungeons)

    def test_an_older_save_is_rebuilt_as_it_was_made_and_then_records_them(self):
        import json
        from hearthdelve.engine import save
        from hearthdelve.world import tile, worldgen
        st = fresh_state(7)
        made = worldgen.generate(7, legacy_ties=True)      # as worlds were built before
        made.npcs = st.surface.npcs
        st.world = st.surface = made
        save.save(st)
        with open(save.default_path()) as f:
            raw = json.load(f)
        raw.pop("sites")                                   # an older save never recorded them
        with open(save.default_path(), "w") as f:
            json.dump(raw, f)
        again = save.load()
        self.assertEqual(sorted(again.surface.dungeon_kind.items()),
                         sorted(made.dungeon_kind.items()))
        for x, y in again.surface.dungeons:
            self.assertEqual(again.surface.tiles[x, y], tile.DUNGEON_DOWN)
        save.save(again)
        with open(save.default_path()) as f:
            self.assertEqual([tuple(s) for s in json.load(f)["sites"]],
                             [(x, y, made.dungeon_kind[(x, y)]) for x, y in made.dungeons])



if __name__ == "__main__":
    unittest.main()
