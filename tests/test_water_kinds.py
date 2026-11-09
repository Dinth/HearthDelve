"""Which water you're standing over decides what you pull out of it.

The map stores only RIVER and WATER, so the sea, the fen's bog pools and a
village pond all share one tile id. `fishing.water_kind` reads the world instead
of the tile — the coastline for salt, the surrounding ground for peat — so no
new save state is needed. Before this, everything named "water" fished as open
sea: tuna in a marsh puddle, and Saltmere's lighthouse lighting it.
"""
from __future__ import annotations

import unittest

import numpy as np

from tests.common import fresh_state, shared_state


def _first(pred, gm, limit=400_000):
    """The first (x, y) water tile satisfying pred, scanning the whole map."""
    for x, y in np.argwhere(np.isin(gm.tiles, (_T().WATER, _T().RIVER)))[:limit]:
        if pred(int(x), int(y)):
            return int(x), int(y)
    return None


def _T():
    from hearthdelve.world import tile
    return tile


class TestWaterClassification(unittest.TestCase):
    def setUp(self):
        self.st = shared_state(1337)          # read-only: we never mutate the map
        self.gm = self.st.surface

    def test_the_river_is_the_river(self):
        from hearthdelve.game import fishing
        tile = _T()
        spot = _first(lambda x, y: self.gm.tiles[x, y] == tile.RIVER, self.gm)
        self.assertIsNotNone(spot)
        self.assertEqual(fishing.water_kind(self.st, *spot), "river")

    def test_below_the_coastline_is_sea(self):
        from hearthdelve.game import fishing
        tile = _T()
        coast = self.gm.coast
        spot = _first(lambda x, y: self.gm.tiles[x, y] == tile.WATER
                      and y >= int(coast[x]) + 3, self.gm)
        self.assertIsNotNone(spot)
        self.assertEqual(fishing.water_kind(self.st, *spot), "sea")

    def test_the_fens_pools_are_marsh_not_sea(self):
        """The bug, precisely: these are inland standing water."""
        from hearthdelve.game import fishing
        tile = _T()
        coast = self.gm.coast
        marshy = np.isin(self.gm.tiles, fishing._MARSHY)
        spot = _first(lambda x, y: self.gm.tiles[x, y] == tile.WATER
                      and y < int(coast[x])
                      and marshy[max(0, x - 3):x + 4, max(0, y - 3):y + 4].sum() >= 10,
                      self.gm)
        self.assertIsNotNone(spot, "the NE fen should have bog pools")
        self.assertEqual(fishing.water_kind(self.st, *spot), "marsh")

    def test_the_whole_map_partitions_sensibly(self):
        """Sanity over every water tile at once: the sea dominates, the fen holds
        thousands of pools, and a handful of clear pools read as ponds."""
        from hearthdelve.game import fishing
        tile = _T()
        coast, counts = self.gm.coast, {}
        marshy = np.isin(self.gm.tiles, fishing._MARSHY).astype(np.int32)
        cs = marshy.cumsum(0).cumsum(1)

        def window(x, y):                     # marshy tiles in the radius-3 box
            x0, y0 = max(x - 3, 0), max(y - 3, 0)
            x1, y1 = min(x + 3, self.gm.width - 1), min(y + 3, self.gm.height - 1)
            t = cs[x1, y1]
            if x0:
                t -= cs[x0 - 1, y1]
            if y0:
                t -= cs[x1, y0 - 1]
            if x0 and y0:
                t += cs[x0 - 1, y0 - 1]
            return int(t)

        for x, y in np.argwhere(self.gm.tiles == tile.WATER):
            x, y = int(x), int(y)
            k = ("sea" if y >= int(coast[x])
                 else "marsh" if window(x, y) >= fishing._MARSH_MIN else "lake")
            counts[k] = counts.get(k, 0) + 1
        self.assertGreater(counts.get("sea", 0), 100_000, "the southern sea")
        self.assertGreater(counts.get("marsh", 0), 10_000, "the NE fen's pools")
        self.assertGreater(counts.get("lake", 0), 0, "the village ponds")
        self.assertLess(counts["lake"], counts["marsh"],
                        "ponds are rare next to a whole fen")


class TestCastingPullsTheRightTable(unittest.TestCase):
    def _cast_many(self, st, x, y, casts=140):
        """Cast repeatedly at (x, y) and collect what comes up."""
        import random
        from hearthdelve.game import fishing
        st.player.x, st.player.y = x, y - 1
        got = set()
        for s in range(casts):
            random.seed(s)
            st.player.energy = st.player.max_energy
            st.clock = 0
            before = {e[0] for e in st.player.inventory.slots}
            ctx = fishing.begin(st, x, y)
            if ctx is not None and ctx["bite"]:       # a bite — land it outright
                fishing.resolve(st, ctx, caught=True)
            got |= {e[0] for e in st.player.inventory.slots} - before
        return {it.name for it in got if it.kind == "fish"}

    def test_a_fen_pool_yields_fen_fish_and_never_a_tuna(self):
        from hearthdelve.data import content
        from hearthdelve.game import fishing
        import numpy as np
        st = fresh_state(1337)
        gm, tile = st.surface, _T()
        marshy = np.isin(gm.tiles, fishing._MARSHY)
        spot = None
        for x, y in np.argwhere(gm.tiles == tile.WATER):
            x, y = int(x), int(y)
            if y >= int(gm.coast[x]) or not gm.walkable(x, y - 1):
                continue
            if marshy[max(0, x - 3):x + 4, max(0, y - 3):y + 4].sum() >= 10:
                spot = (x, y)
                break
        self.assertIsNotNone(spot, "need a fen pool with a bank to stand on")
        self.assertEqual(fishing.water_kind(st, *spot), "marsh")
        caught = self._cast_many(st, *spot)
        self.assertTrue(caught, "the fen should give up something")
        marsh_names = {it.name for it, _w in content.MARSH_FISH}
        sea_names = {it.name for it, _w in content.SEA_FISH}
        self.assertTrue(caught <= marsh_names, f"non-fen catch: {caught - marsh_names}")
        self.assertFalse(caught & sea_names, "no sea fish in a bog pool")


class TestTheNewCatchesHaveSomewhereToGo(unittest.TestCase):
    def test_the_crayfish_is_a_fish_for_every_system_that_matters(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        c = items.CRAYFISH
        self.assertEqual(c.family, "fish", "so any-fish dishes and gift tastes take it")
        self.assertIn(c, content.FISH_CURED, "the smoker should cure it")
        self.assertIn(c.name, {it.name for it in content.COLLECTION["Angler's Cabinet"]})
        # it invades both the fen and the ponds — that's the whole joke
        self.assertIn(c, [it for it, _w in content.MARSH_FISH])
        self.assertIn(c, [it for it, _w in content.LAKE_FISH])

    def test_every_new_catch_cooks_cures_and_can_be_asked_for(self):
        from hearthdelve.data import content
        from hearthdelve.game import requests
        st = fresh_state(11)
        pool = {p.name for p in requests._fish_pool(st)}
        for it, _w in content.MARSH_FISH + content.LAKE_FISH:
            self.assertIn(it.name, pool, f"{it.name} can never be requested")
            sashimi = next(r for r in content.RECIPES if r.name == "Sashimi")
            variant = content.cooked_dish(sashimi, it)
            self.assertGreater(variant.value, 0, f"{it.name} makes no dish")

    def test_dish_and_cured_value_track_the_catch(self):
        """A lamprey is worth cooking; a roach is a snack. Rarity has to pay."""
        from hearthdelve.data import content
        from hearthdelve.entities import items
        sashimi = next(r for r in content.RECIPES if r.name == "Sashimi")
        self.assertLess(content.cooked_dish(sashimi, items.ROACH).value,
                        content.cooked_dish(sashimi, items.LAMPREY).value)
        self.assertLess(content.FISH_CURED[items.TENCH].value,
                        content.FISH_CURED[items.MIRROR_CARP].value)

    def test_the_waters_pay_in_the_order_you_earn_them(self):
        """Expected value per cast: the safe home pond least, the deep dark most."""
        from hearthdelve.data import content

        def ev(table):
            tot = sum(w for _it, w in table)
            return sum(it.value * w for it, w in table) / tot

        river = ev(content.fish_in_season("Spring"))
        lake, marsh = ev(content.LAKE_FISH), ev(content.MARSH_FISH)
        sea, cave = ev(content.SEA_FISH), ev(content.CAVE_FISH)
        self.assertLess(river, lake, "the doorstep river is the trickle")
        self.assertLess(lake, marsh, "a trek to the fen should beat a village pond")
        self.assertLess(marsh, cave, "the dark pays best of all")
        self.assertLess(lake, sea)


if __name__ == "__main__":
    unittest.main()
