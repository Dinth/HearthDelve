"""Every resident must be addressable, in every village, on every seed.

Fenwick sits in a fen. Scattered water put every candidate rectangle in NO_BUILD,
so ``_try_building`` failed for the whole village and it was generated with no
buildings at all — which sent all seven residents down the ``home = work =
(vx, vy)`` fallback onto the square's centre tile. ``npc_near`` then built a
``{pos: npc}`` dict, so only the last one on that tile was ever returned: six of
seven residents, including the tavern and the trading counter, were unreachable
for the entire game.

Two layers are tested here, because either alone leaves a hole: villages must get
buildings (so residents get distinct homes), and ``npc_near`` must cope with a
stack regardless (schedules still send several people to one fireside).
"""
from __future__ import annotations

import unittest
from collections import Counter

from tests.common import fresh_state

from hearthdelve.world import worldgen

SEEDS = (7, 99, 555, 1337, 4242)


class VillageBuildingsTest(unittest.TestCase):
    def test_every_village_gets_buildings(self):
        for seed in SEEDS:
            gm = worldgen.generate(seed)
            per = Counter(b.get("village") for b in gm.buildings if b.get("village"))
            villages = {getattr(n, "village", None) for n in gm.npcs}
            villages.discard(None)
            for v in villages:
                with self.subTest(seed=seed, village=v):
                    self.assertGreater(per.get(v, 0), 0,
                                       f"{v} was generated with no buildings on seed {seed}")

    def test_residents_get_distinct_homes(self):
        """A village whose residents share a home tile has lost the fallback."""
        for seed in SEEDS:
            gm = worldgen.generate(seed)
            homes: dict = {}
            for n in gm.npcs:
                homes.setdefault(getattr(n, "village", None), []).append(tuple(n.home))
            for v, hs in homes.items():
                if v is None or len(hs) < 2:
                    continue
                with self.subTest(seed=seed, village=v):
                    dupes = {t: c for t, c in Counter(hs).items() if c > 1}
                    self.assertEqual(dupes, {},
                                     f"{v} on seed {seed} stacks residents on {dupes}")

    def test_a_shop_role_always_has_somewhere_to_trade(self):
        """An unreachable shopkeeper is unreachable content, not a cosmetic bug."""
        for seed in SEEDS:
            gm = worldgen.generate(seed)
            for n in gm.npcs:
                if n.role in ("innkeeper", "shopkeeper", "blacksmith", "trader"):
                    with self.subTest(seed=seed, npc=n.name, role=n.role):
                        self.assertIsNotNone(n.home)


class NpcNearStackTest(unittest.TestCase):
    def test_a_stack_of_residents_all_become_reachable(self):
        from hearthdelve.game import village
        st = fresh_state(99)
        crowd = [n for n in st.world.npcs if getattr(n, "village", None)][:6]
        self.assertGreaterEqual(len(crowd), 2)
        tx, ty = crowd[0].x, crowd[0].y
        for n in crowd:
            n.x, n.y = tx, ty
            n.talked_today = n.gifted_today = False
        st.player.x, st.player.y = tx - 1, ty
        st.player.facing = (1, 0)

        reached = []
        for _ in range(len(crowd)):
            n = village.npc_near(st)
            self.assertIsNotNone(n, "npc_near lost the crowd entirely")
            reached.append(n.name)
            n.talked_today = n.gifted_today = True      # a completed interaction
        self.assertEqual(len(set(reached)), len(crowd),
                         f"only reached {sorted(set(reached))} of {[n.name for n in crowd]}")

    def test_npc_near_still_prefers_the_faced_tile(self):
        from hearthdelve.game import village
        st = fresh_state(99)
        a, b = [n for n in st.world.npcs if getattr(n, "village", None)][:2]
        st.player.x, st.player.y = 300, 300
        st.player.facing = (1, 0)
        a.x, a.y = 301, 300          # faced
        b.x, b.y = 300, 301          # merely adjacent
        self.assertIs(village.npc_near(st), a)


if __name__ == "__main__":
    unittest.main()
