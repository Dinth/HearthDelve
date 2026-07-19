"""Festival depth: stalls up and struck, the tombola, treats, and warm days."""
from __future__ import annotations

import unittest

from tests.common import fresh_state

FESTIVAL_DAY = 10          # state.day 10 -> Spring 11, the Spring Equinox


class TestFairStalls(unittest.TestCase):
    def test_stalls_rise_and_are_struck(self):
        from hearthdelve.game import village
        st = fresh_state(11)
        st.day = FESTIVAL_DAY
        village.fair_stalls(st)
        kinds = [m.kind for m in st.surface.machines.values()]
        self.assertGreaterEqual(kinds.count("fair_games"), 4)   # one per square
        self.assertGreaterEqual(kinds.count("fair_treats"), 4)
        village.clear_fair_stalls(st)
        kinds = [m.kind for m in st.surface.machines.values()]
        self.assertNotIn("fair_games", kinds)
        self.assertNotIn("fair_treats", kinds)

    def test_tombola_always_wins_and_is_seeded(self):
        from hearthdelve.game import crafting
        a, b = fresh_state(11), fresh_state(11)
        for st in (a, b):
            st.day = FESTIVAL_DAY
            st.player.gold = 200
        packa = sum(q for _i, q, _ql in a.player.inventory.slots)
        crafting._play_tombola(a)
        crafting._play_tombola(b)
        self.assertEqual(a.player.gold, 175)
        self.assertGreater(sum(q for _i, q, _ql in a.player.inventory.slots), packa)
        self.assertEqual([(i.name, q) for i, q, _ in a.player.inventory.slots],
                         [(i.name, q) for i, q, _ in b.player.inventory.slots],
                         "tombola must be seeded, not scummable")

    def test_treat_stall(self):
        from hearthdelve.game import crafting
        st = fresh_state(11)
        st.player.gold = 20
        before = sum(q for _i, q, _ql in st.player.inventory.slots)
        crafting._buy_treat(st)
        self.assertEqual(st.player.gold, 5)
        self.assertEqual(sum(q for _i, q, _ql in st.player.inventory.slots), before + 1)
        crafting._buy_treat(st)                      # can't afford another
        self.assertEqual(st.player.gold, 5)

    def test_festival_warmth_doubles_friendship(self):
        from hearthdelve.game import village
        st = fresh_state(11)
        st.day = 2                                   # an ordinary day
        self.assertEqual(village._warmth(st), 1)
        st.day = FESTIVAL_DAY
        self.assertEqual(village._warmth(st), 2)
        st.event = {"id": "fete"}                    # never stacks past double
        self.assertEqual(village._warmth(st), 2)


if __name__ == "__main__":
    unittest.main()
