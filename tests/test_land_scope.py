"""Land claims are Vale ground, and only Vale ground.

``state.claims`` holds bare ``(x, y)`` tuples with no map identity, while
``land.claim`` resolves bounds and ownership against ``state.surface``. Both
callers, though, act on ``state.world`` — which can be the Westreach. So fencing
or tilling at (100, 100) out west added (100, 100) to the *Vale's* claim set, and
the weekly bailiff charged 2g on ground the player had never stood on, with a
notice they could not reconcile.

``_place_machine`` did guard the Westreach, but the ``kind == "fence"`` branch
returns above that check, so the guard never applied to fences.
"""
from __future__ import annotations

import unittest

from tests.common import fresh_state

from hearthdelve.game import crafting, land
from hearthdelve.world import westgen


def _go_west(st):
    st.west = westgen.generate(st.seed)
    st.world = st.west
    st.player.x, st.player.y = 100, 100
    st.player.facing = (1, 0)
    return st


class LandScopeTest(unittest.TestCase):
    def test_claiming_works_on_the_vale(self):
        st = fresh_state(77)
        self.assertEqual(land.claim(st, [(400, 400), (401, 400)]), 2)
        self.assertIn((400, 400), st.claims)

    def test_the_westreach_cannot_be_claimed(self):
        st = _go_west(fresh_state(77))
        before = set(st.claims)
        self.assertEqual(land.claim(st, [(100, 100), (101, 100)]), 0)
        self.assertEqual(set(st.claims), before,
                         "a Westreach coordinate leaked into the Vale's claim set")

    def test_fencing_the_westreach_is_refused_with_a_reason(self):
        st = _go_west(fresh_state(77))
        before = set(st.claims)
        self.assertFalse(crafting._place_fence(st))
        self.assertEqual(set(st.claims), before)

    def test_tilling_off_map_claims_nothing(self):
        """The hoe path calls note_claim directly; the choke point must hold."""
        st = _go_west(fresh_state(77))
        before = set(st.claims)
        land.note_claim(st, [(100, 100)])
        self.assertEqual(set(st.claims), before)

    def test_the_weekly_tax_only_ever_bills_claimed_vale_tiles(self):
        from hearthdelve.world import tile
        st = fresh_state(77)
        st.surface.tiles[400, 400] = st.surface.tiles[401, 400] = tile.TILLED   # worked ground
        land.claim(st, [(400, 400), (401, 400)])
        _go_west(st)
        land.claim(st, [(100, 100)])            # must not add anything
        self.assertEqual(len(st.claims), 2)
        st.world = st.surface
        st.last_tax_day = st.day - land.TAX_INTERVAL
        st.tax_owed = 0
        land.weekly_tax(st)
        self.assertEqual(st.tax_owed, 2 * land.TAX_PER_TILE,
                         "the bill counted tiles the player never claimed")



class ClaimsAreGivenBack(unittest.TestCase):
    """Nothing ever released a claimed tile: one L-shaped fence put its whole
    bounding box on the weekly tax roll for good, and pulling the fence up,
    or letting tilled soil go back to grass, changed nothing. Ground you no
    longer work is now struck off at the next assessment."""

    def _fenced(self):
        from hearthdelve.world import tile
        st = fresh_state(77)
        x0, y0 = 400, 400
        run = [(x0 + i, y0) for i in range(6)] + [(x0, y0 + i) for i in range(1, 6)]   # an L
        for x in range(x0, x0 + 6):
            for y in range(y0, y0 + 6):
                st.surface.tiles[x, y] = tile.GRASS
        for xy in run:
            st.surface.tiles[xy] = tile.FENCE
        land.claim(st, run)
        land.claim(st, land.enclosed_tiles(st, run[0]))
        self.assertEqual(len(st.claims), 36)
        return st, run

    def _assess(self, st):
        st.last_tax_day = st.day - land.TAX_INTERVAL
        st.tax_owed = 0
        land.weekly_tax(st)

    def test_a_standing_fence_keeps_its_plot(self):
        st, _run = self._fenced()
        self._assess(st)
        self.assertEqual(len(st.claims), 36)
        self.assertEqual(st.tax_owed, 36 * land.TAX_PER_TILE)

    def test_pulling_the_fence_up_gives_the_plot_back(self):
        from hearthdelve.world import tile
        st, run = self._fenced()
        for xy in run:
            st.surface.tiles[xy] = tile.GRASS
        self._assess(st)
        self.assertEqual(st.claims, set())
        self.assertEqual(st.tax_owed, 0)

    def test_tilled_soil_and_your_buildings_stay_claimed(self):
        from hearthdelve.world import tile
        st, run = self._fenced()
        for xy in run:
            st.surface.tiles[xy] = tile.GRASS
        st.surface.tiles[402, 402] = tile.TILLED
        st.surface.buildings.append({"x": 403, "y": 403, "w": 2, "h": 2, "kind": "coop",
                                     "village": "", "owner": None})
        self._assess(st)
        self.assertEqual(st.claims, {(402, 402), (403, 403), (404, 403), (403, 404), (404, 404)})


if __name__ == "__main__":
    unittest.main()
