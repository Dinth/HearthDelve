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
        npc = st.surface.npcs[0]
        st.day = 2                                   # an ordinary day
        self.assertEqual(village._warmth(st, npc), 1)
        st.day = FESTIVAL_DAY
        self.assertEqual(village._warmth(st, npc), 2)
        st.event = {"id": "fete", "village": npc.village}   # never stacks past double
        self.assertEqual(village._warmth(st, npc), 2)


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


class TestPastInvitationsAreCleared(unittest.TestCase):
    """A festival invitation arrives the day before and was kept forever, so
    unread ones piled up: 39 letters in the post box after 120 days."""

    def _invites(self, st):
        return [m for m in st.mail if m.get("until") is not None or "invited" in m["body"]]

    def test_a_year_of_post_leaves_at_most_the_next_invitation(self):
        import random
        from hearthdelve.game import farming
        st = fresh_state(11)
        random.seed(3)
        most = 0
        for day in range(0, 112):
            st.day = day
            farming._deliver_mail(st)
            most = max(most, len(self._invites(st)))
        self.assertEqual(most, 1)

    def test_a_letter_with_a_gift_waits_to_be_taken(self):
        from hearthdelve.entities import items
        from hearthdelve.game import farming
        st = fresh_state(11)
        st.mail.append({"sender": "Marda", "body": "For you.", "items": [(items.HONEY, 1, 0)],
                        "until": 0})
        st.day = 40
        farming._deliver_mail(st)
        self.assertTrue(any(m["sender"] == "Marda" for m in st.mail))

    def test_the_date_survives_a_save_and_older_letters_load_as_they_were(self):
        from hearthdelve.engine import save
        st = fresh_state(11)
        st.mail = [{"sender": "Ivo", "body": "Come to the fair.", "items": [], "until": 11},
                   {"sender": "Ivo", "body": "An older letter.", "items": []}]
        save.save(st)
        again = save.load()
        self.assertEqual(again.mail[0].get("until"), 11)
        self.assertIsNone(again.mail[1].get("until"))


class TestTheContestThanksItsOwnJudge(unittest.TestCase):
    """Every surface inn holds the produce contest, its innkeeper judging —
    but a ribbon warmed Mossford's folk and a 2nd or 3rd place Mossford's
    innkeeper, whoever had judged. And the rival said to edge the field was
    simply the first one drawn, not the one who scored best."""

    def _fair(self, day=FESTIVAL_DAY):
        from hearthdelve.game import projects
        st = fresh_state(11)
        st.day = day
        projects.get(st, "grange_hall")["state"] = "done"
        return st

    def _enter_until(self, st, judge, places):
        """Enter goods of rising quality until one lands in `places`; returns
        (place, friendship before by name, the line)."""
        from hearthdelve.entities import items
        from hearthdelve.game import village
        for ql in range(6):
            for it in (items.PARSNIP, items.STRAWBERRY, items.CHEESE, items.TRUFFLE):
                st.stats.pop(village._contest_key(st), None)
                st.player.inventory.add(it, 1, quality=ql)
                before = {n.name: n.friendship for n in st.surface.npcs}
                won = st.stats.get("contests_won", 0)
                gifts = st.player.inventory.count(items.FAIR_RIBBON)
                line = village.enter_contest(st, it, ql, judge=judge)
                place = 1 if st.player.inventory.count(items.FAIR_RIBBON) > gifts else (
                    2 if "place —" in line else 4)
                if place in places:
                    return place, before, line
                for n in st.surface.npcs:            # undo, and try a finer entry
                    n.friendship = before[n.name]
                st.stats["contests_won"] = won
        self.skipTest(f"no entry placed {places} on this fair")

    def _innkeeper(self, st, village_name):
        return next(n for n in st.surface.npcs
                    if n.role == "innkeeper" and n.village == village_name)

    def test_a_placing_warms_the_innkeeper_who_judged(self):
        st = self._fair()
        judge = self._innkeeper(st, "Saltmere")
        mossford = self._innkeeper(st, "Mossford")
        _place, before, _line = self._enter_until(st, judge, (2, 3))
        self.assertGreater(judge.friendship, before[judge.name])
        self.assertEqual(mossford.friendship, before[mossford.name])

    def test_a_ribbon_warms_the_judges_own_village(self):
        st = self._fair()
        judge = self._innkeeper(st, "Saltmere")
        _place, before, _line = self._enter_until(st, judge, (1,))
        for n in st.surface.npcs:
            with self.subTest(npc=n.name):
                if n.village == "Saltmere":
                    self.assertGreater(n.friendship, before[n.name])
                elif n.village == "Mossford":
                    self.assertEqual(n.friendship, before[n.name])

    def test_the_rival_named_is_the_one_who_scored_best(self):
        import random
        from hearthdelve.entities import items
        from hearthdelve.game import village
        for day in range(FESTIVAL_DAY, FESTIVAL_DAY + 112 * 4, 112):   # the same fair, years on
            st = self._fair(day)
            rng = random.Random((st.seed * 42_589 + st.day * 631) & 0x7FFFFFFF)
            grown = [n for n in st.surface.npcs if n.role != "child"]
            rivals = rng.sample(grown, min(3, len(grown)))
            scores = [rng.uniform(2.5, 5.5) for _ in rivals]
            best = rivals[scores.index(max(scores))]
            if best is rivals[0]:
                continue                                 # the old code would name them too
            st.player.inventory.add(items.PARSNIP, 1)
            line = village.enter_contest(st, items.PARSNIP, 0,
                                         judge=self._innkeeper(st, "Mossford"))
            self.assertIn(best.name, line)
            self.assertNotIn(rivals[0].name, line)
            return
        self.skipTest("the first-drawn rival led every year checked")


if __name__ == "__main__":
    unittest.main()
