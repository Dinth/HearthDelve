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


class TestAFairIsATreatNotATrade(unittest.TestCase):
    """The 15g treat hands out a dish worth 215-284g at the bin and a 25g spin's
    prizes average ~106g, with no limit: 100 treats posted back made ~24,000g.
    The prices stay cosy; each guest gets one treat and three spins a fair."""

    def _at_the_fair(self, day=FESTIVAL_DAY):
        st = fresh_state(11)
        st.day = day
        st.player.gold = 1000
        return st

    def _pack(self, st):
        return sum(q for _i, q, _ql in st.player.inventory.slots)

    def test_one_treat_a_fair(self):
        from hearthdelve.game import crafting
        st = self._at_the_fair()
        before = self._pack(st)
        crafting._buy_treat(st)
        crafting._buy_treat(st)
        self.assertEqual(st.player.gold, 1000 - crafting._TREAT_COST)
        self.assertEqual(self._pack(st), before + 1)

    def test_three_spins_a_fair_and_a_fresh_go_at_the_next(self):
        from hearthdelve.data import content
        from hearthdelve.engine import constants as C
        from hearthdelve.game import crafting
        st = self._at_the_fair()
        for _ in range(5):
            crafting._play_tombola(st)
        self.assertEqual(st.player.gold, 1000 - 3 * crafting._TOMBOLA_COST)
        nxt = next(d for d in range(FESTIVAL_DAY + 1, FESTIVAL_DAY + 4 * C.SEASON_LEN)
                   if content.festival_on(C.SEASONS[(d // C.SEASON_LEN) % 4], d % C.SEASON_LEN + 1))
        st.day = nxt
        crafting._play_tombola(st)
        self.assertEqual(st.player.gold, 1000 - 4 * crafting._TOMBOLA_COST)

    def test_a_reload_does_not_hand_out_more_goes(self):
        from hearthdelve.engine import save
        from hearthdelve.game import crafting
        st = self._at_the_fair()
        crafting._buy_treat(st)
        for _ in range(3):
            crafting._play_tombola(st)
        save.save(st)
        again = save.load()
        gold = again.player.gold
        crafting._buy_treat(again)
        crafting._play_tombola(again)
        self.assertEqual(again.player.gold, gold)


class TestTheFairSurvivesAReload(unittest.TestCase):
    """new_day autosaved, and only afterwards did the morning raise the stalls
    and pay out the fireworks: reload on a fair day and there was no fair, and
    the fireworks' karma and friendship were lost for good."""

    def test_a_fair_morning_autosaves_with_its_stalls_up(self):
        from hearthdelve.engine import save
        from hearthdelve.game import farming
        st = fresh_state(11)
        st.day = FESTIVAL_DAY - 1
        farming.sleep(st)                                  # wake on the Spring Equinox
        kinds = [m.kind for m in save.load().surface.machines.values()]
        self.assertGreaterEqual(kinds.count("fair_games"), 4)
        self.assertGreaterEqual(kinds.count("fair_treats"), 4)
        farming.sleep(st)                                  # and they're struck the day after
        kinds = [m.kind for m in save.load().surface.machines.values()]
        self.assertNotIn("fair_games", kinds)

    def test_the_fireworks_payoff_is_in_the_dawn_autosave(self):
        from hearthdelve.data import content
        from hearthdelve.engine import save
        from hearthdelve.game import farming
        from hearthdelve.game.requests import _year_finale
        from hearthdelve.engine import constants as C
        season, fday, _name = _year_finale()
        st = fresh_state(11)
        st.day = C.SEASONS.index(season) * C.SEASON_LEN + fday - 1   # the finale itself
        self.assertIsNotNone(content.festival_on(st.season, st.day_of_season))
        key = f"fireworks_{st.year}"
        st.day -= 1                                        # the evening before
        st.stats[key] = 1                                  # the fireworks order is filled
        st.player.karma = 0
        friend = st.surface.npcs[0].friendship
        farming.collapse(st, "You doze off on the green...")   # either way into the morning
        again = save.load()
        self.assertEqual(again.stats[key], 2)
        self.assertEqual(again.player.karma, 2)
        self.assertGreater(st.surface.npcs[0].friendship, friend)          # the Vale cheered…
        self.assertEqual(again.surface.npcs[0].friendship, st.surface.npcs[0].friendship)  # …and it was kept


if __name__ == "__main__":
    unittest.main()
